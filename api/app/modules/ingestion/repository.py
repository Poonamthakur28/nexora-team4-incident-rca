"""Process-local observation reservation, Stage 2, and completion single-flight."""

import threading
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal, Protocol, runtime_checkable

from app.modules.ingestion.completion import (
    CREATED_INCIDENT_UNBOUND,
    CompletionClaim,
    ObservationBinding,
    ObservationCompletion,
    aligned_full_binding,
    aligned_incident_binding,
    copy_binding,
    is_full_binding,
    require_local_id,
)
from app.modules.ingestion.contracts import Observation
from app.modules.ingestion.errors import (
    IngestionConfigurationError,
    ObservationIdempotencyConflict,
)
from app.modules.ingestion.fingerprint import NormalizedObservation
from app.modules.ingestion.normalization import IdempotencyIdentity
from app.modules.ingestion.stage2 import Stage2Assessment


@dataclass(frozen=True, slots=True)
class ObservationReservation:
    """In-memory reservation for one provider-event identity.

    This is not a CT-04 receipt and has no processing attempt.
    `assessment` is a stored Stage 2 domain result, or None when none exists.
    `binding` is a process-local Incident/Evidence bind, or None when none
    exists. It is not `completed`.
    """

    observation_id: str
    organization_id: str
    observation: Observation
    fingerprint_digest: bytes
    canonical_payload: bytes
    assessment: Stage2Assessment | None = None
    binding: ObservationBinding | None = None


@dataclass(frozen=True, slots=True)
class ReservationResult:
    """Outcome of an atomic reserve. `conflict` is raised, not returned."""

    outcome: Literal["accepted", "duplicate"]
    record: ObservationReservation


@dataclass(frozen=True, slots=True)
class Stage2Claim:
    """How this caller should proceed with Stage 2. `in_flight` is not public.

    `generation` is an internal ownership token for a `run` claim. It is not a
    processing status.
    """

    action: Literal["run", "use_stored", "failed"]
    assessment: Stage2Assessment | None
    generation: int | None = None


class ObservationRepository(Protocol):
    """Reserve or locate a provider-event identity inside one process."""

    def reserve(
        self, observation: Observation, normalized: NormalizedObservation
    ) -> ReservationResult:
        """Accept a new identity, return a duplicate, or raise a conflict.

        `observation` and `normalized` must describe the same Stage 1-validated
        input. `ObservationIngestionService.accept` guarantees that. This method
        does not re-run Observation or fingerprint validation.
        """

    def get(self, observation_id: str, organization_id: str) -> ObservationReservation | None:
        """Return a visible reservation, or None when it is missing or out of scope."""


@runtime_checkable
class Stage2ObservationRepository(Protocol):
    """Single-flight Stage 2 claims. `accept` does not require this Protocol."""

    def claim_stage2(self, identity: IdempotencyIdentity) -> Stage2Claim:
        """Return a stored assessment, wait for an in-flight one, or become assessor."""

    def complete_stage2(
        self,
        identity: IdempotencyIdentity,
        assessment: Stage2Assessment,
        generation: int,
    ) -> Stage2Assessment:
        """Store a domain assessment owned by `generation` and release waiters."""

    def abort_stage2(self, identity: IdempotencyIdentity, generation: int) -> None:
        """Release an in-flight claim only if the caller still owns it."""


@dataclass
class _CompletionSlot:
    condition: threading.Condition
    binding: ObservationBinding | None = None
    in_flight: bool = False
    generation: int = 0
    block_new_incident: bool = False


@dataclass
class _AssessmentSlot:
    condition: threading.Condition
    assessment: Stage2Assessment | None = None
    in_flight: bool = False
    generation: int = 0


