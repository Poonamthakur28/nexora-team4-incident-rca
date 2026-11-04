import logging

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.modules.evidence_collection.errors import (
    EvidenceDomainError,
    EvidenceNotFound,
    InvalidEvidenceInput,
)
from app.modules.incidents.errors import (
    IncidentConcurrencyConflict,
    IncidentDomainError,
    IncidentNotFound,
    InvalidIncidentInput,
    InvalidLifecycleTransition,
    InvalidRequestContext,
    OrganizationScopeError,
    SameStatusTransition,
)
from app.schemas.errors import ErrorBody, ErrorDetail, ErrorResponse

logger = logging.getLogger(__name__)


class ContentReferenceNotConfigured(Exception):
    """HTTP policy: a contentRef was supplied but no verifier is configured."""

    def __init__(self) -> None:
        super().__init__("Content-reference verification is not configured.")


def _error(status_code: int, body: ErrorBody) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content=ErrorResponse(error=body).model_dump(exclude_none=True),
    )


async def _validation_error(_request: Request, exc: RequestValidationError) -> JSONResponse:
    errors = exc.errors()
    logger.warning("Rejected invalid request", extra={"issue_count": len(errors)})
    details = [
        ErrorDetail(path=".".join(str(part) for part in error.get("loc", ())), message=error["msg"])
        for error in errors
    ]
    return _error(
        status.HTTP_400_BAD_REQUEST,
        ErrorBody(code="INVALID_REQUEST", message="The request is invalid.", details=details),
    )


async def _http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    if exc.status_code == status.HTTP_404_NOT_FOUND:
        body = ErrorBody(code="NOT_FOUND", message=f"No route for {request.method} {request.url.path}")
    elif exc.status_code == status.HTTP_405_METHOD_NOT_ALLOWED:
        body = ErrorBody(code="METHOD_NOT_ALLOWED", message=f"{request.method} is not allowed here")
    else:
        body = ErrorBody(code="HTTP_ERROR", message=str(exc.detail))
    response = _error(exc.status_code, body)
    if exc.headers:
        response.headers.update(exc.headers)
    return response


async def _unhandled_error(_request: Request, exc: Exception) -> JSONResponse:
    logger.error("Unhandled request error", exc_info=exc)
    return _error(
        status.HTTP_500_INTERNAL_SERVER_ERROR,
        ErrorBody(code="INTERNAL_SERVER_ERROR", message="An unexpected error occurred."),
    )


def map_incident_domain_error(exc: IncidentDomainError) -> tuple[int, str, str]:
    """Map an incident domain error to HTTP status, public code, and public message."""
    if isinstance(exc, IncidentNotFound):
        return status.HTTP_404_NOT_FOUND, "INCIDENT_NOT_FOUND", str(exc)
    if isinstance(exc, InvalidLifecycleTransition):
        return status.HTTP_409_CONFLICT, "INVALID_LIFECYCLE_TRANSITION", str(exc)
    if isinstance(exc, SameStatusTransition):
        return status.HTTP_409_CONFLICT, "SAME_STATUS_TRANSITION", str(exc)
    if isinstance(exc, IncidentConcurrencyConflict):
        return status.HTTP_409_CONFLICT, "INCIDENT_CONFLICT", str(exc)
    if isinstance(exc, (OrganizationScopeError, InvalidRequestContext)):
        return status.HTTP_400_BAD_REQUEST, "INVALID_REQUEST_CONTEXT", str(exc)
    if isinstance(exc, InvalidIncidentInput):
        return status.HTTP_400_BAD_REQUEST, "INVALID_INCIDENT_INPUT", str(exc)
    return (
        status.HTTP_500_INTERNAL_SERVER_ERROR,
        "INTERNAL_SERVER_ERROR",
        "An unexpected error occurred.",
    )


async def _incident_domain_error(_request: Request, exc: IncidentDomainError) -> JSONResponse:
    status_code, code, message = map_incident_domain_error(exc)
    if status_code >= 500:
        logger.error("Incident domain error", exc_info=exc)
    else:
        logger.warning("Rejected incident request", extra={"code": code})
    return _error(status_code, ErrorBody(code=code, message=message))


def map_evidence_domain_error(exc: EvidenceDomainError) -> tuple[int, str, str]:
    """Map an Evidence domain error to HTTP status, public code, and public message."""
    if isinstance(exc, EvidenceNotFound):
        return status.HTTP_404_NOT_FOUND, "EVIDENCE_NOT_FOUND", str(exc)
    if isinstance(exc, InvalidEvidenceInput):
        return status.HTTP_400_BAD_REQUEST, "INVALID_EVIDENCE_INPUT", str(exc)
    return (
        status.HTTP_500_INTERNAL_SERVER_ERROR,
        "INTERNAL_SERVER_ERROR",
        "An unexpected error occurred.",
    )


async def _evidence_domain_error(_request: Request, exc: EvidenceDomainError) -> JSONResponse:
    status_code, code, message = map_evidence_domain_error(exc)
    if status_code >= 500:
        logger.error("Evidence domain error", exc_info=exc)
    else:
        logger.warning("Rejected evidence request", extra={"code": code})
    return _error(status_code, ErrorBody(code=code, message=message))


async def _content_reference_not_configured(
    _request: Request, _exc: ContentReferenceNotConfigured
) -> JSONResponse:
    logger.warning("Rejected evidence request", extra={"code": "CONTENT_REFERENCE_NOT_CONFIGURED"})
    return _error(
        status.HTTP_400_BAD_REQUEST,
        ErrorBody(
            code="CONTENT_REFERENCE_NOT_CONFIGURED",
            message="Content-reference verification is not configured.",
        ),
    )


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(RequestValidationError, _validation_error)  # type: ignore[arg-type]
    app.add_exception_handler(StarletteHTTPException, _http_error)  # type: ignore[arg-type]
    app.add_exception_handler(IncidentDomainError, _incident_domain_error)  # type: ignore[arg-type]
    app.add_exception_handler(EvidenceDomainError, _evidence_domain_error)  # type: ignore[arg-type]
    app.add_exception_handler(ContentReferenceNotConfigured, _content_reference_not_configured)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, _unhandled_error)
