import inspect
import threading

import pytest

from app.modules.ingestion import repository as ingestion_repository_module
from app.modules.ingestion import service as ingestion_service_module
from app.modules.ingestion.errors import (
    IngestionConfigurationError,
    ObservationAuthorizationDenied,
    ObservationIdempotencyConflict,
)
from app.modules.ingestion.normalization import build_idempotency_identity
from app.modules.ingestion.ports import (
    InMemoryServiceResolver,
    InMemorySeverityMapper,
    SYNTHETIC_MONITOR_SEVERITY_FIXTURE_VERSION,
)
from app.modules.ingestion.repository import InMemoryObservationRepository
from app.modules.ingestion.service import IngestionResult, ObservationIngestionService
from app.modules.ingestion.stage2 import Stage2Assessment
from app.shared.identifiers import as_external_ref
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

PROVIDER_SERVICE = as_external_ref("synthetic-monitor", "checkout-api-prod")
CANONICAL_SERVICE = as_external_ref("catalog.test", "svc_checkout_api_prod")
OTHER_CANONICAL = as_external_ref("catalog.test", "svc_other")
_UNAVAILABLE = "The Stage 2 assessment could not be completed."


class RecordingResolver:
    def __init__(
        self,
        grants=None,
        *,
        hold: threading.Event | None = None,
        error: Exception | None = None,
    ) -> None:
        self._inner = InMemoryServiceResolver(grants if grants is not None else default_grants())
        self.calls: list[tuple[object, str]] = []
        self.entered = threading.Event()
        self.hold = hold
        self.error = error

    def resolve(self, provider_service_ref, organization_id):
        self.calls.append((provider_service_ref, organization_id))
        self.entered.set()
        if self.hold is not None:
            assert self.hold.wait(5)
        if self.error is not None:
            raise self.error
        return self._inner.resolve(provider_service_ref, organization_id)


class RecordingMapper:
    def __init__(
        self,
        inner=None,
        *,
        hold: threading.Event | None = None,
        error: Exception | None = None,
    ) -> None:
        self._inner = inner or InMemorySeverityMapper()
        self.calls: list[tuple[str, str | None]] = []
        self.entered = threading.Event()
        self.hold = hold
        self.error = error

    def map(self, source, external_severity):
        self.calls.append((source, external_severity))
        self.entered.set()
        if self.hold is not None:
            assert self.hold.wait(5)
        if self.error is not None:
            raise self.error
        return self._inner.map(source, external_severity)


class WaitTrackingRepository(InMemoryObservationRepository):
    """Signals when production claim_stage2 is about to wait."""

    def __init__(self, *, id_factory, expected_waiters: int) -> None:
        super().__init__(id_factory=id_factory)
        self.expected_waiters = expected_waiters
        self.waiters_parked = threading.Event()
        self._waiters = 0

    def _note_waiter_parked(self) -> None:
        self._waiters += 1
        if self._waiters >= self.expected_waiters:
            self.waiters_parked.set()


class ForcedInterrupt(BaseException):
    """Test-only BaseException so assess cleanup can be proven without SIGINT."""


def default_grants():
    return [(ORG, PROVIDER_SERVICE, CANONICAL_SERVICE)]


def stage2_service(repo=None, resolver=None, mapper=None) -> ObservationIngestionService:
    return ObservationIngestionService(
        repo or repository(),
        RecordingHasher(),
        resolver=resolver or RecordingResolver(),
        mapper=mapper or RecordingMapper(),
    )


def join_all(threads: list[threading.Thread], timeout: float = 5) -> None:
    for thread in threads:
        thread.join(timeout)
        assert not thread.is_alive()


def assert_no_completion(result: IngestionResult) -> None:
    assert not hasattr(result, "incident_id")
    assert not hasattr(result, "evidence_id")
    assert not hasattr(result, "receipt_id")
    assert not hasattr(result, "delivery_id")
    assert not hasattr(result, "attempt")
    assert not hasattr(result, "in_flight")
    assert not hasattr(result.assessment, "incident_id")
    assert not hasattr(result.assessment, "receipt_id")
    assert not hasattr(result.reservation, "delivery_id")
    assert not hasattr(result.reservation.record, "in_flight")
    assert not hasattr(result.reservation.record, "attempt")
    assert not hasattr(result.reservation.record, "completed")
    assert not hasattr(result.reservation.record, "processing_status")
    assert result.reservation.record.binding is None


