import json
from datetime import datetime, timedelta, timezone

import pytest

from app.modules.ingestion.contracts import Observation
from app.modules.ingestion.errors import IngestionConfigurationError
from app.modules.ingestion.fingerprint import normalize_observation
from tests.unit.ingestion.test_contracts import observation_payload, provenance

ORG = "org_synth_0001"


class RecordingHasher:
    def __init__(self) -> None:
        self.calls: list[bytes] = []

    def digest(self, canonical_payload: bytes) -> bytes:
        self.calls.append(canonical_payload)
        return b"test:" + canonical_payload


def observation(**overrides: object) -> Observation:
    return Observation.model_validate(observation_payload(**overrides))


def normalized(
    built: Observation | None = None,
    organization_id: str = ORG,
    hasher: RecordingHasher | None = None,
) -> tuple[object, RecordingHasher]:
    checker = hasher or RecordingHasher()
    return normalize_observation(built or observation(), organization_id, checker), checker


def decoded(payload: bytes) -> dict[str, object]:
    return json.loads(payload.decode("utf-8"))


def test_identical_observations_produce_identical_canonical_bytes() -> None:
    first, hasher = normalized()
    second, _ = normalized()

    assert first.canonical_payload == second.canonical_payload
    assert first.fingerprint.digest == second.fingerprint.digest
    assert hasher.calls == [first.canonical_payload]


def test_repeated_calls_are_deterministic() -> None:
    hasher = RecordingHasher()
    first, _ = normalized(hasher=hasher)
    second, _ = normalized(hasher=hasher)

    assert first.canonical_payload == second.canonical_payload
    assert first.fingerprint == second.fingerprint
    assert hasher.calls == [first.canonical_payload, first.canonical_payload]


@pytest.mark.parametrize(
    "overrides",
    [
        {"source": "other-monitor"},
        {"sourceAccountRef": {"owner": "synthetic-monitor", "id": "acct_synth_0099"}},
        {"sourceEventId": "evt-other"},
        {"occurredAt": "2026-10-01T09:14:31Z"},
        {"serviceRef": {"owner": "synthetic-monitor", "id": "other-service"}},
        {"externalSeverity": "SEV1"},
        {"title": "Checkout API latency above threshold"},
        {"description": "A different description."},
        {"provenance": provenance(provider="other-monitor")},
        {"provenance": provenance(sourceEventId="evt-other")},
        {
            "provenance": provenance(
                sourceAccountRef={"owner": "synthetic-monitor", "id": "acct_synth_0002"}
            )
        },
    ],
)
def test_included_field_change_changes_canonical_bytes(overrides: dict[str, object]) -> None:
    baseline, _ = normalized()
    changed, hasher = normalized(observation(**overrides))

    assert changed.canonical_payload != baseline.canonical_payload
    assert changed.fingerprint.digest != baseline.fingerprint.digest
    assert hasher.calls == [changed.canonical_payload]


@pytest.mark.parametrize(
    "overrides",
    [
        {"idempotencyKey": "idem_other"},
        {"correlationId": "corr-other"},
        {"receivedAt": "2026-10-01T09:15:00Z"},
        {"submittedAt": "2026-10-01T09:15:01Z"},
        {"occurredAtSupplied": "2026-10-01T14:44:30+05:30"},
        {
            "provenance": provenance(
                collectorRef={"owner": "team5.connector", "id": "conn_synth_monitor_02"}
            )
        },
    ],
)
def test_excluded_metadata_does_not_change_canonical_bytes(overrides: dict[str, object]) -> None:
    baseline, _ = normalized()
    changed, _ = normalized(observation(**overrides))

    assert changed.canonical_payload == baseline.canonical_payload
    assert changed.fingerprint == baseline.fingerprint


def test_organization_id_is_excluded_from_the_fingerprint() -> None:
    first, _ = normalized(organization_id=ORG)
    second, _ = normalized(organization_id="org_synth_9999")

    assert first.canonical_payload == second.canonical_payload
    assert first.fingerprint == second.fingerprint
    assert first.identity != second.identity


