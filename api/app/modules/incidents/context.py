"""Trusted caller context for incident operations.

Organization and actor values are opaque. This module does not model Team 1 users,
employees, or membership, and it does not accept organization identity from a
create-request body. Organization format is D-02 (Needs Team 1 Input).
"""

from dataclasses import dataclass

from app.modules.incidents.errors import InvalidRequestContext, OrganizationScopeError
from app.shared.identifiers import ExternalRef


@dataclass(frozen=True, slots=True)
class IncidentRequestContext:
    """Organization, actor, and optional correlation supplied by a trusted boundary.

    Status changes require `correlation_id`; it is never taken from a command body.
    """

    organization_id: str
    actor_ref: ExternalRef
    correlation_id: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.organization_id, str) or not self.organization_id.strip():
            raise OrganizationScopeError("A trusted organization is required.")
        object.__setattr__(self, "organization_id", self.organization_id.strip())

        if not isinstance(self.actor_ref, ExternalRef):
            raise InvalidRequestContext("actor_ref must be an ExternalRef.")

        if self.correlation_id is None:
            return
        if not isinstance(self.correlation_id, str) or not self.correlation_id.strip():
            raise InvalidRequestContext("correlation_id must be a non-empty string when it is provided.")
        object.__setattr__(self, "correlation_id", self.correlation_id.strip())
