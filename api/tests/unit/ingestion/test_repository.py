import threading
from itertools import count

import pytest

from app.modules.ingestion.contracts import Observation
from app.modules.ingestion.errors import (
    IngestionConfigurationError,
    ObservationIdempotencyConflict,
)
from app.modules.ingestion.fingerprint import normalize_observation
from app.modules.ingestion.repository import InMemoryObservationRepository, ReservationResult
from tests.unit.ingestion.test_contracts import observation_payload, provenance
from tests.unit.ingestion.test_fingerprint import RecordingHasher

ORG = "org_synth_0001"
OTHER_ORG = "org_synth_9999"
_CONFLICT = "This provider event was already accepted with different content."


class IdFactory:
    def __init__(self) -> None:
        self._values = count(1)

    def __call__(self) -> str:
        return f"obs-{next(self._values)}"


def observation(**overrides: object) -> Observation:
    return Observation.model_validate(observation_payload(**overrides))


def normalized(built: Observation | None = None, organization_id: str = ORG):
    return normalize_observation(built or observation(), organization_id, RecordingHasher())


def repository(factory: IdFactory | None = None) -> InMemoryObservationRepository:
    return InMemoryObservationRepository(id_factory=factory or IdFactory())


def reserve(
    repo: InMemoryObservationRepository,
    built: Observation | None = None,
    organization_id: str = ORG,
) -> ReservationResult:
    current = built or observation()
    return repo.reserve(current, normalized(current, organization_id))


def assert_reservation_only(result: ReservationResult) -> None:
    assert not hasattr(result, "delivery_id")
    assert not hasattr(result, "receipt_status")
    assert not hasattr(result.record, "delivery_id")
    assert not hasattr(result.record, "processing_status")
    assert not hasattr(result.record, "attempt")


def test_first_insert_is_accepted() -> None:
    repo = repository()
    built = observation()

    result = reserve(repo, built)

    assert result.outcome == "accepted"
    assert result.record.observation_id == "obs-1"
    assert result.record.organization_id == ORG
    assert result.record.observation.title == built.title
    assert result.record.fingerprint_digest.startswith(b"test:")
    assert result.record.canonical_payload
    assert repo.get("obs-1", ORG) is not None
    assert_reservation_only(result)


def test_exact_duplicate_returns_the_original_reservation() -> None:
    repo = repository()
    first = reserve(repo)
    second = reserve(repo)

    assert second.outcome == "duplicate"
    assert second.record.observation_id == first.record.observation_id == "obs-1"
    assert second.record.canonical_payload == first.record.canonical_payload
    assert repo.get("obs-2", ORG) is None
    assert_reservation_only(second)


@pytest.mark.parametrize(
    "overrides",
    [
        {"idempotencyKey": "idem_other"},
        {"correlationId": "corr-other"},
        {"receivedAt": "2026-10-01T09:15:00Z"},
        {
            "provenance": provenance(
                collectorRef={"owner": "team5.connector", "id": "conn_synth_monitor_02"}
            )
        },
    ],
)
def test_excluded_metadata_change_is_a_duplicate(overrides: dict[str, object]) -> None:
    repo = repository()
    first = reserve(repo)
    second = reserve(repo, observation(**overrides))

    assert second.outcome == "duplicate"
    assert second.record.observation_id == first.record.observation_id
    assert second.record.canonical_payload == first.record.canonical_payload
    assert first.record.observation.idempotency_key == "idem_synth_0001"


def test_changed_business_payload_conflicts_and_leaves_the_original() -> None:
    repo = repository()
    first = reserve(repo)
    original_bytes = first.record.canonical_payload

    with pytest.raises(ObservationIdempotencyConflict) as caught:
        reserve(repo, observation(title="Checkout API latency above threshold"))

    assert str(caught.value) == _CONFLICT
    assert "latency" not in str(caught.value)
    assert ORG not in str(caught.value)
    assert "acct_synth_0001" not in str(caught.value)
    stored = repo.get("obs-1", ORG)
    assert stored is not None
    assert stored.observation.title == first.record.observation.title
    assert stored.canonical_payload == original_bytes
    assert repo.get("obs-2", ORG) is None


def test_same_event_in_another_organization_is_a_separate_identity() -> None:
    repo = repository()
    first = reserve(repo, organization_id=ORG)
    second = reserve(repo, organization_id=OTHER_ORG)

    assert second.outcome == "accepted"
    assert second.record.observation_id != first.record.observation_id
    assert repo.get(first.record.observation_id, OTHER_ORG) is None
    assert repo.get(second.record.observation_id, ORG) is None


