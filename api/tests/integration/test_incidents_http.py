from fastapi.testclient import TestClient

from app.modules.incidents.errors import UncertainIncidentCreate
from app.modules.incidents.repository import InMemoryIncidentRepository

ORG = "org_synth_0001"
OTHER_ORG = "org_synth_0002"
ACTOR_OWNER = "team1.user"
ACTOR_ID = "user_synth_0007"
CORRELATION_ID = "corr-synth-0001"

INCIDENT_PATHS = {
    "/api/v1/incidents",
    "/api/v1/incidents/{incident_id}",
    "/api/v1/incidents/{incident_id}/status",
    "/api/v1/incidents/{incident_id}/assignment",
}

INCIDENT_WIRE_KEYS = {
    "id",
    "organizationId",
    "title",
    "description",
    "severity",
    "status",
    "serviceRef",
    "assignedTeamRef",
    "assignedUserRef",
    "externalRefs",
    "createdAt",
    "updatedAt",
}


def stand_in_headers(
    organization_id: str = ORG,
    *,
    actor_owner: str = ACTOR_OWNER,
    actor_id: str = ACTOR_ID,
    correlation_id: str | None = None,
) -> dict[str, str]:
    headers = {
        "X-Nexora-Organization-Id": organization_id,
        "X-Nexora-Actor-Owner": actor_owner,
        "X-Nexora-Actor-Id": actor_id,
    }
    if correlation_id is not None:
        headers["X-Nexora-Correlation-Id"] = correlation_id
    return headers


def create_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "title": "Checkout API error rate above threshold",
        "severity": "high",
        "description": "Synthetic monitor reported a 12% HTTP 5xx rate.",
        "externalRefs": [{"owner": "synthetic-monitor", "id": "evt-10001"}],
        "serviceRef": {"owner": "service-catalog", "id": "svc_synth_checkout"},
    }
    payload.update(overrides)
    return payload


def create_incident(client: TestClient, **overrides: object) -> dict[str, object]:
    response = client.post("/api/v1/incidents", headers=stand_in_headers(), json=create_payload(**overrides))
    assert response.status_code == 201, response.text
    return response.json()


def assert_incident_wire_shape(body: dict[str, object]) -> None:
    assert set(body) == INCIDENT_WIRE_KEYS
    assert "organization_id" not in body
    assert "created_at" not in body
    assert "external_refs" not in body
    assert isinstance(body["createdAt"], str) and body["createdAt"].endswith("Z")
    assert isinstance(body["updatedAt"], str) and body["updatedAt"].endswith("Z")


def test_create_incident_uses_trusted_organization_and_camel_case(client: TestClient) -> None:
    body = create_incident(client)

    assert_incident_wire_shape(body)
    assert body["organizationId"] == ORG
    assert body["title"] == "Checkout API error rate above threshold"
    assert body["severity"] == "high"
    assert body["status"] == "open"
    assert body["serviceRef"] == {"owner": "service-catalog", "id": "svc_synth_checkout"}
    assert body["assignedTeamRef"] is None
    assert body["assignedUserRef"] is None


def test_create_incident_rejects_protected_body_fields(client: TestClient) -> None:
    for extra in (
        {"organizationId": OTHER_ORG},
        {"status": "closed"},
        {"id": "client-supplied-id"},
        {"actorRef": {"owner": ACTOR_OWNER, "id": ACTOR_ID}},
        {"createdAt": "2026-10-01T09:15:04Z"},
    ):
        response = client.post(
            "/api/v1/incidents",
            headers=stand_in_headers(),
            json=create_payload(**extra),
        )
        assert response.status_code == 400, extra
        assert response.json()["error"]["code"] == "INVALID_REQUEST"


def test_create_incident_rejects_missing_trusted_organization(client: TestClient) -> None:
    headers = stand_in_headers()
    del headers["X-Nexora-Organization-Id"]

    response = client.post("/api/v1/incidents", headers=headers, json=create_payload())

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_REQUEST_CONTEXT"


def test_get_incident_returns_created_record(client: TestClient) -> None:
    created = create_incident(client)

    response = client.get(f"/api/v1/incidents/{created['id']}", headers=stand_in_headers())

    assert response.status_code == 200
    body = response.json()
    assert_incident_wire_shape(body)
    assert body["id"] == created["id"]
    assert body["organizationId"] == ORG


def test_get_incident_is_404_for_another_organization(client: TestClient) -> None:
    created = create_incident(client)

    response = client.get(
        f"/api/v1/incidents/{created['id']}",
        headers=stand_in_headers(OTHER_ORG),
    )
    missing = client.get("/api/v1/incidents/does-not-exist", headers=stand_in_headers())

    assert response.status_code == 404
    assert missing.status_code == 404
    assert response.json()["error"]["code"] == "INCIDENT_NOT_FOUND"
    assert missing.json()["error"]["code"] == "INCIDENT_NOT_FOUND"


