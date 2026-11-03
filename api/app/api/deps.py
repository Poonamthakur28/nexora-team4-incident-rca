from collections.abc import Iterator
from typing import Annotated

from fastapi import Header, Request
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.modules.incidents.context import IncidentRequestContext
from app.modules.incidents.errors import InvalidRequestContext
from app.modules.incidents.service import IncidentService
from app.modules.timeline.service import TimelineService
from app.shared.identifiers import ExternalRef

STAND_IN_HEADER_NOTE = (
    "Development/test stand-in for a trusted request boundary. "
    "This header is not authentication, not authorization, and not Team 1 /auth/me. "
    "The API process trusts the value as already established."
)


def get_engine(request: Request) -> Engine:
    return request.app.state.engine


def get_session(request: Request) -> Iterator[Session]:
    with request.app.state.session_factory() as session:
        yield session


def get_incident_service(request: Request) -> IncidentService:
    """Return the process-local IncidentService attached to this FastAPI app."""
    return request.app.state.incident_service


def get_timeline_service(request: Request) -> TimelineService:
    """Return the process-local TimelineService attached to this FastAPI app."""
    return request.app.state.timeline_service


def get_incident_request_context(
    organization_id: Annotated[
        str | None,
        Header(alias="X-Nexora-Organization-Id", description=STAND_IN_HEADER_NOTE),
    ] = None,
    actor_owner: Annotated[
        str | None,
        Header(alias="X-Nexora-Actor-Owner", description=STAND_IN_HEADER_NOTE),
    ] = None,
    actor_id: Annotated[
        str | None,
        Header(alias="X-Nexora-Actor-Id", description=STAND_IN_HEADER_NOTE),
    ] = None,
    correlation_id: Annotated[
        str | None,
        Header(alias="X-Nexora-Correlation-Id", description=STAND_IN_HEADER_NOTE),
    ] = None,
) -> IncidentRequestContext:
    """Build IncidentRequestContext from stand-in headers, never from a JSON body.

    These headers are a development/test stand-in. They are not authentication or
    authorization. Organization and actor values in a request body are ignored
    (and extra body keys are rejected by the domain contracts).
    """
    if (
        actor_owner is None
        or actor_id is None
        or not actor_owner.strip()
        or not actor_id.strip()
    ):
        raise InvalidRequestContext("A trusted actor is required.")
    return IncidentRequestContext(
        organization_id="" if organization_id is None else organization_id,
        actor_ref=ExternalRef(owner=actor_owner, id=actor_id),
        correlation_id=correlation_id,
    )
