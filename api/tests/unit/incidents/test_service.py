from datetime import UTC, datetime, timedelta, timezone
from itertools import count

import pytest
from pydantic import ValidationError

from app.modules.incidents.context import IncidentRequestContext
from app.modules.incidents.contracts import AssignIncident, ChangeIncidentStatus, CreateIncident, Incident
from app.modules.incidents.errors import (
    IncidentConcurrencyConflict,
    IncidentNotFound,
    IncidentServiceConfigurationError,
    InvalidIncidentInput,
    InvalidLifecycleTransition,
    InvalidRequestContext,
    OrganizationScopeError,
    SameStatusTransition,
)
from app.modules.incidents.repository import InMemoryIncidentRepository
from app.modules.incidents.service import IncidentService
from app.shared.identifiers import ExternalRef, as_external_ref

ORG = "org_synth_0001"
OTHER_ORG = "org_synth_0002"
ACTOR = as_external_ref("team1.user", "user_synth_0007")
TEAM = as_external_ref("team1.team", "team_synth_payments")
START = datetime(2026, 10, 1, 9, 15, 4, tzinfo=UTC)


class IdFactory:
    """Deterministic ids: id-1, id-2, ..."""

    def __init__(self) -> None:
        self._counter = count(1)
        self.issued: list[str] = []

    def __call__(self) -> str:
        value = f"id-{next(self._counter)}"
        self.issued.append(value)
        return value


class Clock:
    def __init__(self, start: datetime = START) -> None:
        self.current = start

    def __call__(self) -> datetime:
        value = self.current
        self.current = value + timedelta(minutes=5)
        return value


def context(
    organization_id: str = ORG,
    *,
    actor_ref: ExternalRef = ACTOR,
    correlation_id: str | None = "corr-synth-0001",
) -> IncidentRequestContext:
    return IncidentRequestContext(
        organization_id=organization_id,
        actor_ref=actor_ref,
        correlation_id=correlation_id,
    )


def create_command(**overrides: object) -> CreateIncident:
    payload: dict[str, object] = {
        "title": "  Checkout API error rate above threshold  ",
        "description": "  Synthetic monitor reported a 12% HTTP 5xx rate over 5 minutes.  ",
        "severity": "high",
        "external_refs": [as_external_ref("synthetic-monitor", "evt-10001")],
        "service_ref": as_external_ref("service-catalog", "svc_synth_checkout"),
    }
    payload.update(overrides)
    return CreateIncident(**payload)  # type: ignore[arg-type]


def service_for() -> tuple[IncidentService, InMemoryIncidentRepository, IdFactory, Clock]:
    repository = InMemoryIncidentRepository()
    ids = IdFactory()
    clock = Clock()
    return IncidentService(repository, id_factory=ids, clock=clock), repository, ids, clock


def change(to_status: str, reason: str = "Status change") -> ChangeIncidentStatus:
    return ChangeIncidentStatus(to_status=to_status, reason=reason)  # type: ignore[arg-type]


def assert_no_status_history(repository: InMemoryIncidentRepository, incident: Incident) -> None:
    assert repository.list_transitions(incident.id, ORG) == ()
    assert repository.list_audit_intents(incident.id, ORG) == ()


# Trusted context


def test_context_requires_a_trusted_organization() -> None:
    with pytest.raises(OrganizationScopeError):
        context(organization_id="   ")


@pytest.mark.parametrize("organization_id", [None, 123, b"org"])
def test_context_requires_an_organization_string(organization_id: object) -> None:
    with pytest.raises(OrganizationScopeError):
        IncidentRequestContext(organization_id=organization_id, actor_ref=ACTOR)  # type: ignore[arg-type]


@pytest.mark.parametrize("actor_ref", [None, {"owner": "team1.user", "id": "u1"}, "team1.user/u1"])
def test_context_requires_an_external_ref_actor(actor_ref: object) -> None:
    with pytest.raises(InvalidRequestContext):
        IncidentRequestContext(organization_id=ORG, actor_ref=actor_ref)  # type: ignore[arg-type]


