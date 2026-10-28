from fastapi.testclient import TestClient

from app import __version__


def test_openapi_schema_is_available(client: TestClient) -> None:
    response = client.get("/openapi.json")

    assert response.status_code == 200
    schema = response.json()
    assert schema["info"]["title"] == "Nexora Team 4 Incident RCA API"
    assert schema["info"]["version"] == __version__
    assert schema["info"]["description"]
    assert {"/health", "/api/v1/health", "/api/v1/health/database"} <= set(schema["paths"])


def test_openapi_documents_health_response(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()
    operation = schema["paths"]["/api/v1/health"]["get"]

    assert {"200", "400"} <= set(operation["responses"])
    health = schema["components"]["schemas"]["HealthResponse"]
    assert set(health["required"]) == {"status", "service", "timestamp"}
    assert health["properties"]["timestamp"]["format"] == "date-time"


def test_swagger_ui_is_served(client: TestClient) -> None:
    response = client.get("/docs")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "/openapi.json" in response.text
