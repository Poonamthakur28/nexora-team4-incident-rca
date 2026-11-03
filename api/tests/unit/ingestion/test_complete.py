import inspect
import threading
from datetime import UTC, datetime
from itertools import count

import pytest

from app.modules.evidence_collection.contracts import RecordObservationEventEvidence
from app.modules.evidence_collection.errors import UnverifiedContentReference
from app.modules.evidence_collection.repository import InMemoryEvidenceRepository
from app.modules.evidence_collection.service import EvidenceService
from app.modules.incidents.context import IncidentRequestContext
from app.modules.incidents.errors import IncidentNotFound, UncertainIncidentCreate
from app.modules.incidents.repository import InMemoryIncidentRepository
from app.modules.incidents.service import IncidentService
from app.modules.ingestion import repository as ingestion_repository_module
from app.modules.ingestion.completion import (
    CREATED_INCIDENT_UNBOUND,
    ObservationBinding,
    ObservationCompletion,
)
from app.modules.ingestion.context import ConnectorRegistrationActorFactory
from app.modules.ingestion.errors import (
    IngestionConfigurationError,
    ObservationIdempotencyConflict,
    ObservationNotReadyForCompletion,
)
from app.modules.ingestion.ports import StaticContentReferenceFactory
from app.modules.ingestion.repository import InMemoryObservationRepository
from app.modules.ingestion.service import (
    CompletionResult,
    ObservationIngestionService,
    _COMPLETION_UNAVAILABLE,
)
from app.shared.identifiers import as_external_ref
from tests.unit.evidence.test_service import FakeVerifier, TenantScopedVerifier
from tests.unit.ingestion.test_completion import CompletionOverlapRepository, CompletionWaitRepository
from tests.unit.ingestion.test_contracts import provenance
from tests.unit.ingestion.test_fingerprint import RecordingHasher
from tests.unit.ingestion.test_repository import IdFactory, ORG, OTHER_ORG, observation, repository
from tests.unit.ingestion.test_stage1_validation import ACCOUNT, REGISTRATION, authorizer, context
from tests.unit.ingestion.test_stage2 import (
    CANONICAL_SERVICE,
    PROVIDER_SERVICE,
    RecordingMapper,
    RecordingResolver,
    default_grants,
    join_all,
    stage2_service,
)

CONTENT_REF = "content_synth_0051"
NOW = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)
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
    "transaction",
    "atomic",
)


class SeqFactory:
    def __init__(self, prefix: str) -> None:
        self._ids = count(1)
        self.issued: list[str] = []
        self.prefix = prefix

    def __call__(self) -> str:
        value = f"{self.prefix}-{next(self._ids)}"
        self.issued.append(value)
        return value