def assert_ready(assessment: Stage2Assessment) -> None:
    assert assessment.kind == "ready"
    assert assessment.resolved_service_ref == CANONICAL_SERVICE
    assert assessment.mapped_severity == "high"
    assert assessment.mapping_version == SYNTHETIC_MONITOR_SEVERITY_FIXTURE_VERSION
    assert assessment.error_code is None


def assert_failure(assessment: Stage2Assessment, kind: str, error_code: str) -> None:
    assert assessment.kind == kind
    assert assessment.error_code == error_code
    assert assessment.resolved_service_ref is None
    assert assessment.mapped_severity is None
    assert assessment.mapping_version is None


def test_matching_provider_and_source_event_id_is_ready() -> None:
    repo = repository()
    result = stage2_service(repo).assess(observation(), context(), authorizer())

    assert result.reservation.outcome == "accepted"
    assert_ready(result.assessment)
    stored = repo.get("obs-1", ORG)
    assert stored is not None
    assert stored.assessment == result.assessment
    assert_no_completion(result)


def test_provider_mismatch_is_provenance_mismatch() -> None:
    resolver = RecordingResolver()
    mapper = RecordingMapper()
    built = observation(provenance=provenance(provider="other-monitor"))

    result = stage2_service(resolver=resolver, mapper=mapper).assess(
        built, context(), authorizer()
    )

    assert_failure(result.assessment, "provenance_mismatch", "PROVENANCE_MISMATCH")
    assert resolver.calls == []
    assert mapper.calls == []
    assert result.reservation.record.assessment == result.assessment


def test_provenance_source_event_id_mismatch() -> None:
    built = observation(provenance=provenance(sourceEventId="evt-99999"))

    result = stage2_service().assess(built, context(), authorizer())

    assert_failure(result.assessment, "provenance_mismatch", "PROVENANCE_MISMATCH")


def test_opaque_whitespace_in_source_event_id_is_compared_as_stored() -> None:
    padded = observation(sourceEventId=" evt-10001 ")
    assert padded.source_event_id == " evt-10001 "
    assert padded.provenance.source_event_id == "evt-10001"

    trimmed_on_both = observation(
        sourceEventId=" evt-10001 ",
        provenance=provenance(sourceEventId=" evt-10001 "),
    )
    assert trimmed_on_both.source_event_id == " evt-10001 "
    assert trimmed_on_both.provenance.source_event_id == "evt-10001"

    first = stage2_service().assess(padded, context(), authorizer())
    second = stage2_service().assess(trimmed_on_both, context(), authorizer())

    assert_failure(first.assessment, "provenance_mismatch", "PROVENANCE_MISMATCH")
    assert_failure(second.assessment, "provenance_mismatch", "PROVENANCE_MISMATCH")


def test_stage1_collector_or_account_mismatch_never_reaches_stage2() -> None:
    repo = repository()
    resolver = RecordingResolver()
    mapper = RecordingMapper()
    ingestion = stage2_service(repo, resolver, mapper)
    collector = observation(
        provenance=provenance(collectorRef={"owner": "team5.connector", "id": "conn_synth_monitor_99"})
    )
    account = observation(
        provenance=provenance(sourceAccountRef={"owner": "synthetic-monitor", "id": "acct_synth_0002"})
    )

    with pytest.raises(ObservationAuthorizationDenied):
        ingestion.assess(collector, context(), authorizer())
    with pytest.raises(ObservationAuthorizationDenied):
        ingestion.assess(account, context(), authorizer())

    assert resolver.calls == []
    assert mapper.calls == []
    assert repo.get("obs-1", ORG) is None


@pytest.mark.parametrize(
    "built, grants",
    [
        (observation(serviceRef=None), default_grants()),
        (
            observation(serviceRef={"owner": "synthetic-monitor", "id": "unknown-service"}),
            default_grants(),
        ),
        (observation(), [(OTHER_ORG, PROVIDER_SERVICE, CANONICAL_SERVICE)]),
        (
            observation(),
            [
                (ORG, PROVIDER_SERVICE, CANONICAL_SERVICE),
                (ORG, PROVIDER_SERVICE, OTHER_CANONICAL),
            ],
        ),
    ],
)
def test_missing_unknown_cross_org_and_ambiguous_services_are_unresolved(built, grants) -> None:
    resolver = RecordingResolver(grants)
    mapper = RecordingMapper()

    result = stage2_service(resolver=resolver, mapper=mapper).assess(
        built, context(), authorizer()
    )

    assert_failure(result.assessment, "service_unresolved", "SERVICE_UNRESOLVED")
    assert mapper.calls == []
    assert ORG not in str(result.assessment.error_code)
    assert "unknown-service" not in str(result.assessment.error_code)


