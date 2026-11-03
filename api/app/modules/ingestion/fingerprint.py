"""Payload fingerprinting for a constructed Observation (CT-04 §10.3, Proposed).

The digest algorithm is injected. This module does not choose a production hash
and does not compare fingerprints to stored rows.
"""

import json
from dataclasses import dataclass

from app.modules.ingestion.contracts import Observation
from app.modules.ingestion.errors import IngestionConfigurationError
from app.modules.ingestion.normalization import (
    IdempotencyIdentity,
    build_idempotency_identity,
    canonical_business_payload,
)
from app.modules.ingestion.ports import PayloadHasher


@dataclass(frozen=True, slots=True)
class PayloadFingerprint:
    """Digest of the canonical business payload. The algorithm is not agreed (D-10)."""

    digest: bytes


@dataclass(frozen=True, slots=True)
class NormalizedObservation:
    """In-memory identity, fingerprint, and canonical bytes. Nothing is stored."""

    identity: IdempotencyIdentity
    fingerprint: PayloadFingerprint
    canonical_payload: bytes


def normalize_observation(
    observation: Observation,
    organization_id: str,
    hasher: PayloadHasher,
) -> NormalizedObservation:
    """Return identity and fingerprint for a constructed Observation.

    Stage 1 authorization is assumed to have already passed. This function does
    not reserve an identity, detect duplicates, or create a receipt.
    """
    canonical_payload = serialize_canonical_payload(canonical_business_payload(observation))
    return NormalizedObservation(
        identity=build_idempotency_identity(observation, organization_id),
        fingerprint=PayloadFingerprint(digest=_digest(hasher, canonical_payload)),
        canonical_payload=canonical_payload,
    )


def serialize_canonical_payload(payload: dict[str, object]) -> bytes:
    """Encode the business object as sorted camelCase JSON without extra spaces."""
    return json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _digest(hasher: PayloadHasher, canonical_payload: bytes) -> bytes:
    try:
        digest = hasher.digest(canonical_payload)
    except Exception as exc:
        raise IngestionConfigurationError("The payload hasher failed.") from exc
    if not isinstance(digest, bytes):
        raise IngestionConfigurationError("The payload hasher must return bytes.")
    return digest