class InMemoryObservationRepository:
    """Instance-owned reservation map. The lock is not a database transaction.

    Stage 2 and completion each have their own per-identity generation. Aborting
    one wave cannot release the other.
    """

    def __init__(self, *, id_factory: Callable[[], str]) -> None:
        self._id_factory = id_factory
        self._records: dict[IdempotencyIdentity, ObservationReservation] = {}
        self._by_id: dict[str, IdempotencyIdentity] = {}
        self._slots: dict[IdempotencyIdentity, _AssessmentSlot] = {}
        self._completion_slots: dict[IdempotencyIdentity, _CompletionSlot] = {}
        self._lock = threading.Lock()

    def reserve(
        self, observation: Observation, normalized: NormalizedObservation
    ) -> ReservationResult:
        """See `ObservationRepository.reserve` for the caller trust boundary."""
        with self._lock:
            existing = self._records.get(normalized.identity)
            if existing is not None:
                if existing.fingerprint_digest == normalized.fingerprint.digest:
                    return ReservationResult("duplicate", _copy_record(existing))
                raise ObservationIdempotencyConflict()
            record = _new_record(observation, normalized, self._id_factory, self._by_id)
            self._records[normalized.identity] = record
            self._by_id[record.observation_id] = normalized.identity
            return ReservationResult("accepted", _copy_record(record))

    def get(self, observation_id: str, organization_id: str) -> ObservationReservation | None:
        with self._lock:
            identity = self._by_id.get(observation_id)
            if identity is None:
                return None
            record = self._records[identity]
            if record.organization_id != organization_id:
                return None
            slot = self._completion_slots.get(identity)
            if record.binding is None and slot is not None and slot.binding is not None:
                return _copy_record_with_binding(record, slot.binding)
            return _copy_record(record)

    def claim_stage2(self, identity: IdempotencyIdentity) -> Stage2Claim:
        with self._lock:
            if identity not in self._records:
                raise IngestionConfigurationError("The observation has not been reserved.")
            slot = self._slot(identity)
            if slot.assessment is not None:
                return Stage2Claim("use_stored", slot.assessment)
            if slot.in_flight:
                waited_generation = slot.generation
                self._note_waiter_parked()
                while slot.in_flight and slot.generation == waited_generation:
                    slot.condition.wait()
                if slot.assessment is not None and slot.generation == waited_generation:
                    return Stage2Claim("use_stored", slot.assessment)
                return Stage2Claim("failed", None)
            slot.in_flight = True
            return Stage2Claim("run", None, slot.generation)

    def complete_stage2(
        self,
        identity: IdempotencyIdentity,
        assessment: Stage2Assessment,
        generation: int,
    ) -> Stage2Assessment:
        failure: Exception | None = None
        with self._lock:
            slot = self._slot(identity)
            if not _owns_in_flight(slot, generation):
                raise IngestionConfigurationError("The Stage 2 claim is no longer owned.")
            record = self._records.get(identity)
            if record is None:
                _release_owned_wave(slot, generation)
                raise IngestionConfigurationError("The observation has not been reserved.")
            try:
                updated = _with_assessment(record, assessment)
            except Exception as exc:
                _release_owned_wave(slot, generation)
                failure = exc
            else:
                slot.assessment = assessment
                slot.in_flight = False
                self._records[identity] = updated
                slot.condition.notify_all()
                return assessment
        self._after_failed_publication()
        assert failure is not None
        raise failure

    def abort_stage2(self, identity: IdempotencyIdentity, generation: int) -> None:
        with self._lock:
            slot = self._slots.get(identity)
            if slot is None:
                return
            _release_owned_wave(slot, generation)

    def claim_completion(self, identity: IdempotencyIdentity) -> CompletionClaim:
        with self._lock:
            if identity not in self._records:
                raise IngestionConfigurationError("The observation has not been reserved.")
            slot = self._completion_slot(identity)
            if is_full_binding(slot.binding):
                return CompletionClaim("use_stored", copy_binding(slot.binding))
            if slot.in_flight:
                waited_generation = slot.generation
                self._note_completion_waiter_parked()
                while slot.in_flight and slot.generation == waited_generation:
                    slot.condition.wait()
                if is_full_binding(slot.binding) and slot.generation == waited_generation:
                    return CompletionClaim("use_stored", copy_binding(slot.binding))
                return CompletionClaim("failed", None)
            slot.in_flight = True
            return CompletionClaim("run", copy_binding(slot.binding), slot.generation)

    def bind_incident(
        self, identity: IdempotencyIdentity, incident_id: str, generation: int
    ) -> ObservationBinding:
        with self._lock:
            slot = self._completion_slot(identity)
            if not _owns_in_flight(slot, generation):
                raise IngestionConfigurationError("The completion claim is no longer owned.")
            record = self._records.get(identity)
            existing = slot.binding if slot.binding is not None else (
                None if record is None else record.binding
            )
            binding = aligned_incident_binding(incident_id, existing)
            slot.binding = binding
            if record is None:
                _release_owned_wave(slot, generation)
                raise IngestionConfigurationError("The observation has not been reserved.")
            try:
                self._records[identity] = _with_binding(record, binding)
            except Exception:
                # slot.binding already holds the Incident id for a later owner.
                raise
            return ObservationBinding(binding.incident_id, binding.evidence_id)

    def remember_created_incident(
        self, identity: IdempotencyIdentity, incident_id: str, generation: int
    ) -> ObservationBinding:
        """Persist an incident-only bind after create. Does not notify waiters."""
        with self._lock:
            slot = self._completion_slot(identity)
            incident_id = require_local_id(incident_id, "incident_id")
            record = self._records.get(identity)
            existing = slot.binding if slot.binding is not None else (
                None if record is None else record.binding
            )
            if existing is not None and existing.incident_id != incident_id:
                raise IngestionConfigurationError(
                    "The observation is already bound to a different Incident."
                )
            if not _owns_in_flight(slot, generation) and slot.in_flight:
                slot.block_new_incident = True
                raise IngestionConfigurationError(CREATED_INCIDENT_UNBOUND)
            slot.block_new_incident = True
            binding = aligned_incident_binding(incident_id, existing)
            slot.binding = binding
            slot.block_new_incident = False
            if record is not None:
                try:
                    self._records[identity] = _with_binding(record, binding)
                except IngestionConfigurationError:
                    raise
                except Exception:
                    pass
            return ObservationBinding(binding.incident_id, binding.evidence_id)

    def assert_can_create_incident(
        self, identity: IdempotencyIdentity, generation: int
    ) -> None:
        with self._lock:
            slot = self._completion_slot(identity)
            if not _owns_in_flight(slot, generation):
                raise IngestionConfigurationError("The completion claim is no longer owned.")
            if slot.binding is None and slot.block_new_incident:
                raise IngestionConfigurationError(CREATED_INCIDENT_UNBOUND)

    def block_uncertain_incident_create(
        self, identity: IdempotencyIdentity, generation: int
    ) -> None:
        with self._lock:
            slot = self._completion_slot(identity)
            if slot.binding is not None:
                return
            slot.block_new_incident = True
            if not _owns_in_flight(slot, generation) and slot.in_flight:
                raise IngestionConfigurationError(CREATED_INCIDENT_UNBOUND)

    def complete_binding(
        self,
        identity: IdempotencyIdentity,
        incident_id: str,
        evidence_id: str,
        generation: int,
    ) -> ObservationCompletion:
        failure: Exception | None = None
        with self._lock:
            slot = self._completion_slot(identity)
            if not _owns_in_flight(slot, generation):
                raise IngestionConfigurationError("The completion claim is no longer owned.")
            record = self._records.get(identity)
            if record is None:
                _release_owned_wave(slot, generation)
                raise IngestionConfigurationError("The observation has not been reserved.")
            try:
                binding = aligned_full_binding(
                    incident_id, evidence_id, slot.binding or record.binding
                )
                updated = _with_binding(record, binding)
                completion = ObservationCompletion(binding.incident_id, binding.evidence_id)
            except IngestionConfigurationError:
                raise
            except Exception as exc:
                _release_owned_wave(slot, generation)
                failure = exc
            else:
                slot.binding = binding
                slot.in_flight = False
                self._records[identity] = updated
                slot.condition.notify_all()
                return completion
        self._after_failed_completion_publication()
        assert failure is not None
        raise failure

    def abort_completion(self, identity: IdempotencyIdentity, generation: int) -> None:
        with self._lock:
            slot = self._completion_slots.get(identity)
            if slot is None:
                return
            _release_owned_wave(slot, generation)

    def _note_waiter_parked(self) -> None:
        """Test hook. Called under the lock just before a waiter waits."""

    def _after_failed_publication(self) -> None:
        """Test hook. Called after a failed publication releases the lock."""

    def _note_completion_waiter_parked(self) -> None:
        """Test hook. Called under the lock just before a completion waiter waits."""

    def _after_failed_completion_publication(self) -> None:
        """Test hook. Called after a failed completion publication releases the lock."""

    def _slot(self, identity: IdempotencyIdentity) -> _AssessmentSlot:
        slot = self._slots.get(identity)
        if slot is None:
            slot = _AssessmentSlot(condition=threading.Condition(self._lock))
            self._slots[identity] = slot
        return slot

    def _completion_slot(self, identity: IdempotencyIdentity) -> _CompletionSlot:
        slot = self._completion_slots.get(identity)
        if slot is None:
            record = self._records.get(identity)
            slot = _CompletionSlot(
                condition=threading.Condition(self._lock),
                binding=None if record is None else copy_binding(record.binding),
            )
            self._completion_slots[identity] = slot
        return slot


