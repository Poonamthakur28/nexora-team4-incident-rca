from datetime import UTC, datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from app.modules.incidents.contracts import (
    AssignIncident,
    ChangeIncidentStatus,
    CreateIncident,
    Incident,
    IncidentAuditIntent,
    IncidentStatusChangedData,
    IncidentStatusTransition,
    IncidentSummary,
)
from app.shared.identifiers import as_external_ref, as_team4_entity_id

CREATED_AT = "2026-10-01T09:15:04Z"
UPDATED_AT = "2026-10-01T09:20:00Z"


def incident_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "id": "11111111-1111-4111-8111-000000000001",
        "organizationId": "org_synth_0001",
        "title": "Checkout API error rate above threshold",
        "description": "Synthetic monitor reported a 12% HTTP 5xx rate over 5 minutes.",
        "severity": "high",
        "status": "open",
        "serviceRef": {"owner": "service-catalog", "id": "svc_synth_checkout"},
        "assignedTeamRef": {"owner": "team1.team", "id": "team_synth_payments"},
        "assignedUserRef": None,
        "externalRefs": [{"owner": "synthetic-monitor", "id": "evt-10001"}],
        "createdAt": CREATED_AT,
        "updatedAt": CREATED_AT,
    }
    payload.update(overrides)
    return payload


