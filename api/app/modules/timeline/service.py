"""Read-time incident chronology. No store, outbox, or write hooks."""

from app.modules.evidence_collection.contracts import Evidence
from app.modules.incidents.context import IncidentRequestContext
from app.modules.incidents.contracts import Incident, IncidentStatusTransition, serialize_utc_z
from app.modules.timeline.contracts import TimelineCategory, TimelineEntry
from app.modules.timeline.ports import EvidenceReader, IncidentLookup, TransitionReader
from app.shared.identifiers import Team4EntityId, as_team4_entity_id

_CATEGORY_RANK: dict[TimelineCategory, int] = {
    "incident.opened": 0,
    "evidence.recorded": 1,
    "incident.status_changed": 2,
}


class TimelineService:
    """Project a tenant-scoped incident timeline from existing source records."""

    def __init__(
        self,
        incidents: IncidentLookup,
        transitions: TransitionReader,
        evidence: EvidenceReader,
    ) -> None:
        self._incidents = incidents
        self._transitions = transitions
        self._evidence = evidence

    def list_incident_timeline(
        self, incident_id: Team4EntityId, context: IncidentRequestContext
    ) -> tuple[TimelineEntry, ...]:
        incident = self._incidents.get_incident(incident_id, context)
        transitions = self._transitions.list_status_transitions(incident.id, context)
        evidence = self._evidence.list_incident_evidence(incident.id, context)
        entries = [
            _opened_entry(incident),
            *(_status_changed_entry(incident, transition) for transition in transitions),
            *(_evidence_recorded_entry(incident, item) for item in evidence),
        ]
        return tuple(sorted(entries, key=_sort_key))


def _opened_entry(incident: Incident) -> TimelineEntry:
    return TimelineEntry(
        id=as_team4_entity_id(f"tl:incident.opened:{incident.id}"),
        organization_id=incident.organization_id,
        incident_id=incident.id,
        category="incident.opened",
        source_kind="incident",
        source_id=str(incident.id),
        occurred_at=incident.created_at,
        recorded_at=incident.created_at,
        label="Incident opened",
        detail=incident.title,
    )


def _status_changed_entry(incident: Incident, transition: IncidentStatusTransition) -> TimelineEntry:
    occurred = serialize_utc_z(transition.occurred_at)
    source_id = f"{transition.correlation_id}:{occurred}"
    return TimelineEntry(
        id=as_team4_entity_id(
            f"tl:incident.status_changed:{incident.id}:{transition.correlation_id}:{occurred}"
        ),
        organization_id=incident.organization_id,
        incident_id=incident.id,
        category="incident.status_changed",
        source_kind="status_transition",
        source_id=source_id,
        occurred_at=transition.occurred_at,
        recorded_at=transition.occurred_at,
        label=f"Status changed from {transition.from_status} to {transition.to_status}",
        detail=transition.reason,
    )


def _evidence_recorded_entry(incident: Incident, evidence: Evidence) -> TimelineEntry:
    return TimelineEntry(
        id=as_team4_entity_id(f"tl:evidence.recorded:{evidence.id}"),
        organization_id=incident.organization_id,
        incident_id=incident.id,
        category="evidence.recorded",
        source_kind="evidence",
        source_id=str(evidence.id),
        occurred_at=evidence.captured_at,
        recorded_at=evidence.collected_at,
        label="Evidence recorded",
        detail=evidence.description,
    )


def _sort_key(entry: TimelineEntry) -> tuple[object, ...]:
    return (
        entry.occurred_at,
        entry.recorded_at,
        _CATEGORY_RANK[entry.category],
        str(entry.id),
    )
