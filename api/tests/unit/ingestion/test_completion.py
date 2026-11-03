import inspect
import threading

import pytest

from app.modules.ingestion import repository as ingestion_repository_module
from app.modules.ingestion.completion import (
    CREATED_INCIDENT_UNBOUND,
    ObservationBinding,
    ObservationCompletion,
)
from app.modules.ingestion.errors import IngestionConfigurationError
from app.modules.ingestion.normalization import build_idempotency_identity
from app.modules.ingestion.repository import InMemoryObservationRepository
from app.modules.ingestion.service import ObservationIngestionService
from tests.unit.ingestion.test_contracts import provenance
from tests.unit.ingestion.test_fingerprint import RecordingHasher
from tests.unit.ingestion.test_repository import (
    IdFactory,
    ORG,
    OTHER_ORG,
    observation,
    repository,
    reserve,
)
from tests.unit.ingestion.test_stage1_validation import authorizer, context
from tests.unit.ingestion.test_stage2 import stage2_service

INCIDENT = "inc-local-1"
EVIDENCE = "ev-local-1"
OTHER_INCIDENT = "inc-local-2"
_NOT_OWNED = "The completion claim is no longer owned."
FORBIDDEN = (
    "processing_status",
    "processingStatus",
    "completed",
    "receipt",
    "receipt_id",
    "delivery_id",
    "deliveryId",
    "attempt",
    "in_flight",
)


class CompletionWaitRepository(InMemoryObservationRepository):
    """Signals when production claim_completion is about to wait."""

    def __init__(self, *, id_factory, expected_waiters: int = 1) -> None:
        super().__init__(id_factory=id_factory)
        self.expected_waiters = expected_waiters
        self.waiters_parked = threading.Event()
        self._waiters = 0

    def _note_completion_waiter_parked(self) -> None:
        self._waiters += 1
        if self._waiters >= self.expected_waiters:
            self.waiters_parked.set()


class CompletionOverlapRepository(InMemoryObservationRepository):
    """Parks completion waiters and optionally holds a failed publisher."""

    def __init__(self, *, id_factory, hold_publication: bool = False) -> None:
        super().__init__(id_factory=id_factory)
        self.hold_publication = hold_publication
        self.first_waiter_parked = threading.Event()
        self.retry_waiter_parked = threading.Event()
        self.third_waiter_parked = threading.Event()
        self.retry_waiter_finished = threading.Event()
        self.publication_failed = threading.Event()
        self.allow_complete_return = threading.Event()
        self._waiters = 0

    def _note_completion_waiter_parked(self) -> None:
        self._waiters += 1
        if self._waiters == 1:
            self.first_waiter_parked.set()
        if self._waiters == 2:
            self.retry_waiter_parked.set()
        if self._waiters >= 3:
            self.third_waiter_parked.set()

    def _after_failed_completion_publication(self) -> None:
        self.publication_failed.set()
        if self.hold_publication:
            assert self.allow_complete_return.wait(5)


def identity_for(result, organization_id: str = ORG):
    return build_idempotency_identity(result.record.observation, organization_id)


def join_all(threads: list[threading.Thread], timeout: float = 5) -> None:
    for thread in threads:
        thread.join(timeout)
        assert not thread.is_alive()


def assert_no_public_status(*values: object) -> None:
    for value in values:
        for name in FORBIDDEN:
            assert not hasattr(value, name)


def test_new_reservation_has_no_binding() -> None:
    repo = repository()
    result = reserve(repo)

    assert result.record.binding is None
    stored = repo.get("obs-1", ORG)
    assert stored is not None
    assert stored.binding is None
    assert_no_public_status(result, result.record, stored)


def test_incident_only_binding() -> None:
    repo = repository()
    reserved = reserve(repo)
    identity = identity_for(reserved)
    claim = repo.claim_completion(identity)

    binding = repo.bind_incident(identity, INCIDENT, claim.generation)

    assert binding.incident_id == INCIDENT
    assert binding.evidence_id is None
    stored = repo.get("obs-1", ORG)
    assert stored is not None
    assert stored.binding == ObservationBinding(INCIDENT)
    assert_no_public_status(binding, stored.binding)


