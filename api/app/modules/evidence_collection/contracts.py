from datetime import datetime
from typing import Literal

from pydantic import AwareDatetime, field_serializer, field_validator, model_validator

from app.modules.incidents.contracts import InvestigationId
from app.modules.incidents.contracts import (
    as_utc,
    normalize_optional_text,
    normalize_required_text,
    serialize_utc_z,
)
from app.shared.contract import ContractModel
from app.shared.identifiers import ExternalRef, Team4EntityId


class EvidenceSubmission(ContractModel):
    incident_id: Team4EntityId
    investigation_id: InvestigationId | None = None
    description: str
    source_label: str
    captured_at: AwareDatetime
    external_source_ref: ExternalRef | None = None


# Canonical types below follow CT-04 §7 (Proposed, not agreed). They sit beside
# EvidenceSubmission; they do not replace that existing manual-submission DTO.
EvidenceType = Literal["log", "metric", "trace", "event", "other"]
EvidenceAvailability = Literal["available", "partial", "unavailable"]
ProvenanceOrigin = Literal["observation", "tool_execution", "manual"]
SOURCE_LABEL_MAX_LENGTH = 255


def normalize_source_label(value: str) -> str:
    """Trim and enforce the CT-04 source-label length of 1–255 (D-15 Proposed)."""
    trimmed = value.strip()
    if not trimmed or len(trimmed) > SOURCE_LABEL_MAX_LENGTH:
        raise ValueError("source_label must be between 1 and 255 characters after trimming")
    return trimmed


class Provenance(ContractModel):
    """Evidence provenance shape from CT-04 §7.4.

    This validates record shape only. Connector authentication and source-account
    binding remain D-21/D-23 work and are not implemented here.
    """

    origin_type: ProvenanceOrigin
    provider: str | None
    source_event_id: str | None
    source_account_ref: ExternalRef | None
    collector_ref: ExternalRef | None

    @field_validator("provider", "source_event_id")
    @classmethod
    def _optional_text(cls, value: str | None) -> str | None:
        """Trim and treat blank as absent, so a required check below rejects it.

        ExternalRef fields (source_account_ref, collector_ref) are unchanged
        here; their owner/id blank-part behavior stays tied to D-04 (Proposed).
        """
        return normalize_optional_text(value)

    @model_validator(mode="after")
    def _origin_shape(self) -> "Provenance":
        from app.modules.evidence_collection.validation import validate_provenance

        validate_provenance(self)
        return self


class Evidence(ContractModel):
    """Canonical Evidence metadata from CT-04 §7.3 (Proposed, not agreed)."""

    id: Team4EntityId
    incident_id: Team4EntityId
    investigation_id: InvestigationId | None
    triggered_by_observation_id: Team4EntityId | None
    evidence_type: EvidenceType
    description: str
    source_label: str
    external_source_ref: ExternalRef | None
    content_ref: str | None
    captured_at: AwareDatetime
    collected_at: AwareDatetime
    availability: EvidenceAvailability
    provenance: Provenance

    @field_validator("id", "incident_id")
    @classmethod
    def _id(cls, value: Team4EntityId) -> Team4EntityId:
        if not value.strip():
            raise ValueError("id must be non-empty")
        return value

    @field_validator("description")
    @classmethod
    def _description(cls, value: str) -> str:
        return normalize_required_text(value)

    @field_validator("source_label")
    @classmethod
    def _source_label(cls, value: str) -> str:
        return normalize_source_label(value)

    @field_validator("content_ref")
    @classmethod
    def _content_ref(cls, value: str | None) -> str | None:
        from app.modules.evidence_collection.validation import validate_opaque_content_reference

        return validate_opaque_content_reference(value)

    @field_validator("captured_at", "collected_at")
    @classmethod
    def _timestamps(cls, value: datetime) -> datetime:
        return as_utc(value)

    @field_serializer("captured_at", "collected_at", when_used="json")
    def _serialize_timestamps(self, value: datetime) -> str:
        return serialize_utc_z(value)

    @model_validator(mode="after")
    def _availability_shape(self) -> "Evidence":
        from app.modules.evidence_collection.validation import validate_availability_shape

        validate_availability_shape(self.availability, self.content_ref)
        return self


