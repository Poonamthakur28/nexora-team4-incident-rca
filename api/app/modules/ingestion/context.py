"""Map trusted connector context to IncidentRequestContext.

This is a local test/stand-in adapter. It does not authenticate a connector
registration as a Team 1 employee or membership record (D-02, D-21).
"""

from typing import Protocol

from app.modules.incidents.context import IncidentRequestContext
from app.modules.ingestion.ports import AuthenticatedConnectorContext
from app.shared.identifiers import ExternalRef


class IncidentRequestContextFactory(Protocol):
    """Build a trusted Incident request context from connector identity."""

    def build(
        self,
        context: AuthenticatedConnectorContext,
        *,
        correlation_id: str,
    ) -> IncidentRequestContext:
        """Return a context whose organization is the connector organization."""


class ConnectorRegistrationActorFactory:
    """Use the trusted organization and a stand-in actor for Incident/Evidence calls.

    Organization always comes from `AuthenticatedConnectorContext`. The actor is
    either an injected test `ExternalRef` or the connector `registration_ref`.
    `registration_ref` is not treated as an authenticated employee identity.
    A custom factory that returns another organization is rejected by
    `ObservationIngestionService`, not here.
    """

    def __init__(self, *, actor_ref: ExternalRef | None = None) -> None:
        self._actor_ref = actor_ref

    def build(
        self,
        context: AuthenticatedConnectorContext,
        *,
        correlation_id: str,
    ) -> IncidentRequestContext:
        actor = self._actor_ref if self._actor_ref is not None else context.registration_ref
        return IncidentRequestContext(
            organization_id=context.organization_id,
            actor_ref=actor,
            correlation_id=correlation_id,
        )
