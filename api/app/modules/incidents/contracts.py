from datetime import UTC, datetime
from typing import Literal, NewType

from pydantic import AwareDatetime, field_serializer, field_validator, model_validator

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


# Canonical types below follow CT-04 §6.1 and §6.4 (Proposed, not agreed).
# They sit beside IncidentSummary; they do not replace it.

IncidentStatus = Literal["open", "investigating", "resolved", "closed"]
IncidentSeverity = Literal["critical", "high", "medium", "low"]
TITLE_MAX_LENGTH = 255


def normalize_title(value: str) -> str:
    """Trim and enforce the CT-04 title length of 1–255 characters (D-15 Proposed)."""
    trimmed = value.strip()
    if not trimmed or len(trimmed) > TITLE_MAX_LENGTH:
        raise ValueError("title must be between 1 and 255 characters after trimming")
    return trimmed


def normalize_optional_text(value: str | None) -> str | None:
    """Store empty optional text as null. No maximum is defined (CT-04 D-15)."""
    if value is None:
        return None
    trimmed = value.strip()
    return trimmed or None


def normalize_required_text(value: str) -> str:
    trimmed = value.strip()
    if not trimmed:
        raise ValueError("value must be non-empty after trimming")
    return trimmed


def require_unique_external_refs(value: list[ExternalRef]) -> list[ExternalRef]:
    seen: set[tuple[str, str]] = set()
    for ref in value:
        key = (ref.owner, ref.id)
        if key in seen:
            raise ValueError("external_refs must be unique by owner and id")
        seen.add(key)
    return value


def as_utc(value: datetime) -> datetime:
    if value.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")
    return value.astimezone(UTC)


def serialize_utc_z(value: datetime) -> str:
    """Serialize a UTC instant as RFC 3339 with a Z suffix (CT-04 §6.1, D-16 Proposed)."""
    text = as_utc(value).isoformat()
    if text.endswith("+00:00"):
        return f"{text[:-6]}Z"
    return text


class CreateIncident(ContractModel):
    """Caller input for a manual incident.

    Identity, organization, initial status, and timestamps are system-managed.
    Those keys are rejected because this model forbids extra fields.
    """

    title: str
    severity: IncidentSeverity
    external_refs: list[ExternalRef]
    description: str | None = None
    service_ref: ExternalRef | None = None
    assigned_team_ref: ExternalRef | None = None
    assigned_user_ref: ExternalRef | None = None

    @field_validator("title")
    @classmethod
    def _title(cls, value: str) -> str:
        return normalize_title(value)

    @field_validator("description")
    @classmethod
    def _description(cls, value: str | None) -> str | None:
        return normalize_optional_text(value)

    @field_validator("external_refs")
    @classmethod
    def _external_refs(cls, value: list[ExternalRef]) -> list[ExternalRef]:
        return require_unique_external_refs(value)


class AssignIncident(ContractModel):
    """Opaque assignment update. Omitted fields are left unchanged; explicit null clears.

    CT-04 does not define assignment update semantics. The omitted/null rule, whether a
    closed incident may be reassigned, whether empty `ExternalRef` parts are rejected
    (D-04), and whether assignment produces history or an audit intent are unresolved.
    """

    assigned_team_ref: ExternalRef | None = None
    assigned_user_ref: ExternalRef | None = None


class ChangeIncidentStatus(ContractModel):
    """Requested status change.

    Actor and correlation come from the trusted context; the current status comes from stored state.
    """

    to_status: IncidentStatus
    reason: str

    @field_validator("reason")
    @classmethod
    def _reason(cls, value: str) -> str:
        return normalize_required_text(value)


class Incident(ContractModel):
    """Canonical Incident (CT-04 §6.1). organization_id is an opaque tenant id, not a Team 1 UUID."""

    id: Team4EntityId
    organization_id: str
    title: str
    description: str | None
    severity: IncidentSeverity
    status: IncidentStatus
    service_ref: ExternalRef | None
    assigned_team_ref: ExternalRef | None
    assigned_user_ref: ExternalRef | None
    external_refs: list[ExternalRef]
    created_at: AwareDatetime
    updated_at: AwareDatetime

    @field_validator("id")
    @classmethod
    def _id(cls, value: Team4EntityId) -> Team4EntityId:
        # D-01 is not agreed, so only emptiness is checked, not UUID format.
        if not value.strip():
            raise ValueError("id must be non-empty")
        return value

    @field_validator("organization_id")
    @classmethod
    def _organization_id(cls, value: str) -> str:
        return normalize_required_text(value)

    @field_validator("title")
    @classmethod
    def _title(cls, value: str) -> str:
        return normalize_title(value)

    @field_validator("description")
    @classmethod
    def _description(cls, value: str | None) -> str | None:
        return normalize_optional_text(value)

    @field_validator("external_refs")
    @classmethod
    def _external_refs(cls, value: list[ExternalRef]) -> list[ExternalRef]:
        return require_unique_external_refs(value)

    @field_validator("created_at", "updated_at")
    @classmethod
    def _timestamps(cls, value: datetime) -> datetime:
        return as_utc(value)

    @field_serializer("created_at", "updated_at", when_used="json")
    def _serialize_timestamps(self, value: datetime) -> str:
        return serialize_utc_z(value)

    @model_validator(mode="after")
    def _updated_at_not_before_created_at(self) -> "Incident":
        if self.updated_at < self.created_at:
            raise ValueError("updated_at must be greater than or equal to created_at")
        return self


class IncidentStatusTransition(ContractModel):
    """One status change (CT-04 §6.4).

    occurred_at is when the change took effect, not when the incident occurred.
    """

    incident_id: Team4EntityId
    from_status: IncidentStatus
    to_status: IncidentStatus
    actor_ref: ExternalRef
    reason: str
    correlation_id: str
    occurred_at: AwareDatetime

    @field_validator("reason", "correlation_id")
    @classmethod
    def _required_text(cls, value: str) -> str:
        return normalize_required_text(value)

    @field_validator("occurred_at")
    @classmethod
    def _occurred_at(cls, value: datetime) -> datetime:
        return as_utc(value)

    @field_serializer("occurred_at", when_used="json")
    def _serialize_occurred_at(self, value: datetime) -> str:
        return serialize_utc_z(value)


class IncidentStatusChangedData(ContractModel):
    from_status: IncidentStatus
    to_status: IncidentStatus
    reason: str

    @field_validator("reason")
    @classmethod
    def _reason(cls, value: str) -> str:
        return normalize_required_text(value)


class IncidentAuditIntent(ContractModel):
    """In-memory audit intent for incident.status_changed.

    CT-06 owns the delivery envelope. This value is not an outbox row and has not been
    delivered to an audit sink.
    """

    event_id: Team4EntityId
    event_type: Literal["incident.status_changed"]
    organization_id: str
    actor_ref: ExternalRef
    resource_type: Literal["incident"]
    resource_id: Team4EntityId
    occurred_at: AwareDatetime
    correlation_id: str
    data: IncidentStatusChangedData

    @field_validator("organization_id", "correlation_id")
    @classmethod
    def _required_text(cls, value: str) -> str:
        return normalize_required_text(value)

    @field_validator("occurred_at")
    @classmethod
    def _occurred_at(cls, value: datetime) -> datetime:
        return as_utc(value)

    @field_serializer("occurred_at", when_used="json")
    def _serialize_occurred_at(self, value: datetime) -> str:
        return serialize_utc_z(value)
