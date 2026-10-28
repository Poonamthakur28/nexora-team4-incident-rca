from typing import Literal

from app.modules.incidents.contracts import InvestigationId
from app.shared.contract import ContractModel
from app.shared.identifiers import Team4EntityId


class FixProposalDraft(ContractModel):
    investigation_id: InvestigationId
    candidate_id: Team4EntityId
    summary: str
    expected_outcome: str
    risks: list[str]
    requires_human_review: Literal[True]
