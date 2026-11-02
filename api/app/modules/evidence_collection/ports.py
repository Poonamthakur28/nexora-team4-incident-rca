"""Narrow integration ports for the RCA-004 in-memory core."""

from typing import Protocol

from app.modules.incidents.context import IncidentRequestContext
from app.modules.incidents.contracts import Incident
from app.shared.identifiers import Team4EntityId


class IncidentLookup(Protocol):
    """Organization-scoped Incident lookup.

    `IncidentService.get_incident` satisfies this protocol. It raises the existing
    IncidentNotFound error for both missing and cross-organization records.
    """

    def get_incident(self, incident_id: Team4EntityId, context: IncidentRequestContext) -> Incident:
        """Return a visible Incident or raise IncidentNotFound."""


class ContentReferenceVerifier(Protocol):
    """Boundary to future Team 5-owned content storage (D-08).

    The reference is opaque. This port neither parses it nor uploads, reads, or
    manages content. `organization_id` is always the trusted value from the
    caller's IncidentRequestContext, never a value taken from the Evidence
    command, so a verifier can scope its lookup to the authenticated tenant.
    """

    def verify(self, content_ref: str, *, organization_id: str) -> bool:
        """Return whether the reference identifies stored content for this organization."""
