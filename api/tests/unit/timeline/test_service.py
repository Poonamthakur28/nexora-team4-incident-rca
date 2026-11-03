from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from itertools import count

import pytest

from app.modules.evidence_collection.contracts import Provenance, RecordManualEvidence, RecordObservationEventEvidence
from app.modules.evidence_collection.errors import UnverifiedContentReference
from app.modules.evidence_collection.repository import InMemoryEvidenceRepository
from app.modules.evidence_collection.service import EvidenceService
from app.modules.incidents.context import IncidentRequestContext
from app.modules.incidents.contracts import AssignIncident, ChangeIncidentStatus, CreateIncident, serialize_utc_z
from app.modules.incidents.errors import IncidentNotFound, UncertainIncidentCreate
from app.modules.incidents.repository import InMemoryIncidentRepository
from app.modules.incidents.service import IncidentService
from app.modules.ingestion.context import ConnectorRegistrationActorFactory
from app.modules.ingestion.errors import IngestionConfigurationError, ObservationNotReadyForCompletion
from app.modules.ingestion.ports import StaticContentReferenceFactory
from app.modules.ingestion.service import ObservationIngestionService
from app.modules.timeline.service import TimelineService
from app.shared.identifiers import as_external_ref
from tests.unit.evidence.test_service import FakeVerifier
from tests.unit.ingestion.test_fingerprint import RecordingHasher
from tests.unit.ingestion.test_repository import observation, repository as observation_repository
from tests.unit.ingestion.test_stage1_validation import authorizer, context as connector_context
from tests.unit.ingestion.test_stage2 import RecordingMapper, RecordingResolver, default_grants

ORG = "org_synth_0001"
OTHER_ORG = "org_synth_0002"
ACTOR = as_external_ref("team1.user", "user_synth_0007")
TEAM = as_external_ref("team1.team", "team_synth_payments")
START = datetime(2026, 10, 1, 9, 15, 4, tzinfo=UTC)
CONTENT_REF = "content_synth_0051"


class IdFactory:
    def __init__(self, prefix: str) -> None:
        self._ids = count(1)
        self.issued: list[str] = []
        self.prefix = prefix

    def __call__(self) -> str:
        value = f"{self.prefix}-{next(self._ids)}"
        self.issued.append(value)
        return value


class Clock:
    def __init__(self, start: datetime = START) -> None:
        self.current = start

    def __call__(self) -> datetime:
        value = self.current
        self.current = value + timedelta(minutes=5)
        return value


class ReloadFailsOnce(IncidentService):
    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        self.reload_failures_left = 1

    def get_incident(self, incident_id, request_context):
        if self.reload_failures_left > 0:
            self.reload_failures_left -= 1
            raise RuntimeError("secret reload")
        return super().get_incident(incident_id, request_context)


def context(
    organization_id: str = ORG,
    *,
    actor_ref=ACTOR,
    correlation_id: str | None = "corr-synth-0001",
) -> IncidentRequestContext:
    return IncidentRequestContext(
        organization_id=organization_id,
        actor_ref=actor_ref,
        correlation_id=correlation_id,
    )


def create_command(**overrides: object) -> CreateIncident:
    payload: dict[str, object] = {
        "title": "Checkout API error rate above threshold",
        "severity": "high",
        "external_refs": [],
        "description": "Synthetic monitor reported a 12% HTTP 5xx rate.",
    }
    payload.update(overrides)
    return CreateIncident(**payload)  # type: ignore[arg-type]


def stack(
    *,
    incident_clock: Callable[[], datetime] | None = None,
    evidence_clock: Callable[[], datetime] | None = None,
) -> tuple[IncidentService, InMemoryIncidentRepository, EvidenceService, InMemoryEvidenceRepository, TimelineService]:
    incident_repo = InMemoryIncidentRepository()
    incidents = IncidentService(
        incident_repo,
        id_factory=IdFactory("incident"),
        clock=incident_clock or Clock(),
    )
    evidence_repo = InMemoryEvidenceRepository()
    evidence = EvidenceService(
        evidence_repo,
        incidents,
        content_verifier=FakeVerifier({CONTENT_REF}),
        id_factory=IdFactory("evidence"),
        clock=evidence_clock or Clock(START + timedelta(minutes=30)),
    )
    timeline = TimelineService(incidents, incidents, evidence)
    return incidents, incident_repo, evidence, evidence_repo, timeline


