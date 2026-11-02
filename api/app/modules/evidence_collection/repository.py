"""Append-only Evidence storage port and a process-local implementation."""

from dataclasses import dataclass, field
from typing import Protocol

from app.modules.evidence_collection.contracts import Evidence, EvidenceRecordedAuditIntent
from app.modules.evidence_collection.errors import (
    EvidenceNotFound,
    InconsistentEvidenceRecord,
    InvalidEvidenceInput,
)
from app.shared.identifiers import Team4EntityId


class EvidenceRepository(Protocol):
    """Append-only Evidence metadata storage scoped by organization.

    `add` stores Evidence and its local, undelivered audit intent together. A
    rejected operation writes neither. The canonical Evidence wire record has no
    organization field, so organization ownership remains internal to storage.
    """

    def add(
        self,
        evidence: Evidence,
        *,
        organization_id: str,
        audit_intent: EvidenceRecordedAuditIntent,
    ) -> None:
        """Atomically store a new Evidence record and its local audit intent."""

    def get(self, evidence_id: Team4EntityId, organization_id: str) -> Evidence | None:
        """Return visible Evidence, or None for a missing or foreign record."""

    def list_for_incident(
        self, incident_id: Team4EntityId, organization_id: str
    ) -> tuple[Evidence, ...]:
        """Return visible Evidence for an Incident in insertion order."""

    def list_audit_intents(
        self, evidence_id: Team4EntityId, organization_id: str
    ) -> tuple[EvidenceRecordedAuditIntent, ...]:
        """Return the locally stored, undelivered audit intent for visible Evidence."""


@dataclass
class _StoredEvidence:
    evidence: Evidence
    audit_intents: list[EvidenceRecordedAuditIntent] = field(default_factory=list)


class InMemoryEvidenceRepository:
    """Process-local, append-only Evidence store with no module-level mutable state."""

    def __init__(self) -> None:
        self._records: dict[str, tuple[str, _StoredEvidence]] = {}

    def add(
        self,
        evidence: Evidence,
        *,
        organization_id: str,
        audit_intent: EvidenceRecordedAuditIntent,
    ) -> None:
        if not organization_id or not organization_id.strip():
            raise InvalidEvidenceInput("organization_id must be non-empty.")
        key = str(evidence.id)
        if key in self._records:
            raise InvalidEvidenceInput("An Evidence record with this id already exists.")
        _check_audit_intent(evidence, organization_id, audit_intent)

        stored_evidence = evidence.model_copy(deep=True)
        stored_intent = audit_intent.model_copy(deep=True)
        self._records[key] = (organization_id, _StoredEvidence(stored_evidence, [stored_intent]))

    def get(self, evidence_id: Team4EntityId, organization_id: str) -> Evidence | None:
        record = self._visible(evidence_id, organization_id)
        return record.evidence.model_copy(deep=True) if record is not None else None

    def list_for_incident(
        self, incident_id: Team4EntityId, organization_id: str
    ) -> tuple[Evidence, ...]:
        return tuple(
            stored.evidence.model_copy(deep=True)
            for owner, stored in self._records.values()
            if owner == organization_id and stored.evidence.incident_id == incident_id
        )

    def list_audit_intents(
        self, evidence_id: Team4EntityId, organization_id: str
    ) -> tuple[EvidenceRecordedAuditIntent, ...]:
        record = self._visible(evidence_id, organization_id)
        if record is None:
            raise EvidenceNotFound(str(evidence_id))
        return tuple(intent.model_copy(deep=True) for intent in record.audit_intents)

    def _visible(self, evidence_id: Team4EntityId, organization_id: str) -> _StoredEvidence | None:
        record = self._records.get(str(evidence_id))
        if record is None:
            return None
        owner, stored = record
        return stored if owner == organization_id else None


def _check_audit_intent(
    evidence: Evidence, organization_id: str, audit_intent: EvidenceRecordedAuditIntent
) -> None:
    if (
        str(audit_intent.resource_id) != str(evidence.id)
        or audit_intent.organization_id != organization_id
        or audit_intent.data.evidence_type != evidence.evidence_type
        or audit_intent.data.availability != evidence.availability
        or audit_intent.occurred_at != evidence.collected_at
    ):
        raise InconsistentEvidenceRecord("The audit intent does not describe the Evidence record.")
    if (
        evidence.provenance.origin_type == "manual"
        and audit_intent.actor_ref != evidence.provenance.collector_ref
    ):
        raise InconsistentEvidenceRecord(
            "The audit intent actor does not match the manual Evidence collector."
        )