class RecordManualEvidence(ContractModel):
    """Caller input for manual Evidence.

    Identity, organization, collection time and provenance are system-managed.
    Non-null investigation and Observation relationships are unsupported until
    those entities and workflows exist.
    """

    incident_id: Team4EntityId
    investigation_id: InvestigationId | None = None
    triggered_by_observation_id: Team4EntityId | None = None
    evidence_type: EvidenceType
    description: str
    source_label: str
    external_source_ref: ExternalRef | None = None
    content_ref: str | None = None
    captured_at: AwareDatetime
    availability: EvidenceAvailability

    @field_validator("incident_id")
    @classmethod
    def _incident_id(cls, value: Team4EntityId) -> Team4EntityId:
        if not value.strip():
            raise ValueError("incident_id must be non-empty")
        return value

    @field_validator("description")
    @classmethod
    def _description(cls, value: str) -> str:
        return normalize_required_text(value)

    @field_validator("source_label")
    @classmethod
    def _source_label(cls, value: str) -> str:
        return normalize_source_label(value)

    @field_validator("content_ref")
    @classmethod
    def _content_ref(cls, value: str | None) -> str | None:
        from app.modules.evidence_collection.validation import validate_opaque_content_reference

        return validate_opaque_content_reference(value)

    @field_validator("captured_at")
    @classmethod
    def _captured_at(cls, value: datetime) -> datetime:
        return as_utc(value)

    @model_validator(mode="after")
    def _availability_shape(self) -> "RecordManualEvidence":
        from app.modules.evidence_collection.validation import validate_availability_shape

        validate_availability_shape(self.availability, self.content_ref)
        return self


class RecordObservationEventEvidence(ContractModel):
    """Caller input for observation-origin event Evidence (F-04a).

    Organization, actor, collection time, Evidence id, `evidence_type`, and
    `availability` are system-managed. `triggered_by_observation_id` is not a
    field: F-04a event Evidence keeps it null. Provenance must already be the
    stored Observation provenance; this command does not invent one.
    """

    incident_id: Team4EntityId
    description: str
    source_label: str
    content_ref: str
    captured_at: AwareDatetime
    provenance: Provenance
    external_source_ref: ExternalRef | None = None

    @field_validator("incident_id")
    @classmethod
    def _incident_id(cls, value: Team4EntityId) -> Team4EntityId:
        if not value.strip():
            raise ValueError("incident_id must be non-empty")
        return value

    @field_validator("description")
    @classmethod
    def _description(cls, value: str) -> str:
        return normalize_required_text(value)

    @field_validator("source_label")
    @classmethod
    def _source_label(cls, value: str) -> str:
        return normalize_source_label(value)

    @field_validator("content_ref")
    @classmethod
    def _content_ref(cls, value: str) -> str:
        from app.modules.evidence_collection.validation import validate_opaque_content_reference

        verified = validate_opaque_content_reference(value)
        if verified is None:
            raise ValueError("content_ref is required")
        return verified

    @field_validator("captured_at")
    @classmethod
    def _captured_at(cls, value: datetime) -> datetime:
        return as_utc(value)

    @model_validator(mode="after")
    def _observation_event_shape(self) -> "RecordObservationEventEvidence":
        from app.modules.evidence_collection.validation import validate_availability_shape

        if self.provenance.origin_type != "observation":
            raise ValueError("Observation-origin Evidence requires observation provenance.")
        validate_availability_shape("available", self.content_ref)
        return self


class EvidenceRecordedData(ContractModel):
    """Provisional local audit payload; CT-04/CT-06 do not define it yet."""

    evidence_type: EvidenceType
    availability: EvidenceAvailability


class EvidenceRecordedAuditIntent(ContractModel):
    """In-memory, undelivered `evidence.recorded` audit intent.

    Its data payload is provisional because CT-04 requires the event but does
    not define the payload, and CT-06 owns the delivery envelope.
    """

    event_id: Team4EntityId
    event_type: Literal["evidence.recorded"]
    organization_id: str
    actor_ref: ExternalRef
    resource_type: Literal["evidence"]
    resource_id: Team4EntityId
    occurred_at: AwareDatetime
    # Optional, unlike RCA-001's IncidentAuditIntent.correlation_id. RCA-001's
    # IncidentRequestContext.correlation_id is itself optional; IncidentService
    # separately enforces it as a business rule only for change_status. CT-04
    # and this milestone define no equivalent requirement for evidence.recorded,
    # so EvidenceRecordedAuditIntent stays consistent with the trusted
    # context's own shape instead of inventing a new requirement.
    correlation_id: str | None
    data: EvidenceRecordedData

    @field_validator("event_id", "resource_id")
    @classmethod
    def _id(cls, value: Team4EntityId) -> Team4EntityId:
        if not value.strip():
            raise ValueError("id must be non-empty")
        return value

    @field_validator("organization_id")
    @classmethod
    def _organization_id(cls, value: str) -> str:
        return normalize_required_text(value)

    @field_validator("correlation_id")
    @classmethod
    def _correlation_id(cls, value: str | None) -> str | None:
        return normalize_optional_text(value)

    @field_validator("occurred_at")
    @classmethod
    def _occurred_at(cls, value: datetime) -> datetime:
        return as_utc(value)

    @field_serializer("occurred_at", when_used="json")
    def _serialize_occurred_at(self, value: datetime) -> str:
        return serialize_utc_z(value)