@pytest.mark.parametrize("correlation_id", ["", "  ", 7])
def test_context_rejects_a_blank_or_non_string_correlation_id(correlation_id: object) -> None:
    with pytest.raises(InvalidRequestContext):
        IncidentRequestContext(
            organization_id=ORG, actor_ref=ACTOR, correlation_id=correlation_id  # type: ignore[arg-type]
        )


def test_context_trims_values_and_is_immutable() -> None:
    trusted = context(organization_id="  org_synth_0001  ", correlation_id="  corr-1  ")

    assert trusted.organization_id == ORG
    assert trusted.correlation_id == "corr-1"
    with pytest.raises(AttributeError):
        trusted.organization_id = OTHER_ORG  # type: ignore[misc]


# Creation and retrieval


def test_create_uses_the_trusted_organization_and_opens_the_incident() -> None:
    incident_service, repository, ids, clock = service_for()

    incident = incident_service.create_incident(
        create_command(description="   "),
        context(organization_id="  org_synth_0001  "),
    )

    assert ids.issued == ["id-1"]
    assert incident.id == "id-1"
    assert incident.organization_id == ORG
    assert incident.title == "Checkout API error rate above threshold"
    assert incident.description is None
    assert incident.severity == "high"
    assert incident.status == "open"
    assert incident.service_ref == as_external_ref("service-catalog", "svc_synth_checkout")
    assert incident.created_at == START
    assert incident.updated_at == START
    assert incident.created_at.utcoffset() == timedelta(0)
    stored = repository.get(incident.id, ORG)
    assert stored is not None
    assert stored.incident == incident
    assert stored.version == 1
    assert clock.current == START + timedelta(minutes=5)


def test_create_normalizes_a_non_utc_clock_to_utc() -> None:
    offset = timezone(timedelta(hours=5, minutes=30))
    repository = InMemoryIncidentRepository()
    incident_service = IncidentService(
        repository,
        id_factory=IdFactory(),
        clock=lambda: datetime(2026, 10, 1, 14, 45, 4, tzinfo=offset),
    )

    incident = incident_service.create_incident(create_command(), context())

    assert incident.created_at == START
    assert incident.updated_at == START
    dumped = incident.model_dump(by_alias=True, mode="json")
    assert dumped["createdAt"] == "2026-10-01T09:15:04Z"
    assert dumped["updatedAt"] == "2026-10-01T09:15:04Z"


def test_get_returns_the_incident_in_the_trusted_organization() -> None:
    incident_service, _, _, _ = service_for()
    created = incident_service.create_incident(create_command(), context())

    assert incident_service.get_incident(created.id, context()) == created


def test_cross_organization_access_is_not_found_for_read_status_and_assignment() -> None:
    incident_service, repository, ids, _ = service_for()
    created = incident_service.create_incident(create_command(), context())
    outsider = context(OTHER_ORG, correlation_id="corr-synth-0099")

    with pytest.raises(IncidentNotFound):
        incident_service.get_incident(created.id, outsider)
    with pytest.raises(IncidentNotFound):
        incident_service.change_status(created.id, change("investigating"), outsider)
    with pytest.raises(IncidentNotFound):
        incident_service.assign_incident(created.id, AssignIncident(assigned_team_ref=TEAM), outsider)

    assert incident_service.get_incident(created.id, context()) == created
    assert_no_status_history(repository, created)
    assert ids.issued == ["id-1"]


def test_callers_cannot_choose_the_initial_status_or_organization() -> None:
    incident_service, _, _, _ = service_for()

    incident = incident_service.create_incident(create_command(), context())

    assert isinstance(incident, Incident)
    assert incident.status == "open"
    assert incident.organization_id == ORG


# Status changes