def record_manual(evidence: EvidenceService, incident_id: str, **overrides: object):
    payload: dict[str, object] = {
        "incident_id": incident_id,
        "evidence_type": "other",
        "description": "Screenshot of the checkout error.",
        "source_label": "Operations desk upload",
        "captured_at": START - timedelta(minutes=1),
        "availability": "unavailable",
        "content_ref": None,
    }
    payload.update(overrides)
    return evidence.record_manual_evidence(RecordManualEvidence(**payload), context())  # type: ignore[arg-type]


def record_observation_evidence(evidence: EvidenceService, incident_id: str, **overrides: object):
    payload: dict[str, object] = {
        "incident_id": incident_id,
        "description": "Provider event attached as Evidence.",
        "source_label": "synthetic-monitor",
        "content_ref": CONTENT_REF,
        "captured_at": datetime(2026, 10, 1, 9, 14, 30, tzinfo=UTC),
        "provenance": Provenance.model_validate(
            {
                "originType": "observation",
                "provider": "synthetic-monitor",
                "sourceEventId": "evt-10001",
                "sourceAccountRef": {"owner": "synthetic-monitor", "id": "acct_synth_0001"},
                "collectorRef": {"owner": "team5.connector", "id": "conn_synth_monitor_01"},
            }
        ),
    }
    payload.update(overrides)
    return evidence.record_observation_event_evidence(
        RecordObservationEventEvidence(**payload),  # type: ignore[arg-type]
        context(),
    )


def complete_stack(*, incidents=None, evidence=None, grants=None):
    incident_repo = InMemoryIncidentRepository()
    raw_incidents = incidents or IncidentService(
        incident_repo,
        id_factory=IdFactory("incident"),
        clock=lambda: datetime(2026, 10, 1, 12, 0, tzinfo=UTC),
    )
    raw_evidence = evidence or EvidenceService(
        InMemoryEvidenceRepository(),
        raw_incidents,
        content_verifier=FakeVerifier({CONTENT_REF}),
        id_factory=IdFactory("evidence"),
        clock=lambda: datetime(2026, 10, 1, 12, 0, tzinfo=UTC),
    )
    ingestion = ObservationIngestionService(
        observation_repository(),
        RecordingHasher(),
        resolver=RecordingResolver(grants if grants is not None else default_grants()),
        mapper=RecordingMapper(),
        incidents=raw_incidents,
        evidence=raw_evidence,
        content_refs=StaticContentReferenceFactory(CONTENT_REF),
        request_contexts=ConnectorRegistrationActorFactory(),
    )
    timeline = TimelineService(raw_incidents, raw_incidents, raw_evidence)
    return ingestion, raw_incidents, raw_evidence, timeline


def test_unknown_incident_is_not_found() -> None:
    _, _, _, _, timeline = stack()

    with pytest.raises(IncidentNotFound):
        timeline.list_incident_timeline("missing", context())


def test_cross_organization_incident_is_not_found() -> None:
    incidents, _, _, _, timeline = stack()
    created = incidents.create_incident(create_command(), context())

    with pytest.raises(IncidentNotFound):
        timeline.list_incident_timeline(created.id, context(OTHER_ORG))
    entries = timeline.list_incident_timeline(created.id, context())
    assert [entry.category for entry in entries] == ["incident.opened"]


def test_open_incident_projects_one_opened_entry() -> None:
    incidents, _, _, _, timeline = stack()
    created = incidents.create_incident(create_command(), context())

    entries = timeline.list_incident_timeline(created.id, context())

    assert len(entries) == 1
    entry = entries[0]
    assert entry.category == "incident.opened"
    assert entry.source_kind == "incident"
    assert entry.source_id == created.id
    assert entry.organization_id == ORG
    assert entry.incident_id == created.id
    assert entry.occurred_at == created.created_at
    assert entry.recorded_at == created.created_at
    assert entry.label == "Incident opened"
    assert entry.detail == created.title
    assert entry.id == "tl:incident.opened:incident-1"


def test_projection_ids_are_stable_across_repeated_reads() -> None:
    incidents, _, _, _, timeline = stack()
    created = incidents.create_incident(create_command(), context())

    first = timeline.list_incident_timeline(created.id, context())
    second = timeline.list_incident_timeline(created.id, context())

    assert first == second
    assert [entry.id for entry in first] == [entry.id for entry in second]