def test_full_binding() -> None:
    repo = repository()
    reserved = reserve(repo)
    identity = identity_for(reserved)
    claim = repo.claim_completion(identity)

    completion = repo.complete_binding(identity, INCIDENT, EVIDENCE, claim.generation)

    assert completion == ObservationCompletion(INCIDENT, EVIDENCE)
    stored = repo.get("obs-1", ORG)
    assert stored is not None
    assert stored.binding == ObservationBinding(INCIDENT, EVIDENCE)
    assert_no_public_status(completion, stored.binding)


def test_duplicate_read_returns_the_same_binding() -> None:
    repo = repository()
    first = reserve(repo)
    identity = identity_for(first)
    claim = repo.claim_completion(identity)
    repo.bind_incident(identity, INCIDENT, claim.generation)
    repo.complete_binding(identity, INCIDENT, EVIDENCE, claim.generation)

    duplicate = reserve(repo)
    again = repo.get(first.record.observation_id, ORG)
    reused = repo.claim_completion(identity)

    assert duplicate.outcome == "duplicate"
    assert duplicate.record.observation_id == first.record.observation_id
    assert duplicate.record.binding == ObservationBinding(INCIDENT, EVIDENCE)
    assert again is not None
    assert again.binding == duplicate.record.binding
    assert reused.action == "use_stored"
    assert reused.binding == duplicate.record.binding
    assert reused.generation is None


def test_organization_isolation() -> None:
    repo = repository()
    first = reserve(repo, organization_id=ORG)
    second = reserve(repo, organization_id=OTHER_ORG)
    first_identity = identity_for(first, ORG)
    second_identity = identity_for(second, OTHER_ORG)
    claim = repo.claim_completion(first_identity)
    repo.complete_binding(first_identity, INCIDENT, EVIDENCE, claim.generation)

    assert repo.get(first.record.observation_id, OTHER_ORG) is None
    other = repo.get(second.record.observation_id, OTHER_ORG)
    assert other is not None
    assert other.binding is None
    other_claim = repo.claim_completion(second_identity)
    assert other_claim.action == "run"
    assert other_claim.binding is None
    assert other_claim.generation == 0


def test_one_completion_owner_with_concurrent_waiters() -> None:
    repo = CompletionWaitRepository(id_factory=IdFactory(), expected_waiters=2)
    reserved = reserve(repo)
    identity = identity_for(reserved)
    owner = repo.claim_completion(identity)
    assert owner.action == "run"
    claims: list[object] = []
    guard = threading.Lock()

    def waiter() -> None:
        claim = repo.claim_completion(identity)
        with guard:
            claims.append(claim)

    waiters = [threading.Thread(target=waiter) for _ in range(2)]
    for thread in waiters:
        thread.start()
    assert repo.waiters_parked.wait(5)
    completion = repo.complete_binding(identity, INCIDENT, EVIDENCE, owner.generation)
    join_all(waiters)

    assert completion == ObservationCompletion(INCIDENT, EVIDENCE)
    assert len(claims) == 2
    assert all(item.action == "use_stored" for item in claims)
    assert all(item.binding == ObservationBinding(INCIDENT, EVIDENCE) for item in claims)
    assert all(item.generation is None for item in claims)


def test_failed_wave_waiter_stays_failed_when_retry_claims() -> None:
    repo = CompletionWaitRepository(id_factory=IdFactory(), expected_waiters=1)
    reserved = reserve(repo)
    identity = identity_for(reserved)
    first = repo.claim_completion(identity)
    claims: list[object] = []

    def waiter() -> None:
        claims.append(repo.claim_completion(identity))

    parked = threading.Thread(target=waiter)
    parked.start()
    assert repo.waiters_parked.wait(5)
    repo.abort_completion(identity, first.generation)
    retry = repo.claim_completion(identity)
    join_all([parked])

    assert retry.action == "run"
    assert retry.generation == 1
    assert claims[0].action == "failed"
    assert claims[0].binding is None
    stored = repo.get("obs-1", ORG)
    assert stored is not None
    assert stored.binding is None


