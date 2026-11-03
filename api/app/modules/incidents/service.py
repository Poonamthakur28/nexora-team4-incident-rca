"""RCA-001 incident operations without persistence or transport.

Status changes store an audit intent with their transition in the repository. Nothing in
this module writes an outbox row or delivers that intent to an audit sink.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from app.modules.incidents.context import IncidentRequestContext
from app.modules.incidents.contracts import (
    AssignIncident,
    ChangeIncidentStatus,
    CreateIncident,
    Incident,
    IncidentAuditIntent,
    IncidentStatusChangedData,
    IncidentStatusTransition,
)
from app.modules.incidents.errors import (
    IncidentNotFound,
    IncidentServiceConfigurationError,
    InvalidIncidentInput,
    InvalidRequestContext,
    UncertainIncidentCreate,
)
from app.modules.incidents.lifecycle import validate_transition
from app.modules.incidents.repository import IncidentRepository, VersionedIncident
from app.shared.identifiers import Team4EntityId, as_team4_entity_id


@dataclass(frozen=True, slots=True)
class StatusChangeResult:
    """A completed status change and the audit intent stored with it.

    `audit_intent` has not been delivered.
    """

    incident: Incident
    transition: IncidentStatusTransition
    audit_intent: IncidentAuditIntent


def new_incident_id() -> str:
    """Default id factory.

    CT-04 proposes a UUID (D-01). That decision is not agreed; callers can inject another factory.
    """
    return str(uuid4())


class IncidentService:
    def __init__(
        self,
        repository: IncidentRepository,
        *,
        id_factory: Callable[[], str] | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._repository = repository
        self._id_factory = id_factory or new_incident_id
        self._clock = clock or (lambda: datetime.now(UTC))

    def create_incident(self, command: CreateIncident, context: IncidentRequestContext) -> Incident:
        now = self._now()
        incident = Incident(
            id=self._new_id(),
            organization_id=context.organization_id,
            title=command.title,
            description=command.description,
            severity=command.severity,
            status="open",
            service_ref=command.service_ref,
            assigned_team_ref=command.assigned_team_ref,
            assigned_user_ref=command.assigned_user_ref,
            external_refs=list(command.external_refs),
            created_at=now,
            updated_at=now,
        )
        self._repository.add(incident)
        try:
            return self.get_incident(incident.id, context)
        except UncertainIncidentCreate:
            raise
        except Exception as exc:
            raise UncertainIncidentCreate(str(incident.id)) from exc

    def get_incident(self, incident_id: Team4EntityId, context: IncidentRequestContext) -> Incident:
        return self._load(incident_id, context).incident

    def change_status(
        self,
        incident_id: Team4EntityId,
        command: ChangeIncidentStatus,
        context: IncidentRequestContext,
    ) -> StatusChangeResult:
        current = self._load(incident_id, context)
        incident = current.incident
        validate_transition(incident.status, command.to_status)
        if context.correlation_id is None:
            raise InvalidRequestContext("A trusted correlation id is required to change incident status.")
        occurred_at = self._now_not_before(incident)
        updated = incident.model_copy(update={"status": command.to_status, "updated_at": occurred_at})
        transition = IncidentStatusTransition(
            incident_id=updated.id,
            from_status=incident.status,
            to_status=command.to_status,
            actor_ref=context.actor_ref,
            reason=command.reason,
            correlation_id=context.correlation_id,
            occurred_at=occurred_at,
        )
        audit_intent = IncidentAuditIntent(
            event_id=self._new_id(),
            event_type="incident.status_changed",
            organization_id=context.organization_id,
            actor_ref=context.actor_ref,
            resource_type="incident",
            resource_id=updated.id,
            occurred_at=occurred_at,
            correlation_id=transition.correlation_id,
            data=IncidentStatusChangedData(
                from_status=transition.from_status,
                to_status=transition.to_status,
                reason=transition.reason,
            ),
        )
        self._repository.save(
            updated,
            expected_version=current.version,
            transition=transition,
            audit_intent=audit_intent,
        )
        return StatusChangeResult(
            incident=self.get_incident(updated.id, context),
            transition=self._repository.list_transitions(updated.id, context.organization_id)[-1],
            audit_intent=self._repository.list_audit_intents(updated.id, context.organization_id)[-1],
        )

    def assign_incident(
        self,
        incident_id: Team4EntityId,
        command: AssignIncident,
        context: IncidentRequestContext,
    ) -> Incident:
        """Replace the assignment references that the command sets.

        Assignment rules are not defined by CT-04. This does not decide whether closed incidents
        may be reassigned, and it records no history or audit intent; both remain unresolved.
        """
        if not command.model_fields_set:
            raise InvalidIncidentInput("Assignment requires at least one reference.")
        current = self._load(incident_id, context)
        changes: dict[str, object] = {}
        if "assigned_team_ref" in command.model_fields_set:
            changes["assigned_team_ref"] = command.assigned_team_ref
        if "assigned_user_ref" in command.model_fields_set:
            changes["assigned_user_ref"] = command.assigned_user_ref
        changes["updated_at"] = self._now_not_before(current.incident)
        self._repository.save(current.incident.model_copy(update=changes), expected_version=current.version)
        return self.get_incident(current.incident.id, context)

    def _load(self, incident_id: Team4EntityId, context: IncidentRequestContext) -> VersionedIncident:
        found = self._repository.get(incident_id, context.organization_id)
        if found is None:
            raise IncidentNotFound(str(incident_id))
        return found

    def _now_not_before(self, incident: Incident) -> datetime:
        moment = self._now()
        if moment < incident.created_at:
            raise IncidentServiceConfigurationError(
                "The clock returned a time earlier than incident creation."
            )
        return moment

    def _now(self) -> datetime:
        current: object = self._clock()
        if not isinstance(current, datetime) or current.utcoffset() is None:
            raise IncidentServiceConfigurationError("The clock must return a timezone-aware datetime.")
        return current.astimezone(UTC)

    def _new_id(self) -> Team4EntityId:
        value: object = self._id_factory()
        if not isinstance(value, str) or not value.strip():
            raise IncidentServiceConfigurationError("The id factory must return a non-empty string.")
        return as_team4_entity_id(value.strip())
