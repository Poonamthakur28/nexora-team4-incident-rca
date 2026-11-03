"""Canonical observation identity and business payload (CT-04 §10, Proposed).

Identity is the four D-09 dimensions. The payload is the D-10 business object
before hashing. Neither value is persisted. The hash algorithm is unset.
"""

from dataclasses import dataclass

from app.modules.incidents.contracts import serialize_utc_z
from app.modules.ingestion.contracts import Observation
from app.shared.identifiers import ExternalRef


@dataclass(frozen=True, slots=True)
class IdempotencyIdentity:
    """Structured provider-event identity. This is not a hash and not a database key."""

    organization_id: str
    source: str
    source_account_ref: ExternalRef
    source_event_id: str


def build_idempotency_identity(
    observation: Observation, organization_id: str
) -> IdempotencyIdentity:
    """Copy the four identity dimensions from a constructed Observation.

    `organization_id` is the trusted value from the caller context. It is not
    read from the observation body. Format is D-02 (Needs Team 1 Input).
    `source_account_ref` is the stored ExternalRef; that shape is provisional
    (D-09, D-23). `source_event_id` is kept exactly, including surrounding space.
    """
    return IdempotencyIdentity(
        organization_id=organization_id,
        source=observation.source,
        source_account_ref=observation.source_account_ref,
        source_event_id=observation.source_event_id,
    )


def canonical_business_payload(observation: Observation) -> dict[str, object]:
    """Build the D-10 business object from stored Observation values.

    Optional fields are always present so an omitted input and an explicit null
    serialize the same way (D-17 Proposed). `collectorRef` and delivery
    metadata are omitted.
    """
    return {
        "description": observation.description,
        "externalSeverity": observation.external_severity,
        "occurredAt": serialize_utc_z(observation.occurred_at),
        "provenance": _provenance_payload(observation),
        "serviceRef": _external_ref_payload(observation.service_ref),
        "source": observation.source,
        "sourceAccountRef": _external_ref_payload(observation.source_account_ref),
        "sourceEventId": observation.source_event_id,
        "title": observation.title,
    }


def _provenance_payload(observation: Observation) -> dict[str, object]:
    provenance = observation.provenance
    return {
        "originType": provenance.origin_type,
        "provider": provenance.provider,
        "sourceAccountRef": _external_ref_payload(provenance.source_account_ref),
        "sourceEventId": provenance.source_event_id,
    }


def _external_ref_payload(ref: ExternalRef | None) -> dict[str, str] | None:
    if ref is None:
        return None
    return {"id": ref.id, "owner": ref.owner}
