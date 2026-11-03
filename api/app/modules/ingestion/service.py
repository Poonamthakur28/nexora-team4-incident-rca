"""Stage 1, normalize, reserve, Stage 2 assessment, then optional completion."""

from dataclasses import dataclass

from app.modules.evidence_collection.contracts import Evidence, RecordObservationEventEvidence
from app.modules.evidence_collection.service import EvidenceService
from app.modules.incidents.context import IncidentRequestContext
from app.modules.incidents.contracts import CreateIncident
from app.modules.incidents.errors import UncertainIncidentCreate
from app.modules.incidents.service import IncidentService
from app.modules.ingestion.completion import (
    CREATED_INCIDENT_UNBOUND,
    CompletionObservationRepository,
    ObservationCompletion,
    is_full_binding,
)
from app.modules.ingestion.context import IncidentRequestContextFactory
from app.modules.ingestion.contracts import Observation
from app.modules.ingestion.errors import IngestionConfigurationError, ObservationNotReadyForCompletion
from app.modules.ingestion.fingerprint import normalize_observation
from app.modules.ingestion.normalization import build_idempotency_identity
from app.modules.ingestion.ports import (
    AuthenticatedConnectorContext,
    ContentReferenceFactory,
    PayloadHasher,
    ServiceResolver,
    SeverityMapper,
    SourceAccountAuthorizer,
)
from app.modules.ingestion.repository import (
    ObservationReservation,
    ObservationRepository,
    ReservationResult,
    Stage2ObservationRepository,
)
from app.modules.ingestion.stage2 import Stage2Assessment, evaluate_stage2
from app.modules.ingestion.validation import validate_observation_stage1

_STAGE2_UNAVAILABLE = "The Stage 2 assessment could not be completed."
_COMPLETION_UNAVAILABLE = "The observation completion could not be finished."
_COMPLETION_DEPS = (
    "Completion requires injected Incident, Evidence, content-ref, and request-context dependencies."
)


@dataclass(frozen=True, slots=True)
class IngestionResult:
    """Reservation plus a stored Stage 2 domain assessment.

    `accept` still returns only the reservation. `assess` is the additive path
    that runs Stage 2. This is not a completion result.
    """

    reservation: ReservationResult
    assessment: Stage2Assessment


@dataclass(frozen=True, slots=True)
class CompletionResult:
    """Process-local Incident and Evidence ids. Not CT-04 `completed`.

    There is no shared transaction across Incident, Evidence, and ingestion
    stores. This is not a receipt, processing attempt, or completion guarantee.
    """

    reservation: ReservationResult
    assessment: Stage2Assessment
    completion: ObservationCompletion


