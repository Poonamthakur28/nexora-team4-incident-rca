from typing import Literal, Protocol

from pydantic import AwareDatetime

from app.modules.incidents.contracts import InvestigationId
from app.shared.contract import ContractModel
from app.shared.identifiers import ExternalRef, Team4EntityId

EvidencePolarity = Literal["supports", "contradicts", "context"]


class IncidentContext(ContractModel):
    external_incident_ref: ExternalRef | None = None
    summary: str
    occurred_at: AwareDatetime


class ContextEvidence(ContractModel):
    evidence_id: Team4EntityId
    description: str
    source_ref: ExternalRef | None = None


class InvestigationContext(ContractModel):
    investigation_id: InvestigationId
    incident: IncidentContext
    evidence: list[ContextEvidence]


class CandidateEvidenceLink(ContractModel):
    evidence_id: Team4EntityId
    polarity: EvidencePolarity
    explanation: str


class RootCauseCandidateDraft(ContractModel):
    title: str
    rationale: str
    confidence: float
    uncertainty: list[str]
    missing_information: list[str]
    evidence: list[CandidateEvidenceLink]
    status: Literal["proposed"]


class AiRcaAgent(Protocol):
    async def analyze(self, context: InvestigationContext) -> list[RootCauseCandidateDraft]: ...
