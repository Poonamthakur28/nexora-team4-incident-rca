from datetime import UTC, datetime

import pytest

from app.modules.evidence_collection.contracts import (
    Evidence,
    EvidenceRecordedAuditIntent,
    EvidenceRecordedData,
    Provenance,
)
from app.modules.evidence_collection.errors import (
    EvidenceNotFound,
    InconsistentEvidenceRecord,
    InvalidEvidenceInput,
)
from app.modules.evidence_collection.repository import InMemoryEvidenceRepository
from app.shared.identifiers import as_external_ref, as_team4_entity_id


def make_evidence(evidence_id: str = "evidence-1", incident_id: str = "incident-1") -> Evidence:
    moment = datetime(2026, 10, 1, 9, 30, tzinfo=UTC)
    return Evidence(
        id=as_team4_entity_id(evidence_id),
        incident_id=as_team4_entity_id(incident_id),
        investigation_id=None,
        triggered_by_observation_id=None,
        evidence_type="other",
        description="Responder screenshot",
        source_label="Operations desk",
        external_source_ref=None,
        content_ref=None,
        captured_at=moment,
        collected_at=moment,
        availability="unavailable",
        provenance=Provenance(
            origin_type="manual",
            provider=None,
            source_event_id=None,
            source_account_ref=None,
            collector_ref=as_external_ref("team1.user", "user-1"),
        ),
    )


def make_intent(evidence: Evidence, **overrides: object) -> EvidenceRecordedAuditIntent:
    values: dict[str, object] = {
        "event_id": as_team4_entity_id(f"audit-{evidence.id}"),
        "event_type": "evidence.recorded",
        "organization_id": "org-1",
        "actor_ref": evidence.provenance.collector_ref,
        "resource_type": "evidence",
        "resource_id": evidence.id,
        "occurred_at": evidence.collected_at,
        "correlation_id": None,
        "data": EvidenceRecordedData(
            evidence_type=evidence.evidence_type, availability=evidence.availability
        ),
    }
    values.update(overrides)
    return EvidenceRecordedAuditIntent(**values)  # type: ignore[arg-type]


def test_add_stores_evidence_and_audit_together_and_scopes_reads() -> None:
    repository = InMemoryEvidenceRepository()
    evidence = make_evidence()
    intent = make_intent(evidence)

    repository.add(evidence, organization_id="org-1", audit_intent=intent)

    assert repository.get(evidence.id, "org-1") == evidence
    assert repository.get(evidence.id, "org-2") is None
    assert repository.list_for_incident(evidence.incident_id, "org-1") == (evidence,)
    assert repository.list_for_incident(evidence.incident_id, "org-2") == ()
    assert repository.list_audit_intents(evidence.id, "org-1") == (intent,)
    with pytest.raises(EvidenceNotFound):
        repository.list_audit_intents(evidence.id, "org-2")


@pytest.mark.parametrize(
    "override",
    [
        {"resource_id": as_team4_entity_id("other")},
        {"organization_id": "org-2"},
        {"occurred_at": datetime(2026, 10, 1, 9, 31, tzinfo=UTC)},
        {"data": EvidenceRecordedData(evidence_type="log", availability="unavailable")},
        {"actor_ref": as_external_ref("forged.actor", "attacker")},
    ],
)
def test_invalid_audit_intent_leaves_no_partial_state(override: dict[str, object]) -> None:
    repository = InMemoryEvidenceRepository()
    evidence = make_evidence()

    with pytest.raises(InconsistentEvidenceRecord):
        repository.add(evidence, organization_id="org-1", audit_intent=make_intent(evidence, **override))

    assert repository.get(evidence.id, "org-1") is None
    assert repository.list_for_incident(evidence.incident_id, "org-1") == ()


def test_audit_actor_mismatch_for_manual_evidence_is_rejected() -> None:
    """L3: a manual Evidence record's audit intent actor must match its collector."""
    repository = InMemoryEvidenceRepository()
    evidence = make_evidence()
    forged_intent = make_intent(evidence, actor_ref=as_external_ref("forged.actor", "attacker"))
    assert evidence.provenance.collector_ref != forged_intent.actor_ref

    with pytest.raises(InconsistentEvidenceRecord):
        repository.add(evidence, organization_id="org-1", audit_intent=forged_intent)

    assert repository.get(evidence.id, "org-1") is None


def test_blank_organization_id_is_rejected_and_stores_nothing() -> None:
    """L5: the repository must not trust a blank organization id from its caller."""
    repository = InMemoryEvidenceRepository()
    evidence = make_evidence()

    with pytest.raises(InvalidEvidenceInput):
        repository.add(evidence, organization_id="   ", audit_intent=make_intent(evidence))

    assert repository.get(evidence.id, "org-1") is None
    assert repository.list_for_incident(evidence.incident_id, "org-1") == ()


def test_repository_returns_defensive_copies() -> None:
    repository = InMemoryEvidenceRepository()
    evidence = make_evidence()
    intent = make_intent(evidence)
    repository.add(evidence, organization_id="org-1", audit_intent=intent)

    loaded = repository.get(evidence.id, "org-1")
    assert loaded is not None
    loaded.description = "mutated"
    history = repository.list_audit_intents(evidence.id, "org-1")
    history[0].data.availability = "available"

    stored = repository.get(evidence.id, "org-1")
    assert stored is not None
    assert stored.description == "Responder screenshot"
    assert repository.list_audit_intents(evidence.id, "org-1")[0].data.availability == "unavailable"


def test_observation_audit_actor_need_not_match_collector() -> None:
    repository = InMemoryEvidenceRepository()
    moment = datetime(2026, 10, 1, 9, 30, tzinfo=UTC)
    evidence = Evidence(
        id=as_team4_entity_id("evidence-obs"),
        incident_id=as_team4_entity_id("incident-1"),
        investigation_id=None,
        triggered_by_observation_id=None,
        evidence_type="event",
        description="All synthetic checks failing for 3 minutes.",
        source_label="synthetic-monitor",
        external_source_ref=None,
        content_ref="content_synth_0051",
        captured_at=moment,
        collected_at=moment,
        availability="available",
        provenance=Provenance(
            origin_type="observation",
            provider="synthetic-monitor",
            source_event_id="evt-10005",
            source_account_ref=as_external_ref("synthetic-monitor", "acct_synth_0001"),
            collector_ref=as_external_ref("team5.connector", "conn_synth_monitor_01"),
        ),
    )
    intent = make_intent(evidence, actor_ref=as_external_ref("team1.user", "user-1"))
    assert intent.actor_ref != evidence.provenance.collector_ref

    repository.add(evidence, organization_id="org-1", audit_intent=intent)

    assert repository.get(evidence.id, "org-1") == evidence
    assert repository.list_audit_intents(evidence.id, "org-1") == (intent,)


def test_repository_is_append_only_and_has_no_update_or_delete_operations() -> None:
    repository = InMemoryEvidenceRepository()
    evidence = make_evidence()
    repository.add(evidence, organization_id="org-1", audit_intent=make_intent(evidence))

    with pytest.raises(InvalidEvidenceInput):
        repository.add(evidence, organization_id="org-1", audit_intent=make_intent(evidence))
    assert not hasattr(repository, "save")
    assert not hasattr(repository, "delete")
