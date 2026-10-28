from typing import Literal

from pydantic import AwareDatetime

from app.shared.contract import ContractModel
from app.shared.identifiers import ExternalRef


class IncidentIntake(ContractModel):
    source: Literal["manual", "fixture"]
    external_incident_ref: ExternalRef | None = None
    title: str
    description: str
    occurred_at: AwareDatetime
