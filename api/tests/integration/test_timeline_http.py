from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.modules.evidence_collection.contracts import RecordManualEvidence
from app.modules.evidence_collection.repository import InMemoryEvidenceRepository
from app.modules.evidence_collection.service import EvidenceService
from app.modules.incidents.context import IncidentRequestContext
from app.modules.incidents.repository import InMemoryIncidentRepository
from app.modules.incidents.service import IncidentService
from app.modules.ingestion.context import ConnectorRegistrationActorFactory
from app.modules.ingestion.ports import StaticContentReferenceFactory
from app.modules.ingestion.service import ObservationIngestionService
from app.shared.identifiers import ExternalRef
from tests.integration.test_incidents_http import (
    CORRELATION_ID,
    ORG,
    OTHER_ORG,
    create_incident,
    create_payload,
    stand_in_headers,
)
from tests.unit.evidence.test_service import FakeVerifier
from tests.unit.ingestion.test_fingerprint import RecordingHasher
from tests.unit.ingestion.test_repository import observation, repository as observation_repository
from tests.unit.ingestion.test_stage1_validation import authorizer, context as connector_context
from tests.unit.ingestion.test_stage2 import RecordingMapper, RecordingResolver

TIMELINE_PATH = "/api/v1/incidents/{incident_id}/timeline"
TIMELINE_WIRE_KEYS = {
    "id",
    "organizationId",
    "incidentId",
    "category",
    "sourceKind",
    "sourceId",
    "occurredAt",
    "recordedAt",
    "label",
    "detail",
}


def timeline_url(incident_id: str) -> str:
    return f"/api/v1/incidents/{incident_id}/timeline"


def get_timeline(client: TestClient, incident_id: str, **header_overrides: object):
    return client.get(timeline_url(incident_id), headers=stand_in_headers(**header_overrides))


def assert_timeline_wire_shape(entry: dict[str, object]) -> None:
    assert set(entry) == TIMELINE_WIRE_KEYS
    assert "organization_id" not in entry
    assert "occurred_at" not in entry
    assert "source_kind" not in entry
    assert isinstance(entry["occurredAt"], str) and entry["occurredAt"].endswith("Z")
    assert isinstance(entry["recordedAt"], str) and entry["recordedAt"].endswith("Z")


def trusted_context() -> IncidentRequestContext:
    return IncidentRequestContext(
        organization_id=ORG,
        actor_ref=ExternalRef(owner="team1.user", id="user_synth_0007"),
        correlation_id=CORRELATION_ID,
    )


def test_create_incident_then_get_timeline_returns_one_opened_entry(client: TestClient) -> None:
    created = create_incident(client)

    response = get_timeline(client, created["id"])

    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)
    assert len(body) == 1
    assert_timeline_wire_shape(body[0])
    assert body[0]["category"] == "incident.opened"
    assert body[0]["sourceKind"] == "incident"
    assert body[0]["organizationId"] == ORG
    assert body[0]["incidentId"] == created["id"]
    assert body[0]["sourceId"] == created["id"]
    assert body[0]["label"] == "Incident opened"
    assert body[0]["detail"] == created["title"]


def test_repeat_get_returns_identical_ids_and_order(client: TestClient) -> None:
    created = create_incident(client)

    first = get_timeline(client, created["id"]).json()
    second = get_timeline(client, created["id"]).json()

    assert first == second
    assert [entry["id"] for entry in first] == [entry["id"] for entry in second]


def test_status_change_adds_status_changed_entry(client: TestClient) -> None:
    created = create_incident(client)
    status = client.post(
        f"/api/v1/incidents/{created['id']}/status",
        headers=stand_in_headers(correlation_id=CORRELATION_ID),
        json={"toStatus": "investigating", "reason": "On-call accepted the page"},
    )
    assert status.status_code == 200

    body = get_timeline(client, created["id"]).json()

    assert [entry["category"] for entry in body] == ["incident.opened", "incident.status_changed"]
    assert body[1]["sourceKind"] == "status_transition"
    assert body[1]["label"] == "Status changed from open to investigating"
    assert body[1]["detail"] == "On-call accepted the page"
    assert "auditIntent" not in body[1]
    assert all("eventType" not in entry for entry in body)


def test_assignment_does_not_add_a_timeline_event(client: TestClient) -> None:
    created = create_incident(client)
    assigned = client.patch(
        f"/api/v1/incidents/{created['id']}/assignment",
        headers=stand_in_headers(),
        json={"assignedTeamRef": {"owner": "team1.team", "id": "team_synth_payments"}},
    )
    assert assigned.status_code == 200

    body = get_timeline(client, created["id"]).json()

    assert [entry["category"] for entry in body] == ["incident.opened"]


