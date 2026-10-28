from typing import Literal

from pydantic import AwareDatetime

from app.shared.contract import ContractModel
from app.shared.identifiers import ExternalRef, Team4EntityId

ReviewDecision = Literal["pending", "approved", "rejected", "needs_changes"]


class HumanReview(ContractModel):
    id: Team4EntityId
    subject_type: Literal["candidate", "fix_proposal", "resolution"]
    subject_id: Team4EntityId
    decision: ReviewDecision
    reviewer_ref: ExternalRef | None = None
    decided_at: AwareDatetime | None = None
    rationale: str | None = None