def test_known_mock_service_maps_to_canonical_ref() -> None:
    resolver = RecordingResolver()

    result = stage2_service(resolver=resolver).assess(observation(), context(), authorizer())

    assert_ready(result.assessment)
    assert result.assessment.resolved_service_ref == CANONICAL_SERVICE
    assert result.assessment.resolved_service_ref != PROVIDER_SERVICE
    assert resolver.calls == [(PROVIDER_SERVICE, ORG)]


def test_service_resolution_failure_does_not_call_severity_mapper() -> None:
    mapper = RecordingMapper()
    built = observation(serviceRef=None)

    result = stage2_service(mapper=mapper).assess(built, context(), authorizer())

    assert_failure(result.assessment, "service_unresolved", "SERVICE_UNRESOLVED")
    assert mapper.calls == []


@pytest.mark.parametrize(
    "external, severity",
    [("SEV1", "critical"), ("SEV2", "high"), ("SEV3", "medium"), ("SEV4", "low")],
)
def test_known_fixture_severity_mapping(external: str, severity: str) -> None:
    result = stage2_service().assess(
        observation(externalSeverity=external), context(), authorizer()
    )

    assert result.assessment.kind == "ready"
    assert result.assessment.mapped_severity == severity
    assert result.assessment.mapping_version == SYNTHETIC_MONITOR_SEVERITY_FIXTURE_VERSION


@pytest.mark.parametrize("external", [None, "SEV9", "critical"])
def test_missing_or_unknown_severity_has_no_default(external: str | None) -> None:
    mapper = RecordingMapper()

    result = stage2_service(mapper=mapper).assess(
        observation(externalSeverity=external), context(), authorizer()
    )

    assert_failure(result.assessment, "severity_unmapped", "SEVERITY_UNMAPPED")
    assert mapper.calls == [("synthetic-monitor", external)]


def test_resolver_exception_leaves_reservation_and_empty_assessment() -> None:
    repo = repository()
    resolver = RecordingResolver(error=RuntimeError("secret catalog"))
    ingestion = stage2_service(repo, resolver, RecordingMapper())

    with pytest.raises(IngestionConfigurationError) as caught:
        ingestion.assess(observation(), context(), authorizer())

    assert str(caught.value) == "The service resolver failed."
    assert "secret" not in str(caught.value)
    stored = repo.get("obs-1", ORG)
    assert stored is not None
    assert stored.assessment is None


def test_mapper_exception_leaves_reservation_and_empty_assessment() -> None:
    repo = repository()
    mapper = RecordingMapper(error=RuntimeError("secret mapping table"))
    ingestion = stage2_service(repo, RecordingResolver(), mapper)

    with pytest.raises(IngestionConfigurationError) as caught:
        ingestion.assess(observation(), context(), authorizer())

    assert str(caught.value) == "The severity mapper failed."
    assert "secret" not in str(caught.value)
    stored = repo.get("obs-1", ORG)
    assert stored is not None
    assert stored.assessment is None


def test_later_independent_retry_after_dependency_failure() -> None:
    repo = repository()
    failing = stage2_service(repo, RecordingResolver(error=RuntimeError("down")), RecordingMapper())

    with pytest.raises(IngestionConfigurationError):
        failing.assess(observation(), context(), authorizer())

    retry = stage2_service(repo, RecordingResolver(), RecordingMapper())
    result = retry.assess(observation(), context(), authorizer())

    assert result.reservation.outcome == "duplicate"
    assert result.reservation.record.observation_id == "obs-1"
    assert_ready(result.assessment)


def test_duplicate_after_ready_assessment_does_not_rerun_dependencies() -> None:
    resolver = RecordingResolver()
    mapper = RecordingMapper()
    ingestion = stage2_service(resolver=resolver, mapper=mapper)
    first = ingestion.assess(observation(), context(), authorizer())

    second = ingestion.assess(
        observation(idempotencyKey="idem_other"), context(), authorizer()
    )

    assert second.reservation.outcome == "duplicate"
    assert second.assessment == first.assessment
    assert_ready(second.assessment)
    assert len(resolver.calls) == 1
    assert len(mapper.calls) == 1


