from pydantic import AwareDatetime

from app.shared.contract import ContractModel
from app.shared.identifiers import Team4EntityId


class TimelineEntry(ContractModel):
    id: Team4EntityId
    incident_id: Team4EntityId
    occurred_at: AwareDatetime
    recorded_at: AwareDatetime
    label: str
    detail: str | None = None