def test_incident_only_does_not_release_waiters() -> None:
    repo = CompletionWaitRepository(id_factory=IdFactory(), expected_waiters=1)
    reserved = reserve(repo)
    identity = identity_for(reserved)
    owner = repo.claim_completion(identity)
    claims: list[object] = []

    def waiter() -> None:
        claims.append(repo.claim_completion(identity))

    parked = threading.Thread(target=waiter)
    parked.start()
    assert repo.waiters_parked.wait(5)
    repo.bind_incident(identity, INCIDENT, owner.generation)
    assert parked.is_alive()
    assert not claims
    repo.complete_binding(identity, INCIDENT, EVIDENCE, owner.generation)
    join_all([parked])

    assert claims[0].action == "use_stored"
    assert claims[0].binding == ObservationBinding(INCIDENT, EVIDENCE)


def test_incident_only_survives_abort_for_the_next_owner() -> None:
    repo = CompletionWaitRepository(id_factory=IdFactory(), expected_waiters=1)
    reserved = reserve(repo)
    identity = identity_for(reserved)
    first = repo.claim_completion(identity)
    repo.bind_incident(identity, INCIDENT, first.generation)
    claims: list[object] = []

    def waiter() -> None:
        claims.append(repo.claim_completion(identity))

    parked = threading.Thread(target=waiter)
    parked.start()
    assert repo.waiters_parked.wait(5)
    repo.abort_completion(identity, first.generation)
    retry = repo.claim_completion(identity)
    join_all([parked])

    assert claims[0].action == "failed"
    assert retry.action == "run"
    assert retry.binding == ObservationBinding(INCIDENT)
    stored = repo.get("obs-1", ORG)
    assert stored is not None
    assert stored.binding == ObservationBinding(INCIDENT)


def test_stale_abort_does_not_release_newer_generation(monkeypatch) -> None:
    original = ingestion_repository_module._with_binding

    def boom(record, binding):
        raise RuntimeError("secret copy")

    monkeypatch.setattr(ingestion_repository_module, "_with_binding", boom)
    repo = CompletionOverlapRepository(id_factory=IdFactory())
    reserved = reserve(repo)
    identity = identity_for(reserved)
    first = repo.claim_completion(identity)
    assert first.action == "run"
    assert first.generation == 0
    first_wave: list[object] = []
    retry_wave: list[object] = []
    third_wave: list[object] = []
    third_got_run = threading.Event()

    def wait_first() -> None:
        first_wave.append(repo.claim_completion(identity))

    def wait_retry() -> None:
        claim = repo.claim_completion(identity)
        retry_wave.append(claim)
        repo.retry_waiter_finished.set()

    def wait_third() -> None:
        claim = repo.claim_completion(identity)
        if claim.action == "run":
            third_got_run.set()
        third_wave.append(claim)

    first_waiter = threading.Thread(target=wait_first)
    first_waiter.start()
    assert repo.first_waiter_parked.wait(5)
    with pytest.raises(RuntimeError):
        repo.complete_binding(identity, INCIDENT, EVIDENCE, first.generation)
    join_all([first_waiter])
    assert first_wave[0].action == "failed"

    retry = repo.claim_completion(identity)
    assert retry.action == "run"
    assert retry.generation == 1
    retry_waiter = threading.Thread(target=wait_retry)
    retry_waiter.start()
    assert repo.retry_waiter_parked.wait(5)
    repo.abort_completion(identity, first.generation)
    assert not repo.retry_waiter_finished.is_set()
    assert retry_waiter.is_alive()

    third = threading.Thread(target=wait_third)
    third.start()
    assert repo.third_waiter_parked.wait(5)
    assert not third_got_run.is_set()

    monkeypatch.setattr(ingestion_repository_module, "_with_binding", original)
    stored = repo.complete_binding(identity, INCIDENT, EVIDENCE, retry.generation)
    join_all([retry_waiter, third])

    assert stored == ObservationCompletion(INCIDENT, EVIDENCE)
    assert retry_wave[0].action == "use_stored"
    assert third_wave[0].action == "use_stored"
    assert not third_got_run.is_set()
    visible = repo.get("obs-1", ORG)
    assert visible is not None
    assert visible.binding == ObservationBinding(INCIDENT, EVIDENCE)


