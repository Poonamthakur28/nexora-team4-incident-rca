from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
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


def evidence_by_id_url(evidence_id: str) -> str:
    return f"/api/v1/evidence/{evidence_id}"


def list_incident_evidence(client: TestClient, incident_id: str, **header_overrides: str):
    return client.get(evidence_url(incident_id), headers=stand_in_headers(**header_overrides))


def get_evidence(client: TestClient, evidence_id: str, **header_overrides: str):
    return client.get(evidence_by_id_url(evidence_id), headers=stand_in_headers(**header_overrides))


def test_list_incident_evidence_returns_recorded_manual_evidence(client: TestClient) -> None:
    created = create_incident(client)
    recorded = record_manual_evidence(client, created["id"])
    assert recorded.status_code == 201

    response = list_incident_evidence(client, created["id"])

    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)
    assert len(body) == 1
    assert_evidence_wire_shape(body[0])
    assert body[0] == recorded.json()


def test_list_incident_evidence_empty_array_when_none_recorded(client: TestClient) -> None:
    created = create_incident(client)

    response = list_incident_evidence(client, created["id"])

    assert response.status_code == 200
    assert response.json() == []


def test_list_missing_and_cross_organization_incident_return_same_404(client: TestClient) -> None:
    created = create_incident(client)

    missing = list_incident_evidence(client, "does-not-exist")
    cross = list_incident_evidence(client, created["id"], organization_id=OTHER_ORG)

    assert missing.status_code == 404
    assert cross.status_code == 404
    assert missing.json()["error"]["code"] == "INCIDENT_NOT_FOUND"
    assert cross.json()["error"]["code"] == "INCIDENT_NOT_FOUND"


def test_get_evidence_returns_same_record(client: TestClient) -> None:
    created = create_incident(client)
    recorded = record_manual_evidence(client, created["id"])
    assert recorded.status_code == 201
    evidence_id = recorded.json()["id"]

    response = get_evidence(client, evidence_id)

    assert response.status_code == 200
    body = response.json()
    assert_evidence_wire_shape(body)
    assert body == recorded.json()
    assert body["id"] == evidence_id
    assert body["incidentId"] == created["id"]


def test_get_missing_and_cross_organization_evidence_return_same_404(client: TestClient) -> None:
    created = create_incident(client)
    recorded = record_manual_evidence(client, created["id"])
    assert recorded.status_code == 201
    evidence_id = recorded.json()["id"]

    missing = get_evidence(client, "does-not-exist")
    cross = get_evidence(client, evidence_id, organization_id=OTHER_ORG)

    assert missing.status_code == 404
    assert cross.status_code == 404
    assert missing.json()["error"]["code"] == "EVIDENCE_NOT_FOUND"
    assert cross.json()["error"]["code"] == "EVIDENCE_NOT_FOUND"
    assert "was not found" in missing.json()["error"]["message"]
    assert "was not found" in cross.json()["error"]["message"]
    assert "org" not in missing.json()["error"]["message"].lower()
    assert "org" not in cross.json()["error"]["message"].lower()


def test_http_list_and_get_use_app_state_evidence_service(client: TestClient) -> None:
    created = create_incident(client)
    recorded = record_manual_evidence(client, created["id"])
    assert recorded.status_code == 201
    context = IncidentRequestContext(
        organization_id=ORG,
        actor_ref=ExternalRef(owner=ACTOR_OWNER, id=ACTOR_ID),
    )

    listed = list_incident_evidence(client, created["id"]).json()
    fetched = get_evidence(client, recorded.json()["id"]).json()
    domain_listed = client.app.state.evidence_service.list_incident_evidence(created["id"], context)
    domain_fetched = client.app.state.evidence_service.get_evidence(recorded.json()["id"], context)

    assert [item["id"] for item in listed] == [item.id for item in domain_listed]
    assert fetched["id"] == domain_fetched.id
    assert client.app.state.evidence_service is client.app.state.timeline_service._evidence


def test_available_content_ref_without_verifier_returns_400_and_stores_nothing(
    client: TestClient,
) -> None:
    created = create_incident(client)

    response = record_manual_evidence(
        client,
        created["id"],
        availability="available",
        contentRef="content_synth_http_available",
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "CONTENT_REFERENCE_NOT_CONFIGURED"
    assert "not configured" in response.json()["error"]["message"].lower()
    assert "content_verifier" not in response.text
    assert list_incident_evidence(client, created["id"]).json() == []
    assert client.app.state.evidence_repository._records == {}


def test_partial_content_ref_without_verifier_returns_400_and_stores_nothing(
    client: TestClient,
) -> None:
    created = create_incident(client)

    response = record_manual_evidence(
        client,
        created["id"],
        availability="partial",
        contentRef="content_synth_http_partial",
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "CONTENT_REFERENCE_NOT_CONFIGURED"
    assert list_incident_evidence(client, created["id"]).json() == []
    assert client.app.state.evidence_repository._records == {}


def test_unavailable_without_content_ref_still_returns_201(client: TestClient) -> None:
    created = create_incident(client)

    response = record_manual_evidence(client, created["id"])

    assert response.status_code == 201
    assert response.json()["availability"] == "unavailable"
    assert response.json()["contentRef"] is None
    assert len(list_incident_evidence(client, created["id"]).json()) == 1


def test_content_ref_is_accepted_when_verifier_is_configured(settings: Settings) -> None:
    app = create_app(settings)
    accepted = "content_synth_http_verified"
    app.state.evidence_service = EvidenceService(
        app.state.evidence_repository,
        app.state.incident_service,
        content_verifier=FakeVerifier({accepted}),
    )

    with TestClient(app) as client:
        created = create_incident(client)
        response = record_manual_evidence(
            client,
            created["id"],
            availability="available",
            contentRef=accepted,
        )
        listed = list_incident_evidence(client, created["id"])

    assert response.status_code == 201
    body = response.json()
    assert body["availability"] == "available"
    assert body["contentRef"] == accepted
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()] == [body["id"]]


def test_openapi_includes_evidence_get_operations(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()
    incident_evidence = schema["paths"]["/api/v1/incidents/{incident_id}/evidence"]
    by_id = schema["paths"]["/api/v1/evidence/{evidence_id}"]

    assert "get" in incident_evidence
    assert "post" in incident_evidence
    assert "patch" not in incident_evidence
    assert "delete" not in incident_evidence
    assert "get" in by_id
    assert "post" not in by_id
    assert "patch" not in by_id
    assert "delete" not in by_id