def test_duplicate_after_domain_failure_returns_same_failure() -> None:
    resolver = RecordingResolver([])
    mapper = RecordingMapper()
    ingestion = stage2_service(resolver=resolver, mapper=mapper)
    first = ingestion.assess(observation(), context(), authorizer())

    second = ingestion.assess(observation(), context(), authorizer())

    assert_failure(first.assessment, "service_unresolved", "SERVICE_UNRESOLVED")
    assert second.assessment == first.assessment
    assert len(resolver.calls) == 1
    assert mapper.calls == []


def test_two_concurrent_identical_requests_one_assessor_one_waiter() -> None:
    hold = threading.Event()
    resolver = RecordingResolver(hold=hold)
    mapper = RecordingMapper()
    repo = WaitTrackingRepository(id_factory=IdFactory(), expected_waiters=1)
    ingestion = stage2_service(repo, resolver, mapper)
    outcomes: list[object] = []
    guard = threading.Lock()

    def worker() -> None:
        try:
            result = ingestion.assess(observation(), context(), authorizer())
        except Exception as exc:
            with guard:
                outcomes.append(exc)
            return
        with guard:
            outcomes.append(result)

    assessor = threading.Thread(target=worker)
    waiter = threading.Thread(target=worker)
    assessor.start()
    assert resolver.entered.wait(5)
    waiter.start()
    assert repo.waiters_parked.wait(5)
    hold.set()
    join_all([assessor, waiter])

    results = [item for item in outcomes if isinstance(item, IngestionResult)]
    assert len(results) == 2
    assert {item.reservation.outcome for item in results} == {"accepted", "duplicate"}
    assert results[0].assessment == results[1].assessment
    assert_ready(results[0].assessment)
    assert len(resolver.calls) == 1
    assert len(mapper.calls) == 1


def test_concurrent_duplicates_after_domain_failure() -> None:
    resolver = RecordingResolver([])
    mapper = RecordingMapper()
    ingestion = stage2_service(resolver=resolver, mapper=mapper)
    first = ingestion.assess(observation(), context(), authorizer())
    barrier = threading.Barrier(2)
    outcomes: list[IngestionResult] = []
    guard = threading.Lock()

    def worker() -> None:
        barrier.wait()
        result = ingestion.assess(observation(), context(), authorizer())
        with guard:
            outcomes.append(result)

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for thread in threads:
        thread.start()
    join_all(threads)

    assert_failure(first.assessment, "service_unresolved", "SERVICE_UNRESOLVED")
    assert [item.assessment for item in outcomes] == [first.assessment, first.assessment]
    assert len(resolver.calls) == 1
    assert mapper.calls == []


def test_concurrent_waiters_after_configuration_failure_receive_configuration_errors() -> None:
    hold = threading.Event()
    resolver = RecordingResolver(hold=hold, error=RuntimeError("secret catalog"))
    repo = WaitTrackingRepository(id_factory=IdFactory(), expected_waiters=2)
    ingestion = stage2_service(repo, resolver, RecordingMapper())
    outcomes: list[object] = []
    guard = threading.Lock()

    def worker() -> None:
        try:
            result = ingestion.assess(observation(), context(), authorizer())
        except Exception as exc:
            with guard:
                outcomes.append(exc)
            return
        with guard:
            outcomes.append(result)

    assessor = threading.Thread(target=worker)
    waiters = [threading.Thread(target=worker) for _ in range(2)]
    assessor.start()
    assert resolver.entered.wait(5)
    for waiter in waiters:
        waiter.start()
    assert repo.waiters_parked.wait(5)
    hold.set()
    join_all([assessor, *waiters])

    errors = [item for item in outcomes if isinstance(item, IngestionConfigurationError)]
    assert len(errors) == 3
    waiter_messages = {str(item) for item in errors}
    assert "The service resolver failed." in waiter_messages
    assert _UNAVAILABLE in waiter_messages
    assert all("secret" not in str(item) for item in errors)
    stored = repo.get("obs-1", ORG)
    assert stored is not None
    assert stored.assessment is None


