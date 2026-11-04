from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.api.deps import get_evidence_service, get_incident_request_context
from app.core.errors import ContentReferenceNotConfigured
from app.modules.evidence_collection.contracts import Evidence, RecordManualEvidence
from app.modules.evidence_collection.service import EvidenceService
from app.modules.incidents.context import IncidentRequestContext
from app.schemas.errors import ErrorResponse
from app.schemas.evidence import RecordManualEvidenceRequest

router = APIRouter(tags=["evidence"])

_WRITE_ERROR_RESPONSES = {
    status.HTTP_400_BAD_REQUEST: {"model": ErrorResponse, "description": "Invalid request, trusted context, or unconfigured content reference."},
    status.HTTP_404_NOT_FOUND: {"model": ErrorResponse, "description": "Incident not found in the trusted organization."},
    status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ErrorResponse, "description": "Unexpected evidence failure."},
}

_LIST_ERROR_RESPONSES = {
    status.HTTP_400_BAD_REQUEST: {"model": ErrorResponse, "description": "Invalid trusted context."},
    status.HTTP_404_NOT_FOUND: {"model": ErrorResponse, "description": "Incident not found in the trusted organization."},
    status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ErrorResponse, "description": "Unexpected evidence failure."},
}

_GET_ERROR_RESPONSES = {
    status.HTTP_400_BAD_REQUEST: {"model": ErrorResponse, "description": "Invalid trusted context."},
    status.HTTP_404_NOT_FOUND: {"model": ErrorResponse, "description": "Evidence not found in the trusted organization."},
    status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ErrorResponse, "description": "Unexpected evidence failure."},
}


@router.get(
    "/incidents/{incident_id}/evidence",
    response_model=list[Evidence],
    summary="List incident evidence",
    description=(
        "Return Evidence visible on this incident in the trusted organization. "
        "Missing and cross-organization incidents are indistinguishable 404s."
    ),
    responses=_LIST_ERROR_RESPONSES,
)
def list_incident_evidence(
    incident_id: str,
    context: Annotated[IncidentRequestContext, Depends(get_incident_request_context)],
    service: Annotated[EvidenceService, Depends(get_evidence_service)],
) -> list[Evidence]:
    return list(service.list_incident_evidence(incident_id, context))


@router.get(
    "/evidence/{evidence_id}",
    response_model=Evidence,
    summary="Get evidence",
    description=(
        "Return one Evidence record visible to the trusted organization. "
        "Missing and cross-organization ids are indistinguishable 404s."
    ),
    responses=_GET_ERROR_RESPONSES,
)
def get_evidence(
    evidence_id: str,
    context: Annotated[IncidentRequestContext, Depends(get_incident_request_context)],
    service: Annotated[EvidenceService, Depends(get_evidence_service)],
) -> Evidence:
    return service.get_evidence(evidence_id, context)


@router.post(
    "/incidents/{incident_id}/evidence",
    response_model=Evidence,
    status_code=status.HTTP_201_CREATED,
    summary="Record manual evidence",
    description=(
        "Record manual Evidence for a visible incident. Organization and actor come "
        "from stand-in headers, not the JSON body. Observation-origin Evidence is not accepted."
    ),
    responses=_WRITE_ERROR_RESPONSES,
)
def record_manual_incident_evidence(
    incident_id: str,
    body: RecordManualEvidenceRequest,
    context: Annotated[IncidentRequestContext, Depends(get_incident_request_context)],
    service: Annotated[EvidenceService, Depends(get_evidence_service)],
) -> Evidence:
    if body.content_ref is not None and not service.can_verify_content_references():
        raise ContentReferenceNotConfigured()
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
