from typing import Literal

from app.modules.ai_rca.contracts import CandidateEvidenceLink
from app.modules.incidents.contracts import InvestigationId
from app.shared.contract import ContractModel
from app.shared.identifiers import Team4EntityId


class RootCauseCandidate(ContractModel):
    id: Team4EntityId
    investigation_id: InvestigationId
    title: str
    rationale: str
    confidence: float
    uncertainty: list[str]
    missing_information: list[str]
    evidence: list[CandidateEvidenceLink]
    status: Literal["proposed"]
    review_required: Literal[True]
