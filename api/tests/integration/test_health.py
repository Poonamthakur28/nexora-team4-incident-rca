from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine

from app.api.deps import get_engine

HEALTH_PATHS = ["/health", "/api/v1/health"]


@pytest.mark.parametrize("path", HEALTH_PATHS)
def test_health_reports_ok(client: TestClient, path: str) -> None:
    response = client.get(path)

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"status", "service", "timestamp"}
    assert body["status"] == "ok"
    assert body["service"] == "nexora-team4-incident-rca"


@pytest.mark.parametrize("path", HEALTH_PATHS)
def test_health_timestamp_is_current_utc_iso8601(client: TestClient, path: str) -> None:
    before = datetime.now(UTC)
    raw = client.get(path).json()["timestamp"]
    after = datetime.now(UTC)

    assert raw.endswith("Z")
    parsed = datetime.fromisoformat(raw)
    assert parsed.utcoffset() == timedelta(0)
    assert before - timedelta(seconds=1) <= parsed <= after + timedelta(seconds=1)


@pytest.mark.parametrize("path", HEALTH_PATHS)
def test_health_does_not_need_the_database(client: TestClient, path: str) -> None:
    """The test settings point DATABASE_URL at a closed port."""
    assert client.get(path).status_code == 200


@pytest.mark.parametrize("path", HEALTH_PATHS)
def test_health_rejects_unexpected_query_parameters(client: TestClient, path: str) -> None:
    response = client.get(path, params={"extra": "1"})

    assert response.status_code == 400
    body = response.json()
    assert body["error"]["code"] == "INVALID_REQUEST"
    assert body["error"]["details"][0]["path"] == "query.extra"
    assert "stack" not in response.text
    assert "Traceback" not in response.text


def test_unknown_route_returns_not_found_error(client: TestClient) -> None:
    response = client.get("/api/v1/does-not-exist")

    assert response.status_code == 404
    assert response.json() == {
        "error": {"code": "NOT_FOUND", "message": "No route for GET /api/v1/does-not-exist"}
    }


def test_cors_allows_configured_origin(client: TestClient) -> None:
    response = client.get("/api/v1/health", headers={"Origin": "http://localhost:5173"})

    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_cors_ignores_unlisted_origin(client: TestClient) -> None:
    response = client.get("/api/v1/health", headers={"Origin": "http://evil.example"})

    assert "access-control-allow-origin" not in response.headers


def test_database_health_reports_unreachable_database(client: TestClient) -> None:
    response = client.get("/api/v1/health/database")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "unavailable"
    assert body["database"] == "unreachable"
    assert "nexora:nexora" not in response.text
    assert "127.0.0.1" not in response.text


def test_database_health_reports_reachable_database(client: TestClient) -> None:
    engine = create_engine("sqlite://")
    client.app.dependency_overrides[get_engine] = lambda: engine  # type: ignore[attr-defined]
    try:
        response = client.get("/api/v1/health/database")
    finally:
        client.app.dependency_overrides.clear()  # type: ignore[attr-defined]
        engine.dispose()

    assert response.status_code == 200
    assert response.json()["database"] == "reachable"


def test_database_health_is_not_mounted_at_root(client: TestClient) -> None:
    assert client.get("/health/database").status_code == 404
