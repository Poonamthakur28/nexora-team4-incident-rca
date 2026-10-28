import logging

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.schemas.errors import ErrorBody, ErrorDetail, ErrorResponse

logger = logging.getLogger(__name__)


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


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(RequestValidationError, _validation_error)  # type: ignore[arg-type]
    app.add_exception_handler(StarletteHTTPException, _http_error)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, _unhandled_error)
