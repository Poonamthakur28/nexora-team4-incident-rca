from typing import Literal

from pydantic import AwareDatetime, field_validator, model_validator

from app.modules.evidence_collection.contracts import Provenance
from app.modules.incidents.contracts import (
    as_utc,
    normalize_optional_text,
    normalize_required_text,
    normalize_title,
)
from app.shared.contract import ContractModel
from app.shared.identifiers import ExternalRef


class IncidentIntake(ContractModel):
    source: Literal["manual", "fixture"]
    external_incident_ref: ExternalRef | None = None
    title: str
    description: str
    occurred_at: AwareDatetime


class Observation(ContractModel):
    source: str
    source_account_ref: ExternalRef
    source_event_id: str
    occurred_at: AwareDatetime
    occurred_at_supplied: str | None = None
    received_at: AwareDatetime
    submitted_at: AwareDatetime | None = None
    service_ref: ExternalRef | None = None
    external_severity: str | None = None
    title: str
    description: str | None = None
    provenance: Provenance
    idempotency_key: str
    correlation_id: str

    @field_validator("source")
    @classmethod
    def validate_source(cls, value: str) -> str:
        return normalize_required_text(value)

    @field_validator("source_event_id", "idempotency_key", "correlation_id")
    @classmethod
    def validate_opaque_identifier(cls, value: str) -> str:
        # Opaque values are not trimmed. A value that is empty after trimming is
        # rejected; any other value is kept exactly (CT-04 §8.2, D-09 Proposed).
        if not value.strip():
            raise ValueError("Value must be non-empty")
        return value

    @field_validator("external_severity")
    @classmethod
    def validate_external_severity(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return normalize_required_text(value)

    @field_validator("title")
    @classmethod
    def validate_title(cls, value: str) -> str:
        return normalize_title(value)

    @field_validator("description")
    @classmethod
    def validate_description(cls, value: str | None) -> str | None:
        return normalize_optional_text(value)

    @field_validator("occurred_at", "received_at", "submitted_at")
    @classmethod
    def normalize_timestamps(cls, value: AwareDatetime | None) -> AwareDatetime | None:
        if value is None:
            return None
        return as_utc(value)

    @model_validator(mode="after")
    def validate_observation_bindings(self) -> "Observation":
        if self.provenance.origin_type != "observation":
            raise ValueError("Observation provenance originType must be 'observation'")

        refs = [self.source_account_ref]
        if self.service_ref is not None:
            refs.append(self.service_ref)

        for ref in refs:
            if not ref.owner.strip() or not ref.id.strip():
                raise ValueError("ExternalRef owner and id must be non-empty")

        return self
