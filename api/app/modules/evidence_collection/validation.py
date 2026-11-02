"""Pure Evidence validation rules from CT-04 §7 (Proposed, not agreed)."""

from typing import Protocol

from app.modules.evidence_collection.errors import InvalidEvidenceInput


class _ProvenanceShape(Protocol):
    origin_type: str
    provider: str | None
    source_event_id: str | None
    source_account_ref: object | None
    collector_ref: object | None


def validate_opaque_content_reference(value: str | None) -> str | None:
    """Preserve `content_ref` exactly; it is opaque and must not be rewritten.

    A `None` value is passed through unchanged. Any non-null value that is
    empty or whitespace-only is rejected outright rather than silently
    converted to `None`, because CT-04 treats a present `content_ref` as a
    caller-asserted reference, not free text to normalize. A non-blank value,
    including any internal or surrounding whitespace, is returned unchanged.
    """
    if value is None:
        return None
    if not value.strip():
        raise ValueError("content_ref must not be empty or whitespace-only")
    return value


def validate_availability_shape(availability: str, content_ref: str | None) -> None:
    """Enforce CT-04's availability/content-ref relationship, not storage validity."""
    if availability in {"available", "partial"} and content_ref is None:
        raise ValueError(f"{availability} Evidence requires content_ref")
    if availability == "unavailable" and content_ref is not None:
        raise ValueError("unavailable Evidence requires content_ref to be null")


def validate_provenance(provenance: _ProvenanceShape) -> None:
    """Validate the three origin-specific CT-04 §7.4 shapes.

    Authentication, source-account authorization, and observation binding are
    deliberately outside this shape-only validation.
    """
    if provenance.origin_type == "observation":
        _require(provenance.provider, "provider", provenance.origin_type)
        _require(provenance.source_event_id, "source_event_id", provenance.origin_type)
        _require(provenance.source_account_ref, "source_account_ref", provenance.origin_type)
        _require(provenance.collector_ref, "collector_ref", provenance.origin_type)
        return
    if provenance.origin_type == "tool_execution":
        _require(provenance.provider, "provider", provenance.origin_type)
        _require(provenance.collector_ref, "collector_ref", provenance.origin_type)
        return
    if provenance.origin_type == "manual":
        # CT-04 v0.2 (line ~452): manual provider is null or a user-declared
        # label (D-07, Proposed). provider is intentionally unconstrained here;
        # EvidenceService still defaults the manual-command path to None.
        if provenance.source_event_id is not None:
            raise ValueError("manual provenance requires source_event_id to be null")
        if provenance.source_account_ref is not None:
            raise ValueError("manual provenance requires source_account_ref to be null")
        _require(provenance.collector_ref, "collector_ref", provenance.origin_type)
        return
    raise InvalidEvidenceInput("Unsupported provenance origin.")


def _require(value: object | None, field: str, origin: str) -> None:
    if value is None:
        raise ValueError(f"{origin} provenance requires {field}")