def test_status_change_records_history_and_one_audit_intent() -> None:
    incident_service, repository, ids, clock = service_for()
    created = incident_service.create_incident(create_command(), context())

    result = incident_service.change_status(
        created.id,
        change("investigating", "  On-call engineer started investigation.  "),
        context(correlation_id="corr-synth-0007"),
    )

    assert result.incident.status == "investigating"
    assert result.incident.updated_at == START + timedelta(minutes=5)
    assert result.incident.updated_at.utcoffset() == timedelta(0)
    assert result.transition.incident_id == created.id
    assert result.transition.from_status == "open"
    assert result.transition.to_status == "investigating"
    assert result.transition.actor_ref == ACTOR
    assert result.transition.reason == "On-call engineer started investigation."
    assert result.transition.correlation_id == "corr-synth-0007"
    assert result.transition.occurred_at == result.incident.updated_at
    assert repository.list_transitions(created.id, ORG) == (result.transition,)
    assert repository.list_audit_intents(created.id, ORG) == (result.audit_intent,)
    assert result.audit_intent.event_id == "id-2"
    assert result.audit_intent.event_type == "incident.status_changed"
    assert result.audit_intent.organization_id == ORG
    assert result.audit_intent.actor_ref == ACTOR
    assert result.audit_intent.resource_type == "incident"
    assert result.audit_intent.resource_id == created.id
    assert result.audit_intent.correlation_id == "corr-synth-0007"
    assert result.audit_intent.occurred_at == result.transition.occurred_at
    assert result.audit_intent.data.from_status == "open"
    assert result.audit_intent.data.to_status == "investigating"
    assert result.audit_intent.data.reason == result.transition.reason
    stored = repository.get(created.id, ORG)
    assert stored is not None
    assert stored.version == 2
    assert ids.issued == ["id-1", "id-2"]
    assert clock.current == START + timedelta(minutes=10)


def test_status_change_result_serializes_utc_z() -> None:
    incident_service, _, _, _ = service_for()
    created = incident_service.create_incident(create_command(), context())

    result = incident_service.change_status(created.id, change("investigating"), context())

    assert result.incident.model_dump(by_alias=True, mode="json")["updatedAt"] == "2026-10-01T09:20:04Z"
    assert result.transition.model_dump(by_alias=True, mode="json")["occurredAt"] == "2026-10-01T09:20:04Z"
    assert result.audit_intent.model_dump(by_alias=True, mode="json")["occurredAt"] == "2026-10-01T09:20:04Z"


def test_correlation_comes_only_from_the_trusted_context() -> None:
    incident_service, _, _, _ = service_for()
    created = incident_service.create_incident(create_command(), context())

    with pytest.raises(ValidationError):
        ChangeIncidentStatus.model_validate(
            {"toStatus": "investigating", "reason": "Started", "correlationId": "corr-from-body"}
        )
    result = incident_service.change_status(
        created.id, change("investigating"), context(correlation_id="corr-from-context")
    )

    assert result.transition.correlation_id == "corr-from-context"
    assert result.audit_intent.correlation_id == "corr-from-context"


def test_each_successful_status_change_emits_its_own_audit_intent() -> None:
    incident_service, repository, _, _ = service_for()
    created = incident_service.create_incident(create_command(), context())

    first = incident_service.change_status(created.id, change("investigating", "Started"), context())
    second = incident_service.change_status(
        created.id,
        change("resolved", "Error rate returned to baseline."),
        context(correlation_id="corr-synth-0008"),
    )

    assert first.audit_intent.event_id == "id-2"
    assert second.audit_intent.event_id == "id-3"
    assert second.incident.status == "resolved"
    assert [item.to_status for item in repository.list_transitions(created.id, ORG)] == [
        "investigating",
        "resolved",
    ]
    assert repository.list_audit_intents(created.id, ORG) == (first.audit_intent, second.audit_intent)


def test_reopen_and_close_follow_the_lifecycle() -> None:
    incident_service, repository, _, _ = service_for()
    created = incident_service.create_incident(create_command(), context())
    for target in ["investigating", "resolved", "investigating", "resolved"]:
        incident_service.change_status(created.id, change(target), context())
    closed = incident_service.change_status(created.id, change("closed", "Confirmed stable."), context())

    assert closed.incident.status == "closed"
    assert len(repository.list_transitions(created.id, ORG)) == 5
    assert len(repository.list_audit_intents(created.id, ORG)) == 5

    with pytest.raises(InvalidLifecycleTransition):
        incident_service.change_status(created.id, change("investigating", "Reopen closed"), context())
    assert incident_service.get_incident(created.id, context()).status == "closed"
    assert len(repository.list_transitions(created.id, ORG)) == 5
    assert len(repository.list_audit_intents(created.id, ORG)) == 5


