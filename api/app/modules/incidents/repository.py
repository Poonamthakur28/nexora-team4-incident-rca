"""Incident storage port and an in-memory implementation.

Each repository instance owns its data. There is no module-level store.
A later SQL repository can implement the same protocol without changing the service.
"""

from dataclasses import dataclass, field
from typing import Protocol

from app.modules.incidents.contracts import Incident, IncidentAuditIntent, IncidentStatusTransition
from app.modules.incidents.errors import (
    IncidentConcurrencyConflict,
    IncidentNotFound,
    InconsistentStatusChange,
    InvalidIncidentInput,
    OrganizationScopeError,
)
from app.shared.identifiers import Team4EntityId


@dataclass(frozen=True, slots=True)
class VersionedIncident:
    """An incident read together with its storage version.

    The version is internal to the repository port. It is not an Incident field and is not
    part of the CT-04 wire contract.
    """

    incident: Incident
    version: int


class IncidentRepository(Protocol):
    """Incident storage scoped by organization.

    Concurrency: `save` uses optimistic concurrency. The caller passes the version it read;
    if the stored version differs, `save` raises IncidentConcurrencyConflict and changes nothing.
    Every successful save increments the version.

    Status changes: a save that changes status must carry exactly one transition and one audit
    intent describing that change. They are stored together with the incident or not at all.
    The audit intent is stored locally only; it is not an outbox row and is never delivered here.
    """

    def add(self, incident: Incident) -> None:
        """Store a new incident at version 1. Reject a repeated id."""

    def get(self, incident_id: Team4EntityId, organization_id: str) -> VersionedIncident | None:
        """Return the incident and its version, or None when it is absent or out of scope."""

    def save(
        self,
        incident: Incident,
        *,
        expected_version: int,
        transition: IncidentStatusTransition | None = None,
        audit_intent: IncidentAuditIntent | None = None,
    ) -> int:
        """Replace the stored incident and return the new version."""

    def list_transitions(
        self, incident_id: Team4EntityId, organization_id: str
    ) -> tuple[IncidentStatusTransition, ...]:
        """Return status history for an incident in this organization, oldest first."""

    def list_audit_intents(
        self, incident_id: Team4EntityId, organization_id: str
    ) -> tuple[IncidentAuditIntent, ...]:
        """Return locally stored, undelivered audit intents for an incident, oldest first."""


@dataclass
class _StoredIncident:
    incident: Incident
    version: int = 1
    transitions: list[IncidentStatusTransition] = field(default_factory=list)
    audit_intents: list[IncidentAuditIntent] = field(default_factory=list)


class InMemoryIncidentRepository:
    """Process-local incident store scoped by organization on every read."""

    def __init__(self) -> None:
        self._records: dict[str, _StoredIncident] = {}

    def add(self, incident: Incident) -> None:
        key = str(incident.id)
        if key in self._records:
            raise InvalidIncidentInput("An incident with this id already exists.")
        self._records[key] = _StoredIncident(incident.model_copy(deep=True))

    def get(self, incident_id: Team4EntityId, organization_id: str) -> VersionedIncident | None:
        record = self._visible(incident_id, organization_id)
        if record is None:
            return None
        return VersionedIncident(record.incident.model_copy(deep=True), record.version)

    def save(
        self,
        incident: Incident,
        *,
        expected_version: int,
        transition: IncidentStatusTransition | None = None,
        audit_intent: IncidentAuditIntent | None = None,
    ) -> int:
        key = str(incident.id)
        record = self._records.get(key)
        if record is None:
            raise IncidentNotFound(key)
        if record.incident.organization_id != incident.organization_id:
            raise OrganizationScopeError("An incident cannot be moved to another organization.")
        if record.version != expected_version:
            raise IncidentConcurrencyConflict(key, expected_version, record.version)
        _check_status_change(record.incident, incident, transition, audit_intent)

        stored_incident = incident.model_copy(deep=True)
        stored_transition = transition.model_copy(deep=True) if transition is not None else None
        stored_intent = audit_intent.model_copy(deep=True) if audit_intent is not None else None

        record.incident = stored_incident
        record.version += 1
        if stored_transition is not None and stored_intent is not None:
            record.transitions.append(stored_transition)
            record.audit_intents.append(stored_intent)
        return record.version

    def list_transitions(
        self, incident_id: Team4EntityId, organization_id: str
    ) -> tuple[IncidentStatusTransition, ...]:
        record = self._visible(incident_id, organization_id)
        if record is None:
            raise IncidentNotFound(str(incident_id))
        return tuple(item.model_copy(deep=True) for item in record.transitions)

    def list_audit_intents(
        self, incident_id: Team4EntityId, organization_id: str
    ) -> tuple[IncidentAuditIntent, ...]:
        record = self._visible(incident_id, organization_id)
        if record is None:
            raise IncidentNotFound(str(incident_id))
        return tuple(item.model_copy(deep=True) for item in record.audit_intents)

    def _visible(self, incident_id: Team4EntityId, organization_id: str) -> _StoredIncident | None:
        record = self._records.get(str(incident_id))
        if record is None or record.incident.organization_id != organization_id:
            return None
        return record


def _check_status_change(
    stored: Incident,
    incoming: Incident,
    transition: IncidentStatusTransition | None,
    audit_intent: IncidentAuditIntent | None,
) -> None:
    if transition is None and audit_intent is None:
        if incoming.status != stored.status:
            raise InconsistentStatusChange("A status change requires a transition and an audit intent.")
        return
    if transition is None or audit_intent is None:
        raise InconsistentStatusChange("A transition and its audit intent must be saved together.")

    if str(transition.incident_id) != str(incoming.id):
        raise InconsistentStatusChange("Transition incident id does not match the incident.")
    if transition.from_status != stored.status:
        raise InconsistentStatusChange("Transition from_status does not match the stored status.")
    if transition.to_status != incoming.status:
        raise InconsistentStatusChange("Transition to_status does not match the incident status.")

    data = audit_intent.data
    if (
        str(audit_intent.resource_id) != str(incoming.id)
        or audit_intent.organization_id != incoming.organization_id
        or audit_intent.actor_ref != transition.actor_ref
        or audit_intent.correlation_id != transition.correlation_id
        or audit_intent.occurred_at != transition.occurred_at
        or data.from_status != transition.from_status
        or data.to_status != transition.to_status
        or data.reason != transition.reason
    ):
        raise InconsistentStatusChange("The audit intent does not describe the transition.")
