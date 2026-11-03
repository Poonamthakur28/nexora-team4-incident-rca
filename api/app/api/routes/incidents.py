from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.api.deps import get_incident_request_context, get_incident_service
from app.modules.incidents.context import IncidentRequestContext
from app.modules.incidents.contracts import AssignIncident, ChangeIncidentStatus, CreateIncident, Incident
from app.modules.incidents.service import IncidentService
from app.schemas.errors import ErrorResponse

router = APIRouter(tags=["incidents"])

_ERROR_RESPONSES = {
    status.HTTP_400_BAD_REQUEST: {"model": ErrorResponse, "description": "Invalid request or trusted context."},
    status.HTTP_404_NOT_FOUND: {"model": ErrorResponse, "description": "Incident not found in the trusted organization."},
    status.HTTP_409_CONFLICT: {"model": ErrorResponse, "description": "Lifecycle or concurrency conflict."},
    status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ErrorResponse, "description": "Unexpected incident failure."},
}


@router.post(
    "/incidents",
    response_model=Incident,
    status_code=status.HTTP_201_CREATED,
    summary="Create incident",
    description="Create an open incident in the trusted organization from the stand-in headers.",
    responses=_ERROR_RESPONSES,
)
def create_incident(
    command: CreateIncident,
    context: Annotated[IncidentRequestContext, Depends(get_incident_request_context)],
    service: Annotated[IncidentService, Depends(get_incident_service)],
) -> Incident:
    return service.create_incident(command, context)


@router.get(
    "/incidents/{incident_id}",
    response_model=Incident,
    summary="Get incident",
    description="Return one incident visible to the trusted organization. Cross-organization ids are 404.",
    responses=_ERROR_RESPONSES,
)
def get_incident(
    incident_id: str,
    context: Annotated[IncidentRequestContext, Depends(get_incident_request_context)],
    service: Annotated[IncidentService, Depends(get_incident_service)],
) -> Incident:
    return service.get_incident(incident_id, context)


@router.post(
    "/incidents/{incident_id}/status",
    response_model=Incident,
    summary="Change incident status",
    description=(
        "Apply an allowed status transition. Correlation must come from "
        "X-Nexora-Correlation-Id. The response is the updated Incident."
    ),
    responses=_ERROR_RESPONSES,
)
def change_incident_status(
    incident_id: str,
    command: ChangeIncidentStatus,
    context: Annotated[IncidentRequestContext, Depends(get_incident_request_context)],
    service: Annotated[IncidentService, Depends(get_incident_service)],
) -> Incident:
    return service.change_status(incident_id, command, context).incident


@router.patch(
    "/incidents/{incident_id}/assignment",
    response_model=Incident,
    summary="Assign incident",
    description="Set or clear assignment references. Omitted fields stay unchanged; explicit null clears.",
    responses=_ERROR_RESPONSES,
)
def assign_incident(
    incident_id: str,
    command: AssignIncident,
    context: Annotated[IncidentRequestContext, Depends(get_incident_request_context)],
    service: Annotated[IncidentService, Depends(get_incident_service)],
) -> Incident:
    return service.assign_incident(incident_id, command, context)