def test_publication_failure_finally_does_not_abort_retry_claim(monkeypatch) -> None:
    original = ingestion_repository_module._with_binding
    calls = {"n": 0}

    def boom(record, binding):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("secret copy")
        return original(record, binding)

    monkeypatch.setattr(ingestion_repository_module, "_with_binding", boom)
    repo = CompletionOverlapRepository(id_factory=IdFactory(), hold_publication=True)
    reserved = reserve(repo)
    identity = identity_for(reserved)
    first = repo.claim_completion(identity)
    first_wave: list[object] = []
    retry_wave: list[object] = []
    retry_waiter_done = threading.Event()

    def wait_first() -> None:
        first_wave.append(repo.claim_completion(identity))

    def wait_retry() -> None:
        retry_wave.append(repo.claim_completion(identity))
        retry_waiter_done.set()

    first_waiter = threading.Thread(target=wait_first)
    first_waiter.start()
    assert repo.first_waiter_parked.wait(5)
    owner = threading.Thread(
        target=lambda: _complete_or_capture(repo, identity, first.generation)
    )
    owner.start()
    assert repo.publication_failed.wait(5)
    retry = repo.claim_completion(identity)
    assert retry.action == "run"
    assert retry.generation == 1
    retry_waiter = threading.Thread(target=wait_retry)
    retry_waiter.start()
    assert repo.retry_waiter_parked.wait(5)
    repo.allow_complete_return.set()
    join_all([owner, first_waiter])
    assert not retry_waiter_done.is_set()
    assert retry_waiter.is_alive()
    repo.abort_completion(identity, first.generation)
    assert retry_waiter.is_alive()
    stored = repo.complete_binding(identity, INCIDENT, EVIDENCE, retry.generation)
    join_all([retry_waiter])

    assert first_wave[0].action == "failed"
    assert stored == ObservationCompletion(INCIDENT, EVIDENCE)
    assert retry_wave[0].action == "use_stored"
    assert retry_wave[0].binding == ObservationBinding(INCIDENT, EVIDENCE)


def _complete_or_capture(repo, identity, generation) -> None:
    try:
        repo.complete_binding(identity, INCIDENT, EVIDENCE, generation)
    except RuntimeError:
        return


def test_different_identities_complete_concurrently() -> None:
    repo = repository()
    first = reserve(repo)
    second = reserve(
        repo,
        observation(
            sourceEventId="evt-10002",
            provenance=provenance(sourceEventId="evt-10002"),
            idempotencyKey="idem_synth_0002",
        ),
    )
    first_identity = identity_for(first)
    second_identity = identity_for(second)
    entered = threading.Barrier(3)
    hold = threading.Event()
    outcomes: list[ObservationCompletion] = []
    guard = threading.Lock()

    def worker(identity, incident_id: str, evidence_id: str) -> None:
        claim = repo.claim_completion(identity)
        entered.wait(5)
        assert hold.wait(5)
        completion = repo.complete_binding(
            identity, incident_id, evidence_id, claim.generation
        )
        with guard:
            outcomes.append(completion)

    threads = [
        threading.Thread(target=worker, args=(first_identity, "inc-a", "ev-a")),
        threading.Thread(target=worker, args=(second_identity, "inc-b", "ev-b")),
    ]
    for thread in threads:
        thread.start()
    entered.wait(5)
    hold.set()
    join_all(threads)

    assert {item.incident_id for item in outcomes} == {"inc-a", "inc-b"}
    assert {item.evidence_id for item in outcomes} == {"ev-a", "ev-b"}
    first_stored = repo.get(first.record.observation_id, ORG)
    second_stored = repo.get(second.record.observation_id, ORG)
    assert first_stored is not None
    assert second_stored is not None
    assert first_stored.binding == ObservationBinding("inc-a", "ev-a")
    assert second_stored.binding == ObservationBinding("inc-b", "ev-b")


