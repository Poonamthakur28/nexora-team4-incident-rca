"""Read ports for the RCA-003 in-memory timeline projection."""

from typing import Protocol

from app.modules.evidence_collection.contracts import Evidence
from app.modules.incidents.context import IncidentRequestContext
from app.modules.incidents.contracts import Incident, IncidentStatusTransition
from app.shared.identifiers import Team4EntityId


class IncidentLookup(Protocol):
    """Organization-scoped Incident lookup.

    `IncidentService.get_incident` satisfies this protocol. Missing and
    cross-organization ids both raise IncidentNotFound.
    """

    def get_incident(self, incident_id: Team4EntityId, context: IncidentRequestContext) -> Incident:
        """Return a visible Incident or raise IncidentNotFound."""


class TransitionReader(Protocol):
    """Organization-scoped status-transition history."""

    def list_status_transitions(
        self, incident_id: Team4EntityId, context: IncidentRequestContext
    ) -> tuple[IncidentStatusTransition, ...]:
        """Return stored transitions for a visible Incident, oldest first."""


class EvidenceReader(Protocol):
    """Organization-scoped Evidence list for one Incident."""

    def list_incident_evidence(
        self, incident_id: Team4EntityId, context: IncidentRequestContext
    ) -> tuple[Evidence, ...]:
        """Return visible Evidence for the Incident."""
