from datetime import datetime, timedelta, timezone

from app.modules.ingestion.contracts import Observation
from app.modules.ingestion.fingerprint import normalize_observation
from app.modules.ingestion.normalization import (
    IdempotencyIdentity,
    build_idempotency_identity,
    canonical_business_payload,
)
from app.shared.identifiers import as_external_ref
from tests.unit.ingestion.test_contracts import observation_payload, provenance
from tests.unit.ingestion.test_fingerprint import RecordingHasher

ORG = "org_synth_0001"
ACCOUNT = as_external_ref("synthetic-monitor", "acct_synth_0001")


def observation(**overrides: object) -> Observation:
    return Observation.model_validate(observation_payload(**overrides))


def identity(
    built: Observation | None = None, organization_id: str = ORG
) -> IdempotencyIdentity:
    return build_idempotency_identity(built or observation(), organization_id)


def test_same_dimensions_produce_equal_identities() -> None:
    first = identity()
    second = identity()

    assert first == second
    assert first == IdempotencyIdentity(
        organization_id=ORG,
        source="synthetic-monitor",
        source_account_ref=ACCOUNT,
        source_event_id="evt-10001",
    )


def test_organization_change_changes_identity() -> None:
    assert identity(organization_id="org_synth_0002") != identity()


def test_source_change_changes_identity() -> None:
    assert identity(observation(source="other-monitor")) != identity()


def test_source_account_change_changes_identity() -> None:
    other = observation(sourceAccountRef={"owner": "synthetic-monitor", "id": "acct_synth_0099"})
    assert identity(other).source_account_ref.id == "acct_synth_0099"
    assert identity(other) != identity()


def test_source_event_id_change_changes_identity() -> None:
    assert identity(observation(sourceEventId="evt-other")) != identity()


def test_collector_change_does_not_change_identity() -> None:
    replaced = observation(
        provenance=provenance(
            collectorRef={"owner": "team5.connector", "id": "conn_synth_monitor_02"}
        )
    )
    assert identity(replaced) == identity()


def test_idempotency_key_change_does_not_change_identity() -> None:
    assert identity(observation(idempotencyKey="idem_other")) == identity()


def test_correlation_id_change_does_not_change_identity() -> None:
    assert identity(observation(correlationId="corr-other")) == identity()


def test_opaque_source_event_id_spaces_are_preserved() -> None:
    built = observation(sourceEventId=" evt-10001 ")
    result = identity(built)
    assert result.source_event_id == " evt-10001 "
    assert result.source_event_id != "evt-10001"


def test_identity_is_not_a_hash() -> None:
    result = identity()
    assert result.source_event_id == "evt-10001"
    assert not hasattr(result, "digest")


def test_offset_occurred_at_is_serialized_as_utc_z() -> None:
    offset = datetime(2026, 10, 1, 14, 44, 30, tzinfo=timezone(timedelta(hours=5, minutes=30)))
    built = observation(occurredAt=offset)
    payload = canonical_business_payload(built)

    assert payload["occurredAt"] == "2026-10-01T09:14:30Z"
    assert payload["occurredAt"].endswith("Z")
    assert canonical_business_payload(observation()) == payload


def test_future_occurred_at_is_accepted() -> None:
    payload = canonical_business_payload(observation(occurredAt="2099-01-01T00:00:00Z"))
    assert payload["occurredAt"] == "2099-01-01T00:00:00Z"


def test_omitted_and_null_optional_fields_match() -> None:
    omitted = observation_payload()
    del omitted["description"]
    del omitted["serviceRef"]
    del omitted["externalSeverity"]
    explicit = observation(
        description=None,
        serviceRef=None,
        externalSeverity=None,
    )

    omitted_payload = canonical_business_payload(Observation.model_validate(omitted))
    assert omitted_payload == canonical_business_payload(explicit)
    assert canonical_business_payload(explicit)["description"] is None
    assert canonical_business_payload(explicit)["serviceRef"] is None
    assert canonical_business_payload(explicit)["externalSeverity"] is None


def test_organization_is_taken_from_the_argument_not_the_body() -> None:
    hasher = RecordingHasher()
    result = normalize_observation(observation(), "org_from_context", hasher)

    assert result.identity.organization_id == "org_from_context"
    assert b"org_from_context" not in result.canonical_payload
    assert b"organizationId" not in result.canonical_payload
