from datetime import UTC, datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from app.modules.evidence_collection.contracts import (
    Evidence,
    EvidenceSubmission,
    EvidenceType,
    Provenance,
    RecordManualEvidence,
    RecordObservationEventEvidence,
)
from app.shared.identifiers import as_external_ref, as_team4_entity_id


def provenance_payload(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "originType": "manual",
        "provider": None,
        "sourceEventId": None,
        "sourceAccountRef": None,
        "collectorRef": {"owner": "team1.user", "id": "user-1"},
    }
    value.update(overrides)
    return value


def evidence_payload(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "id": "evidence-1",
        "incidentId": "incident-1",
        "investigationId": None,
        "triggeredByObservationId": None,
        "evidenceType": "other",
        "description": "Responder screenshot.",
        "sourceLabel": "Operations desk",
        "externalSourceRef": None,
        "contentRef": None,
        "capturedAt": "2026-10-01T09:30:00Z",
        "collectedAt": "2026-10-01T09:31:00Z",
        "availability": "unavailable",
        "provenance": provenance_payload(),
    }
    value.update(overrides)
    return value


def test_canonical_evidence_serializes_camel_case_and_explicit_nulls() -> None:
    evidence = Evidence.model_validate(evidence_payload())

    dumped = evidence.model_dump(by_alias=True, mode="json")

    assert set(dumped) == {
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
    assert dumped["investigationId"] is None
    assert dumped["triggeredByObservationId"] is None
    assert dumped["contentRef"] is None
    assert dumped["provenance"]["collectorRef"] == {"owner": "team1.user", "id": "user-1"}


def test_unknown_fields_are_rejected_and_aliases_match_contract_model() -> None:
    with pytest.raises(ValidationError):
        Evidence.model_validate(evidence_payload(projectId="project-1"))

    snake = evidence_payload()
    snake["incident_id"] = snake.pop("incidentId")
    snake["captured_at"] = snake.pop("capturedAt")
    evidence = Evidence.model_validate(snake)
    assert evidence.incident_id == "incident-1"
    with pytest.raises(ValidationError):
        Evidence.model_validate(evidence_payload(incidentId="one", incident_id="two"))


def test_existing_evidence_submission_remains_unchanged() -> None:
    submission = EvidenceSubmission(
        incident_id=as_team4_entity_id("incident-1"),
        investigation_id=None,
        description="  Existing DTO stays unnormalized.  ",
        source_label="Existing label",
        captured_at="2026-10-01T09:30:00Z",
    )
    assert submission.description == "  Existing DTO stays unnormalized.  "
    assert "availability" not in EvidenceSubmission.model_fields


@pytest.mark.parametrize("evidence_type", ["log", "metric", "trace", "event", "other"])
def test_evidence_type_enum(evidence_type: str) -> None:
    assert Evidence.model_validate(evidence_payload(evidenceType=evidence_type)).evidence_type == evidence_type


def test_unknown_evidence_type_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Evidence.model_validate(evidence_payload(evidenceType="attachment"))


@pytest.mark.parametrize("description", ["", " ", "\n\t"])
def test_description_must_be_non_empty(description: str) -> None:
    with pytest.raises(ValidationError):
        Evidence.model_validate(evidence_payload(description=description))


def test_description_and_source_label_are_trimmed() -> None:
    evidence = Evidence.model_validate(
        evidence_payload(description="  useful context  ", sourceLabel="  Operations desk  ")
    )
    assert evidence.description == "useful context"
    assert evidence.source_label == "Operations desk"


@pytest.mark.parametrize("label", ["", " ", "a" * 256])
def test_source_label_length_is_enforced(label: str) -> None:
    with pytest.raises(ValidationError):
        Evidence.model_validate(evidence_payload(sourceLabel=label))


def test_timestamps_normalize_to_utc_and_serialize_z() -> None:
    offset = datetime(2026, 10, 1, 15, tzinfo=timezone(timedelta(hours=5, minutes=30)))
    evidence = Evidence.model_validate(evidence_payload(capturedAt=offset, collectedAt=offset))
    dumped = evidence.model_dump(by_alias=True, mode="json")
    assert evidence.captured_at == datetime(2026, 10, 1, 9, 30, tzinfo=UTC)
    assert dumped["capturedAt"] == "2026-10-01T09:30:00Z"
    assert dumped["collectedAt"] == "2026-10-01T09:30:00Z"


@pytest.mark.parametrize(
    ("availability", "content_ref", "valid"),
    [
        ("available", "content-1", True),
        ("available", None, False),
        ("partial", "content-1", True),
        ("partial", None, False),
        ("unavailable", None, True),
        ("unavailable", "content-1", False),
    ],
)
def test_availability_content_ref_shape(
    availability: str, content_ref: str | None, valid: bool
) -> None:
    if valid:
        assert Evidence.model_validate(
            evidence_payload(availability=availability, contentRef=content_ref)
        ).availability == availability
    else:
        with pytest.raises(ValidationError):
            Evidence.model_validate(evidence_payload(availability=availability, contentRef=content_ref))


def test_nonempty_opaque_content_ref_is_not_interpreted_as_a_uri() -> None:
    evidence = Evidence.model_validate(evidence_payload(contentRef="opaque-not-a-uri", availability="available"))
    assert evidence.content_ref == "opaque-not-a-uri"


def test_nonblank_content_ref_is_preserved_exactly_without_trimming() -> None:
    """L2: content_ref is opaque and must not be silently rewritten (e.g. trimmed)."""
    evidence = Evidence.model_validate(
        evidence_payload(contentRef="  padded-ref  ", availability="available")
    )
    assert evidence.content_ref == "  padded-ref  "


@pytest.mark.parametrize("availability", ["available", "partial", "unavailable"])
@pytest.mark.parametrize("blank_ref", ["", " ", "\t", "\n  "])
def test_whitespace_only_content_ref_is_rejected_for_every_availability(
    availability: str, blank_ref: str
) -> None:
    """L2: a blank content_ref must be rejected outright, never silently nulled."""
    with pytest.raises(ValidationError):
        Evidence.model_validate(evidence_payload(availability=availability, contentRef=blank_ref))


@pytest.mark.parametrize("availability", ["available", "partial", "unavailable"])
@pytest.mark.parametrize("blank_ref", ["", " ", "\t", "\n  "])
def test_manual_command_whitespace_only_content_ref_is_rejected_for_every_availability(
    availability: str, blank_ref: str
) -> None:
    payload = {
        "incidentId": "incident-1",
        "evidenceType": "other",
        "description": "Screenshot",
        "sourceLabel": "Desk",
        "capturedAt": "2026-10-01T09:30:00Z",
        "availability": availability,
        "contentRef": blank_ref,
    }
    with pytest.raises(ValidationError):
        RecordManualEvidence.model_validate(payload)


def test_valid_observation_provenance_shape() -> None:
    """Shape modelled on CT-04's observation provenance examples (e.g. F-01).

    This test validates the Provenance shape only; it does not load or assert
    against the CT-04 fixture JSON for F-01, F-15, F-18, F-21, F-23, or F-24.
    """
    provenance = Provenance.model_validate(
        {
            "originType": "observation",
            "provider": "synthetic-monitor",
            "sourceEventId": "evt-10001",
            "sourceAccountRef": {"owner": "synthetic-monitor", "id": "acct_synth_0001"},
            "collectorRef": {"owner": "team5.connector", "id": "conn_synth_monitor_01"},
        }
    )
    evidence = Evidence.model_validate(
        evidence_payload(
            evidenceType="event",
            availability="available",
            contentRef="content_synth_0001",
            externalSourceRef={"owner": "synthetic-monitor", "id": "evt-10001"},
            provenance=provenance,
        )
    )
    assert evidence.provenance == provenance


@pytest.mark.parametrize(
    "override",
    [
        {"provider": None},
        {"sourceEventId": None},
        {"sourceAccountRef": None},
        {"collectorRef": None},
    ],
)
def test_observation_provenance_requires_all_bound_fields(override: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        Provenance.model_validate(provenance_payload(originType="observation", **override))


@pytest.mark.parametrize("blank", ["", " ", "\t"])
def test_observation_provenance_rejects_blank_required_strings(blank: str) -> None:
    """L4: a blank provider or sourceEventId must be treated as missing, not accepted."""
    valid_observation: dict[str, object] = {
        "originType": "observation",
        "provider": "synthetic-monitor",
        "sourceEventId": "evt-10001",
        "sourceAccountRef": {"owner": "synthetic-monitor", "id": "acct_synth_0001"},
        "collectorRef": {"owner": "team5.connector", "id": "conn_synth_monitor_01"},
    }
    with pytest.raises(ValidationError):
        Provenance.model_validate({**valid_observation, "provider": blank})
    with pytest.raises(ValidationError):
        Provenance.model_validate({**valid_observation, "sourceEventId": blank})


def test_valid_tool_execution_provenance_shape_modelled_on_f04b() -> None:
    """Shape modelled on the CT-04 F-04b log Evidence example (contracts, not fixture JSON)."""
    provenance = Provenance.model_validate(
        {
            "originType": "tool_execution",
            "provider": "synthetic-logs",
            "sourceEventId": None,
            "sourceAccountRef": None,
            "collectorRef": {"owner": "team5.connector", "id": "conn_synth_logs_01"},
        }
    )
    evidence = Evidence.model_validate(
        evidence_payload(
            evidenceType="log",
            availability="partial",
            contentRef="content_synth_0052",
            description="Log window was truncated at 10:57Z.",
            triggeredByObservationId="33333333-3333-4333-8333-000000000005",
            provenance=provenance,
        )
    )
    assert evidence.provenance.origin_type == "tool_execution"
    assert evidence.triggered_by_observation_id == "33333333-3333-4333-8333-000000000005"


@pytest.mark.parametrize("override", [{"provider": None}, {"collectorRef": None}])
def test_tool_execution_provenance_requires_provider_and_collector(override: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        Provenance.model_validate(provenance_payload(originType="tool_execution", **override))


@pytest.mark.parametrize(
    "override",
    [
        {"sourceEventId": "evt-1"},
        {"sourceAccountRef": {"owner": "source", "id": "account"}},
        {"collectorRef": None},
    ],
)
def test_manual_provenance_rejects_connector_bound_fields(override: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        Provenance.model_validate(provenance_payload(**override))


def test_manual_provenance_allows_null_or_a_user_declared_provider_label() -> None:
    """L1: CT-04 v0.2 (line ~452) allows manual provider to be null or a user label (D-07)."""
    default = Provenance.model_validate(provenance_payload())
    assert default.provider is None

    labeled = Provenance.model_validate(provenance_payload(provider="ops-desk"))
    assert labeled.provider == "ops-desk"
    # sourceEventId and sourceAccountRef stay null for manual regardless of the label.
    assert labeled.source_event_id is None
    assert labeled.source_account_ref is None


def test_manual_provenance_provider_label_is_trimmed_and_blank_becomes_null() -> None:
    padded = Provenance.model_validate(provenance_payload(provider="  ops-desk  "))
    assert padded.provider == "ops-desk"

    blank = Provenance.model_validate(provenance_payload(provider="   "))
    assert blank.provider is None


def test_unavailable_metric_shape_and_available_requires_content_ref() -> None:
    """Shape check inspired by F-04b (unavailable metric) and F-14 (storage failure).

    This does not load or assert against either fixture's JSON.
    """
    metric = Evidence.model_validate(
        evidence_payload(
            evidenceType="metric",
            availability="unavailable",
            contentRef=None,
            provenance=provenance_payload(
                originType="tool_execution",
                provider="synthetic-metrics",
                collectorRef={"owner": "team5.connector", "id": "conn_synth_metrics_01"},
            ),
        )
    )
    assert metric.availability == "unavailable"
    with pytest.raises(ValidationError):
        Evidence.model_validate(evidence_payload(availability="available", contentRef=None))


def test_manual_command_rejects_system_managed_and_trusted_fields() -> None:
    payload = {
        "incidentId": "incident-1",
        "evidenceType": "other",
        "description": "Screenshot",
        "sourceLabel": "Desk",
        "capturedAt": "2026-10-01T09:30:00Z",
        "availability": "unavailable",
        "id": "evidence-1",
        "organizationId": "org-1",
        "collectedAt": "2026-10-01T09:31:00Z",
        "provenance": provenance_payload(),
        "actorRef": {"owner": "team1.user", "id": "forged"},
    }
    with pytest.raises(ValidationError) as caught:
        RecordManualEvidence.model_validate(payload)
    paths = {tuple(error["loc"]) for error in caught.value.errors()}
    assert {("id",), ("organizationId",), ("collectedAt",), ("provenance",), ("actorRef",)} <= paths


@pytest.mark.parametrize(
    "field",
    ["investigationId", "triggeredByObservationId"],
)
def test_manual_command_accepts_nullable_relationship_shape_until_service_rejects_non_null(field: str) -> None:
    payload = {
        "incidentId": "incident-1",
        "evidenceType": "other",
        "description": "Screenshot",
        "sourceLabel": "Desk",
        "capturedAt": "2026-10-01T09:30:00Z",
        "availability": "unavailable",
        field: "unimplemented-id",
    }
    command = RecordManualEvidence.model_validate(payload)
    assert getattr(command, "investigation_id" if field == "investigationId" else "triggered_by_observation_id")


def observation_provenance_payload(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "originType": "observation",
        "provider": "synthetic-monitor",
        "sourceEventId": "evt-10005",
        "sourceAccountRef": {"owner": "synthetic-monitor", "id": "acct_synth_0001"},
        "collectorRef": {"owner": "team5.connector", "id": "conn_synth_monitor_01"},
    }
    value.update(overrides)
    return value


def observation_command_payload(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "incidentId": "incident-1",
        "description": "All synthetic checks failing for 3 minutes.",
        "sourceLabel": "synthetic-monitor",
        "contentRef": "content_synth_0051",
        "capturedAt": "2026-10-01T11:00:00Z",
        "provenance": observation_provenance_payload(),
    }
    value.update(overrides)
    return value


def test_observation_event_command_accepts_f04a_shape() -> None:
    command = RecordObservationEventEvidence.model_validate(observation_command_payload())

    assert command.content_ref == "content_synth_0051"
    assert command.provenance.origin_type == "observation"
    assert command.provenance.source_event_id == "evt-10005"
    assert "triggered_by_observation_id" not in RecordObservationEventEvidence.model_fields
    assert "organization_id" not in RecordObservationEventEvidence.model_fields
    assert "actor_ref" not in RecordObservationEventEvidence.model_fields
    assert "evidence_type" not in RecordObservationEventEvidence.model_fields
    assert "availability" not in RecordObservationEventEvidence.model_fields


def test_observation_event_command_rejects_system_managed_and_trusted_fields() -> None:
    payload = observation_command_payload(
        id="evidence-1",
        organizationId="org-1",
        actorRef={"owner": "team1.user", "id": "forged"},
        collectedAt="2026-10-01T11:01:00Z",
        evidenceType="log",
        availability="partial",
        triggeredByObservationId="observation-1",
        investigationId="investigation-1",
    )
    with pytest.raises(ValidationError) as caught:
        RecordObservationEventEvidence.model_validate(payload)
    paths = {tuple(error["loc"]) for error in caught.value.errors()}
    assert {
        ("id",),
        ("organizationId",),
        ("actorRef",),
        ("collectedAt",),
        ("evidenceType",),
        ("availability",),
        ("triggeredByObservationId",),
        ("investigationId",),
    } <= paths


@pytest.mark.parametrize(
    "override",
    [
        {"originType": "manual", "provider": None, "sourceEventId": None, "sourceAccountRef": None},
        {"originType": "tool_execution", "sourceEventId": None, "sourceAccountRef": None},
        {"provider": None},
        {"sourceEventId": None},
    ],
)
def test_observation_event_command_rejects_invalid_provenance(override: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        RecordObservationEventEvidence.model_validate(
            observation_command_payload(provenance=observation_provenance_payload(**override))
        )


@pytest.mark.parametrize("content_ref", [None, "", "   "])
def test_observation_event_command_requires_a_non_blank_content_ref(content_ref: str | None) -> None:
    payload = observation_command_payload()
    payload["contentRef"] = content_ref
    with pytest.raises(ValidationError):
        RecordObservationEventEvidence.model_validate(payload)


def test_observation_event_command_preserves_opaque_content_ref_whitespace() -> None:
    command = RecordObservationEventEvidence.model_validate(
        observation_command_payload(contentRef="  content_synth_0051  ")
    )
    assert command.content_ref == "  content_synth_0051  "