def test_later_request_can_retry_after_configuration_failure() -> None:
    repo = repository()
    failing = stage2_service(repo, RecordingResolver(error=RuntimeError("down")), RecordingMapper())
    with pytest.raises(IngestionConfigurationError):
        failing.assess(observation(), context(), authorizer())

    result = stage2_service(repo).assess(observation(), context(), authorizer())
    assert_ready(result.assessment)
    assert result.reservation.outcome == "duplicate"


def test_different_identities_assess_concurrently() -> None:
    entered = threading.Barrier(3)
    hold = threading.Event()

    class ConcurrentResolver(RecordingResolver):
        def resolve(self, provider_service_ref, organization_id):
            self.calls.append((provider_service_ref, organization_id))
            entered.wait(5)
            assert hold.wait(5)
            return self._inner.resolve(provider_service_ref, organization_id)

    resolver = ConcurrentResolver()
    mapper = RecordingMapper()
    ingestion = stage2_service(resolver=resolver, mapper=mapper)
    first = observation()
    second = observation(
        sourceEventId="evt-10002",
        provenance=provenance(sourceEventId="evt-10002"),
        idempotencyKey="idem_synth_0002",
    )
    outcomes: list[IngestionResult] = []
    guard = threading.Lock()
    start = threading.Barrier(2)

    def worker(built) -> None:
        start.wait()
        result = ingestion.assess(built, context(), authorizer())
        with guard:
            outcomes.append(result)

    threads = [
        threading.Thread(target=worker, args=(first,)),
        threading.Thread(target=worker, args=(second,)),
    ]
    for thread in threads:
        thread.start()
    entered.wait(5)
    hold.set()
    join_all(threads)

    assert len(resolver.calls) == 2
    assert {item.reservation.record.observation.source_event_id for item in outcomes} == {
        "evt-10001",
        "evt-10002",
    }
    assert all(item.assessment.kind == "ready" for item in outcomes)


def test_conflict_never_enters_stage2() -> None:
    resolver = RecordingResolver()
    mapper = RecordingMapper()
    ingestion = stage2_service(resolver=resolver, mapper=mapper)
    first = ingestion.assess(observation(), context(), authorizer())

    with pytest.raises(ObservationIdempotencyConflict):
        ingestion.assess(
            observation(title="Checkout API latency above threshold"),
            context(),
            authorizer(),
        )

    assert len(resolver.calls) == 1
    assert len(mapper.calls) == 1
    stored = first.reservation.record
    assert stored.assessment == first.assessment
    assert_ready(first.assessment)


def test_unexpected_exception_releases_waiters_and_leaves_no_assessment(monkeypatch) -> None:
    hold = threading.Event()
    entered = threading.Event()

    def boom(*_args, **_kwargs):
        entered.set()
        assert hold.wait(5)
        raise RuntimeError("secret boom")

    monkeypatch.setattr(ingestion_service_module, "evaluate_stage2", boom)
    repo = WaitTrackingRepository(id_factory=IdFactory(), expected_waiters=1)
    ingestion = stage2_service(repo)
    outcomes: list[object] = []
    guard = threading.Lock()

    def worker() -> None:
        try:
            result = ingestion.assess(observation(), context(), authorizer())
        except Exception as exc:
            with guard:
                outcomes.append(exc)
            return
        with guard:
            outcomes.append(result)

    assessor = threading.Thread(target=worker)
    waiter = threading.Thread(target=worker)
    assessor.start()
    assert entered.wait(5)
    waiter.start()
    assert repo.waiters_parked.wait(5)
    hold.set()
    join_all([assessor, waiter])

    errors = [item for item in outcomes if isinstance(item, IngestionConfigurationError)]
    assert len(errors) == 2
    assert all(str(item) == _UNAVAILABLE for item in errors)
    assert all("secret" not in str(item) for item in errors)
    stored = repo.get("obs-1", ORG)
    assert stored is not None
    assert stored.assessment is None


def test_no_incident_evidence_receipt_or_attempt_is_created() -> None:
    result = stage2_service().assess(observation(), context(), authorizer())
    accept_src = inspect.getsource(ObservationIngestionService.accept)
    assess_src = inspect.getsource(ObservationIngestionService.assess)

    assert_no_completion(result)
    assert "create_incident" not in accept_src
    assert "create_incident" not in assess_src
    assert "record_observation_event_evidence" not in accept_src
    assert "record_observation_event_evidence" not in assess_src