def _owns_in_flight(slot: _AssessmentSlot | _CompletionSlot, generation: int) -> bool:
    return slot.in_flight and slot.generation == generation


def _release_owned_wave(slot: _AssessmentSlot | _CompletionSlot, generation: int) -> bool:
    if not _owns_in_flight(slot, generation):
        return False
    slot.in_flight = False
    slot.generation += 1
    slot.condition.notify_all()
    return True


def _new_record(
    observation: Observation,
    normalized: NormalizedObservation,
    id_factory: Callable[[], str],
    used_ids: dict[str, IdempotencyIdentity],
) -> ObservationReservation:
    try:
        observation_id = id_factory()
    except Exception as exc:
        raise IngestionConfigurationError("The observation id factory failed.") from exc
    if not isinstance(observation_id, str) or not observation_id.strip():
        raise IngestionConfigurationError(
            "The observation id factory must return a non-empty string."
        )
    if observation_id in used_ids:
        raise IngestionConfigurationError("The observation id factory produced a repeated id.")
    return ObservationReservation(
        observation_id=observation_id,
        organization_id=normalized.identity.organization_id,
        observation=observation.model_copy(deep=True),
        fingerprint_digest=bytes(normalized.fingerprint.digest),
        canonical_payload=bytes(normalized.canonical_payload),
        assessment=None,
        binding=None,
    )