def test_foreign_organization_and_missing_id_return_none() -> None:
    repo = repository()
    result = reserve(repo)

    assert repo.get(result.record.observation_id, OTHER_ORG) is None
    assert repo.get("obs-missing", ORG) is None


def test_returned_records_are_copies() -> None:
    repo = repository()
    result = reserve(repo)
    result.record.observation.title = "mutated"
    result.record.observation.provenance.provider = "mutated-provider"

    stored = repo.get("obs-1", ORG)
    assert stored is not None
    assert stored.observation.title == "Checkout API error rate above threshold"
    assert stored.observation.provenance.provider == "synthetic-monitor"


def test_separate_repository_instances_do_not_share_data() -> None:
    first = repository()
    second = repository()
    reserve(first)

    assert second.get("obs-1", ORG) is None
    assert reserve(second).outcome == "accepted"


def test_id_factory_failure_leaves_the_repository_unchanged() -> None:
    def exploding() -> str:
        raise RuntimeError("secret id sequence")

    repo = InMemoryObservationRepository(id_factory=exploding)

    with pytest.raises(IngestionConfigurationError) as caught:
        reserve(repo)

    assert str(caught.value) == "The observation id factory failed."
    assert isinstance(caught.value.__cause__, RuntimeError)
    assert "secret" not in str(caught.value)
    assert repo.get("obs-1", ORG) is None


def test_repeated_factory_id_does_not_insert_or_replace() -> None:
    issued = iter(["obs-1", "obs-1", "obs-2"])
    repo = InMemoryObservationRepository(id_factory=lambda: next(issued))
    first = reserve(repo)
    other = observation(sourceEventId="evt-other")

    with pytest.raises(IngestionConfigurationError) as caught:
        reserve(repo, other)

    assert str(caught.value) == "The observation id factory produced a repeated id."
    stored = repo.get("obs-1", ORG)
    assert stored is not None
    assert stored.observation.source_event_id == "evt-10001"
    assert stored.canonical_payload == first.record.canonical_payload
    assert repo.get("obs-2", ORG) is None

    retry = reserve(repo, other)
    assert retry.outcome == "accepted"
    assert retry.record.observation_id == "obs-2"
    original = repo.get("obs-1", ORG)
    assert original is not None
    assert original.observation.source_event_id == "evt-10001"
    assert original.canonical_payload == first.record.canonical_payload


def test_blank_factory_id_does_not_insert() -> None:
    repo = InMemoryObservationRepository(id_factory=lambda: "  ")

    with pytest.raises(IngestionConfigurationError):
        reserve(repo)

    assert repo.get("  ", ORG) is None


def test_concurrent_identical_submissions_accept_once() -> None:
    repo = repository()
    built = observation()
    ready = normalized(built)
    barrier = threading.Barrier(2)
    outcomes: list[object] = []
    guard = threading.Lock()

    def worker() -> None:
        barrier.wait()
        try:
            result = repo.reserve(built, ready)
        except Exception as exc:
            with guard:
                outcomes.append(exc)
            return
        with guard:
            outcomes.append(result)

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    kinds = sorted(
        item.outcome for item in outcomes if isinstance(item, ReservationResult)
    )
    assert kinds == ["accepted", "duplicate"]
    assert repo.get("obs-1", ORG) is not None
    assert repo.get("obs-2", ORG) is None


def test_concurrent_conflicting_submissions_accept_one() -> None:
    repo = repository()
    first = observation()
    second = observation(title="Checkout API latency above threshold")
    first_norm = normalized(first)
    second_norm = normalized(second)
    barrier = threading.Barrier(2)
    outcomes: list[object] = []
    guard = threading.Lock()

    def worker(built: Observation, ready) -> None:
        barrier.wait()
        try:
            result = repo.reserve(built, ready)
        except Exception as exc:
            with guard:
                outcomes.append(exc)
            return
        with guard:
            outcomes.append(result)

    threads = [
        threading.Thread(target=worker, args=(first, first_norm)),
        threading.Thread(target=worker, args=(second, second_norm)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    accepted = [item for item in outcomes if isinstance(item, ReservationResult)]
    conflicts = [item for item in outcomes if isinstance(item, ObservationIdempotencyConflict)]
    assert len(accepted) == 1
    assert accepted[0].outcome == "accepted"
    assert len(conflicts) == 1
    stored = repo.get("obs-1", ORG)
    assert stored is not None
    assert stored.canonical_payload == accepted[0].record.canonical_payload
    assert repo.get("obs-2", ORG) is None
