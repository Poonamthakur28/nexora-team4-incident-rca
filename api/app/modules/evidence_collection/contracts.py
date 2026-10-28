from pydantic import AwareDatetime

from app.modules.incidents.contracts import InvestigationId
from app.shared.contract import ContractModel
from app.shared.identifiers import ExternalRef, Team4EntityId


class EvidenceSubmission(ContractModel):
    incident_id: Team4EntityId
    investigation_id: InvestigationId | None = None
    description: str
    source_label: str
    captured_at: AwareDatetime
    external_source_ref: ExternalRef | None = None
