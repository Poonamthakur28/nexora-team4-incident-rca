from datetime import UTC, datetime, timedelta

import pytest

from app.modules.incidents.contracts import (
    Incident,
    IncidentAuditIntent,
    IncidentStatus,
    IncidentStatusChangedData,
    IncidentStatusTransition,
)
from app.modules.incidents.errors import (
    IncidentConcurrencyConflict,
    IncidentNotFound,
    InconsistentStatusChange,
    InvalidIncidentInput,
    OrganizationScopeError,
)
from app.modules.incidents.repository import InMemoryIncidentRepository
from app.shared.identifiers import as_external_ref, as_team4_entity_id

ORG = "org_synth_0001"
INCIDENT_ID = as_team4_entity_id("inc-1")
ACTOR = as_external_ref("team1.user", "user_synth_0007")
CREATED = datetime(2026, 10, 1, 9, 15, 4, tzinfo=UTC)
CHANGED = CREATED + timedelta(minutes=5)


def _incident(organization_id: str = ORG, status: IncidentStatus = "open") -> Incident:
    return Incident(
        id=INCIDENT_ID,
        organization_id=organization_id,
        title="Checkout API error rate above threshold",
        description=None,
        severity="high",
        status=status,
        service_ref=None,
        assigned_team_ref=None,
        assigned_user_ref=None,
        external_refs=[],
        created_at=CREATED,
        updated_at=CREATED,
    )


def _transition(from_status: IncidentStatus = "open", to_status: IncidentStatus = "investigating"):
    return IncidentStatusTransition(
        incident_id=INCIDENT_ID,
        from_status=from_status,
        to_status=to_status,
        actor_ref=ACTOR,
        reason="Started",
        correlation_id="corr-synth-0001",
        occurred_at=CHANGED,
    )


def _intent(transition: IncidentStatusTransition, **overrides: object) -> IncidentAuditIntent:
    values: dict[str, object] = {
        "event_id": as_team4_entity_id("audit-1"),
        "event_type": "incident.status_changed",
        "organization_id": ORG,
        "actor_ref": transition.actor_ref,
        "resource_type": "incident",
        "resource_id": transition.incident_id,
        "occurred_at": transition.occurred_at,
        "correlation_id": transition.correlation_id,
        "data": IncidentStatusChangedData(
            from_status=transition.from_status,
            to_status=transition.to_status,
            reason=transition.reason,
        ),
    }
    values.update(overrides)
    return IncidentAuditIntent(**values)  # type: ignore[arg-type]


def _moved(status: IncidentStatus = "investigating") -> Incident:
    return _incident().model_copy(update={"status": status, "updated_at": CHANGED})


def _repository() -> InMemoryIncidentRepository:
    repository = InMemoryIncidentRepository()
    repository.add(_incident())
    return repository


def _assert_unchanged(repository: InMemoryIncidentRepository) -> None:
    stored = repository.get(INCIDENT_ID, ORG)
    assert stored is not None
    assert stored.incident == _incident()
    assert stored.version == 1
    assert repository.list_transitions(INCIDENT_ID, ORG) == ()
    assert repository.list_audit_intents(INCIDENT_ID, ORG) == ()


def test_get_hides_an_incident_owned_by_another_organization() -> None:
    repository = _repository()

    assert repository.get(INCIDENT_ID, ORG) is not None
    assert repository.get(INCIDENT_ID, "org_synth_0002") is None
    with pytest.raises(IncidentNotFound):
        repository.list_transitions(INCIDENT_ID, "org_synth_0002")
    with pytest.raises(IncidentNotFound):
        repository.list_audit_intents(INCIDENT_ID, "org_synth_0002")


def test_add_starts_at_version_one_and_rejects_a_repeated_id_without_naming_it() -> None:
    repository = _repository()

    with pytest.raises(InvalidIncidentInput) as caught:
        repository.add(_incident(organization_id="org_synth_0002"))

    assert "inc-1" not in str(caught.value)
    _assert_unchanged(repository)


def test_save_rejects_moving_an_incident_to_another_organization() -> None:
    repository = _repository()

    with pytest.raises(OrganizationScopeError):
        repository.save(_incident(organization_id="org_synth_0002"), expected_version=1)

    _assert_unchanged(repository)


def test_status_change_stores_transition_and_audit_intent_together() -> None:
    repository = _repository()
    transition = _transition()
    intent = _intent(transition)

    new_version = repository.save(_moved(), expected_version=1, transition=transition, audit_intent=intent)

    stored = repository.get(INCIDENT_ID, ORG)
    assert stored is not None
    assert new_version == 2
    assert stored.version == 2
    assert stored.incident.status == "investigating"
    assert repository.list_transitions(INCIDENT_ID, ORG) == (transition,)
    assert repository.list_audit_intents(INCIDENT_ID, ORG) == (intent,)


def test_transition_from_status_must_match_the_stored_status() -> None:
    repository = _repository()
    transition = _transition(from_status="resolved", to_status="closed")

    with pytest.raises(InconsistentStatusChange):
        repository.save(
            _moved("closed"), expected_version=1, transition=transition, audit_intent=_intent(transition)
        )

    _assert_unchanged(repository)