def test_canonical_incident_serializes_with_camel_case_and_explicit_nulls() -> None:
    incident = Incident.model_validate(incident_payload())

    dumped = incident.model_dump(by_alias=True, mode="json")

    assert set(dumped) == {
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
    assert dumped["organizationId"] == "org_synth_0001"
    assert dumped["createdAt"] == CREATED_AT
    assert dumped["updatedAt"] == CREATED_AT
    assert dumped["assignedUserRef"] is None
    assert dumped["serviceRef"] == {"owner": "service-catalog", "id": "svc_synth_checkout"}
    assert dumped["externalRefs"] == [{"owner": "synthetic-monitor", "id": "evt-10001"}]
    assert "organization_id" not in dumped


def test_optional_references_serialize_as_null_when_absent() -> None:
    incident = Incident.model_validate(
        incident_payload(serviceRef=None, assignedTeamRef=None, assignedUserRef=None, description=None)
    )

    dumped = incident.model_dump(by_alias=True, mode="json")

    assert dumped["serviceRef"] is None
    assert dumped["assignedTeamRef"] is None
    assert dumped["assignedUserRef"] is None
    assert dumped["description"] is None
    assert dumped["externalRefs"] == [{"owner": "synthetic-monitor", "id": "evt-10001"}]


def test_unknown_fields_are_rejected() -> None:
    with pytest.raises(ValidationError) as caught:
        Incident.model_validate(incident_payload(projectId="proj_synth_0001"))

    assert any(error["type"] == "extra_forbidden" for error in caught.value.errors())


def test_create_rejects_system_managed_fields() -> None:
    with pytest.raises(ValidationError) as caught:
        CreateIncident.model_validate(
            {
                "title": "Checkout API error rate above threshold",
                "severity": "high",
                "externalRefs": [],
                "id": "11111111-1111-4111-8111-000000000001",
                "organizationId": "org_synth_0001",
                "status": "investigating",
                "createdAt": CREATED_AT,
                "updatedAt": UPDATED_AT,
            }
        )

    paths = {tuple(error["loc"]) for error in caught.value.errors()}
    assert ("id",) in paths
    assert ("organizationId",) in paths
    assert ("status",) in paths
    assert ("createdAt",) in paths
    assert ("updatedAt",) in paths


def test_status_change_rejects_a_body_supplied_actor() -> None:
    with pytest.raises(ValidationError):
        ChangeIncidentStatus.model_validate(
            {
                "toStatus": "investigating",
                "reason": "On-call engineer started investigation.",
                "actorRef": {"owner": "team1.user", "id": "user_synth_0099"},
            }
        )


def test_status_change_rejects_a_body_supplied_correlation_id() -> None:
    with pytest.raises(ValidationError) as caught:
        ChangeIncidentStatus.model_validate(
            {
                "toStatus": "investigating",
                "reason": "On-call engineer started investigation.",
                "correlationId": "corr-from-body",
            }
        )

    assert [tuple(error["loc"]) for error in caught.value.errors()] == [("correlationId",)]
    assert set(ChangeIncidentStatus.model_fields) == {"to_status", "reason"}


@pytest.mark.parametrize("incident_id", ["", "   ", "\t\n"])
def test_empty_incident_id_is_rejected(incident_id: str) -> None:
    with pytest.raises(ValidationError):
        Incident.model_validate(incident_payload(id=incident_id))


def test_non_uuid_incident_id_is_accepted_because_d01_is_not_agreed() -> None:
    incident = Incident.model_validate(incident_payload(id="inc-synthetic-1"))
    assert incident.id == "inc-synthetic-1"


@pytest.mark.parametrize("title", ["", "   ", "\n\t"])
def test_blank_title_is_rejected(title: str) -> None:
    with pytest.raises(ValidationError):
        Incident.model_validate(incident_payload(title=title))


def test_title_is_trimmed_and_limited_to_255_characters() -> None:
    accepted = Incident.model_validate(incident_payload(title=f"  {'a' * 255}  "))
    assert accepted.title == "a" * 255

    with pytest.raises(ValidationError):
        Incident.model_validate(incident_payload(title="a" * 256))


def test_blank_description_is_stored_as_null() -> None:
    incident = Incident.model_validate(incident_payload(description="   "))

    assert incident.description is None
    assert incident.model_dump(by_alias=True, mode="json")["description"] is None


@pytest.mark.parametrize("severity", ["critical", "high", "medium", "low"])
def test_severity_accepts_the_canonical_values(severity: str) -> None:
    incident = Incident.model_validate(incident_payload(severity=severity))
    assert incident.severity == severity


def test_severity_rejects_values_outside_the_canonical_set() -> None:
    with pytest.raises(ValidationError):
        Incident.model_validate(incident_payload(severity="urgent"))


@pytest.mark.parametrize("status", ["open", "investigating", "resolved", "closed"])
def test_status_accepts_the_canonical_values(status: str) -> None:
    incident = Incident.model_validate(incident_payload(status=status))
    assert incident.status == status


def test_status_rejects_values_outside_the_canonical_set() -> None:
    with pytest.raises(ValidationError):
        Incident.model_validate(incident_payload(status="confirmed"))


def test_duplicate_external_refs_are_rejected() -> None:
    with pytest.raises(ValidationError):
        Incident.model_validate(
            incident_payload(
                externalRefs=[
                    {"owner": "synthetic-monitor", "id": "evt-10001"},
                    {"owner": "synthetic-monitor", "id": "evt-10001"},
                ]
            )
        )


def test_empty_external_refs_are_allowed() -> None:
    incident = Incident.model_validate(incident_payload(externalRefs=[]))
    assert incident.external_refs == []


def test_updated_at_cannot_precede_created_at() -> None:
    with pytest.raises(ValidationError):
        Incident.model_validate(incident_payload(createdAt=UPDATED_AT, updatedAt=CREATED_AT))


def test_non_utc_offset_is_normalized_to_utc_z() -> None:
    created = datetime(2026, 10, 1, 14, 45, 4, tzinfo=timezone(timedelta(hours=5, minutes=30)))
    incident = Incident.model_validate(incident_payload(createdAt=created, updatedAt=created))

    assert incident.created_at == datetime(2026, 10, 1, 9, 15, 4, tzinfo=UTC)
    assert incident.updated_at.utcoffset() == timedelta(0)
    assert incident.model_dump(by_alias=True, mode="json")["createdAt"] == CREATED_AT


def test_transition_and_audit_intent_serialize_with_camel_case() -> None:
    occurred_at = datetime(2026, 10, 1, 9, 20, tzinfo=UTC)
    transition = IncidentStatusTransition(
        incident_id=as_team4_entity_id("11111111-1111-4111-8111-000000000001"),
        from_status="open",
        to_status="investigating",
        actor_ref=as_external_ref("team1.user", "user_synth_0007"),
        reason="  On-call engineer started investigation.  ",
        correlation_id=" corr-synth-0001 ",
        occurred_at=occurred_at,
    )
    intent = IncidentAuditIntent(
        event_id=as_team4_entity_id("99999999-9999-4999-8999-000000000007"),
        event_type="incident.status_changed",
        organization_id=" org_synth_0001 ",
        actor_ref=transition.actor_ref,
        resource_type="incident",
        resource_id=transition.incident_id,
        occurred_at=occurred_at,
        correlation_id=transition.correlation_id,
        data=IncidentStatusChangedData(
            from_status=transition.from_status,
            to_status=transition.to_status,
            reason=transition.reason,
        ),
    )

    dumped = intent.model_dump(by_alias=True, mode="json")

    assert transition.reason == "On-call engineer started investigation."
    assert transition.correlation_id == "corr-synth-0001"
    assert dumped["eventType"] == "incident.status_changed"
    assert dumped["resourceType"] == "incident"
    assert dumped["organizationId"] == "org_synth_0001"
    assert dumped["occurredAt"] == "2026-10-01T09:20:00Z"
    assert dumped["data"] == {
        "fromStatus": "open",
        "toStatus": "investigating",
        "reason": "On-call engineer started investigation.",
    }


def test_blank_transition_reason_is_rejected() -> None:
    with pytest.raises(ValidationError):
        ChangeIncidentStatus(to_status="investigating", reason="   ")


def test_assignment_input_accepts_opaque_refs_and_explicit_null() -> None:
    command = AssignIncident.model_validate(
        {
            "assignedTeamRef": {"owner": "team1.team", "id": "team_synth_payments"},
            "assignedUserRef": None,
        }
    )

    assert command.assigned_team_ref == as_external_ref("team1.team", "team_synth_payments")
    assert command.assigned_user_ref is None
    assert command.model_fields_set == {"assigned_team_ref", "assigned_user_ref"}


def test_existing_incident_summary_contract_still_allows_a_free_status() -> None:
    summary = IncidentSummary(
        id=as_team4_entity_id("summary-1"),
        title="Synthetic",
        status="not-an-enum",
        created_at=datetime(2026, 10, 1, tzinfo=UTC),
        external_refs=None,
    )

    assert summary.status == "not-an-enum"
    assert summary.external_refs is None
    assert summary.model_dump(by_alias=True)["createdAt"]
