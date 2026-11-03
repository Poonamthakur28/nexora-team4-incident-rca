"""Process-local observation-to-Incident binding. Not CT-04 completed."""

from dataclasses import dataclass
from typing import Literal, Protocol, runtime_checkable

from app.modules.ingestion.errors import IngestionConfigurationError
from app.modules.ingestion.normalization import IdempotencyIdentity

CREATED_INCIDENT_UNBOUND = "Incident was created but could not be bound."


def require_local_id(value: object, name: str) -> str:
    """Accept any non-empty string. This is not a UUID or Team 4 entity rule."""
    if not isinstance(value, str) or not value.strip():
        raise IngestionConfigurationError(f"A non-empty {name} is required.")
    return value.strip()


@dataclass(frozen=True, slots=True)
class ObservationBinding:
    """Reservation-scoped bind. `evidence_id` is absent until Evidence exists.

    This is not a CT-04 processing status and does not mean `completed`.
    Evidence cannot be stored without an Incident id.
    """

    incident_id: str
    evidence_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "incident_id", require_local_id(self.incident_id, "incident_id"))
        if self.evidence_id is not None:
            object.__setattr__(
                self, "evidence_id", require_local_id(self.evidence_id, "evidence_id")
            )


@dataclass(frozen=True, slots=True)
class ObservationCompletion:
    """Local bind with both Incident and Evidence ids. Not CT-04 `completed`."""

    incident_id: str
    evidence_id: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "incident_id", require_local_id(self.incident_id, "incident_id"))
        object.__setattr__(self, "evidence_id", require_local_id(self.evidence_id, "evidence_id"))


@dataclass(frozen=True, slots=True)
class CompletionClaim:
    """How this caller should proceed with completion. `in_flight` is not public.

    `generation` is an internal ownership token for a `run` claim. It is not a
    processing status.
    """

    action: Literal["run", "use_stored", "failed"]
    binding: ObservationBinding | None
    generation: int | None = None


@runtime_checkable
class CompletionObservationRepository(Protocol):
    """Single-flight completion claims. `accept` and `assess` do not require this."""

    def claim_completion(self, identity: IdempotencyIdentity) -> CompletionClaim:
        """Return a stored full bind, wait for an in-flight one, or become owner."""

    def bind_incident(
        self, identity: IdempotencyIdentity, incident_id: str, generation: int
    ) -> ObservationBinding:
        """Store an Incident id on the owned claim without releasing waiters."""

    def complete_binding(
        self,
        identity: IdempotencyIdentity,
        incident_id: str,
        evidence_id: str,
        generation: int,
    ) -> ObservationCompletion:
        """Store both ids owned by `generation` and release waiters."""

    def abort_completion(self, identity: IdempotencyIdentity, generation: int) -> None:
        """Release an in-flight claim only if the caller still owns it."""

    def remember_created_incident(
        self, identity: IdempotencyIdentity, incident_id: str, generation: int
    ) -> ObservationBinding:
        """Keep a created Incident id after create, including when bind_incident fails.

        This is not a shared transaction. It does not notify waiters or create
        Evidence. A later owner reuses this id instead of creating another Incident.
        """

    def assert_can_create_incident(self, identity: IdempotencyIdentity, generation: int) -> None:
        """Refuse a second create when a prior Incident could not be bound."""

    def block_uncertain_incident_create(
        self, identity: IdempotencyIdentity, generation: int
    ) -> None:
        """Fence a later create when a create outcome has no recoverable Incident id."""


def aligned_incident_binding(
    incident_id: str, existing: ObservationBinding | None
) -> ObservationBinding:
    """Keep a prior Incident id. A different id would be a second Incident."""
    incident_id = require_local_id(incident_id, "incident_id")
    if existing is not None and existing.incident_id != incident_id:
        raise IngestionConfigurationError(
            "The observation is already bound to a different Incident."
        )
    evidence_id = existing.evidence_id if existing is not None else None
    return ObservationBinding(incident_id, evidence_id)


def aligned_full_binding(
    incident_id: str, evidence_id: str, existing: ObservationBinding | None
) -> ObservationBinding:
    """Require both ids and refuse a changed Incident or Evidence id."""
    incident_id = require_local_id(incident_id, "incident_id")
    evidence_id = require_local_id(evidence_id, "evidence_id")
    if existing is not None and existing.incident_id != incident_id:
        raise IngestionConfigurationError(
            "The observation is already bound to a different Incident."
        )
    if existing is not None and existing.evidence_id is not None and existing.evidence_id != evidence_id:
        raise IngestionConfigurationError(
            "The observation is already bound to different Evidence."
        )
    return ObservationBinding(incident_id, evidence_id)


def copy_binding(binding: ObservationBinding | None) -> ObservationBinding | None:
    if binding is None:
        return None
    return ObservationBinding(binding.incident_id, binding.evidence_id)


def is_full_binding(binding: ObservationBinding | None) -> bool:
    return binding is not None and binding.evidence_id is not None