class ObservationIngestionService:
    """Accept an Observation into the in-memory reservation store.

    Authorization, hashing, and storage are injected. `assess` also injects
    mock service and severity ports. `complete` coordinates process-local
    Incident and Evidence writes. `accept` and `assess` still do not create
    those records.
    """

    def __init__(
        self,
        repository: ObservationRepository,
        hasher: PayloadHasher,
        *,
        resolver: ServiceResolver | None = None,
        mapper: SeverityMapper | None = None,
        incidents: IncidentService | None = None,
        evidence: EvidenceService | None = None,
        content_refs: ContentReferenceFactory | None = None,
        request_contexts: IncidentRequestContextFactory | None = None,
    ) -> None:
        self._repository = repository
        self._hasher = hasher
        self._resolver = resolver
        self._mapper = mapper
        self._incidents = incidents
        self._evidence = evidence
        self._content_refs = content_refs
        self._request_contexts = request_contexts

    def accept(
        self,
        observation: Observation,
        context: AuthenticatedConnectorContext,
        authorizer: SourceAccountAuthorizer,
    ) -> ReservationResult:
        """Reserve after Stage 1 and fingerprinting, or raise before any write."""
        stage1 = validate_observation_stage1(observation, context, authorizer)
        normalized = normalize_observation(observation, stage1.organization_id, self._hasher)
        return self._repository.reserve(observation, normalized)

    def assess(
        self,
        observation: Observation,
        context: AuthenticatedConnectorContext,
        authorizer: SourceAccountAuthorizer,
    ) -> IngestionResult:
        """Reserve, then single-flight Stage 2. Conflict never reaches Stage 2."""
        resolver, mapper = self._stage2_ports()
        repo = self._stage2_repository()
        reserved = self.accept(observation, context, authorizer)
        identity = build_idempotency_identity(
            reserved.record.observation, reserved.record.organization_id
        )
        claim = repo.claim_stage2(identity)
        if claim.action == "use_stored":
            if claim.assessment is None:
                raise IngestionConfigurationError(_STAGE2_UNAVAILABLE)
            return IngestionResult(reserved, claim.assessment)
        if claim.action != "run" or claim.generation is None:
            raise IngestionConfigurationError(_STAGE2_UNAVAILABLE)
        owner = claim.generation
        published = False
        try:
            try:
                assessment = evaluate_stage2(
                    reserved.record.observation,
                    reserved.record.organization_id,
                    resolver,
                    mapper,
                )
            except IngestionConfigurationError:
                raise
            except Exception as exc:
                raise IngestionConfigurationError(_STAGE2_UNAVAILABLE) from exc
            stored = repo.complete_stage2(identity, assessment, owner)
            published = True
        finally:
            if not published:
                repo.abort_stage2(identity, owner)
        visible = self._repository.get(
            reserved.record.observation_id, reserved.record.organization_id
        )
        record = visible if visible is not None else reserved.record
        return IngestionResult(ReservationResult(reserved.outcome, record), stored)

    def complete(
        self,
        observation: Observation,
        context: AuthenticatedConnectorContext,
        authorizer: SourceAccountAuthorizer,
    ) -> CompletionResult:
        """Reserve, then single-flight process-local Incident and Evidence writes.

        Requires a stored Stage 2 `ready` assessment. This is not CT-04
        `completed` and does not use a shared transaction.
        """
        incidents, evidence, content_refs, request_contexts = self._completion_ports()
        repo = self._completion_repository()
        reserved = self.accept(observation, context, authorizer)
        record = self._visible_record(reserved, context.organization_id)
        assessment = _require_ready(record)
        identity = build_idempotency_identity(record.observation, record.organization_id)
        claim = repo.claim_completion(identity)
        if claim.action == "use_stored":
            completion = _completion_from_binding(claim.binding)
            return CompletionResult(
                ReservationResult(reserved.outcome, record), assessment, completion
            )
        if claim.action != "run" or claim.generation is None:
            raise IngestionConfigurationError(_COMPLETION_UNAVAILABLE)
        owner = claim.generation
        published = False
        try:
            try:
                request = _request_context(
                    request_contexts, context, record.observation.correlation_id
                )
                completion = _finish_completion(
                    repo,
                    incidents,
                    evidence,
                    content_refs,
                    identity,
                    record,
                    assessment,
                    request,
                    claim.binding,
                    owner,
                )
            except IngestionConfigurationError:
                raise
            except Exception as exc:
                raise IngestionConfigurationError(_COMPLETION_UNAVAILABLE) from exc
            published = True
        finally:
            if not published:
                repo.abort_completion(identity, owner)
        visible = self._repository.get(record.observation_id, record.organization_id)
        stored = visible if visible is not None else record
        return CompletionResult(
            ReservationResult(reserved.outcome, stored), assessment, completion
        )

    def _visible_record(
        self, reserved: ReservationResult, organization_id: str
    ) -> ObservationReservation:
        visible = self._repository.get(reserved.record.observation_id, organization_id)
        if visible is None:
            raise IngestionConfigurationError("The observation has not been reserved.")
        return visible

    def _stage2_ports(self) -> tuple[ServiceResolver, SeverityMapper]:
        if self._resolver is None or self._mapper is None:
            raise IngestionConfigurationError(
                "Stage 2 requires an injected service resolver and severity mapper."
            )
        return self._resolver, self._mapper

    def _stage2_repository(self) -> Stage2ObservationRepository:
        repo = self._repository
        if not isinstance(repo, Stage2ObservationRepository):
            raise IngestionConfigurationError(
                "Stage 2 requires a repository that supports assessment."
            )
        return repo

    def _completion_ports(
        self,
    ) -> tuple[
        IncidentService,
        EvidenceService,
        ContentReferenceFactory,
        IncidentRequestContextFactory,
    ]:
        if (
            self._incidents is None
            or self._evidence is None
            or self._content_refs is None
            or self._request_contexts is None
        ):
            raise IngestionConfigurationError(_COMPLETION_DEPS)
        return self._incidents, self._evidence, self._content_refs, self._request_contexts

    def _completion_repository(self) -> CompletionObservationRepository:
        repo = self._repository
        if not isinstance(repo, CompletionObservationRepository):
            raise IngestionConfigurationError(
                "Completion requires a repository that supports binding."
            )
        return repo


def _require_ready(record: ObservationReservation) -> Stage2Assessment:
    assessment = record.assessment
    if (
        assessment is None
        or assessment.kind != "ready"
        or assessment.mapped_severity is None
        or assessment.resolved_service_ref is None
    ):
        raise ObservationNotReadyForCompletion()
    return assessment


def _request_context(
    factory: IncidentRequestContextFactory,
    context: AuthenticatedConnectorContext,
    correlation_id: str,
) -> IncidentRequestContext:
    built = factory.build(context, correlation_id=correlation_id)
    if built.organization_id != context.organization_id:
        raise IngestionConfigurationError(
            "The request context organization does not match the connector."
        )
    return built