def test_empty_severity_mapper_table_stays_unmapped() -> None:
    mapper = InMemorySeverityMapper({})
    assert mapper.map("synthetic-monitor", "SEV2").mapped is False

    result = stage2_service(mapper=mapper).assess(observation(), context(), authorizer())

    assert_failure(result.assessment, "severity_unmapped", "SEVERITY_UNMAPPED")


def test_complete_stage2_publication_failure_releases_parked_waiter(monkeypatch) -> None:
    original = ingestion_repository_module._with_assessment
    calls = {"n": 0}

    def boom(record, assessment):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("secret copy")
        return original(record, assessment)

    monkeypatch.setattr(ingestion_repository_module, "_with_assessment", boom)
    hold = threading.Event()
    resolver = RecordingResolver(hold=hold)
    repo = WaitTrackingRepository(id_factory=IdFactory(), expected_waiters=1)
    ingestion = stage2_service(repo, resolver, RecordingMapper())
    outcomes: list[object] = []
    guard = threading.Lock()

    def worker() -> None:
        try:
            result = ingestion.assess(observation(), context(), authorizer())
        except BaseException as exc:
            with guard:
                outcomes.append(exc)
            return
        with guard:
            outcomes.append(result)

    assessor = threading.Thread(target=worker)
    waiter = threading.Thread(target=worker)
    assessor.start()
    assert resolver.entered.wait(5)
    waiter.start()
    assert repo.waiters_parked.wait(5)
    hold.set()
    join_all([assessor, waiter])

    assert any(isinstance(item, RuntimeError) and "secret copy" in str(item) for item in outcomes)
    waiter_errors = [item for item in outcomes if isinstance(item, IngestionConfigurationError)]
    assert waiter_errors
    assert all(str(item) == _UNAVAILABLE for item in waiter_errors)
    stored = repo.get("obs-1", ORG)
    assert stored is not None
    assert stored.assessment is None

    retry = ingestion.assess(observation(), context(), authorizer())
    assert_ready(retry.assessment)
    assert retry.reservation.outcome == "duplicate"


def test_failed_wave_waiters_stay_failed_when_retry_overlaps() -> None:
    fail_hold = threading.Event()
    retry_hold = threading.Event()
    failing_resolver = RecordingResolver(hold=fail_hold, error=RuntimeError("down"))
    retry_resolver = RecordingResolver(hold=retry_hold)
    repo = WaitTrackingRepository(id_factory=IdFactory(), expected_waiters=1)
    failing = stage2_service(repo, failing_resolver, RecordingMapper())
    retrying = stage2_service(repo, retry_resolver, RecordingMapper())
    outcomes: list[tuple[str, object]] = []
    guard = threading.Lock()

    def capture(label: str, service: ObservationIngestionService) -> None:
        try:
            result = service.assess(observation(), context(), authorizer())
        except Exception as exc:
            with guard:
                outcomes.append((label, exc))
            return
        with guard:
            outcomes.append((label, result))

    assessor = threading.Thread(target=capture, args=("assessor", failing))
    waiter = threading.Thread(target=capture, args=("waiter", failing))
    retry = threading.Thread(target=capture, args=("retry", retrying))
    assessor.start()
    assert failing_resolver.entered.wait(5)
    waiter.start()
    assert repo.waiters_parked.wait(5)
    fail_hold.set()
    join_all([assessor])
    retry.start()
    assert retry_resolver.entered.wait(5)
    join_all([waiter])
    retry_hold.set()
    join_all([retry])

    by_label = {label: value for label, value in outcomes}
    assert isinstance(by_label["assessor"], IngestionConfigurationError)
    assert isinstance(by_label["waiter"], IngestionConfigurationError)
    assert str(by_label["waiter"]) == _UNAVAILABLE
    assert isinstance(by_label["retry"], IngestionResult)
    assert_ready(by_label["retry"].assessment)


def test_claim_after_abort_does_not_capture_failed_wave_waiters() -> None:
    repo = WaitTrackingRepository(id_factory=IdFactory(), expected_waiters=1)
    reserved = reserve(repo)
    identity = build_idempotency_identity(reserved.record.observation, ORG)
    first = repo.claim_stage2(identity)
    assert first.action == "run"
    assert first.generation == 0
    claims: list[object] = []

    def waiter() -> None:
        claims.append(repo.claim_stage2(identity))

    parked = threading.Thread(target=waiter)
    parked.start()
    assert repo.waiters_parked.wait(5)
    repo.abort_stage2(identity, first.generation)
    retry = repo.claim_stage2(identity)
    join_all([parked])

    assert retry.action == "run"
    assert retry.generation == 1
    assert claims[0].action == "failed"
    stored = repo.get("obs-1", ORG)
    assert stored is not None
    assert stored.assessment is None


