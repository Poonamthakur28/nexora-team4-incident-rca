"""RCA-002 domain failures, independent of FastAPI and transport."""


class IngestionDomainError(Exception):
    """Base type for Incident Ingestion domain failures."""


class InvalidObservationRequest(IngestionDomainError):
    """Stage 1 request-shape failure.

    This is the domain form of CT-04 `INVALID_REQUEST`. No receipt, reservation,
    or processing attempt is created.
    """


class ObservationAuthorizationDenied(IngestionDomainError):
    """Stage 1 authorization or binding denial.

    The message is generic: it does not say whether a source account exists or
    which organization it belongs to.
    """


class InvalidConnectorContext(IngestionDomainError):
    """The injected mock connector context is missing a required trusted value."""


class IngestionConfigurationError(IngestionDomainError):
    """An injected authorizer, hasher, or other dependency failed or is invalid."""