def test_change_status_updates_incident(client: TestClient) -> None:
    created = create_incident(client)

    response = client.post(
        f"/api/v1/incidents/{created['id']}/status",
        headers=stand_in_headers(correlation_id=CORRELATION_ID),
        json={"toStatus": "investigating", "reason": "On-call accepted the page"},
    )

    assert response.status_code == 200
    body = response.json()
    assert_incident_wire_shape(body)
    assert body["status"] == "investigating"
    assert "auditIntent" not in body
    assert "transition" not in body


def test_change_status_rejects_invalid_transition(client: TestClient) -> None:
    created = create_incident(client)

    response = client.post(
        f"/api/v1/incidents/{created['id']}/status",
        headers=stand_in_headers(correlation_id=CORRELATION_ID),
        json={"toStatus": "closed", "reason": "Skip investigation"},
    )
    stored = client.get(f"/api/v1/incidents/{created['id']}", headers=stand_in_headers())

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "INVALID_LIFECYCLE_TRANSITION"
    assert stored.json()["status"] == "open"


def test_change_status_requires_correlation_header(client: TestClient) -> None:
    created = create_incident(client)

    response = client.post(
        f"/api/v1/incidents/{created['id']}/status",
        headers=stand_in_headers(),
        json={"toStatus": "investigating", "reason": "On-call accepted the page"},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_REQUEST_CONTEXT"


def test_change_status_rejects_correlation_in_body(client: TestClient) -> None:
    created = create_incident(client)

    response = client.post(
        f"/api/v1/incidents/{created['id']}/status",
        headers=stand_in_headers(correlation_id=CORRELATION_ID),
        json={
            "toStatus": "investigating",
            "reason": "On-call accepted the page",
            "correlationId": "body-correlation",
        },
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_REQUEST"


def test_assign_incident_sets_and_clears_references(client: TestClient) -> None:
    created = create_incident(client)
    repository: InMemoryIncidentRepository = client.app.state.incident_repository

    assigned = client.patch(
        f"/api/v1/incidents/{created['id']}/assignment",
        headers=stand_in_headers(),
        json={
            "assignedTeamRef": {"owner": "team1.team", "id": "team_synth_payments"},
            "assignedUserRef": {"owner": "team1.user", "id": "user_synth_0042"},
        },
    )
    cleared = client.patch(
        f"/api/v1/incidents/{created['id']}/assignment",
        headers=stand_in_headers(),
        json={"assignedUserRef": None},
    )

    assert assigned.status_code == 200
    assert assigned.json()["assignedTeamRef"] == {"owner": "team1.team", "id": "team_synth_payments"}
    assert assigned.json()["assignedUserRef"] == {"owner": "team1.user", "id": "user_synth_0042"}
    assert_incident_wire_shape(assigned.json())
    assert cleared.status_code == 200
    assert cleared.json()["assignedTeamRef"] == {"owner": "team1.team", "id": "team_synth_payments"}
    assert cleared.json()["assignedUserRef"] is None
    assert repository.list_audit_intents(created["id"], ORG) == ()


def test_empty_assignment_is_rejected(client: TestClient) -> None:
    created = create_incident(client)

    response = client.patch(
        f"/api/v1/incidents/{created['id']}/assignment",
        headers=stand_in_headers(),
        json={},
    )
    stored = client.get(f"/api/v1/incidents/{created['id']}", headers=stand_in_headers())

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_INCIDENT_INPUT"
    assert stored.json()["assignedTeamRef"] is None
    assert stored.json()["assignedUserRef"] is None


def test_uncertain_create_returns_500_without_incident_id(client: TestClient) -> None:
    class UncertainService:
        def create_incident(self, command: object, context: object) -> object:
            raise UncertainIncidentCreate("secret-orphan-id")

    client.app.state.incident_service = UncertainService()

    response = client.post("/api/v1/incidents", headers=stand_in_headers(), json=create_payload())

    assert response.status_code == 500
    body = response.json()
    assert body["error"]["code"] == "INTERNAL_SERVER_ERROR"
    assert body["error"]["message"] == "An unexpected error occurred."
    assert "secret-orphan-id" not in response.text


def test_health_endpoints_remain_available(client: TestClient) -> None:
    assert client.get("/health").status_code == 200
    assert client.get("/api/v1/health").status_code == 200


def test_openapi_includes_the_four_incident_endpoints(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()
    paths = schema["paths"]

    assert INCIDENT_PATHS <= set(paths)
    assert "post" in paths["/api/v1/incidents"]
    assert "get" in paths["/api/v1/incidents/{incident_id}"]
    assert "post" in paths["/api/v1/incidents/{incident_id}/status"]
    assert "patch" in paths["/api/v1/incidents/{incident_id}/assignment"]
    assert "get" not in paths["/api/v1/incidents"]
