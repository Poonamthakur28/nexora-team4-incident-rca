"""Stage 1 observation checks from CT-04 §8.5 and §9.3 (Proposed, not agreed).

Stage 2 consistency, service resolution, and severity mapping are not done here.
"""

from dataclasses import dataclass

from app.modules.ingestion.contracts import Observation
from app.modules.ingestion.errors import (
    IngestionConfigurationError,
    InvalidObservationRequest,
    ObservationAuthorizationDenied,
)
from app.modules.ingestion.ports import AuthenticatedConnectorContext, SourceAccountAuthorizer

_DENIAL_MESSAGE = "The observation was denied."


@dataclass(frozen=True, slots=True)
class Stage1Result:
    """Stage 1 acceptance.

    No receipt, delivery id, observation id, reservation, or attempt is created.
    """

    organization_id: str


def validate_observation_stage1(
    observation: Observation,
    context: AuthenticatedConnectorContext,
    authorizer: SourceAccountAuthorizer,
) -> Stage1Result:
    """Apply Stage 1 authorization and binding checks to an already built Observation.

    Schema failures are raised while constructing `Observation`. This function
    repeats the origin-type check so a bypassed model still cannot pass, then
    checks collector binding. The provenance source account must match the
    top-level source account before the authorizer is called. Provider and
    source-event consistency are Stage 2 and are intentionally not checked.
    """
    if observation.provenance.origin_type != "observation":
        raise InvalidObservationRequest("Observation provenance originType must be 'observation'.")
    if observation.provenance.collector_ref != context.registration_ref:
        raise ObservationAuthorizationDenied(_DENIAL_MESSAGE)
    if observation.provenance.source_account_ref != observation.source_account_ref:
        raise ObservationAuthorizationDenied(_DENIAL_MESSAGE)
    if not _source_account_authorized(observation, context, authorizer):
        raise ObservationAuthorizationDenied(_DENIAL_MESSAGE)
    return Stage1Result(organization_id=context.organization_id)


def _source_account_authorized(
    observation: Observation,
    context: AuthenticatedConnectorContext,
    authorizer: SourceAccountAuthorizer,
) -> bool:
    try:
        authorized = authorizer.is_authorized(
            context.registration_ref,
            observation.source_account_ref,
            context.organization_id,
        )
    except Exception as exc:
        raise IngestionConfigurationError("The source-account authorizer failed.") from exc
    if not isinstance(authorized, bool):
        raise IngestionConfigurationError("The source-account authorizer must return a boolean.")
    return authorized
