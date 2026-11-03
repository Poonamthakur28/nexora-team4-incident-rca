from datetime import UTC, datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from app.modules.ingestion.contracts import IncidentIntake, Observation


def provenance(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "originType": "observation",
        "provider": "synthetic-monitor",
        "sourceEventId": "evt-10001",
        "sourceAccountRef": {"owner": "synthetic-monitor", "id": "acct_synth_0001"},
        "collectorRef": {"owner": "team5.connector", "id": "conn_synth_monitor_01"},
    }
    value.update(overrides)
    return value


def observation_payload(**overrides: object) -> dict[str, object]:
    """CT-04 §8.7 example. Values are synthetic and are not a live connector payload."""
    value: dict[str, object] = {
        "source": "synthetic-monitor",
        "sourceAccountRef": {"owner": "synthetic-monitor", "id": "acct_synth_0001"},
        "sourceEventId": "evt-10001",
        "occurredAt": "2026-10-01T09:14:30Z",
        "occurredAtSupplied": None,
        "receivedAt": "2026-10-01T09:14:58Z",
        "submittedAt": "2026-10-01T09:14:59Z",
        "serviceRef": {"owner": "synthetic-monitor", "id": "checkout-api-prod"},
        "externalSeverity": "SEV2",
        "title": "Checkout API error rate above threshold",
        "description": "Synthetic monitor reported a 12% HTTP 5xx rate over 5 minutes.",
        "provenance": provenance(),
        "idempotencyKey": "idem_synth_0001",
        "correlationId": "corr-synth-0001",
    }
    value.update(overrides)
    return value


def test_ct04_observation_example_is_accepted() -> None:
    observation = Observation.model_validate(observation_payload())

    assert observation.source == "synthetic-monitor"
    assert observation.source_account_ref.owner == "synthetic-monitor"
    assert observation.source_account_ref.id == "acct_synth_0001"
    assert observation.source_event_id == "evt-10001"
    assert observation.occurred_at == datetime(2026, 10, 1, 9, 14, 30, tzinfo=UTC)
    assert observation.received_at == datetime(2026, 10, 1, 9, 14, 58, tzinfo=UTC)
    assert observation.submitted_at == datetime(2026, 10, 1, 9, 14, 59, tzinfo=UTC)
    assert observation.title == "Checkout API error rate above threshold"
    assert observation.provenance.origin_type == "observation"
    assert observation.provenance.collector_ref is not None
    assert observation.provenance.collector_ref.id == "conn_synth_monitor_01"
    assert observation.idempotency_key == "idem_synth_0001"
    assert observation.correlation_id == "corr-synth-0001"


def test_snake_case_input_is_accepted() -> None:
    payload = observation_payload()
    payload["source_event_id"] = payload.pop("sourceEventId")
    payload["idempotency_key"] = payload.pop("idempotencyKey")
    payload["occurred_at"] = payload.pop("occurredAt")

    observation = Observation.model_validate(payload)

    assert observation.source_event_id == "evt-10001"
    assert observation.idempotency_key == "idem_synth_0001"


def test_both_aliases_for_one_field_are_rejected() -> None:
    with pytest.raises(ValidationError):
        Observation.model_validate(
            observation_payload(sourceEventId="evt-10001", source_event_id="evt-10001")
        )


def test_unknown_field_is_rejected() -> None:
    with pytest.raises(ValidationError) as caught:
        Observation.model_validate(observation_payload(organizationId="org_synth_0001"))
    assert ("organizationId",) in {tuple(error["loc"]) for error in caught.value.errors()}


@pytest.mark.parametrize(
    "field",
    [
        "source",
        "sourceAccountRef",
        "sourceEventId",
        "occurredAt",
        "receivedAt",
        "title",
        "provenance",
        "idempotencyKey",
        "correlationId",
    ],
)
def test_missing_required_field_is_rejected(field: str) -> None:
    payload = observation_payload()
    del payload[field]
    with pytest.raises(ValidationError):
        Observation.model_validate(payload)


