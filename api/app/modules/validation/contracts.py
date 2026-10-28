from typing import Literal

from pydantic import AwareDatetime

from app.shared.contract import ContractModel
from app.shared.identifiers import Team4EntityId

ValidationState = Literal["not_started", "pending", "passed", "failed", "blocked"]


class ValidationSummary(ContractModel):
    proposal_id: Team4EntityId
    state: ValidationState
    completed_at: AwareDatetime | None = None
    notes: list[str]
