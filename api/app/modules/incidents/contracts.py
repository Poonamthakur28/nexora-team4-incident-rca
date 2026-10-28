from typing import NewType

from pydantic import AwareDatetime

from app.shared.contract import ContractModel
from app.shared.identifiers import ExternalRef, Team4EntityId

InvestigationId = NewType("InvestigationId", Team4EntityId)
"""Canonical investigation id.

Owner: RCA-001 Incident Management.
Unresolved: `docs/erd/team4-erd.md` proposes `rca_investigation`, but no entity,
foreign key, or lifecycle is approved. This alias adds no module and no database model.
"""


def as_investigation_id(value: str) -> InvestigationId:
    return InvestigationId(Team4EntityId(value))


class IncidentSummary(ContractModel):
    id: Team4EntityId
    title: str
    status: str
    created_at: AwareDatetime
    external_refs: list[ExternalRef] | None = None
