from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.api.deps import get_evidence_service, get_incident_request_context
from app.modules.evidence_collection.contracts import Evidence, RecordManualEvidence
from app.modules.evidence_collection.service import EvidenceService
from app.modules.incidents.context import IncidentRequestContext
from app.schemas.errors import ErrorResponse
from app.schemas.evidence import RecordManualEvidenceRequest

router = APIRouter(tags=["evidence"])

_ERROR_RESPONSES = {
    status.HTTP_400_BAD_REQUEST: {"model": ErrorResponse, "description": "Invalid request or trusted context."},
    status.HTTP_404_NOT_FOUND: {"model": ErrorResponse, "description": "Incident not found in the trusted organization."},
    status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ErrorResponse, "description": "Unexpected evidence failure."},
}


@router.post(
    "/incidents/{incident_id}/evidence",
    response_model=Evidence,
    status_code=status.HTTP_201_CREATED,
    summary="Record manual evidence",
    description=(
        "Record manual Evidence for a visible incident. Organization and actor come "
        "from stand-in headers, not the JSON body. Observation-origin Evidence is not accepted."
    ),
    responses=_ERROR_RESPONSES,
)
def record_manual_incident_evidence(
    incident_id: str,
    body: RecordManualEvidenceRequest,
    context: Annotated[IncidentRequestContext, Depends(get_incident_request_context)],
    service: Annotated[EvidenceService, Depends(get_evidence_service)],
) -> Evidence:
    command = RecordManualEvidence(
        incident_id=incident_id,
        evidence_type=body.evidence_type,
        description=body.description,
        source_label=body.source_label,
        external_source_ref=body.external_source_ref,
        content_ref=body.content_ref,
        captured_at=body.captured_at,
        availability=body.availability,
    )
    return service.record_manual_evidence(command, context)
