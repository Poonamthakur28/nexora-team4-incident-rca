from typing import Any

from pydantic import AwareDatetime

from app.modules.incidents.contracts import InvestigationId
from app.shared.contract import ContractModel
from app.shared.identifiers import ExternalRef, Team4EntityId


class InvestigationHistoryEntry(ContractModel):
    id: Team4EntityId
    investigation_id: InvestigationId
    event_type: str
    actor_ref: ExternalRef | None = None
    occurred_at: AwareDatetime
    details: dict[str, Any]