def test_equivalent_offset_timestamps_match_and_end_with_z() -> None:
    offset = datetime(2026, 10, 1, 14, 44, 30, tzinfo=timezone(timedelta(hours=5, minutes=30)))
    zulu, _ = normalized()
    shifted, _ = normalized(observation(occurredAt=offset))

    assert shifted.canonical_payload == zulu.canonical_payload
    assert decoded(shifted.canonical_payload)["occurredAt"] == "2026-10-01T09:14:30Z"


def test_future_timestamp_is_not_rejected() -> None:
    result, _ = normalized(observation(occurredAt="2099-01-01T00:00:00Z"))
    assert decoded(result.canonical_payload)["occurredAt"] == "2099-01-01T00:00:00Z"


def test_omitted_and_null_optional_fields_have_the_same_bytes() -> None:
    omitted = observation_payload()
    del omitted["description"]
    del omitted["serviceRef"]
    del omitted["externalSeverity"]
    omitted_result, _ = normalized(Observation.model_validate(omitted))
    null_result, _ = normalized(
        observation(description=None, serviceRef=None, externalSeverity=None)
    )

    assert omitted_result.canonical_payload == null_result.canonical_payload
    body = decoded(null_result.canonical_payload)
    assert body["description"] is None
    assert body["serviceRef"] is None
    assert body["externalSeverity"] is None


def test_submitted_at_is_excluded_when_omitted_or_set() -> None:
    omitted = observation_payload()
    del omitted["submittedAt"]
    with_value, _ = normalized()
    without_value, _ = normalized(Observation.model_validate(omitted))

    assert with_value.canonical_payload == without_value.canonical_payload
    assert "submittedAt" not in decoded(with_value.canonical_payload)


def test_canonical_json_uses_sorted_camelcase_keys_without_spaces() -> None:
    result, hasher = normalized()
    text = result.canonical_payload.decode("utf-8")
    body = decoded(result.canonical_payload)

    assert "source_event_id" not in text
    assert list(body) == sorted(body)
    assert list(body["provenance"]) == sorted(body["provenance"])
    assert list(body["sourceAccountRef"]) == ["id", "owner"]
    assert list(body["serviceRef"]) == ["id", "owner"]
    assert ": " not in text
    assert ", " not in text
    assert hasher.calls == [result.canonical_payload]


def test_non_ascii_title_is_preserved_as_utf8() -> None:
    result, _ = normalized(observation(title="Erreur de paiement — 12%"))
    assert "Erreur de paiement — 12%".encode("utf-8") in result.canonical_payload
    assert b"\\u" not in result.canonical_payload


def test_opaque_source_event_id_whitespace_is_preserved() -> None:
    result, _ = normalized(observation(sourceEventId=" evt-10001 "))
    assert decoded(result.canonical_payload)["sourceEventId"] == " evt-10001 "


def test_canonical_payload_omits_delivery_and_collector_fields() -> None:
    body = decoded(normalized()[0].canonical_payload)
    assert set(body) == {
        "description",
        "externalSeverity",
        "occurredAt",
        "provenance",
        "serviceRef",
        "source",
        "sourceAccountRef",
        "sourceEventId",
        "title",
    }
    assert set(body["provenance"]) == {
        "originType",
        "provider",
        "sourceAccountRef",
        "sourceEventId",
    }


def test_hasher_exception_is_a_configuration_error() -> None:
    class RaisingHasher:
        def digest(self, canonical_payload: bytes) -> bytes:
            raise RuntimeError("secret key material")

    with pytest.raises(IngestionConfigurationError) as caught:
        normalize_observation(observation(), ORG, RaisingHasher())

    assert str(caught.value) == "The payload hasher failed."
    assert isinstance(caught.value.__cause__, RuntimeError)
    assert "secret" not in str(caught.value)


def test_non_bytes_hasher_result_is_a_configuration_error() -> None:
    class HexHasher:
        def digest(self, canonical_payload: bytes) -> object:
            return "not-bytes"

    with pytest.raises(IngestionConfigurationError) as caught:
        normalize_observation(observation(), ORG, HexHasher())

    assert str(caught.value) == "The payload hasher must return bytes."
    assert caught.value.__cause__ is None