def _completion_from_binding(binding) -> ObservationCompletion:
    if binding is None or binding.evidence_id is None:
        raise IngestionConfigurationError(_COMPLETION_UNAVAILABLE)
    return ObservationCompletion(binding.incident_id, binding.evidence_id)


def _finish_completion(
    repo: CompletionObservationRepository,
    incidents: IncidentService,
    evidence: EvidenceService,
    content_refs: ContentReferenceFactory,
    identity,
    record: ObservationReservation,
    assessment: Stage2Assessment,
    request: IncidentRequestContext,
    existing_binding,
    owner: int,
) -> ObservationCompletion:
    observation = record.observation
    if is_full_binding(existing_binding):
        assert existing_binding is not None and existing_binding.evidence_id is not None
        return ObservationCompletion(existing_binding.incident_id, existing_binding.evidence_id)

    if existing_binding is None:
        repo.assert_can_create_incident(identity, owner)
        try:
            created = incidents.create_incident(
                _create_incident_command(observation, assessment), request
            )
        except UncertainIncidentCreate as exc:
            _remember_created_incident(
                repo, identity, exc.incident_id, owner, _original_cause(exc)
            )
            raise
        except Exception as exc:
            _block_uncertain_incident_create(repo, identity, owner, exc)
            raise
        try:
            repo.remember_created_incident(identity, created.id, owner)
            repo.bind_incident(identity, created.id, owner)
        except Exception as exc:
            _remember_created_incident(repo, identity, created.id, owner, exc)
            raise
        incident_id = created.id
    else:
        incident_id = existing_binding.incident_id

    found = _existing_observation_evidence(evidence, incident_id, observation, request)
    if found is not None:
        return repo.complete_binding(identity, incident_id, found.id, owner)

    content_ref = content_refs.content_ref(observation)
    if not isinstance(content_ref, str) or not content_ref.strip():
        raise IngestionConfigurationError("The content reference factory must return a non-empty string.")
    recorded = evidence.record_observation_event_evidence(
        RecordObservationEventEvidence(
            incident_id=incident_id,
            description=_evidence_description(observation),
            source_label=observation.source,
            content_ref=content_ref,
            captured_at=observation.occurred_at,
            provenance=observation.provenance,
        ),
        request,
    )
    return repo.complete_binding(identity, incident_id, recorded.id, owner)


def _remember_created_incident(
    repo: CompletionObservationRepository,
    identity,
    incident_id: str,
    owner: int,
    cause: Exception,
) -> None:
    """Keep a created Incident id when bind_incident fails.

    If the id cannot be persisted safely, raise a reconciliation error so a
    later owner does not silently create a second Incident.
    """
    try:
        repo.remember_created_incident(identity, incident_id, owner)
    except Exception:
        raise IngestionConfigurationError(CREATED_INCIDENT_UNBOUND) from cause


def _block_uncertain_incident_create(
    repo: CompletionObservationRepository,
    identity,
    owner: int,
    cause: Exception,
) -> None:
    """Fence another create when create_incident raised without a recoverable id."""
    try:
        repo.block_uncertain_incident_create(identity, owner)
    except Exception:
        raise IngestionConfigurationError(CREATED_INCIDENT_UNBOUND) from cause


def _original_cause(exc: Exception) -> Exception:
    if exc.__cause__ is not None:
        return exc.__cause__
    return exc


def _create_incident_command(
    observation: Observation, assessment: Stage2Assessment
) -> CreateIncident:
    assert assessment.mapped_severity is not None
    return CreateIncident(
        title=observation.title,
        description=observation.description,
        severity=assessment.mapped_severity,
        service_ref=assessment.resolved_service_ref,
        external_refs=[],
    )


def _evidence_description(observation: Observation) -> str:
    """Use stored description, or title when description is absent.

    Observation.description is optional; Evidence description is required.
    """
    if observation.description is not None:
        return observation.description
    return observation.title


def _existing_observation_evidence(
    evidence: EvidenceService,
    incident_id: str,
    observation: Observation,
    request: IncidentRequestContext,
) -> Evidence | None:
    """Reuse already-written observation-origin Evidence; never guess a second write.

    The match key is the bound Incident plus stored provenance provider,
    sourceEventId, and sourceAccountRef. collector_ref is omitted so the key
    stays aligned with M2 IdempotencyIdentity, which also excludes collectorRef.
    """
    listed = evidence.list_incident_evidence(incident_id, request)
    matches = [
        row
        for row in listed
        if row.evidence_type == "event"
        and row.provenance.origin_type == "observation"
        and row.provenance.provider == observation.provenance.provider
        and row.provenance.source_event_id == observation.provenance.source_event_id
        and row.provenance.source_account_ref == observation.provenance.source_account_ref
    ]
    if len(matches) > 1:
        raise IngestionConfigurationError(
            "Multiple observation-origin Evidence records exist for this Incident."
        )
    if len(matches) == 1:
        return matches[0]
    return None
