from fastapi.testclient import TestClient

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
    ACTOR_ID,
    ACTOR_OWNER,
    ORG,
    OTHER_ORG,
    create_incident,
    stand_in_headers,
)
from tests.unit.evidence.test_service import FakeVerifier
from tests.unit.ingestion.test_fingerprint import RecordingHasher
from tests.unit.ingestion.test_repository import observation, repository as observation_repository
from tests.unit.ingestion.test_stage1_validation import authorizer, context as connector_context
from tests.unit.ingestion.test_stage2 import RecordingMapper, RecordingResolver

EVIDENCE_WIRE_KEYS = {
    "id",
    "incidentId",
    "investigationId",
    "triggeredByObservationId",
    "evidenceType",
    "description",
    "sourceLabel",
    "externalSourceRef",
    "contentRef",
    "capturedAt",
    "collectedAt",
    "availability",
    "provenance",
}


def evidence_url(incident_id: str) -> str:
    return f"/api/v1/incidents/{incident_id}/evidence"


def evidence_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "evidenceType": "other",
        "description": "Screenshot of the checkout error.",
        "sourceLabel": "Operations desk upload",
        "capturedAt": "2026-10-01T09:14:00Z",
        "availability": "unavailable",
    }
    payload.update(overrides)
    return payload


def record_manual_evidence(client: TestClient, incident_id: str, **overrides: object):
    return client.post(
        evidence_url(incident_id),
        headers=stand_in_headers(),
        json=evidence_payload(**overrides),
    )


def assert_evidence_wire_shape(body: dict[str, object]) -> None:
    assert set(body) == EVIDENCE_WIRE_KEYS
    assert "incident_id" not in body
    assert "captured_at" not in body
    assert "source_label" not in body
    assert isinstance(body["capturedAt"], str) and body["capturedAt"].endswith("Z")
    assert isinstance(body["collectedAt"], str) and body["collectedAt"].endswith("Z")


def test_record_manual_evidence_returns_201_camel_case(client: TestClient) -> None:
    created = create_incident(client)

    response = record_manual_evidence(client, created["id"])

    assert response.status_code == 201
    body = response.json()
    assert_evidence_wire_shape(body)
    assert body["incidentId"] == created["id"]
    assert body["evidenceType"] == "other"
    assert body["availability"] == "unavailable"
    assert body["contentRef"] is None
    assert body["investigationId"] is None
    assert body["triggeredByObservationId"] is None
    assert body["provenance"]["originType"] == "manual"
    assert body["provenance"]["collectorRef"] == {"owner": ACTOR_OWNER, "id": ACTOR_ID}


def test_timeline_includes_recorded_manual_evidence(client: TestClient) -> None:
    created = create_incident(client)
    recorded = record_manual_evidence(client, created["id"])
    assert recorded.status_code == 201
    evidence_id = recorded.json()["id"]

    timeline = client.get(
        f"/api/v1/incidents/{created['id']}/timeline",
        headers=stand_in_headers(),
    )

    assert timeline.status_code == 200
    evidence_entries = [entry for entry in timeline.json() if entry["category"] == "evidence.recorded"]
    assert len(evidence_entries) == 1
    assert evidence_entries[0]["sourceId"] == evidence_id
    assert evidence_entries[0]["sourceKind"] == "evidence"


def test_missing_incident_returns_404(client: TestClient) -> None:
    response = record_manual_evidence(client, "does-not-exist")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "INCIDENT_NOT_FOUND"


def test_cross_organization_matches_unknown_incident_404(client: TestClient) -> None:
    created = create_incident(client)

    cross = client.post(
        evidence_url(created["id"]),
        headers=stand_in_headers(organization_id=OTHER_ORG),
        json=evidence_payload(),
    )
    missing = record_manual_evidence(client, "does-not-exist")

    assert cross.status_code == 404
    assert missing.status_code == 404
    assert cross.json()["error"]["code"] == "INCIDENT_NOT_FOUND"
    assert missing.json()["error"]["code"] == "INCIDENT_NOT_FOUND"


def test_missing_context_headers_return_400(client: TestClient) -> None:
    created = create_incident(client)
    missing_org = stand_in_headers()
    del missing_org["X-Nexora-Organization-Id"]
    missing_actor = stand_in_headers()
    del missing_actor["X-Nexora-Actor-Id"]

    org_response = client.post(evidence_url(created["id"]), headers=missing_org, json=evidence_payload())
    actor_response = client.post(evidence_url(created["id"]), headers=missing_actor, json=evidence_payload())

    assert org_response.status_code == 400
    assert actor_response.status_code == 400
    assert org_response.json()["error"]["code"] == "INVALID_REQUEST_CONTEXT"
    assert actor_response.json()["error"]["code"] == "INVALID_REQUEST_CONTEXT"


def test_invalid_payload_and_protected_fields_return_400(client: TestClient) -> None:
    created = create_incident(client)

    invalid = record_manual_evidence(client, created["id"], description="")
    protected = record_manual_evidence(
        client,
        created["id"],
        organizationId=OTHER_ORG,
        actorRef={"owner": ACTOR_OWNER, "id": ACTOR_ID},
    )
    observation = record_manual_evidence(
        client,
        created["id"],
        originType="observation",
        triggeredByObservationId="obs-1",
    )

    assert invalid.status_code == 400
    assert protected.status_code == 400
    assert observation.status_code == 400
    assert invalid.json()["error"]["code"] == "INVALID_REQUEST"
    assert protected.json()["error"]["code"] == "INVALID_REQUEST"
    assert observation.json()["error"]["code"] == "INVALID_REQUEST"


def test_http_evidence_uses_the_same_app_state_service_as_timeline(client: TestClient) -> None:
    created = create_incident(client)
    recorded = record_manual_evidence(client, created["id"])
    assert recorded.status_code == 201
    context = IncidentRequestContext(
        organization_id=ORG,
        actor_ref=ExternalRef(owner=ACTOR_OWNER, id=ACTOR_ID),
    )

    listed = client.app.state.evidence_service.list_incident_evidence(created["id"], context)
    timeline = client.get(
        f"/api/v1/incidents/{created['id']}/timeline",
        headers=stand_in_headers(),
    ).json()

    assert [item.id for item in listed] == [recorded.json()["id"]]
    assert client.app.state.evidence_service is client.app.state.timeline_service._evidence
    assert any(entry["sourceId"] == recorded.json()["id"] for entry in timeline)


def test_rca002_injected_evidence_is_not_visible_on_http(client: TestClient) -> None:
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

    foreign = client.post(
        evidence_url(completed.completion.incident_id),
        headers=stand_in_headers(),
        json=evidence_payload(),
    )
    http_timeline = client.get(
        f"/api/v1/incidents/{http_incident['id']}/timeline",
        headers=stand_in_headers(),
    ).json()

    assert foreign.status_code == 404
    assert foreign.json()["error"]["code"] == "INCIDENT_NOT_FOUND"
    assert all(entry["sourceId"] != completed.completion.evidence_id for entry in http_timeline)
    assert client.app.state.evidence_service is not evidence
