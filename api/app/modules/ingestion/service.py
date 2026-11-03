"""Stage 1, normalize, then reserve. No Stage 2 and no completion workflow."""

from app.modules.ingestion.contracts import Observation
from app.modules.ingestion.fingerprint import normalize_observation
from app.modules.ingestion.ports import (
    AuthenticatedConnectorContext,
    PayloadHasher,
    SourceAccountAuthorizer,
)
from app.modules.ingestion.repository import ObservationRepository, ReservationResult
from app.modules.ingestion.validation import validate_observation_stage1


class ObservationIngestionService:
    """Accept an Observation into the in-memory reservation store.

    Authorization, hashing, and storage are injected. This service does not
    create a durable receipt, processing attempt, Incident, or Evidence.
    """

    def __init__(self, repository: ObservationRepository, hasher: PayloadHasher) -> None:
        self._repository = repository
        self._hasher = hasher

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
