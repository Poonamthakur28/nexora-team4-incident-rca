import asyncio

from app.modules.ai_rca.contracts import ContextEvidence, IncidentContext, InvestigationContext
from app.modules.ai_rca.mock_agent import mock_ai_rca_agent
from app.modules.incidents.contracts import as_investigation_id
from app.modules.root_candidates.contracts import RootCauseCandidate
from app.shared.identifiers import as_external_ref, as_team4_entity_id

INCIDENT = IncidentContext(summary="Synthetic fixture", occurred_at="2026-01-01T00:00:00Z")


def test_returns_proposed_candidate_with_traceable_evidence() -> None:
    context = InvestigationContext(
        investigation_id=as_investigation_id("inv-1"),
        incident=INCIDENT,
        evidence=[ContextEvidence(evidence_id=as_team4_entity_id("ev-1"), description="Synthetic event")],
    )

    draft = asyncio.run(mock_ai_rca_agent.analyze(context))[0]

    assert draft.status == "proposed"
    assert draft.evidence[0].evidence_id == "ev-1"
    assert draft.confidence < 1
    assert draft.rationale and draft.uncertainty and draft.missing_information

    stored = RootCauseCandidate(
        id=as_team4_entity_id("candidate-1"),
        investigation_id=as_investigation_id("inv-1"),
        title=draft.title,
        rationale=draft.rationale,
        confidence=draft.confidence,
        uncertainty=draft.uncertainty,
        missing_information=draft.missing_information,
        evidence=draft.evidence,
        status="proposed",
        review_required=True,
    )
    assert stored.status == "proposed"
    assert stored.missing_information == draft.missing_information
    assert stored.review_required is True


def test_empty_evidence_draft_stays_proposed_and_lists_missing_information() -> None:
    context = InvestigationContext(
        investigation_id=as_investigation_id("inv-empty"), incident=INCIDENT, evidence=[]
    )

    draft = asyncio.run(mock_ai_rca_agent.analyze(context))[0]

    assert draft.status == "proposed"
    assert draft.confidence == 0
    assert "Collect investigation evidence." in draft.missing_information
    assert draft.evidence == []


def test_contracts_serialize_with_camel_case_aliases() -> None:
    context = InvestigationContext.model_validate(
        {
            "investigationId": "inv-1",
            "incident": {
                "externalIncidentRef": {"owner": "team-x", "id": "ext-1"},
                "summary": "Synthetic fixture",
                "occurredAt": "2026-01-01T00:00:00Z",
            },
            "evidence": [],
        }
    )

    assert context.incident.external_incident_ref == as_external_ref("team-x", "ext-1")
    dumped = context.model_dump(by_alias=True, mode="json", exclude_none=True)
    assert dumped["investigationId"] == "inv-1"
    assert dumped["incident"]["occurredAt"] == "2026-01-01T00:00:00Z"
