from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app

# Port 1 is reserved and refuses connections, so nothing here needs a running PostgreSQL.
UNREACHABLE_DATABASE_URL = "postgresql+psycopg://nexora:nexora@127.0.0.1:1/nexora_team4"


def make_settings(**overrides: object) -> Settings:
    """Settings isolated from developer `.env` files."""
    values: dict[str, object] = {
        "app_env": "test",
        "database_url": UNREACHABLE_DATABASE_URL,
        "database_connect_timeout_seconds": 1,
        "cors_origins": ["http://localhost:5173"],
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)  # type: ignore[arg-type]


@pytest.fixture
def settings() -> Settings:
    return make_settings()


@pytest.fixture
def app(settings: Settings) -> FastAPI:
    return create_app(settings)


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client