def test_failed_transition_does_not_change_state_or_emit_an_audit_intent() -> None:
    incident_service, repository, ids, _ = service_for()
    created = incident_service.create_incident(create_command(), context())

    with pytest.raises(InvalidLifecycleTransition):
        incident_service.change_status(created.id, change("closed", "Skip the investigation."), context())

    assert incident_service.get_incident(created.id, context()) == created
    assert_no_status_history(repository, created)
    assert ids.issued == ["id-1"]


def test_same_status_change_does_not_change_state_or_emit_an_audit_intent() -> None:
    incident_service, repository, ids, _ = service_for()
    created = incident_service.create_incident(create_command(), context())

    with pytest.raises(SameStatusTransition):
        incident_service.change_status(created.id, change("open", "Still open."), context())

    assert incident_service.get_incident(created.id, context()) == created
    assert_no_status_history(repository, created)
    assert ids.issued == ["id-1"]


def test_missing_trusted_correlation_changes_nothing() -> None:
    incident_service, repository, ids, _ = service_for()
    created = incident_service.create_incident(create_command(), context(correlation_id=None))

    with pytest.raises(InvalidRequestContext):
        incident_service.change_status(created.id, change("investigating"), context(correlation_id=None))

    assert incident_service.get_incident(created.id, context()) == created
    assert_no_status_history(repository, created)
    assert ids.issued == ["id-1"]


def test_lifecycle_is_checked_before_correlation() -> None:
    incident_service, repository, _, _ = service_for()
    created = incident_service.create_incident(create_command(), context())

    with pytest.raises(InvalidLifecycleTransition):
        incident_service.change_status(created.id, change("closed"), context(correlation_id=None))
    with pytest.raises(SameStatusTransition):
        incident_service.change_status(created.id, change("open"), context(correlation_id=None))

    assert_no_status_history(repository, created)


def test_stale_status_change_is_a_conflict_and_stores_nothing() -> None:
    incident_service, repository, ids, _ = service_for()
    created = incident_service.create_incident(create_command(), context())
    original_get = repository.get

    def get_then_concurrent_assignment(incident_id, organization_id):  # type: ignore[no-untyped-def]
        snapshot = original_get(incident_id, organization_id)
        assert snapshot is not None
        repository.save(
            snapshot.incident.model_copy(update={"assigned_team_ref": TEAM}),
            expected_version=snapshot.version,
        )
        return snapshot

    repository.get = get_then_concurrent_assignment  # type: ignore[method-assign]
    with pytest.raises(IncidentConcurrencyConflict):
        incident_service.change_status(created.id, change("investigating"), context())
    repository.get = original_get  # type: ignore[method-assign]

    stored = repository.get(created.id, ORG)
    assert stored is not None
    assert stored.version == 2
    assert stored.incident.status == "open"
    assert stored.incident.assigned_team_ref == TEAM
    assert_no_status_history(repository, created)
    assert ids.issued == ["id-1", "id-2"]


# Assignment


def test_assignment_stores_opaque_references_without_resolving_them() -> None:
    incident_service, repository, ids, _ = service_for()
    created = incident_service.create_incident(create_command(), context())
    user = as_external_ref("team1.user", "user_synth_0042")

    assigned = incident_service.assign_incident(
        created.id,
        AssignIncident(assigned_team_ref=TEAM, assigned_user_ref=user),
        context(),
    )
    cleared_user = incident_service.assign_incident(
        created.id,
        AssignIncident.model_validate({"assignedUserRef": None}),
        context(),
    )

    assert assigned.assigned_team_ref == TEAM
    assert assigned.assigned_user_ref == user
    assert assigned.status == "open"
    assert assigned.organization_id == ORG
    assert assigned.updated_at == START + timedelta(minutes=5)
    assert cleared_user.assigned_team_ref == TEAM
    assert cleared_user.assigned_user_ref is None
    assert cleared_user.updated_at == START + timedelta(minutes=10)
    stored = repository.get(created.id, ORG)
    assert stored is not None
    assert stored.version == 3
    assert_no_status_history(repository, created)
    assert ids.issued == ["id-1"]


