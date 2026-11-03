from datetime import datetime
from typing import Literal

from pydantic import AwareDatetime, field_serializer, field_validator

from app.modules.incidents.contracts import as_utc, normalize_required_text, serialize_utc_z
from app.shared.contract import ContractModel
from app.shared.identifiers import Team4EntityId

TimelineCategory = Literal["incident.opened", "incident.status_changed", "evidence.recorded"]
TimelineSourceKind = Literal["incident", "status_transition", "evidence"]


class TimelineEntry(ContractModel):
    """Read-time incident chronology entry. This is not a stored row or an audit intent."""

    id: Team4EntityId
    organization_id: str
    incident_id: Team4EntityId
    category: TimelineCategory
    source_kind: TimelineSourceKind
    source_id: str
    occurred_at: AwareDatetime
    recorded_at: AwareDatetime
    label: str
    detail: str | None = None

    @field_validator("id", "incident_id")
    @classmethod
    def _id(cls, value: Team4EntityId) -> Team4EntityId:
        if not value.strip():
            raise ValueError("id must be non-empty")
        return value

    @field_validator("organization_id", "source_id", "label")
    @classmethod
    def _required_text(cls, value: str) -> str:
        return normalize_required_text(value)

    @field_validator("occurred_at", "recorded_at")
    @classmethod
    def _timestamps(cls, value: datetime) -> datetime:
        return as_utc(value)

    @field_serializer("occurred_at", "recorded_at", when_used="json")
    def _serialize_timestamps(self, value: datetime) -> str:
        return serialize_utc_z(value)
