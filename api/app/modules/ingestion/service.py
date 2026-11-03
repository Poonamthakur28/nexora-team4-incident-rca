"""Stage 1, normalize, reserve, then optional Stage 2 assessment."""

from dataclasses import dataclass

from app.modules.ingestion.contracts import Observation
from app.modules.ingestion.errors import IngestionConfigurationError
from app.modules.ingestion.fingerprint import normalize_observation
from app.modules.ingestion.normalization import build_idempotency_identity
from app.modules.ingestion.ports import (
    AuthenticatedConnectorContext,
    PayloadHasher,
    ServiceResolver,
    SeverityMapper,
    SourceAccountAuthorizer,
)
from app.modules.ingestion.repository import (
    ObservationRepository,
    ReservationResult,
    Stage2ObservationRepository,
)
from app.modules.ingestion.stage2 import Stage2Assessment, evaluate_stage2
from app.modules.ingestion.validation import validate_observation_stage1

_STAGE2_UNAVAILABLE = "The Stage 2 assessment could not be completed."


@dataclass(frozen=True, slots=True)
class IngestionResult:
    """Reservation plus a stored Stage 2 domain assessment.

    `accept` still returns only the reservation. `assess` is the additive path
    that runs Stage 2. This is not a completion result.
    """

    reservation: ReservationResult
    assessment: Stage2Assessment


class ObservationIngestionService:
    """Accept an Observation into the in-memory reservation store.

    Authorization, hashing, and storage are injected. `assess` also injects
    mock service and severity ports. This service does not create a durable
    receipt, processing attempt, Incident, or Evidence.
    """

    def __init__(
        self,
        repository: ObservationRepository,
        hasher: PayloadHasher,
        *,
        resolver: ServiceResolver | None = None,
        mapper: SeverityMapper | None = None,
    ) -> None:
        self._repository = repository
        self._hasher = hasher
        self._resolver = resolver
        self._mapper = mapper

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