def test_empty_assignment_is_rejected() -> None:
    incident_service, repository, ids, _ = service_for()
    created = incident_service.create_incident(create_command(), context())

    with pytest.raises(InvalidIncidentInput):
        incident_service.assign_incident(created.id, AssignIncident(), context())

    stored = repository.get(created.id, ORG)
    assert stored is not None
    assert stored.incident == created
    assert stored.version == 1
    assert ids.issued == ["id-1"]


def test_stale_assignment_is_a_conflict() -> None:
    incident_service, repository, _, _ = service_for()
    created = incident_service.create_incident(create_command(), context())
    original_get = repository.get

    def get_then_concurrent_status_change(incident_id, organization_id):  # type: ignore[no-untyped-def]
        snapshot = original_get(incident_id, organization_id)
        repository.get = original_get  # type: ignore[method-assign]
        incident_service.change_status(incident_id, change("investigating"), context())
        return snapshot

    repository.get = get_then_concurrent_status_change  # type: ignore[method-assign]
    with pytest.raises(IncidentConcurrencyConflict):
        incident_service.assign_incident(created.id, AssignIncident(assigned_team_ref=TEAM), context())

    stored = repository.get(created.id, ORG)
    assert stored is not None
    assert stored.incident.status == "investigating"
    assert stored.incident.assigned_team_ref is None
    assert stored.version == 2


# Injected clock and id factory


@pytest.mark.parametrize("bad_id", ["", "   ", 42, None])
def test_invalid_id_factory_output_is_a_configuration_error(bad_id: object) -> None:
    repository = InMemoryIncidentRepository()
    incident_service = IncidentService(
        repository, id_factory=lambda: bad_id, clock=Clock()  # type: ignore[arg-type, return-value]
    )

    with pytest.raises(IncidentServiceConfigurationError):
        incident_service.create_incident(create_command(), context())


def test_invalid_audit_id_leaves_the_status_unchanged() -> None:
    repository = InMemoryIncidentRepository()
    values = iter(["inc-1", ""])
    incident_service = IncidentService(repository, id_factory=lambda: next(values), clock=Clock())
    created = incident_service.create_incident(create_command(), context())

    with pytest.raises(IncidentServiceConfigurationError):
        incident_service.change_status(created.id, change("investigating"), context())

    assert incident_service.get_incident(created.id, context()) == created
    assert_no_status_history(repository, created)


@pytest.mark.parametrize("bad_time", [datetime(2026, 10, 1, 9, 15, 4), "2026-10-01T09:15:04Z", None])
def test_naive_or_non_datetime_clock_is_a_configuration_error(bad_time: object) -> None:
    repository = InMemoryIncidentRepository()
    incident_service = IncidentService(
        repository, id_factory=IdFactory(), clock=lambda: bad_time  # type: ignore[arg-type, return-value]
    )

    with pytest.raises(IncidentServiceConfigurationError):
        incident_service.create_incident(create_command(), context())


def test_clock_earlier_than_creation_is_a_configuration_error_and_changes_nothing() -> None:
    repository = InMemoryIncidentRepository()
    times = iter([START, START - timedelta(seconds=1), START - timedelta(seconds=1)])
    incident_service = IncidentService(repository, id_factory=IdFactory(), clock=lambda: next(times))
    created = incident_service.create_incident(create_command(), context())

    with pytest.raises(IncidentServiceConfigurationError):
        incident_service.change_status(created.id, change("investigating"), context())
    with pytest.raises(IncidentServiceConfigurationError):
        incident_service.assign_incident(created.id, AssignIncident(assigned_team_ref=TEAM), context())

    stored = repository.get(created.id, ORG)
    assert stored is not None
    assert stored.incident == created
    assert stored.version == 1
    assert_no_status_history(repository, created)
