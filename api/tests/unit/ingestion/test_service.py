import pytest

from app.modules.ingestion.errors import (
    IngestionConfigurationError,
    ObservationAuthorizationDenied,
    ObservationIdempotencyConflict,
)
from app.modules.ingestion.ports import InMemorySourceAccountAuthorizer
from app.modules.ingestion.service import ObservationIngestionService
from tests.unit.ingestion.test_fingerprint import RecordingHasher
from tests.unit.ingestion.test_repository import (
    IdFactory,
    ORG,
    OTHER_ORG,
    assert_reservation_only,
    observation,
    repository,
)
from tests.unit.ingestion.test_stage1_validation import (
    ACCOUNT,
    REGISTRATION,
    REPLACEMENT,
    authorizer,
    context,
)
from tests.unit.ingestion.test_contracts import provenance


def service(repo=None, hasher=None) -> ObservationIngestionService:
    return ObservationIngestionService(repo or repository(), hasher or RecordingHasher())


def test_accept_reserves_after_stage1() -> None:
    repo = repository()
    result = service(repo).accept(observation(), context(), authorizer())

    assert result.outcome == "accepted"
    assert result.record.observation_id == "obs-1"
    assert repo.get("obs-1", ORG) is not None
    assert_reservation_only(result)


def test_accept_duplicate_does_not_issue_another_id() -> None:
    ingestion = service()
    first = ingestion.accept(observation(), context(), authorizer())
    second = ingestion.accept(observation(idempotencyKey="idem_other"), context(), authorizer())

    assert second.outcome == "duplicate"
    assert second.record.observation_id == first.record.observation_id


def test_accept_conflict_does_not_reserve_a_second_row() -> None:
    repo = repository()
    ingestion = service(repo)
    first = ingestion.accept(observation(), context(), authorizer())

    with pytest.raises(ObservationIdempotencyConflict):
        ingestion.accept(
            observation(title="Checkout API latency above threshold"),
            context(),
            authorizer(),
        )

    stored = repo.get(first.record.observation_id, ORG)
    assert stored is not None
    assert stored.observation.title == first.record.observation.title
    assert repo.get("obs-2", ORG) is None


def test_stage1_denial_does_not_reserve() -> None:
    repo = repository()
    checker = authorizer()

    unauthorized = observation(
        sourceAccountRef={"owner": "synthetic-monitor", "id": "acct_synth_0099"},
        provenance=provenance(
            sourceAccountRef={"owner": "synthetic-monitor", "id": "acct_synth_0099"}
        ),
    )
    with pytest.raises(ObservationAuthorizationDenied):
        service(repo).accept(unauthorized, context(), checker)

    assert repo.get("obs-1", ORG) is None
    assert checker.calls == [(ORG, REGISTRATION.id, "acct_synth_0099")]


def test_hasher_failure_does_not_reserve() -> None:
    class RaisingHasher:
        def digest(self, canonical_payload: bytes) -> bytes:
            raise RuntimeError("secret digest key")

    repo = repository()

    with pytest.raises(IngestionConfigurationError) as caught:
        service(repo, RaisingHasher()).accept(observation(), context(), authorizer())

    assert str(caught.value) == "The payload hasher failed."
    assert "secret" not in str(caught.value)
    assert repo.get("obs-1", ORG) is None


def test_replacement_collector_is_a_duplicate_when_authorized() -> None:
    grants = InMemorySourceAccountAuthorizer(
        [(ORG, REGISTRATION, ACCOUNT), (ORG, REPLACEMENT, ACCOUNT)]
    )
    ingestion = service()
    first = ingestion.accept(observation(), context(), grants)
    replaced = observation(
        provenance=provenance(collectorRef={"owner": REPLACEMENT.owner, "id": REPLACEMENT.id})
    )

    second = ingestion.accept(replaced, context(registration=REPLACEMENT), grants)

    assert second.outcome == "duplicate"
    assert second.record.observation_id == first.record.observation_id
    stored_collector = first.record.observation.provenance.collector_ref
    assert second.record.observation.provenance.collector_ref == stored_collector


def test_other_organization_context_is_a_new_reservation() -> None:
    grants = InMemorySourceAccountAuthorizer(
        [(ORG, REGISTRATION, ACCOUNT), (OTHER_ORG, REGISTRATION, ACCOUNT)]
    )
    repo = repository()
    ingestion = service(repo)
    first = ingestion.accept(observation(), context(ORG), grants)
    second = ingestion.accept(observation(), context(OTHER_ORG), grants)

    assert second.outcome == "accepted"
    assert repo.get(first.record.observation_id, OTHER_ORG) is None


def test_service_uses_the_injected_factory() -> None:
    repo = repository(IdFactory())
    result = service(repo).accept(observation(), context(), authorizer())
    assert result.record.observation_id == "obs-1"