@pytest.mark.parametrize("source", ["", " ", "\n\t"])
def test_blank_source_is_rejected(source: str) -> None:
    with pytest.raises(ValidationError):
        Observation.model_validate(observation_payload(source=source))


@pytest.mark.parametrize("source_event_id", ["", " ", "\t"])
def test_blank_source_event_id_is_rejected(source_event_id: str) -> None:
    with pytest.raises(ValidationError):
        Observation.model_validate(observation_payload(sourceEventId=source_event_id))


def test_nonblank_opaque_identifiers_are_preserved_without_trimming() -> None:
    observation = Observation.model_validate(
        observation_payload(sourceEventId=" evt-10001 ", idempotencyKey=" idem_synth_0001 ")
    )
    assert observation.source_event_id == " evt-10001 "
    assert observation.idempotency_key == " idem_synth_0001 "


@pytest.mark.parametrize("idempotency_key", ["", " ", "\t"])
def test_blank_idempotency_key_is_rejected(idempotency_key: str) -> None:
    with pytest.raises(ValidationError):
        Observation.model_validate(observation_payload(idempotencyKey=idempotency_key))


def test_null_idempotency_key_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Observation.model_validate(observation_payload(idempotencyKey=None))


@pytest.mark.parametrize("correlation_id", ["", " ", "\t"])
def test_blank_correlation_id_is_rejected(correlation_id: str) -> None:
    with pytest.raises(ValidationError):
        Observation.model_validate(observation_payload(correlationId=correlation_id))


def test_title_is_trimmed_and_limited_to_255_characters() -> None:
    trimmed = Observation.model_validate(observation_payload(title="  Checkout API  "))
    assert trimmed.title == "Checkout API"
    assert Observation.model_validate(observation_payload(title="a" * 255)).title == "a" * 255
    with pytest.raises(ValidationError):
        Observation.model_validate(observation_payload(title="a" * 256))
    with pytest.raises(ValidationError):
        Observation.model_validate(observation_payload(title="   "))


def test_description_is_trimmed_and_blank_becomes_null() -> None:
    trimmed = Observation.model_validate(observation_payload(description="  useful context  "))
    assert trimmed.description == "useful context"
    blank = Observation.model_validate(observation_payload(description="  \n"))
    assert blank.description is None
    omitted = observation_payload()
    del omitted["description"]
    assert Observation.model_validate(omitted).description is None


def test_optional_fields_accept_null() -> None:
    observation = Observation.model_validate(
        observation_payload(
            occurredAtSupplied=None,
            submittedAt=None,
            serviceRef=None,
            externalSeverity=None,
            description=None,
        )
    )
    assert observation.occurred_at_supplied is None
    assert observation.submitted_at is None
    assert observation.service_ref is None
    assert observation.external_severity is None
    assert observation.description is None


def test_blank_external_severity_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Observation.model_validate(observation_payload(externalSeverity="  "))


@pytest.mark.parametrize("field", ["occurredAt", "receivedAt", "submittedAt"])
def test_naive_timestamp_is_rejected(field: str) -> None:
    with pytest.raises(ValidationError):
        Observation.model_validate(observation_payload(**{field: datetime(2026, 10, 1, 9, 14, 30)}))


def test_offset_timestamp_is_normalized_to_utc() -> None:
    offset = datetime(2026, 10, 1, 14, 44, 30, tzinfo=timezone(timedelta(hours=5, minutes=30)))
    observation = Observation.model_validate(observation_payload(occurredAt=offset))
    assert observation.occurred_at == datetime(2026, 10, 1, 9, 14, 30, tzinfo=UTC)