def test_baseexception_during_evaluate_releases_waiters(monkeypatch) -> None:
    hold = threading.Event()
    entered = threading.Event()

    def boom(*_args, **_kwargs):
        entered.set()
        assert hold.wait(5)
        raise ForcedInterrupt("secret boom")

    monkeypatch.setattr(ingestion_service_module, "evaluate_stage2", boom)
    repo = WaitTrackingRepository(id_factory=IdFactory(), expected_waiters=1)
    ingestion = stage2_service(repo)
    outcomes: list[object] = []
    guard = threading.Lock()

    def worker() -> None:
        try:
            result = ingestion.assess(observation(), context(), authorizer())
        except BaseException as exc:
            with guard:
                outcomes.append(exc)
            return
        with guard:
            outcomes.append(result)

    assessor = threading.Thread(target=worker)
    waiter = threading.Thread(target=worker)
    assessor.start()
    assert entered.wait(5)
    waiter.start()
    assert repo.waiters_parked.wait(5)
    hold.set()
    join_all([assessor, waiter])

    assert any(isinstance(item, ForcedInterrupt) for item in outcomes)
    waiter_errors = [item for item in outcomes if isinstance(item, IngestionConfigurationError)]
    assert waiter_errors
    assert all(str(item) == _UNAVAILABLE for item in waiter_errors)
    assert all("secret" not in str(item) for item in waiter_errors)
    stored = repo.get("obs-1", ORG)
    assert stored is not None
    assert stored.assessment is None

    monkeypatch.undo()
    retry = stage2_service(repo).assess(observation(), context(), authorizer())
    assert_ready(retry.assessment)


def _ready_assessment() -> Stage2Assessment:
    return Stage2Assessment(
        kind="ready",
        resolved_service_ref=CANONICAL_SERVICE,
        mapped_severity="high",
        mapping_version=SYNTHETIC_MONITOR_SEVERITY_FIXTURE_VERSION,
        error_code=None,
    )


class PublicationOverlapRepository(InMemoryObservationRepository):
    """Parks waiters and optionally holds a failed publisher until a retry claims."""

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

    def _note_waiter_parked(self) -> None:
        self._waiters += 1
        if self._waiters == 1:
            self.first_waiter_parked.set()
        if self._waiters == 2:
            self.retry_waiter_parked.set()
        if self._waiters >= 3:
            self.third_waiter_parked.set()

    def _after_failed_publication(self) -> None:
        self.publication_failed.set()
        if self.hold_publication:
            assert self.allow_complete_return.wait(5)


def test_stale_abort_does_not_release_newer_generation(monkeypatch) -> None:
    original = ingestion_repository_module._with_assessment

    def boom(record, assessment):
        raise RuntimeError("secret copy")

    monkeypatch.setattr(ingestion_repository_module, "_with_assessment", boom)
    repo = PublicationOverlapRepository(id_factory=IdFactory())
    reserved = reserve(repo)
    identity = build_idempotency_identity(reserved.record.observation, ORG)
    first = repo.claim_stage2(identity)
    assert first.action == "run"
    assert first.generation == 0
    first_wave: list[object] = []
    retry_wave: list[object] = []
    third_wave: list[object] = []
    third_got_run = threading.Event()

    def wait_first() -> None:
        first_wave.append(repo.claim_stage2(identity))

    def wait_retry() -> None:
        claim = repo.claim_stage2(identity)
        retry_wave.append(claim)
        repo.retry_waiter_finished.set()

    def wait_third() -> None:
        claim = repo.claim_stage2(identity)
        if claim.action == "run":
            third_got_run.set()
        third_wave.append(claim)

    first_waiter = threading.Thread(target=wait_first)
    first_waiter.start()
    assert repo.first_waiter_parked.wait(5)
    with pytest.raises(RuntimeError):
        repo.complete_stage2(identity, _ready_assessment(), first.generation)
    join_all([first_waiter])
    assert first_wave[0].action == "failed"

    retry = repo.claim_stage2(identity)
    assert retry.action == "run"
    assert retry.generation == 1
    retry_waiter = threading.Thread(target=wait_retry)
    retry_waiter.start()
    assert repo.retry_waiter_parked.wait(5)
    repo.abort_stage2(identity, first.generation)
    assert not repo.retry_waiter_finished.is_set()
    assert retry_waiter.is_alive()

    third = threading.Thread(target=wait_third)
    third.start()
    assert repo.third_waiter_parked.wait(5)
    assert not third_got_run.is_set()

    monkeypatch.setattr(ingestion_repository_module, "_with_assessment", original)
    stored = repo.complete_stage2(identity, _ready_assessment(), retry.generation)
    join_all([retry_waiter, third])

    assert stored.kind == "ready"
    assert retry_wave[0].action == "use_stored"
    assert third_wave[0].action == "use_stored"
    assert not third_got_run.is_set()
    visible = repo.get("obs-1", ORG)
    assert visible is not None
    assert visible.assessment == stored


