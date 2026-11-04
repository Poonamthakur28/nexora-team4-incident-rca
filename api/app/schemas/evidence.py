from datetime import datetime

from pydantic import AwareDatetime, field_validator, model_validator

from app.modules.evidence_collection.contracts import (
    EvidenceAvailability,
    EvidenceType,
    normalize_source_label,
)
from app.modules.evidence_collection.validation import validate_availability_shape, validate_opaque_content_reference
from app.modules.incidents.contracts import as_utc, normalize_required_text
from app.shared.contract import ContractModel
from app.shared.identifiers import ExternalRef


class RecordManualEvidenceRequest(ContractModel):
    """HTTP body for manual Evidence. Incident id comes from the path.

    Organization and actor are taken from stand-in headers, never from this body.
    """

    evidence_type: EvidenceType
    description: str
    source_label: str
    captured_at: AwareDatetime
    availability: EvidenceAvailability
    external_source_ref: ExternalRef | None = None
    content_ref: str | None = None

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
        return validate_opaque_content_reference(value)

    @field_validator("captured_at")
    @classmethod
    def _captured_at(cls, value: datetime) -> datetime:
        return as_utc(value)

    @model_validator(mode="after")
    def _availability_shape(self) -> "RecordManualEvidenceRequest":
        validate_availability_shape(self.availability, self.content_ref)
        return self
