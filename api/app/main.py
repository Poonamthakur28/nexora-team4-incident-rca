from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api.router import api_router
from app.api.routes.health import liveness_router
from app.core.config import Settings, get_settings
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging
from app.db.session import build_engine, build_session_factory
from app.modules.evidence_collection.repository import InMemoryEvidenceRepository
from app.modules.evidence_collection.service import EvidenceService
from app.modules.incidents.repository import InMemoryIncidentRepository
from app.modules.incidents.service import IncidentService
from app.modules.timeline.service import TimelineService

DESCRIPTION = (
    "Nexora Team 4 incident management and AI-assisted root cause analysis API. "
    "Phase 1: health checks and in-memory incident HTTP operations. "
    "Persistence and Team 1 authentication are not implemented."
)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)
    engine = build_engine(settings)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        yield
        engine.dispose()

    app = FastAPI(
        title="Nexora Team 4 Incident RCA API",
        version=__version__,
        description=DESCRIPTION,
        docs_url="/docs",
        redoc_url=None,
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )
    incident_repository = InMemoryIncidentRepository()
    incident_service = IncidentService(incident_repository)
    evidence_repository = InMemoryEvidenceRepository()
    evidence_service = EvidenceService(evidence_repository, incident_service)
    timeline_service = TimelineService(incident_service, incident_service, evidence_service)
    app.state.settings = settings
    app.state.engine = engine
    app.state.session_factory = build_session_factory(engine)
    app.state.incident_repository = incident_repository
    app.state.incident_service = incident_service
    app.state.evidence_repository = evidence_repository
    app.state.evidence_service = evidence_service
    app.state.timeline_service = timeline_service

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    register_exception_handlers(app)
    app.include_router(liveness_router)
    app.include_router(api_router)
    return app


app = create_app()