def _with_assessment(
    record: ObservationReservation, assessment: Stage2Assessment
) -> ObservationReservation:
    return ObservationReservation(
        observation_id=record.observation_id,
        organization_id=record.organization_id,
        observation=record.observation.model_copy(deep=True),
        fingerprint_digest=bytes(record.fingerprint_digest),
        canonical_payload=bytes(record.canonical_payload),
        assessment=assessment,
        binding=copy_binding(record.binding),
    )


def _with_binding(
    record: ObservationReservation, binding: ObservationBinding
) -> ObservationReservation:
    return ObservationReservation(
        observation_id=record.observation_id,
        organization_id=record.organization_id,
        observation=record.observation.model_copy(deep=True),
        fingerprint_digest=bytes(record.fingerprint_digest),
        canonical_payload=bytes(record.canonical_payload),
        assessment=record.assessment,
        binding=copy_binding(binding),
    )


def _copy_record(record: ObservationReservation) -> ObservationReservation:
    return _copy_record_with_binding(record, record.binding)


def _copy_record_with_binding(
    record: ObservationReservation, binding: ObservationBinding | None
) -> ObservationReservation:
    return ObservationReservation(
        observation_id=record.observation_id,
        organization_id=record.organization_id,
        observation=record.observation.model_copy(deep=True),
        fingerprint_digest=bytes(record.fingerprint_digest),
        canonical_payload=bytes(record.canonical_payload),
        assessment=record.assessment,
        binding=copy_binding(binding),
    )