def test_stage2_and_completion_generations_are_independent() -> None:
    repo = CompletionWaitRepository(id_factory=IdFactory(), expected_waiters=1)
    reserved = reserve(repo)
    identity = identity_for(reserved)
    stage2 = repo.claim_stage2(identity)
    completion = repo.claim_completion(identity)
    claims: list[object] = []

    def waiter() -> None:
        claims.append(repo.claim_completion(identity))

    parked = threading.Thread(target=waiter)
    parked.start()
    assert repo.waiters_parked.wait(5)
    repo.abort_stage2(identity, stage2.generation)
    assert parked.is_alive()
    repo.complete_binding(identity, INCIDENT, EVIDENCE, completion.generation)
    join_all([parked])

    assert claims[0].action == "use_stored"
    retry_stage2 = repo.claim_stage2(identity)
    assert retry_stage2.action == "run"
    assert retry_stage2.generation == 1
    stored = repo.get("obs-1", ORG)
    assert stored is not None
    assert stored.assessment is None
    assert stored.binding == ObservationBinding(INCIDENT, EVIDENCE)


def test_assessment_preserves_an_existing_binding() -> None:
    repo = repository()
    reserved = reserve(repo)
    identity = identity_for(reserved)
    claim = repo.claim_completion(identity)
    repo.bind_incident(identity, INCIDENT, claim.generation)
    repo.abort_completion(identity, claim.generation)

    result = stage2_service(repo).assess(observation(), context(), authorizer())

    assert result.reservation.outcome == "duplicate"
    assert result.reservation.record.binding == ObservationBinding(INCIDENT)
    stored = repo.get("obs-1", ORG)
    assert stored is not None
    assert stored.assessment is not None
    assert stored.binding == ObservationBinding(INCIDENT)


def test_accept_and_assess_still_do_not_write_a_binding() -> None:
    repo = repository()
    accepted = ObservationIngestionService(repo, RecordingHasher()).accept(
        observation(), context(), authorizer()
    )
    assessed = stage2_service(repo).assess(observation(), context(), authorizer())
    accept_src = inspect.getsource(ObservationIngestionService.accept)
    assess_src = inspect.getsource(ObservationIngestionService.assess)

    assert accepted.record.binding is None
    assert assessed.reservation.record.binding is None
    assert "claim_completion" not in accept_src
    assert "claim_completion" not in assess_src
    assert "complete_binding" not in accept_src
    assert "bind_incident" not in assess_src


def test_blank_ids_are_rejected_without_uuid_rules() -> None:
    repo = repository()
    reserved = reserve(repo)
    identity = identity_for(reserved)
    claim = repo.claim_completion(identity)

    with pytest.raises(IngestionConfigurationError, match="incident_id"):
        repo.bind_incident(identity, "  ", claim.generation)
    with pytest.raises(IngestionConfigurationError, match="evidence_id"):
        repo.complete_binding(identity, INCIDENT, "", claim.generation)
    with pytest.raises(IngestionConfigurationError, match="evidence_id"):
        ObservationCompletion("inc-1", "")

    stored = repo.get("obs-1", ORG)
    assert stored is not None
    assert stored.binding is None
    still_owned = repo.bind_incident(identity, "not-a-uuid", claim.generation)
    assert still_owned.incident_id == "not-a-uuid"


def test_incident_id_cannot_change_once_bound() -> None:
    repo = repository()
    reserved = reserve(repo)
    identity = identity_for(reserved)
    claim = repo.claim_completion(identity)
    repo.bind_incident(identity, INCIDENT, claim.generation)

    with pytest.raises(IngestionConfigurationError, match="different Incident"):
        repo.bind_incident(identity, OTHER_INCIDENT, claim.generation)
    with pytest.raises(IngestionConfigurationError, match="different Incident"):
        repo.complete_binding(identity, OTHER_INCIDENT, EVIDENCE, claim.generation)

    stored = repo.get("obs-1", ORG)
    assert stored is not None
    assert stored.binding == ObservationBinding(INCIDENT)
    completion = repo.complete_binding(identity, INCIDENT, EVIDENCE, claim.generation)
    assert completion.incident_id == INCIDENT