def test_cross_organization_matches_unknown_incident_404(client: TestClient) -> None:
    created = create_incident(client)

    cross = get_timeline(client, created["id"], organization_id=OTHER_ORG)
    missing = get_timeline(client, "does-not-exist")

    assert cross.status_code == 404
    assert missing.status_code == 404
    assert cross.json()["error"]["code"] == "INCIDENT_NOT_FOUND"
    assert missing.json()["error"]["code"] == "INCIDENT_NOT_FOUND"


def test_missing_context_headers_return_400(client: TestClient) -> None:
    created = create_incident(client)
    headers = stand_in_headers()
    del headers["X-Nexora-Organization-Id"]

    response = client.get(timeline_url(created["id"]), headers=headers)

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_REQUEST_CONTEXT"


def test_manual_evidence_on_app_state_appears_in_timeline(client: TestClient) -> None:
    created = create_incident(client)
    recorded = client.app.state.evidence_service.record_manual_evidence(
        RecordManualEvidence(
            incident_id=created["id"],
            evidence_type="other",
            description="Screenshot of the checkout error.",
            source_label="Operations desk upload",
            captured_at=datetime(2026, 10, 1, 9, 14, 0, tzinfo=UTC),
            availability="unavailable",
        ),
        trusted_context(),
    )

    body = get_timeline(client, created["id"]).json()

    assert [entry["category"] for entry in body] == ["evidence.recorded", "incident.opened"]
    assert body[0]["sourceKind"] == "evidence"
    assert body[0]["sourceId"] == recorded.id
    assert body[0]["detail"] == recorded.description
    assert_timeline_wire_shape(body[0])


def test_separate_create_app_instances_have_isolated_stores(settings: Settings) -> None:
    first = create_app(settings)
    second = create_app(settings)
    with TestClient(first) as client_a, TestClient(second) as client_b:
        created = create_incident(client_a)

        visible = get_timeline(client_a, created["id"])
        isolated = get_timeline(client_b, created["id"])

        assert visible.status_code == 200
        assert isolated.status_code == 404
        assert isolated.json()["error"]["code"] == "INCIDENT_NOT_FOUND"
        assert first.state.incident_service is not second.state.incident_service
        assert first.state.timeline_service is not second.state.timeline_service


def test_rca002_injected_services_are_not_connected_to_http_app_state(client: TestClient) -> None:
    http_incident = create_incident(client)
    incidents = IncidentService(InMemoryIncidentRepository())
    evidence = EvidenceService(
        InMemoryEvidenceRepository(),
        incidents,
        content_verifier=FakeVerifier({"content_synth_0051"}),
    )
    ingestion = ObservationIngestionService(
        observation_repository(),
        RecordingHasher(),
        resolver=RecordingResolver(),
        mapper=RecordingMapper(),
        incidents=incidents,
        evidence=evidence,
        content_refs=StaticContentReferenceFactory("content_synth_0051"),
        request_contexts=ConnectorRegistrationActorFactory(),
    )
    ingestion.assess(observation(), connector_context(), authorizer())
    completed = ingestion.complete(observation(), connector_context(), authorizer())

    http_timeline = get_timeline(client, http_incident["id"]).json()
    foreign = get_timeline(client, completed.completion.incident_id)

    assert [entry["category"] for entry in http_timeline] == ["incident.opened"]
    assert all(entry["sourceId"] != completed.completion.evidence_id for entry in http_timeline)
    assert foreign.status_code == 404
    assert foreign.json()["error"]["code"] == "INCIDENT_NOT_FOUND"
    assert client.app.state.incident_service is not incidents
    assert client.app.state.evidence_service is not evidence


def test_existing_incident_and_health_routes_remain_functional(client: TestClient) -> None:
    created = create_incident(client)
    fetched = client.get(f"/api/v1/incidents/{created['id']}", headers=stand_in_headers())

    assert fetched.status_code == 200
    assert fetched.json()["id"] == created["id"]
    assert client.post("/api/v1/incidents", headers=stand_in_headers(), json=create_payload(title="Second")).status_code == 201
    assert client.get("/health").status_code == 200
    assert client.get("/api/v1/health").status_code == 200


def test_openapi_includes_timeline_get(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()
    paths = schema["paths"]

    assert TIMELINE_PATH in paths
    assert "get" in paths[TIMELINE_PATH]
    assert "post" not in paths[TIMELINE_PATH]
    assert "patch" not in paths[TIMELINE_PATH]
