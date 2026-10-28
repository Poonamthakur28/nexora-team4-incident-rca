from pydantic import AwareDatetime

from app.shared.contract import ContractModel
from app.shared.identifiers import Team4EntityId


class EvidenceAssessment(ContractModel):
    evidence_id: Team4EntityId
    summary: str
    relevance: float
    limitations: list[str]
    processed_at: AwareDatetime