def test_transition_to_status_must_match_the_incoming_status() -> None:
    repository = _repository()
    transition = _transition(from_status="open", to_status="investigating")

    with pytest.raises(InconsistentStatusChange):
        repository.save(
            _moved("resolved"), expected_version=1, transition=transition, audit_intent=_intent(transition)
        )

    _assert_unchanged(repository)


def test_transition_incident_id_must_match() -> None:
    repository = _repository()
    transition = _transition().model_copy(update={"incident_id": as_team4_entity_id("inc-2")})

    with pytest.raises(InconsistentStatusChange):
        repository.save(
            _moved(), expected_version=1, transition=transition, audit_intent=_intent(_transition())
        )

    _assert_unchanged(repository)


def test_status_change_without_transition_and_intent_is_rejected() -> None:
    repository = _repository()

    with pytest.raises(InconsistentStatusChange):
        repository.save(_moved(), expected_version=1)

    _assert_unchanged(repository)


@pytest.mark.parametrize("missing", ["transition", "audit_intent"])
def test_transition_and_audit_intent_must_be_saved_together(missing: str) -> None:
    repository = _repository()
    transition = _transition()
    arguments = {"transition": transition, "audit_intent": _intent(transition)}
    arguments[missing] = None

    with pytest.raises(InconsistentStatusChange):
        repository.save(_moved(), expected_version=1, **arguments)  # type: ignore[arg-type]

    _assert_unchanged(repository)


@pytest.mark.parametrize(
    "override",
    [
        {"resource_id": as_team4_entity_id("inc-2")},
        {"organization_id": "org_synth_0002"},
        {"actor_ref": as_external_ref("team1.user", "user_synth_0099")},
        {"correlation_id": "corr-other"},
        {"occurred_at": CHANGED + timedelta(seconds=1)},
        {"data": IncidentStatusChangedData(from_status="open", to_status="investigating", reason="Other")},
    ],
)
def test_audit_intent_must_describe_the_transition(override: dict[str, object]) -> None:
    repository = _repository()
    transition = _transition()

    with pytest.raises(InconsistentStatusChange):
        repository.save(
            _moved(), expected_version=1, transition=transition, audit_intent=_intent(transition, **override)
        )

    _assert_unchanged(repository)


def test_stale_save_is_a_conflict_and_changes_nothing() -> None:
    repository = _repository()
    snapshot = repository.get(INCIDENT_ID, ORG)
    assert snapshot is not None
    team = as_external_ref("team1.team", "team_synth_payments")
    repository.save(
        snapshot.incident.model_copy(update={"assigned_team_ref": team, "updated_at": CHANGED}),
        expected_version=snapshot.version,
    )
    transition = _transition()

    with pytest.raises(IncidentConcurrencyConflict) as caught:
        repository.save(
            snapshot.incident.model_copy(update={"status": "investigating", "updated_at": CHANGED}),
            expected_version=snapshot.version,
            transition=transition,
            audit_intent=_intent(transition),
        )

    assert caught.value.expected_version == 1
    assert caught.value.current_version == 2
    stored = repository.get(INCIDENT_ID, ORG)
    assert stored is not None
    assert stored.version == 2
    assert stored.incident.status == "open"
    assert stored.incident.assigned_team_ref == team
    assert repository.list_transitions(INCIDENT_ID, ORG) == ()
    assert repository.list_audit_intents(INCIDENT_ID, ORG) == ()


def test_returned_values_do_not_share_mutable_state_with_the_store() -> None:
    repository = _repository()
    transition = _transition()
    intent = _intent(transition)
    repository.save(_moved(), expected_version=1, transition=transition, audit_intent=intent)

    loaded = repository.get(INCIDENT_ID, ORG)
    assert loaded is not None
    loaded.incident.external_refs.append(as_external_ref("synthetic-monitor", "evt-10001"))
    loaded.incident.status = "closed"
    history = repository.list_transitions(INCIDENT_ID, ORG)
    history[0].reason = "mutated"
    intents = repository.list_audit_intents(INCIDENT_ID, ORG)
    intents[0].data.reason = "mutated"

    again = repository.get(INCIDENT_ID, ORG)
    assert again is not None
    assert again.incident.external_refs == []
    assert again.incident.status == "investigating"
    assert repository.list_transitions(INCIDENT_ID, ORG)[0].reason == "Started"
    assert repository.list_audit_intents(INCIDENT_ID, ORG)[0].data.reason == "Started"


def test_saved_inputs_are_copied_not_shared() -> None:
    repository = _repository()
    moved = _moved()
    transition = _transition()
    intent = _intent(transition)
    repository.save(moved, expected_version=1, transition=transition, audit_intent=intent)

    moved.external_refs.append(as_external_ref("synthetic-monitor", "evt-10001"))
    transition.reason = "mutated"
    intent.data.reason = "mutated"

    stored = repository.get(INCIDENT_ID, ORG)
    assert stored is not None
    assert stored.incident.external_refs == []
    assert repository.list_transitions(INCIDENT_ID, ORG)[0].reason == "Started"
    assert repository.list_audit_intents(INCIDENT_ID, ORG)[0].data.reason == "Started"