def test_one_entry_per_stored_status_transition_without_audit_intent() -> None:
    incidents, repository, _, _, timeline = stack()
    created = incidents.create_incident(create_command(), context())
    changed = incidents.change_status(
        created.id,
        ChangeIncidentStatus(to_status="investigating", reason="On-call accepted the page"),
        context(),
    )

    entries = timeline.list_incident_timeline(created.id, context())
    occurred = serialize_utc_z(changed.transition.occurred_at)

    assert [entry.category for entry in entries] == ["incident.opened", "incident.status_changed"]
    status_entry = entries[1]
    assert status_entry.source_kind == "status_transition"
    assert status_entry.source_id == f"{changed.transition.correlation_id}:{occurred}"
    assert status_entry.id == (
        f"tl:incident.status_changed:{created.id}:{changed.transition.correlation_id}:{occurred}"
    )
    assert status_entry.occurred_at == changed.transition.occurred_at
    assert status_entry.recorded_at == changed.transition.occurred_at
    assert status_entry.label == "Status changed from open to investigating"
    assert status_entry.detail == "On-call accepted the page"
    assert status_entry.id != changed.audit_intent.event_id
    assert repository.list_audit_intents(created.id, ORG) == (changed.audit_intent,)
    assert all(entry.source_kind != "audit_intent" for entry in entries)


def test_manual_evidence_is_projected_once() -> None:
    incidents, _, evidence, evidence_repo, timeline = stack()
    created = incidents.create_incident(create_command(), context())
    recorded = record_manual(evidence, created.id)

    entries = timeline.list_incident_timeline(created.id, context())

    assert [entry.category for entry in entries] == ["evidence.recorded", "incident.opened"]
    evidence_entry = entries[0]
    assert evidence_entry.source_kind == "evidence"
    assert evidence_entry.source_id == recorded.id
    assert evidence_entry.id == f"tl:evidence.recorded:{recorded.id}"
    assert evidence_entry.occurred_at == recorded.captured_at
    assert evidence_entry.recorded_at == recorded.collected_at
    assert evidence_entry.detail == recorded.description
    assert evidence_repo.list_audit_intents(recorded.id, ORG)
    assert evidence_entry.id != evidence_repo.list_audit_intents(recorded.id, ORG)[0].event_id


def test_observation_origin_evidence_is_projected_once() -> None:
    incidents, _, evidence, _, timeline = stack()
    created = incidents.create_incident(create_command(), context())
    recorded = record_observation_evidence(evidence, created.id)

    entries = timeline.list_incident_timeline(created.id, context())

    assert [entry.category for entry in entries] == ["evidence.recorded", "incident.opened"]
    assert entries[0].source_id == recorded.id
    assert entries[0].occurred_at == recorded.captured_at
    assert entries[0].recorded_at == recorded.collected_at
    assert all(entry.category != "observation.bound" for entry in entries)


def test_successful_completion_projects_incident_and_evidence_only() -> None:
    ingestion, incidents, evidence, timeline = complete_stack()
    ingestion.assess(observation(), connector_context(), authorizer())
    result = ingestion.complete(observation(), connector_context(), authorizer())
    request = ConnectorRegistrationActorFactory().build(connector_context(), correlation_id="corr-synth-0001")

    entries = timeline.list_incident_timeline(result.completion.incident_id, request)
    stored_evidence = evidence.get_evidence(result.completion.evidence_id, request)

    assert [entry.category for entry in entries] == ["evidence.recorded", "incident.opened"]
    assert entries[0].source_id == stored_evidence.id
    assert entries[0].occurred_at == stored_evidence.captured_at == observation().occurred_at
    assert entries[1].source_id == result.completion.incident_id
    assert all(entry.category != "observation.bound" for entry in entries)
    assert incidents.get_incident(result.completion.incident_id, request).title == observation().title


def test_repeated_completion_does_not_duplicate_evidence_entries() -> None:
    ingestion, _, _, timeline = complete_stack()
    ingestion.assess(observation(), connector_context(), authorizer())
    first = ingestion.complete(observation(), connector_context(), authorizer())
    second = ingestion.complete(observation(), connector_context(), authorizer())
    request = ConnectorRegistrationActorFactory().build(connector_context(), correlation_id="corr-synth-0001")

    entries = timeline.list_incident_timeline(first.completion.incident_id, request)

    assert second.completion == first.completion
    assert [entry.category for entry in entries] == ["evidence.recorded", "incident.opened"]
    assert [entry.source_id for entry in entries if entry.category == "evidence.recorded"] == [
        first.completion.evidence_id
    ]


def test_failed_completion_adds_no_timeline_entries() -> None:
    ingestion, _, _, timeline = complete_stack(grants=[])
    ingestion.assess(observation(), connector_context(), authorizer())

    with pytest.raises(ObservationNotReadyForCompletion):
        ingestion.complete(observation(), connector_context(), authorizer())

    with pytest.raises(IncidentNotFound):
        timeline.list_incident_timeline("incident-1", context())