@pytest.mark.parametrize(
    ("owner", "account_id"),
    [("", "acct_synth_0001"), ("synthetic-monitor", " "), ("  ", "acct_synth_0001")],
)
def test_source_account_ref_requires_non_empty_owner_and_id(owner: str, account_id: str) -> None:
    with pytest.raises(ValidationError):
        Observation.model_validate(
            observation_payload(sourceAccountRef={"owner": owner, "id": account_id})
        )


def test_service_ref_blank_id_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Observation.model_validate(
            observation_payload(serviceRef={"owner": "synthetic-monitor", "id": " "})
        )


@pytest.mark.parametrize(
    ("owner", "ref_id"),
    [("", "conn_synth_monitor_01"), ("team5.connector", " ")],
)
def test_provenance_collector_ref_blank_parts_are_preserved(owner: str, ref_id: str) -> None:
    """Provenance ExternalRef parts stay as supplied. Shared ExternalRef is unchanged (D-04)."""
    observation = Observation.model_validate(
        observation_payload(
            provenance=provenance(collectorRef={"owner": owner, "id": ref_id})
        )
    )
    assert observation.provenance.collector_ref is not None
    assert observation.provenance.collector_ref.owner == owner
    assert observation.provenance.collector_ref.id == ref_id


@pytest.mark.parametrize(
    ("owner", "ref_id"),
    [("", "acct_synth_0001"), ("  ", "acct_synth_0001"), ("synthetic-monitor", "")],
)
def test_provenance_source_account_ref_blank_parts_are_preserved(owner: str, ref_id: str) -> None:
    observation = Observation.model_validate(
        observation_payload(
            provenance=provenance(sourceAccountRef={"owner": owner, "id": ref_id})
        )
    )
    assert observation.provenance.source_account_ref is not None
    assert observation.provenance.source_account_ref.owner == owner
    assert observation.provenance.source_account_ref.id == ref_id


def test_occurred_at_supplied_keeps_a_lexical_offset() -> None:
    supplied = "2026-10-01T14:44:30+05:30"
    observation = Observation.model_validate(observation_payload(occurredAtSupplied=supplied))
    assert observation.occurred_at_supplied == supplied
    assert observation.occurred_at == datetime(2026, 10, 1, 9, 14, 30, tzinfo=UTC)


def test_service_ref_rejects_blank_parts_and_source_account_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        Observation.model_validate(
            observation_payload(serviceRef={"owner": "", "id": "checkout-api-prod"})
        )
    with pytest.raises(ValidationError):
        Observation.model_validate(
            observation_payload(
                sourceAccountRef={
                    "owner": "synthetic-monitor",
                    "id": "acct_synth_0001",
                    "kind": "account",
                }
            )
        )


@pytest.mark.parametrize("origin", ["manual", "tool_execution"])
def test_non_observation_provenance_origin_is_rejected(origin: str) -> None:
    body = provenance(originType=origin)
    if origin == "manual":
        body["provider"] = None
        body["sourceEventId"] = None
        body["sourceAccountRef"] = None
    else:
        body["sourceEventId"] = None
        body["sourceAccountRef"] = None
    with pytest.raises(ValidationError) as caught:
        Observation.model_validate(observation_payload(provenance=body))
    assert any("observation" in error["msg"] for error in caught.value.errors())


def test_incident_intake_shape_is_unchanged() -> None:
    intake = IncidentIntake(
        source="manual",
        external_incident_ref=None,
        title="  not trimmed  ",
        description="  not trimmed  ",
        occurred_at="2026-10-10T07:30:00Z",
    )
    assert intake.title == "  not trimmed  "
    assert intake.description == "  not trimmed  "
    assert set(IncidentIntake.model_fields) == {
        "source",
        "external_incident_ref",
        "title",
        "description",
        "occurred_at",
    }
    with pytest.raises(ValidationError):
        IncidentIntake.model_validate(
            {
                "source": "manual",
                "title": "Checkout",
                "description": "Desk report",
                "occurredAt": "2026-10-10T07:30:00Z",
                "severity": "high",
            }
        )
