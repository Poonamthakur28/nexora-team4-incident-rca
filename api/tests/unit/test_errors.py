from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


def test_unexpected_failure_returns_500_without_internal_details(settings: Settings) -> None:
    app = create_app(settings)

    @app.get("/boom")
    def boom() -> None:
        raise RuntimeError("database credential detail")

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/boom")

    assert response.status_code == 500
    assert response.json() == {
        "error": {"code": "INTERNAL_SERVER_ERROR", "message": "An unexpected error occurred."}
    }
    assert "database credential detail" not in response.text
    assert "Traceback" not in response.text


def test_wrong_method_returns_structured_error(settings: Settings) -> None:
    with TestClient(create_app(settings)) as client:
        response = client.post("/health")

    assert response.status_code == 405
    assert response.json()["error"]["code"] == "METHOD_NOT_ALLOWED"
    assert "allow" in response.headers