def test_unreserved_identity_cannot_claim_completion() -> None:
    repo = repository()
    reserved = reserve(repo)
    identity = identity_for(reserved)
    other = repository()

    with pytest.raises(IngestionConfigurationError, match="has not been reserved"):
        other.claim_completion(identity)


def test_stale_owner_cannot_bind_or_complete() -> None:
    repo = repository()
    reserved = reserve(repo)
    identity = identity_for(reserved)
    first = repo.claim_completion(identity)
    repo.abort_completion(identity, first.generation)
    retry = repo.claim_completion(identity)

    with pytest.raises(IngestionConfigurationError, match=_NOT_OWNED):
        repo.bind_incident(identity, INCIDENT, first.generation)
    with pytest.raises(IngestionConfigurationError, match=_NOT_OWNED):
        repo.complete_binding(identity, INCIDENT, EVIDENCE, first.generation)
    repo.abort_completion(identity, first.generation)

    assert retry.action == "run"
    assert retry.generation == 1
    stored = repo.bind_incident(identity, INCIDENT, retry.generation)
    assert stored.incident_id == INCIDENT


def test_bind_incident_keeps_incident_id_if_record_copy_fails(monkeypatch) -> None:
    original = ingestion_repository_module._with_binding

    def boom(record, binding):
        raise RuntimeError("secret copy")

    monkeypatch.setattr(ingestion_repository_module, "_with_binding", boom)
    repo = repository()
    reserved = reserve(repo)
    identity = identity_for(reserved)
    claim = repo.claim_completion(identity)

    with pytest.raises(RuntimeError, match="secret copy"):
        repo.bind_incident(identity, INCIDENT, claim.generation)

    stored = repo.get("obs-1", ORG)
    assert stored is not None
    assert stored.binding == ObservationBinding(INCIDENT)
    repo.abort_completion(identity, claim.generation)
    retry = repo.claim_completion(identity)
    assert retry.action == "run"
    assert retry.binding == ObservationBinding(INCIDENT)


def test_stale_remember_cannot_overwrite_recovered_incident_id() -> None:
    repo = repository()
    reserved = reserve(repo)
    identity = identity_for(reserved)
    first = repo.claim_completion(identity)
    repo.remember_created_incident(identity, INCIDENT, first.generation)
    repo.abort_completion(identity, first.generation)
    retry = repo.claim_completion(identity)

    with pytest.raises(IngestionConfigurationError, match="different Incident"):
        repo.remember_created_incident(identity, OTHER_INCIDENT, first.generation)
    repo.block_uncertain_incident_create(identity, first.generation)

    assert retry.action == "run"
    assert retry.binding == ObservationBinding(INCIDENT)
    stored = repo.get("obs-1", ORG)
    assert stored is not None
    assert stored.binding == ObservationBinding(INCIDENT)
    repo.abort_completion(identity, retry.generation)


def test_stale_remember_during_newer_owner_blocks_unbound_create() -> None:
    repo = repository()
    reserved = reserve(repo)
    identity = identity_for(reserved)
    first = repo.claim_completion(identity)
    repo.abort_completion(identity, first.generation)
    retry = repo.claim_completion(identity)

    with pytest.raises(IngestionConfigurationError, match=CREATED_INCIDENT_UNBOUND):
        repo.remember_created_incident(identity, INCIDENT, first.generation)

    with pytest.raises(IngestionConfigurationError, match=CREATED_INCIDENT_UNBOUND):
        repo.assert_can_create_incident(identity, retry.generation)
    repo.abort_completion(identity, retry.generation)


def test_completion_types_have_no_public_status_fields() -> None:
    binding = ObservationBinding(INCIDENT, EVIDENCE)
    completion = ObservationCompletion(INCIDENT, EVIDENCE)
    reserved = reserve(repository())

    assert_no_public_status(binding, completion, reserved, reserved.record)
    assert not hasattr(reserved.record, "incident_id")
    assert not hasattr(reserved.record, "evidence_id")
