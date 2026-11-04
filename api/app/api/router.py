from fastapi import APIRouter

from app.api.routes import evidence, health, incidents, timeline

API_V1_PREFIX = "/api/v1"

api_router = APIRouter(prefix=API_V1_PREFIX)
api_router.include_router(health.router)
api_router.include_router(incidents.router)
api_router.include_router(timeline.router)
api_router.include_router(evidence.router)
