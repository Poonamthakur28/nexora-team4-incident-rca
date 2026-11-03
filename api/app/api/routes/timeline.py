from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.api.deps import get_incident_request_context, get_timeline_service
from app.modules.incidents.context import IncidentRequestContext
from app.modules.timeline.contracts import TimelineEntry
from app.modules.timeline.service import TimelineService
from app.schemas.errors import ErrorResponse

router = APIRouter(tags=["timeline"])

_ERROR_RESPONSES = {
    status.HTTP_400_BAD_REQUEST: {"model": ErrorResponse, "description": "Invalid trusted context."},
    status.HTTP_404_NOT_FOUND: {"model": ErrorResponse, "description": "Incident not found in the trusted organization."},
    status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ErrorResponse, "description": "Unexpected timeline failure."},
}


@router.get(
    "/incidents/{incident_id}/timeline",
    response_model=list[TimelineEntry],
    summary="Get incident timeline",
    description=(
        "Read-time chronology of a visible incident. Organization comes from the "
        "stand-in headers, not from the path or body. This is not authentication."
    ),
    responses=_ERROR_RESPONSES,
)
def get_incident_timeline(
    incident_id: str,
    context: Annotated[IncidentRequestContext, Depends(get_incident_request_context)],
    service: Annotated[TimelineService, Depends(get_timeline_service)],
) -> list[TimelineEntry]:
    return list(service.list_incident_timeline(incident_id, context))