def test_publication_failure_finally_does_not_abort_retry_claim(monkeypatch) -> None:
    original = ingestion_repository_module._with_assessment
    calls = {"n": 0}

    def boom(record, assessment):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("secret copy")
        return original(record, assessment)

    monkeypatch.setattr(ingestion_repository_module, "_with_assessment", boom)
    fail_hold = threading.Event()
    retry_hold = threading.Event()
    failing_resolver = RecordingResolver(hold=fail_hold)
    retry_resolver = RecordingResolver(hold=retry_hold)
    repo = PublicationOverlapRepository(id_factory=IdFactory(), hold_publication=True)
    failing = stage2_service(repo, failing_resolver, RecordingMapper())
    retrying = stage2_service(repo, retry_resolver, RecordingMapper())
    outcomes: list[tuple[str, object]] = []
    guard = threading.Lock()
    retry_waiter_done = threading.Event()

    def capture(label: str, service: ObservationIngestionService) -> None:
        try:
            result = service.assess(observation(), context(), authorizer())
        except BaseException as exc:
            with guard:
                outcomes.append((label, exc))
            return
        with guard:
            outcomes.append((label, result))
        if label == "retry-waiter":
            retry_waiter_done.set()

    assessor = threading.Thread(target=capture, args=("assessor", failing))
    first_waiter = threading.Thread(target=capture, args=("first-waiter", failing))
    retry = threading.Thread(target=capture, args=("retry", retrying))
    retry_waiter = threading.Thread(target=capture, args=("retry-waiter", retrying))
    assessor.start()
    assert failing_resolver.entered.wait(5)
    first_waiter.start()
    assert repo.first_waiter_parked.wait(5)
    fail_hold.set()
    assert repo.publication_failed.wait(5)
    retry.start()
    assert retry_resolver.entered.wait(5)
    retry_waiter.start()
    assert repo.retry_waiter_parked.wait(5)
    repo.allow_complete_return.set()
    join_all([assessor, first_waiter])
    assert not retry_waiter_done.is_set()
    assert retry_waiter.is_alive()
    assert len(retry_resolver.calls) == 1
    retry_hold.set()
    join_all([retry, retry_waiter])

    by_label = {label: value for label, value in outcomes}
    assert isinstance(by_label["assessor"], RuntimeError)
    assert isinstance(by_label["first-waiter"], IngestionConfigurationError)
    assert str(by_label["first-waiter"]) == _UNAVAILABLE
    assert isinstance(by_label["retry"], IngestionResult)
    assert isinstance(by_label["retry-waiter"], IngestionResult)
    assert_ready(by_label["retry"].assessment)
    assert by_label["retry-waiter"].assessment == by_label["retry"].assessment
    assert len(retry_resolver.calls) == 1


def test_repository_instances_remain_isolated() -> None:
    first_repo = repository()
    second_repo = repository()
    first = stage2_service(first_repo).assess(observation(), context(), authorizer())
    identity = build_idempotency_identity(first.reservation.record.observation, ORG)

    assert second_repo.get("obs-1", ORG) is None
    with pytest.raises(IngestionConfigurationError):
        second_repo.claim_stage2(identity)

    second = stage2_service(second_repo).assess(observation(), context(), authorizer())
    first_stored = first_repo.get("obs-1", ORG)
    second_stored = second_repo.get("obs-1", ORG)
    assert second.reservation.record.observation_id == "obs-1"
    assert first_stored is not None
    assert second_stored is not None
    assert first.assessment == second.assessment
    assert first_stored.assessment is not second_stored.assessment
