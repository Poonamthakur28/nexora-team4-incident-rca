from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy import Engine

from app import SERVICE_NAME
from app.api.deps import get_engine
from app.schemas.errors import ErrorResponse
from app.schemas.health import DatabaseHealthResponse, HealthQuery, HealthResponse
from app.services.database_health import is_database_reachable

liveness_router = APIRouter(tags=["health"])
"""Mounted at the application root and under `/api/v1`."""

router = APIRouter(tags=["health"])
"""Versioned health routes, mounted under `/api/v1`."""

_INVALID_REQUEST = {
    status.HTTP_400_BAD_REQUEST: {"model": ErrorResponse, "description": "Unexpected query parameters."}
}


@liveness_router.get(
    "/health",
    response_model=HealthResponse,
    summary="API process liveness",
    description="Reports that the API process is serving requests. Does not contact PostgreSQL.",
    responses=_INVALID_REQUEST,
)
def get_health(_query: Annotated[HealthQuery, Query()]) -> HealthResponse:
    return HealthResponse(status="ok", service=SERVICE_NAME, timestamp=datetime.now(UTC))


router.include_router(liveness_router)


@router.get(
    "/health/database",
    response_model=DatabaseHealthResponse,
    summary="PostgreSQL connectivity",
    description="Runs `SELECT 1` against `DATABASE_URL`. Returns 503 when the database is unreachable.",
    responses={
        **_INVALID_REQUEST,
        status.HTTP_503_SERVICE_UNAVAILABLE: {
            "model": DatabaseHealthResponse,
            "description": "PostgreSQL is unreachable.",
        },
    },
)
def get_database_health(
    _query: Annotated[HealthQuery, Query()],
    response: Response,
    engine: Annotated[Engine, Depends(get_engine)],
) -> DatabaseHealthResponse:
    now = datetime.now(UTC)
    if is_database_reachable(engine):
        return DatabaseHealthResponse(status="ok", database="reachable", timestamp=now)
    response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return DatabaseHealthResponse(status="unavailable", database="unreachable", timestamp=now)
