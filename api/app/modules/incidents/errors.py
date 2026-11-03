"""RCA-001 domain failures.

These exceptions carry no HTTP status and do not depend on FastAPI.
"""


class IncidentDomainError(Exception):
    """Base type for incident domain failures."""


class IncidentNotFound(IncidentDomainError):
    """The incident is absent from the caller's organization.

    A missing id and an id owned by another organization are both reported this way.
    """

    def __init__(self, incident_id: str) -> None:
        self.incident_id = incident_id
        super().__init__(f"Incident {incident_id} was not found.")


class InvalidLifecycleTransition(IncidentDomainError):
    """The requested status is not an allowed next status."""

    def __init__(self, current: str, target: str) -> None:
        self.current = current
        self.target = target
        super().__init__(f"Incident status cannot change from {current} to {target}.")


class SameStatusTransition(IncidentDomainError):
    """Setting the status the incident already has is rejected."""

    def __init__(self, status: str) -> None:
        self.status = status
        super().__init__(f"Incident status is already {status}.")


class InvalidIncidentInput(IncidentDomainError):
    """The domain operation was given input the incident rules reject."""


class InvalidRequestContext(InvalidIncidentInput):
    """The trusted request context is missing a value or carries a value of the wrong type."""


class OrganizationScopeError(IncidentDomainError):
    """The operation leaves or lacks the trusted organization.

    Reading another organization's incident raises IncidentNotFound instead, so a
    caller cannot tell whether that id exists.
    """


class InconsistentStatusChange(IncidentDomainError):
    """A save's status, transition record, and audit intent do not describe the same change."""


class IncidentConcurrencyConflict(IncidentDomainError):
    """The incident changed after it was read, so a save based on that read was refused."""

    def __init__(self, incident_id: str, expected_version: int, current_version: int) -> None:
        self.incident_id = incident_id
        self.expected_version = expected_version
        self.current_version = current_version
        super().__init__(f"Incident {incident_id} was modified by another operation.")


class IncidentServiceConfigurationError(IncidentDomainError):
    """An injected clock or id factory produced a value the service cannot use."""


class UncertainIncidentCreate(IncidentDomainError):
    """`create_incident` stored an incident, then failed before returning it.

    `incident_id` is the locally generated id. This is not a unique observation
    key, a shared transaction, or an `incident.created` audit.
    """

    def __init__(self, incident_id: str) -> None:
        self.incident_id = incident_id
        super().__init__("The incident was stored but could not be returned.")