class ReloadFailsOnce(IncidentService):
    """Persist via add, then fail the first reload used by create_incident."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.reload_failures_left = 1

    def get_incident(self, incident_id, request_context):
        if self.reload_failures_left > 0:
            self.reload_failures_left -= 1
            raise RuntimeError("secret reload")
        return super().get_incident(incident_id, request_context)


class CountingIncidentService:
    def __init__(self, inner: IncidentService, *, hold=None, error: Exception | None = None) -> None:
        self.inner = inner
        self.hold = hold
        self.error = error
        self.creates = 0
        self.fail_get = False
        self.entered = threading.Event()

    def create_incident(self, command, request_context):
        self.creates += 1
        self.entered.set()
        if self.hold is not None:
            assert self.hold.wait(5)
        if self.error is not None:
            raise self.error
        return self.inner.create_incident(command, request_context)

    def get_incident(self, incident_id, request_context):
        if getattr(self, "fail_get", False):
            raise IncidentNotFound(str(incident_id))
        return self.inner.get_incident(incident_id, request_context)


class PersistThenHideId(CountingIncidentService):
    """Create succeeds, then hide the id behind a generic exception."""

    def create_incident(self, command, request_context):
        self.creates += 1
        self.entered.set()
        self.inner.create_incident(command, request_context)
        raise RuntimeError("secret after persist")


class CountingEvidenceService:
    def __init__(
        self,
        inner: EvidenceService,
        *,
        hold=None,
        error: Exception | None = None,
        list_error: Exception | None = None,
    ) -> None:
        self.inner = inner
        self.hold = hold
        self.error = error
        self.list_error = list_error
        self.records = 0
        self.lists = 0
        self.commands: list[object] = []
        self.entered = threading.Event()

    def record_observation_event_evidence(self, command, request_context):
        self.entered.set()
        if self.hold is not None:
            assert self.hold.wait(5)
        if self.error is not None:
            raise self.error
        recorded = self.inner.record_observation_event_evidence(command, request_context)
        self.records += 1
        self.commands.append(command)
        return recorded

    def list_incident_evidence(self, incident_id, request_context):
        self.lists += 1
        if self.list_error is not None:
            raise self.list_error
        return self.inner.list_incident_evidence(incident_id, request_context)

    def get_evidence(self, evidence_id, request_context):
        return self.inner.get_evidence(evidence_id, request_context)


def build_services(
    repo=None,
    *,
    resolver=None,
    mapper=None,
    verifier=None,
    incidents=None,
    evidence=None,
    hold_incident=None,
    incident_error=None,
    hold_evidence=None,
    evidence_error=None,
    grants=None,
):
    repo = repo or repository()
    incident_ids = SeqFactory("incident")
    evidence_ids = SeqFactory("evidence")
    raw_incidents = IncidentService(
        InMemoryIncidentRepository(),
        id_factory=incident_ids,
        clock=lambda: NOW,
    )
    incidents = incidents or CountingIncidentService(
        raw_incidents, hold=hold_incident, error=incident_error
    )
    raw_evidence = EvidenceService(
        InMemoryEvidenceRepository(),
        incidents,
        content_verifier=verifier if verifier is not None else FakeVerifier({CONTENT_REF}),
        id_factory=evidence_ids,
        clock=lambda: NOW,
    )
    evidence = evidence or CountingEvidenceService(
        raw_evidence, hold=hold_evidence, error=evidence_error
    )
    ingestion = ObservationIngestionService(
        repo,
        RecordingHasher(),
        resolver=resolver or RecordingResolver(grants if grants is not None else default_grants()),
        mapper=mapper or RecordingMapper(),
        incidents=incidents,
        evidence=evidence,
        content_refs=StaticContentReferenceFactory(CONTENT_REF),
        request_contexts=ConnectorRegistrationActorFactory(),
    )
    return ingestion, repo, incidents, evidence


def assess_ready(ingestion, built=None, ctx=None, grants=None):
    return ingestion.assess(built or observation(), ctx or context(), grants or authorizer())


def trusted_request():
    return ConnectorRegistrationActorFactory().build(
        context(), correlation_id="corr-synth-0001"
    )


def rebuild_complete(repo, incidents, evidence, *, request_contexts=None):
    return ObservationIngestionService(
        repo,
        RecordingHasher(),
        resolver=RecordingResolver(),
        mapper=RecordingMapper(),
        incidents=incidents,
        evidence=evidence,
        content_refs=StaticContentReferenceFactory(CONTENT_REF),
        request_contexts=request_contexts or ConnectorRegistrationActorFactory(),
    )


def seed_observation_evidence(evidence_service, observation_row, *, incident_id="incident-1", provenance=None):
    return evidence_service.record_observation_event_evidence(
        RecordObservationEventEvidence(
            incident_id=incident_id,
            description=observation_row.description or observation_row.title,
            source_label=observation_row.source,
            content_ref=CONTENT_REF,
            captured_at=observation_row.occurred_at,
            provenance=provenance if provenance is not None else observation_row.provenance,
        ),
        trusted_request(),
    )


def assert_no_public_status(*values: object) -> None:
    for value in values:
        for name in FORBIDDEN:
            assert not hasattr(value, name)


def test_ready_observation_creates_one_incident_and_one_evidence() -> None:
    ingestion, repo, incidents, evidence = build_services()
    assess_ready(ingestion)

    result = ingestion.complete(observation(), context(), authorizer())

    assert result.completion == ObservationCompletion("incident-1", "evidence-1")
    assert result.assessment.kind == "ready"
    assert result.reservation.record.binding == ObservationBinding("incident-1", "evidence-1")
    incident = incidents.get_incident("incident-1", ConnectorRegistrationActorFactory().build(
        context(), correlation_id="corr-synth-0001"
    ))
    assert incident.title == "Checkout API error rate above threshold"
    assert incident.severity == "high"
    assert incident.service_ref == CANONICAL_SERVICE
    assert incident.description == (
        "Synthetic monitor reported a 12% HTTP 5xx rate over 5 minutes."
    )
    stored_evidence = evidence.get_evidence(
        "evidence-1",
        ConnectorRegistrationActorFactory().build(context(), correlation_id="corr-synth-0001"),
    )
    assert stored_evidence.evidence_type == "event"
    assert stored_evidence.triggered_by_observation_id is None
    assert stored_evidence.provenance.origin_type == "observation"
    assert stored_evidence.source_label == "synthetic-monitor"
    assert stored_evidence.captured_at == observation().occurred_at
    assert incidents.creates == 1
    assert evidence.records == 1
    assert_no_public_status(result, result.completion, result.reservation.record)
    stored = repo.get("obs-1", ORG)
    assert stored is not None
    assert stored.binding == result.reservation.record.binding


def test_non_ready_stage2_creates_neither() -> None:
    ingestion, repo, incidents, evidence = build_services(resolver=RecordingResolver([]))
    assessed = assess_ready(ingestion)
    assert assessed.assessment.kind == "service_unresolved"

    with pytest.raises(ObservationNotReadyForCompletion):
        ingestion.complete(observation(), context(), authorizer())

    assert incidents.creates == 0
    assert evidence.records == 0
    stored = repo.get("obs-1", ORG)
    assert stored is not None
    assert stored.binding is None


def test_full_binding_duplicate_returns_same_ids_without_new_writes() -> None:
    ingestion, _, incidents, evidence = build_services()
    assess_ready(ingestion)
    first = ingestion.complete(observation(), context(), authorizer())

    second = ingestion.complete(observation(), context(), authorizer())

    assert second.completion == first.completion
    assert incidents.creates == 1
    assert evidence.records == 1


def test_fingerprint_conflict_never_enters_completion() -> None:
    ingestion, repo, incidents, evidence = build_services()
    assess_ready(ingestion)

    with pytest.raises(ObservationIdempotencyConflict):
        ingestion.complete(
            observation(title="Checkout API latency above threshold"),
            context(),
            authorizer(),
        )

    assert incidents.creates == 0
    assert evidence.records == 0
    stored = repo.get("obs-1", ORG)
    assert stored is not None
    assert stored.binding is None


def test_incident_creation_failure_leaves_no_binding() -> None:
    ingestion, repo, incidents, evidence = build_services(
        incident_error=RuntimeError("secret catalog")
    )
    assess_ready(ingestion)

    with pytest.raises(IngestionConfigurationError) as caught:
        ingestion.complete(observation(), context(), authorizer())

    assert str(caught.value) == _COMPLETION_UNAVAILABLE
    assert isinstance(caught.value.__cause__, RuntimeError)
    assert "secret" not in str(caught.value)
    assert incidents.creates == 1
    assert evidence.records == 0
    stored = repo.get("obs-1", ORG)
    assert stored is not None
    assert stored.binding is None


def test_evidence_failure_after_incident_preserves_incident_only_binding() -> None:
    ingestion, repo, incidents, evidence = build_services(
        evidence_error=UnverifiedContentReference("The content reference could not be verified.")
    )
    assess_ready(ingestion)

    with pytest.raises(IngestionConfigurationError) as caught:
        ingestion.complete(observation(), context(), authorizer())

    assert str(caught.value) == _COMPLETION_UNAVAILABLE
    assert isinstance(caught.value.__cause__, UnverifiedContentReference)
    assert incidents.creates == 1
    assert evidence.records == 0
    stored = repo.get("obs-1", ORG)
    assert stored is not None
    assert stored.binding == ObservationBinding("incident-1")
    request = ConnectorRegistrationActorFactory().build(
        context(), correlation_id="corr-synth-0001"
    )
    assert evidence.list_incident_evidence("incident-1", request) == ()


def test_retry_after_evidence_failure_reuses_incident_and_creates_only_evidence() -> None:
    failing, repo, incidents, failing_evidence = build_services(
        evidence_error=RuntimeError("storage down")
    )
    assess_ready(failing)
    with pytest.raises(IngestionConfigurationError):
        failing.complete(observation(), context(), authorizer())

    retry_evidence = CountingEvidenceService(failing_evidence.inner)
    retry = ObservationIngestionService(
        repo,
        RecordingHasher(),
        resolver=RecordingResolver(),
        mapper=RecordingMapper(),
        incidents=incidents,
        evidence=retry_evidence,
        content_refs=StaticContentReferenceFactory(CONTENT_REF),
        request_contexts=ConnectorRegistrationActorFactory(),
    )
    result = retry.complete(observation(), context(), authorizer())

    assert result.completion.incident_id == "incident-1"
    assert result.completion.evidence_id == "evidence-1"
    assert incidents.creates == 1
    assert failing_evidence.records == 0
    assert retry_evidence.records == 1


def test_two_concurrent_completion_calls_have_one_owner() -> None:
    hold = threading.Event()
    repo = CompletionWaitRepository(id_factory=IdFactory(), expected_waiters=1)
    ingestion, _, incidents, evidence = build_services(repo, hold_incident=hold)
    assess_ready(ingestion)
    outcomes: list[object] = []
    guard = threading.Lock()

    def worker() -> None:
        try:
            result = ingestion.complete(observation(), context(), authorizer())
        except Exception as exc:
            with guard:
                outcomes.append(exc)
            return
        with guard:
            outcomes.append(result)

    owner = threading.Thread(target=worker)
    waiter = threading.Thread(target=worker)
    owner.start()
    assert incidents.entered.wait(5)
    waiter.start()
    assert repo.waiters_parked.wait(5)
    hold.set()
    join_all([owner, waiter])

    results = [item for item in outcomes if isinstance(item, CompletionResult)]
    assert len(results) == 2
    assert results[0].completion == results[1].completion
    assert incidents.creates == 1
    assert evidence.records == 1


def test_failed_wave_waiters_receive_generic_configuration_errors() -> None:
    hold = threading.Event()
    repo = CompletionWaitRepository(id_factory=IdFactory(), expected_waiters=1)
    ingestion, _, _, evidence = build_services(
        repo, hold_evidence=hold, evidence_error=RuntimeError("secret boom")
    )
    assess_ready(ingestion)
    outcomes: list[object] = []
    guard = threading.Lock()

    def worker() -> None:
        try:
            result = ingestion.complete(observation(), context(), authorizer())
        except Exception as exc:
            with guard:
                outcomes.append(exc)
            return
        with guard:
            outcomes.append(result)

    owner = threading.Thread(target=worker)
    waiter = threading.Thread(target=worker)
    owner.start()
    assert evidence.entered.wait(5)
    waiter.start()
    assert repo.waiters_parked.wait(5)
    hold.set()
    join_all([owner, waiter])

    errors = [item for item in outcomes if isinstance(item, IngestionConfigurationError)]
    assert len(errors) == 2
    assert all(str(item) == _COMPLETION_UNAVAILABLE for item in errors)
    assert all("secret" not in str(item) for item in errors)
    assert isinstance(errors[0].__cause__, RuntimeError) or isinstance(errors[1].__cause__, RuntimeError)


def test_stale_completion_cleanup_cannot_release_newer_generation(monkeypatch) -> None:
    original = ingestion_repository_module._with_binding
    failed_full = {"done": False}

    def boom(record, binding):
        if binding.evidence_id is not None and not failed_full["done"]:
            failed_full["done"] = True
            raise RuntimeError("secret copy")
        return original(record, binding)

    monkeypatch.setattr(ingestion_repository_module, "_with_binding", boom)
    repo = CompletionOverlapRepository(id_factory=IdFactory(), hold_publication=True)
    evidence_hold = threading.Event()
    ingestion, _, incidents, evidence = build_services(repo, hold_evidence=evidence_hold)
    assess_ready(ingestion)
    outcomes: list[tuple[str, object]] = []
    guard = threading.Lock()

    def capture(label: str) -> None:
        try:
            result = ingestion.complete(observation(), context(), authorizer())
        except BaseException as exc:
            with guard:
                outcomes.append((label, exc))
            return
        with guard:
            outcomes.append((label, result))

    first = threading.Thread(target=capture, args=("first",))
    waiter = threading.Thread(target=capture, args=("waiter",))
    retry = threading.Thread(target=capture, args=("retry",))
    first.start()
    assert evidence.entered.wait(5)
    waiter.start()
    assert repo.first_waiter_parked.wait(5)
    evidence_hold.set()
    assert repo.publication_failed.wait(5)
    retry.start()
    repo.allow_complete_return.set()
    join_all([first, waiter, retry])

    by_label = {label: value for label, value in outcomes}
    assert isinstance(by_label["first"], IngestionConfigurationError)
    assert isinstance(by_label["waiter"], IngestionConfigurationError)
    assert str(by_label["waiter"]) == _COMPLETION_UNAVAILABLE
    assert isinstance(by_label["retry"], CompletionResult)
    assert by_label["retry"].completion.incident_id == "incident-1"
    assert incidents.creates == 1
    assert evidence.records == 1


def test_different_identities_complete_concurrently() -> None:
    entered = threading.Barrier(3)
    hold = threading.Event()

    class BarrierIncidents(CountingIncidentService):
        def create_incident(self, command, request_context):
            self.creates += 1
            entered.wait(5)
            assert hold.wait(5)
            return self.inner.create_incident(command, request_context)

    raw = IncidentService(InMemoryIncidentRepository(), id_factory=SeqFactory("incident"), clock=lambda: NOW)
    incidents = BarrierIncidents(raw)
    evidence_inner = EvidenceService(
        InMemoryEvidenceRepository(),
        incidents,
        content_verifier=FakeVerifier({CONTENT_REF}),
        id_factory=SeqFactory("evidence"),
        clock=lambda: NOW,
    )
    evidence = CountingEvidenceService(evidence_inner)
    ingestion = ObservationIngestionService(
        repository(),
        RecordingHasher(),
        resolver=RecordingResolver(),
        mapper=RecordingMapper(),
        incidents=incidents,
        evidence=evidence,
        content_refs=StaticContentReferenceFactory(CONTENT_REF),
        request_contexts=ConnectorRegistrationActorFactory(),
    )
    first = observation()
    second = observation(
        sourceEventId="evt-10002",
        provenance=provenance(sourceEventId="evt-10002"),
        idempotencyKey="idem_synth_0002",
    )
    assess_ready(ingestion, first)
    assess_ready(ingestion, second)
    outcomes: list[CompletionResult] = []
    guard = threading.Lock()
    start = threading.Barrier(2)

    def worker(built) -> None:
        start.wait()
        result = ingestion.complete(built, context(), authorizer())
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

    assert incidents.creates == 2
    assert evidence.records == 2
    assert {item.completion.incident_id for item in outcomes} == {"incident-1", "incident-2"}


def test_cross_organization_reservation_cannot_access_another_organizations_binding() -> None:
    grants = authorizer((ORG, REGISTRATION, ACCOUNT), (OTHER_ORG, REGISTRATION, ACCOUNT))
    resolver = RecordingResolver(
        [
            (ORG, PROVIDER_SERVICE, CANONICAL_SERVICE),
            (OTHER_ORG, PROVIDER_SERVICE, CANONICAL_SERVICE),
        ]
    )
    ingestion, repo, incidents, _ = build_services(resolver=resolver)
    assess_ready(ingestion, ctx=context(ORG), grants=grants)
    first = ingestion.complete(observation(), context(ORG), grants)

    assert repo.get(first.reservation.record.observation_id, OTHER_ORG) is None
    assess_ready(ingestion, ctx=context(OTHER_ORG), grants=grants)
    second = ingestion.complete(observation(), context(OTHER_ORG), grants)

    assert second.completion.incident_id != first.completion.incident_id
    assert repo.get(second.reservation.record.observation_id, ORG) is None
    assert incidents.creates == 2


def test_existing_evidence_id_prevents_another_evidence_write() -> None:
    ingestion, _, incidents, evidence = build_services()
    assess_ready(ingestion)
    first = ingestion.complete(observation(), context(), authorizer())
    assert evidence.records == 1

    second = ingestion.complete(observation(), context(), authorizer())

    assert second.completion == first.completion
    assert incidents.creates == 1
    assert evidence.records == 1


def test_stored_provenance_is_passed_through_without_reconstruction() -> None:
    built = observation()
    ingestion, repo, _, evidence = build_services()
    assess_ready(ingestion, built)
    result = ingestion.complete(built, context(), authorizer())
    command = evidence.commands[0]
    stored = repo.get("obs-1", ORG)
    assert stored is not None

    assert command.provenance == stored.observation.provenance
    assert command.provenance.source_event_id == stored.observation.provenance.source_event_id
    assert command.provenance.source_event_id != "reconstructed"
    request = ConnectorRegistrationActorFactory().build(
        context(), correlation_id=built.correlation_id
    )
    recorded = evidence.get_evidence(result.completion.evidence_id, request)
    assert recorded.provenance == stored.observation.provenance


def test_content_verifier_failure_creates_no_evidence() -> None:
    ingestion, repo, incidents, evidence = build_services(verifier=FakeVerifier())
    assess_ready(ingestion)

    with pytest.raises(IngestionConfigurationError):
        ingestion.complete(observation(), context(), authorizer())

    assert incidents.creates == 1
    assert evidence.records == 0
    stored = repo.get("obs-1", ORG)
    assert stored is not None
    assert stored.binding == ObservationBinding("incident-1")
    request = ConnectorRegistrationActorFactory().build(
        context(), correlation_id="corr-synth-0001"
    )
    assert evidence.list_incident_evidence("incident-1", request) == ()


def test_accept_and_assess_still_do_not_create_incident_or_evidence() -> None:
    ingestion, repo, incidents, evidence = build_services()
    accepted = ingestion.accept(observation(), context(), authorizer())
    assessed = ingestion.assess(observation(), context(), authorizer())

    assert accepted.record.binding is None
    assert assessed.reservation.record.binding is None
    assert incidents.creates == 0
    assert evidence.records == 0
    assert repo.get("obs-1", ORG) is not None
    accept_src = inspect.getsource(ObservationIngestionService.accept)
    assess_src = inspect.getsource(ObservationIngestionService.assess)
    assert "create_incident" not in accept_src
    assert "create_incident" not in assess_src


def test_completion_result_has_no_public_status_or_transaction_fields() -> None:
    ingestion, _, _, _ = build_services()
    assess_ready(ingestion)
    result = ingestion.complete(observation(), context(), authorizer())

    assert_no_public_status(result, result.completion, result.reservation, result.reservation.record)
    assert result.reservation.record.binding is not None
    assert result.reservation.record.binding.evidence_id is not None


def test_description_fallback_uses_title_when_observation_description_is_absent() -> None:
    built = observation(description=None)
    ingestion, _, _, evidence = build_services()
    assess_ready(ingestion, built)

    ingestion.complete(built, context(), authorizer())

    assert evidence.commands[0].description == built.title


def test_connector_actor_factory_uses_trusted_organization_and_stand_in_registration() -> None:
    factory = ConnectorRegistrationActorFactory()
    built = factory.build(context(), correlation_id="corr-synth-0001")

    assert built.organization_id == ORG
    assert built.actor_ref == REGISTRATION
    assert built.correlation_id == "corr-synth-0001"


def test_cross_organization_content_reference_is_rejected() -> None:
    verifier = TenantScopedVerifier({ORG: {CONTENT_REF}})
    grants = authorizer((ORG, REGISTRATION, ACCOUNT), (OTHER_ORG, REGISTRATION, ACCOUNT))
    resolver = RecordingResolver(
        [
            (ORG, PROVIDER_SERVICE, CANONICAL_SERVICE),
            (OTHER_ORG, PROVIDER_SERVICE, CANONICAL_SERVICE),
        ]
    )
    ingestion, repo, incidents, evidence = build_services(resolver=resolver, verifier=verifier)
    assess_ready(ingestion, ctx=context(OTHER_ORG), grants=grants)

    with pytest.raises(IngestionConfigurationError):
        ingestion.complete(observation(), context(OTHER_ORG), grants)

    stored = repo.get("obs-1", OTHER_ORG)
    assert stored is not None
    assert stored.binding == ObservationBinding("incident-1")
    assert evidence.records == 0
    assert incidents.creates == 1


def test_bind_failure_after_create_reuses_incident_on_retry() -> None:
    ingestion, repo, incidents, evidence = build_services()
    assess_ready(ingestion)
    original = repo.bind_incident

    def boom(identity, incident_id, generation):
        raise RuntimeError("secret bind")

    repo.bind_incident = boom  # type: ignore[method-assign]
    with pytest.raises(IngestionConfigurationError) as caught:
        ingestion.complete(observation(), context(), authorizer())

    assert str(caught.value) == _COMPLETION_UNAVAILABLE
    assert isinstance(caught.value.__cause__, RuntimeError)
    assert "secret" not in str(caught.value)
    assert incidents.creates == 1
    assert evidence.records == 0
    stored = repo.get("obs-1", ORG)
    assert stored is not None
    assert stored.binding == ObservationBinding("incident-1")

    repo.bind_incident = original  # type: ignore[method-assign]
    retry_evidence = CountingEvidenceService(evidence.inner)
    result = rebuild_complete(repo, incidents, retry_evidence).complete(
        observation(), context(), authorizer()
    )

    assert result.completion.incident_id == "incident-1"
    assert result.completion.evidence_id == "evidence-1"
    assert incidents.creates == 1
    assert retry_evidence.records == 1


def test_bind_record_copy_failure_after_create_still_reuses_incident(monkeypatch) -> None:
    original = ingestion_repository_module._with_binding

    def boom(record, binding):
        if binding.evidence_id is None:
            raise RuntimeError("secret copy")
        return original(record, binding)

    monkeypatch.setattr(ingestion_repository_module, "_with_binding", boom)
    ingestion, repo, incidents, evidence = build_services()
    assess_ready(ingestion)

    with pytest.raises(IngestionConfigurationError) as caught:
        ingestion.complete(observation(), context(), authorizer())

    assert str(caught.value) == _COMPLETION_UNAVAILABLE
    assert isinstance(caught.value.__cause__, RuntimeError)
    assert incidents.creates == 1
    assert evidence.records == 0
    stored = repo.get("obs-1", ORG)
    assert stored is not None
    assert stored.binding == ObservationBinding("incident-1")

    monkeypatch.setattr(ingestion_repository_module, "_with_binding", original)
    retry_evidence = CountingEvidenceService(evidence.inner)
    result = rebuild_complete(repo, incidents, retry_evidence).complete(
        observation(), context(), authorizer()
    )

    assert result.completion.incident_id == "incident-1"
    assert incidents.creates == 1
    assert retry_evidence.records == 1


def test_unrecoverable_created_incident_blocks_a_second_create() -> None:
    class RememberFails(InMemoryObservationRepository):
        def remember_created_incident(self, identity, incident_id, generation):
            with self._lock:
                slot = self._completion_slot(identity)
                slot.block_new_incident = True
            raise RuntimeError("secret remember")

        def bind_incident(self, identity, incident_id, generation):
            raise AssertionError("bind_incident must not run after remember fails")

    repo = RememberFails(id_factory=IdFactory())
    ingestion, _, incidents, evidence = build_services(repo)
    assess_ready(ingestion)

    with pytest.raises(IngestionConfigurationError) as caught:
        ingestion.complete(observation(), context(), authorizer())

    assert str(caught.value) == CREATED_INCIDENT_UNBOUND
    assert isinstance(caught.value.__cause__, RuntimeError)
    assert incidents.creates == 1
    assert evidence.records == 0

    with pytest.raises(IngestionConfigurationError, match="could not be bound"):
        rebuild_complete(repo, incidents, evidence).complete(
            observation(), context(), authorizer()
        )

    assert incidents.creates == 1
    assert evidence.records == 0


def test_multiple_matching_observation_evidence_raises_reconciliation() -> None:
    ingestion, repo, incidents, evidence = build_services(
        evidence_error=RuntimeError("skip first evidence")
    )
    assess_ready(ingestion)
    with pytest.raises(IngestionConfigurationError):
        ingestion.complete(observation(), context(), authorizer())

    stored = repo.get("obs-1", ORG)
    assert stored is not None
    seed_observation_evidence(evidence.inner, stored.observation)
    seed_observation_evidence(evidence.inner, stored.observation)
    assert len(evidence.list_incident_evidence("incident-1", trusted_request())) == 2

    retry_evidence = CountingEvidenceService(evidence.inner)
    retry = rebuild_complete(repo, incidents, retry_evidence)
    with pytest.raises(IngestionConfigurationError, match="Multiple observation-origin"):
        retry.complete(observation(), context(), authorizer())
    with pytest.raises(IngestionConfigurationError, match="Multiple observation-origin"):
        retry.complete(observation(), context(), authorizer())

    assert incidents.creates == 1
    assert retry_evidence.records == 0
    assert len(retry_evidence.list_incident_evidence("incident-1", trusted_request())) == 2


def test_evidence_lookup_failure_after_incident_only_binding_does_not_append() -> None:
    ingestion, repo, incidents, evidence = build_services(
        evidence_error=RuntimeError("skip first evidence")
    )
    assess_ready(ingestion)
    with pytest.raises(IngestionConfigurationError):
        ingestion.complete(observation(), context(), authorizer())

    failing = CountingEvidenceService(evidence.inner, list_error=RuntimeError("secret list"))
    with pytest.raises(IngestionConfigurationError) as caught:
        rebuild_complete(repo, incidents, failing).complete(
            observation(), context(), authorizer()
        )

    assert str(caught.value) == _COMPLETION_UNAVAILABLE
    assert isinstance(caught.value.__cause__, RuntimeError)
    assert "secret" not in str(caught.value)
    assert failing.records == 0
    assert failing.lists == 1
    assert incidents.creates == 1

    recovered = CountingEvidenceService(evidence.inner)
    result = rebuild_complete(repo, incidents, recovered).complete(
        observation(), context(), authorizer()
    )

    assert result.completion.incident_id == "incident-1"
    assert recovered.records == 1
    assert incidents.creates == 1


def test_incident_lookup_failure_during_evidence_recovery_does_not_append() -> None:
    ingestion, repo, incidents, evidence = build_services(
        evidence_error=RuntimeError("skip first evidence")
    )
    assess_ready(ingestion)
    with pytest.raises(IngestionConfigurationError):
        ingestion.complete(observation(), context(), authorizer())

    incidents.fail_get = True
    failing = CountingEvidenceService(evidence.inner)
    with pytest.raises(IngestionConfigurationError) as caught:
        rebuild_complete(repo, incidents, failing).complete(
            observation(), context(), authorizer()
        )

    assert str(caught.value) == _COMPLETION_UNAVAILABLE
    assert isinstance(caught.value.__cause__, IncidentNotFound)
    assert failing.records == 0
    assert incidents.creates == 1

    incidents.fail_get = False
    recovered = CountingEvidenceService(evidence.inner)
    result = rebuild_complete(repo, incidents, recovered).complete(
        observation(), context(), authorizer()
    )

    assert result.completion.evidence_id == "evidence-1"
    assert recovered.records == 1
    assert incidents.creates == 1


def test_evidence_reuse_does_not_include_collector_ref() -> None:
    ingestion, repo, incidents, evidence = build_services(
        evidence_error=RuntimeError("skip first evidence")
    )
    assess_ready(ingestion)
    with pytest.raises(IngestionConfigurationError):
        ingestion.complete(observation(), context(), authorizer())

    stored = repo.get("obs-1", ORG)
    assert stored is not None
    other_collector = stored.observation.provenance.model_copy(
        update={"collector_ref": as_external_ref("team5.connector", "conn_other_01")}
    )
    seeded = seed_observation_evidence(
        evidence.inner, stored.observation, provenance=other_collector
    )

    retry_evidence = CountingEvidenceService(evidence.inner)
    result = rebuild_complete(repo, incidents, retry_evidence).complete(
        observation(), context(), authorizer()
    )

    assert result.completion.evidence_id == seeded.id
    assert retry_evidence.records == 0
    assert incidents.creates == 1
    assert len(retry_evidence.list_incident_evidence("incident-1", trusted_request())) == 1


def test_custom_request_context_factory_cannot_change_organization() -> None:
    class ForeignOrgFactory:
        def build(self, connector, *, correlation_id: str):
            return IncidentRequestContext(
                organization_id=OTHER_ORG,
                actor_ref=connector.registration_ref,
                correlation_id=correlation_id,
            )

    ingestion, repo, incidents, evidence = build_services()
    assess_ready(ingestion)
    foreign = rebuild_complete(
        repo, incidents, evidence, request_contexts=ForeignOrgFactory()
    )

    with pytest.raises(IngestionConfigurationError, match="does not match the connector"):
        foreign.complete(observation(), context(), authorizer())

    assert incidents.creates == 0
    assert evidence.records == 0
    stored = repo.get("obs-1", ORG)
    assert stored is not None
    assert stored.binding is None


def test_uncertain_create_after_add_reuses_incident_on_retry() -> None:
    raw = ReloadFailsOnce(InMemoryIncidentRepository(), id_factory=SeqFactory("incident"), clock=lambda: NOW)
    incidents = CountingIncidentService(raw)
    ingestion, repo, incidents, evidence = build_services(incidents=incidents)
    assess_ready(ingestion)

    with pytest.raises(IngestionConfigurationError) as caught:
        ingestion.complete(observation(), context(), authorizer())

    assert str(caught.value) == _COMPLETION_UNAVAILABLE
    assert isinstance(caught.value.__cause__, UncertainIncidentCreate)
    assert isinstance(caught.value.__cause__.__cause__, RuntimeError)
    assert "secret" not in str(caught.value)
    assert incidents.creates == 1
    assert evidence.records == 0
    stored = repo.get("obs-1", ORG)
    assert stored is not None
    assert stored.binding == ObservationBinding("incident-1")
    assert raw.get_incident("incident-1", trusted_request()).id == "incident-1"

    retry_evidence = CountingEvidenceService(evidence.inner)
    result = rebuild_complete(repo, incidents, retry_evidence).complete(
        observation(), context(), authorizer()
    )

    assert result.completion.incident_id == "incident-1"
    assert result.completion.evidence_id == "evidence-1"
    assert incidents.creates == 1
    assert retry_evidence.records == 1


def test_hidden_persisted_incident_blocks_another_create() -> None:
    raw = IncidentService(InMemoryIncidentRepository(), id_factory=SeqFactory("incident"), clock=lambda: NOW)
    incidents = PersistThenHideId(raw)
    ingestion, repo, incidents, evidence = build_services(incidents=incidents)
    assess_ready(ingestion)

    with pytest.raises(IngestionConfigurationError) as caught:
        ingestion.complete(observation(), context(), authorizer())

    assert str(caught.value) == _COMPLETION_UNAVAILABLE
    assert isinstance(caught.value.__cause__, RuntimeError)
    assert incidents.creates == 1
    stored = repo.get("obs-1", ORG)
    assert stored is not None
    assert stored.binding is None

    with pytest.raises(IngestionConfigurationError, match="could not be bound") as retry:
        rebuild_complete(repo, incidents, evidence).complete(
            observation(), context(), authorizer()
        )

    assert isinstance(retry.value, IngestionConfigurationError)
    assert incidents.creates == 1
    assert evidence.records == 0
    assert raw.get_incident("incident-1", trusted_request()).id == "incident-1"


def test_unknown_create_exception_blocks_another_create() -> None:
    ingestion, repo, incidents, evidence = build_services(
        incident_error=RuntimeError("secret catalog")
    )
    assess_ready(ingestion)
    with pytest.raises(IngestionConfigurationError):
        ingestion.complete(observation(), context(), authorizer())

    with pytest.raises(IngestionConfigurationError, match="could not be bound"):
        rebuild_complete(repo, incidents, evidence).complete(
            observation(), context(), authorizer()
        )

    assert incidents.creates == 1
    assert evidence.records == 0
    stored = repo.get("obs-1", ORG)
    assert stored is not None
    assert stored.binding is None


def test_uncertain_create_stays_tenant_scoped() -> None:
    grants = authorizer((ORG, REGISTRATION, ACCOUNT), (OTHER_ORG, REGISTRATION, ACCOUNT))
    resolver = RecordingResolver(
        [
            (ORG, PROVIDER_SERVICE, CANONICAL_SERVICE),
            (OTHER_ORG, PROVIDER_SERVICE, CANONICAL_SERVICE),
        ]
    )
    raw = ReloadFailsOnce(InMemoryIncidentRepository(), id_factory=SeqFactory("incident"), clock=lambda: NOW)
    incidents = CountingIncidentService(raw)
    ingestion, repo, incidents, _ = build_services(incidents=incidents, resolver=resolver)
    assess_ready(ingestion, ctx=context(ORG), grants=grants)

    with pytest.raises(IngestionConfigurationError):
        ingestion.complete(observation(), context(ORG), grants)

    stored = repo.get("obs-1", ORG)
    assert stored is not None
    assert stored.binding == ObservationBinding("incident-1")
    assert repo.get("obs-1", OTHER_ORG) is None
    with pytest.raises(IncidentNotFound):
        raw.get_incident("incident-1", ConnectorRegistrationActorFactory().build(
            context(OTHER_ORG), correlation_id="corr-synth-0001"
        ))

    assess_ready(ingestion, ctx=context(OTHER_ORG), grants=grants)
    second = ingestion.complete(observation(), context(OTHER_ORG), grants)

    assert second.completion.incident_id == "incident-2"
    assert incidents.creates == 2
    retry = ingestion.complete(observation(), context(ORG), grants)
    assert retry.completion.incident_id == "incident-1"
    assert incidents.creates == 2