def test_uncertain_completion_does_not_add_evidence_or_observation_entries() -> None:
    incidents = ReloadFailsOnce(
        InMemoryIncidentRepository(),
        id_factory=IdFactory("incident"),
        clock=lambda: datetime(2026, 10, 1, 12, 0, tzinfo=UTC),
    )
    ingestion, incidents, _, timeline = complete_stack(incidents=incidents)
    ingestion.assess(observation(), connector_context(), authorizer())

    with pytest.raises(IngestionConfigurationError) as caught:
        ingestion.complete(observation(), connector_context(), authorizer())
    assert isinstance(caught.value.__cause__, UncertainIncidentCreate)

    request = ConnectorRegistrationActorFactory().build(connector_context(), correlation_id="corr-synth-0001")
    entries = timeline.list_incident_timeline("incident-1", request)

    assert [entry.category for entry in entries] == ["incident.opened"]
    assert all(entry.category != "evidence.recorded" for entry in entries)


def test_failed_evidence_write_after_create_adds_no_evidence_entry() -> None:
    incidents, _, evidence, _, timeline = stack()
    created = incidents.create_incident(create_command(), context())
    evidence._content_verifier = FakeVerifier()

    with pytest.raises(UnverifiedContentReference):
        record_observation_evidence(evidence, created.id)

    entries = timeline.list_incident_timeline(created.id, context())
    assert [entry.category for entry in entries] == ["incident.opened"]


def test_ordering_uses_occurred_then_recorded_then_category() -> None:
    incidents, _, evidence, _, timeline = stack()
    created = incidents.create_incident(create_command(), context())
    incidents.change_status(
        created.id,
        ChangeIncidentStatus(to_status="investigating", reason="On-call accepted the page"),
        context(),
    )
    record_manual(evidence, created.id, captured_at=START - timedelta(minutes=10))

    entries = timeline.list_incident_timeline(created.id, context())

    assert [entry.category for entry in entries] == [
        "evidence.recorded",
        "incident.opened",
        "incident.status_changed",
    ]
    assert entries[0].occurred_at < entries[1].occurred_at < entries[2].occurred_at


def test_equal_timestamps_use_category_then_id() -> None:
    frozen = START
    incidents, _, evidence, _, timeline = stack(
        incident_clock=lambda: frozen,
        evidence_clock=lambda: frozen,
    )
    created = incidents.create_incident(create_command(), context())
    first = record_manual(
        evidence,
        created.id,
        captured_at=frozen,
        description="First evidence",
    )
    second = record_manual(
        evidence,
        created.id,
        captured_at=frozen,
        description="Second evidence",
    )

    entries = timeline.list_incident_timeline(created.id, context())

    assert [entry.category for entry in entries] == [
        "incident.opened",
        "evidence.recorded",
        "evidence.recorded",
    ]
    assert [entry.source_id for entry in entries[1:]] == [first.id, second.id]
    assert entries[1].id < entries[2].id


def test_assignment_does_not_generate_a_timeline_event() -> None:
    incidents, repository, _, _, timeline = stack()
    created = incidents.create_incident(create_command(), context())

    incidents.assign_incident(created.id, AssignIncident(assigned_team_ref=TEAM), context())
    entries = timeline.list_incident_timeline(created.id, context())

    assert [entry.category for entry in entries] == ["incident.opened"]
    assert repository.list_audit_intents(created.id, ORG) == ()
    assert repository.list_transitions(created.id, ORG) == ()


def test_source_records_remain_unchanged() -> None:
    incidents, incident_repo, evidence, evidence_repo, timeline = stack()
    created = incidents.create_incident(create_command(), context())
    changed = incidents.change_status(
        created.id,
        ChangeIncidentStatus(to_status="investigating", reason="On-call accepted the page"),
        context(),
    )
    recorded = record_manual(evidence, created.id)
    before_incident = incident_repo.get(created.id, ORG)
    before_evidence = evidence_repo.get(recorded.id, ORG)
    before_transitions = incident_repo.list_transitions(created.id, ORG)
    before_intents = incident_repo.list_audit_intents(created.id, ORG)

    timeline.list_incident_timeline(created.id, context())

    after_incident = incident_repo.get(created.id, ORG)
    assert before_incident is not None and after_incident is not None
    assert after_incident.version == before_incident.version
    assert after_incident.incident == before_incident.incident
    assert evidence_repo.get(recorded.id, ORG) == before_evidence
    assert incident_repo.list_transitions(created.id, ORG) == before_transitions
    assert incident_repo.list_audit_intents(created.id, ORG) == before_intents
    assert changed.incident.status == "investigating"
