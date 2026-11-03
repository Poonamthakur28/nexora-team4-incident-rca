"""RCA-004 Evidence Collection operations without persistence or transport."""

from collections.abc import Callable
from datetime import UTC, datetime
from uuid import uuid4

from app.modules.evidence_collection.contracts import (
    Evidence,
    EvidenceRecordedAuditIntent,
    EvidenceRecordedData,
    Provenance,
    RecordManualEvidence,
    RecordObservationEventEvidence,
)
from app.modules.evidence_collection.errors import (
    EvidenceNotFound,
    EvidenceServiceConfigurationError,
    InvalidEvidenceInput,
    UnsupportedEvidenceRelationship,
    UnverifiedContentReference,
)
from app.modules.evidence_collection.ports import ContentReferenceVerifier, IncidentLookup
from app.modules.evidence_collection.repository import EvidenceRepository
from app.modules.incidents.context import IncidentRequestContext
from app.shared.identifiers import Team4EntityId, as_team4_entity_id


def new_evidence_id() -> str:
    """Default id factory. D-01's UUID proposal is not agreed."""
    return str(uuid4())


class EvidenceService:
    """Record and retrieve append-only Evidence metadata.

    Manual recording and observation-origin event recording (F-04a) are
    supported. Tool-execution creation, Investigation relationships, content
    storage, and audit delivery remain outside this milestone.
    """

    def __init__(
        self,
        repository: EvidenceRepository,
        incident_lookup: IncidentLookup,
        *,
        content_verifier: ContentReferenceVerifier | None = None,
        id_factory: Callable[[], str] | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._repository = repository
        self._incident_lookup = incident_lookup
        self._content_verifier = content_verifier
        self._id_factory = id_factory or new_evidence_id
        self._clock = clock or (lambda: datetime.now(UTC))

    def record_manual_evidence(
        self, command: RecordManualEvidence, context: IncidentRequestContext
    ) -> Evidence:
        """Record manual Evidence after trusted Incident and content-reference checks."""
        self._incident_lookup.get_incident(command.incident_id, context)
        if command.investigation_id is not None:
            raise UnsupportedEvidenceRelationship("Investigation relationships are not implemented.")
        if command.triggered_by_observation_id is not None:
            raise UnsupportedEvidenceRelationship("Observation-trigger relationships are not implemented.")
        self._verify_content_reference(command.content_ref, context.organization_id)

        collected_at = self._now()
        evidence = Evidence(
            id=self._new_id(),
            incident_id=command.incident_id,
            investigation_id=None,
            triggered_by_observation_id=None,
            evidence_type=command.evidence_type,
            description=command.description,
            source_label=command.source_label,
            external_source_ref=command.external_source_ref,
            content_ref=command.content_ref,
            captured_at=command.captured_at,
            collected_at=collected_at,
            availability=command.availability,
            provenance=Provenance(
                origin_type="manual",
                provider=None,
                source_event_id=None,
                source_account_ref=None,
                collector_ref=context.actor_ref,
            ),
        )
        audit_intent = EvidenceRecordedAuditIntent(
            event_id=self._new_id(),
            event_type="evidence.recorded",
            organization_id=context.organization_id,
            actor_ref=context.actor_ref,
            resource_type="evidence",
            resource_id=evidence.id,
            occurred_at=collected_at,
            correlation_id=context.correlation_id,
            data=EvidenceRecordedData(
                evidence_type=evidence.evidence_type,
                availability=evidence.availability,
            ),
        )
        self._repository.add(
            evidence,
            organization_id=context.organization_id,
            audit_intent=audit_intent,
        )
        return self.get_evidence(evidence.id, context)

    def record_observation_event_evidence(
        self, command: RecordObservationEventEvidence, context: IncidentRequestContext
    ) -> Evidence:
        """Record F-04a event Evidence from stored Observation provenance.

        Organization and actor come only from `context`. `triggered_by_observation_id`
        is always null. Content storage is not implemented; `content_ref` is an
        injected opaque mock verified by the existing port (D-08).
        """
        self._incident_lookup.get_incident(command.incident_id, context)
        if command.provenance.origin_type != "observation":
            raise InvalidEvidenceInput("Observation-origin Evidence requires observation provenance.")
        self._verify_content_reference(command.content_ref, context.organization_id)

        collected_at = self._now()
        evidence = Evidence(
            id=self._new_id(),
            incident_id=command.incident_id,
            investigation_id=None,
            triggered_by_observation_id=None,
            evidence_type="event",
            description=command.description,
            source_label=command.source_label,
            external_source_ref=command.external_source_ref,
            content_ref=command.content_ref,
            captured_at=command.captured_at,
            collected_at=collected_at,
            availability="available",
            provenance=Provenance(
                origin_type="observation",
                provider=command.provenance.provider,
                source_event_id=command.provenance.source_event_id,
                source_account_ref=command.provenance.source_account_ref,
                collector_ref=command.provenance.collector_ref,
            ),
        )
        audit_intent = EvidenceRecordedAuditIntent(
            event_id=self._new_id(),
            event_type="evidence.recorded",
            organization_id=context.organization_id,
            actor_ref=context.actor_ref,
            resource_type="evidence",
            resource_id=evidence.id,
            occurred_at=collected_at,
            correlation_id=context.correlation_id,
            data=EvidenceRecordedData(
                evidence_type=evidence.evidence_type,
                availability=evidence.availability,
            ),
        )
        self._repository.add(
            evidence,
            organization_id=context.organization_id,
            audit_intent=audit_intent,
        )
        return self.get_evidence(evidence.id, context)

    def get_evidence(self, evidence_id: Team4EntityId, context: IncidentRequestContext) -> Evidence:
        evidence = self._repository.get(evidence_id, context.organization_id)
        if evidence is None:
            raise EvidenceNotFound(str(evidence_id))
        return evidence

    def list_incident_evidence(
        self, incident_id: Team4EntityId, context: IncidentRequestContext
    ) -> tuple[Evidence, ...]:
        self._incident_lookup.get_incident(incident_id, context)
        return self._repository.list_for_incident(incident_id, context.organization_id)

    def _verify_content_reference(self, content_ref: str | None, organization_id: str) -> None:
        if content_ref is None:
            return
        if self._content_verifier is None:
            raise EvidenceServiceConfigurationError(
                "A content verifier is required when content_ref is supplied."
            )
        try:
            verified = self._content_verifier.verify(content_ref, organization_id=organization_id)
        except Exception as exc:
            raise EvidenceServiceConfigurationError("The content verifier failed.") from exc
        if not isinstance(verified, bool):
            raise EvidenceServiceConfigurationError("The content verifier must return a boolean.")
        if not verified:
            raise UnverifiedContentReference("The content reference could not be verified.")

    def _now(self) -> datetime:
        current: object = self._clock()
        if not isinstance(current, datetime) or current.utcoffset() is None:
            raise EvidenceServiceConfigurationError("The clock must return a timezone-aware datetime.")
        return current.astimezone(UTC)

    def _new_id(self) -> Team4EntityId:
        value: object = self._id_factory()
        if not isinstance(value, str) or not value.strip():
            raise EvidenceServiceConfigurationError("The id factory must return a non-empty string.")
        return as_team4_entity_id(value.strip())
