"""Mock connector and hasher ports for RCA-002. Not a production security boundary."""

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Protocol

from app.modules.incidents.contracts import IncidentSeverity
from app.modules.ingestion.errors import InvalidConnectorContext
from app.shared.identifiers import ExternalRef


@dataclass(frozen=True, slots=True)
class AuthenticatedConnectorContext:
    """Trusted connector identity supplied by a test or a future receiving boundary.

    This is an injected mock for domain checks. It does not authenticate a
    connector, validate a credential, or decide Team 1 membership. Organization
    format is D-02 (Needs Team 1 Input). How a registration is authenticated is
    D-21 and D-23 (Needs Team 5 Confirmation).
    """

    organization_id: str
    registration_ref: ExternalRef

    def __post_init__(self) -> None:
        if not isinstance(self.organization_id, str) or not self.organization_id.strip():
            raise InvalidConnectorContext("A trusted organization is required.")
        object.__setattr__(self, "organization_id", self.organization_id.strip())
        if not _is_registration_ref(self.registration_ref):
            raise InvalidConnectorContext("A trusted connector registration is required.")


class SourceAccountAuthorizer(Protocol):
    """Whether a connector registration may submit for a stable source account.

    The real registry is Team 5 with Team 1 (D-21, D-23). This port returns a
    boolean only. It must not disclose whether the account exists.
    """

    def is_authorized(
        self,
        registration_ref: ExternalRef,
        source_account_ref: ExternalRef,
        organization_id: str,
    ) -> bool:
        """Return whether this registration may use the account in this organization."""


class PayloadHasher(Protocol):
    """Hash canonical observation bytes. The algorithm is unset (D-10).

    Team 5 has not confirmed a production digest. Implementations are injected
    stand-ins for tests and later wiring. This port does not choose SHA-256,
    SHA-3, or BLAKE2.
    """

    def digest(self, canonical_payload: bytes) -> bytes:
        """Return a digest of the canonical UTF-8 payload."""


@dataclass(frozen=True, slots=True)
class ServiceResolution:
    """Result of a mock service lookup. `resolved` is False for every miss."""

    resolved: bool
    service_ref: ExternalRef | None = None


class ServiceResolver(Protocol):
    """Resolve a provider service id in a trusted organization (D-03).

    The real catalog owner is unset. Implementations are injected stand-ins.
    This port does not disclose whether a service exists in another organization.
    """

    def resolve(
        self, provider_service_ref: ExternalRef | None, organization_id: str
    ) -> ServiceResolution:
        """Return one resolved canonical ref, or unresolved."""


class InMemoryServiceResolver:
    """Instance-owned allow-list. Not a coordinator-approved catalog."""

    def __init__(self, grants: Iterable[tuple[str, ExternalRef, ExternalRef]]) -> None:
        self._grants = tuple(
            (organization_id, provider, canonical)
            for organization_id, provider, canonical in grants
        )

    def resolve(
        self, provider_service_ref: ExternalRef | None, organization_id: str
    ) -> ServiceResolution:
        if provider_service_ref is None:
            return ServiceResolution(resolved=False)
        matches = [
            canonical
            for grant_org, provider, canonical in self._grants
            if grant_org == organization_id and provider == provider_service_ref
        ]
        unique = {(ref.owner, ref.id) for ref in matches}
        if len(unique) != 1:
            return ServiceResolution(resolved=False)
        return ServiceResolution(resolved=True, service_ref=matches[0])


@dataclass(frozen=True, slots=True)
class SeverityMapping:
    """Result of a mock severity map. Unmapped pairs have no default."""

    mapped: bool
    severity: IncidentSeverity | None = None
    version: str | None = None


class SeverityMapper(Protocol):
    """Map provider severity to a canonical IncidentSeverity (D-05).

    Version token format is unset. Implementations are injected stand-ins, not
    a production mapping document.
    """

    def map(self, source: str, external_severity: str | None) -> SeverityMapping:
        """Return a mapped severity and version, or unmapped."""


# Illustrative CT-04 §8.3 fixture table. Not an approved production mapping.
SYNTHETIC_MONITOR_SEVERITY_FIXTURE_V1 = {
    ("synthetic-monitor", "SEV1"): "critical",
    ("synthetic-monitor", "SEV2"): "high",
    ("synthetic-monitor", "SEV3"): "medium",
    ("synthetic-monitor", "SEV4"): "low",
}
SYNTHETIC_MONITOR_SEVERITY_FIXTURE_VERSION = "synthetic-monitor-severity/v1"


class InMemorySeverityMapper:
    """Instance-owned fixture table. Not a Team 5 mapping version."""

    def __init__(
        self,
        pairs: dict[tuple[str, str], IncidentSeverity] | None = None,
        *,
        version: str = SYNTHETIC_MONITOR_SEVERITY_FIXTURE_VERSION,
    ) -> None:
        self._pairs = dict(SYNTHETIC_MONITOR_SEVERITY_FIXTURE_V1 if pairs is None else pairs)
        self._version = version

    def map(self, source: str, external_severity: str | None) -> SeverityMapping:
        if external_severity is None:
            return SeverityMapping(mapped=False)
        severity = self._pairs.get((source, external_severity))
        if severity is None:
            return SeverityMapping(mapped=False)
        return SeverityMapping(mapped=True, severity=severity, version=self._version)


class InMemorySourceAccountAuthorizer:
    """Deterministic allow-list. Grants are copied in; nothing here is global."""

    def __init__(self, grants: Iterable[tuple[str, ExternalRef, ExternalRef]]) -> None:
        self._grants = frozenset(
            _grant_key(organization_id, registration, account)
            for organization_id, registration, account in grants
        )

    def is_authorized(
        self,
        registration_ref: ExternalRef,
        source_account_ref: ExternalRef,
        organization_id: str,
    ) -> bool:
        return _grant_key(organization_id, registration_ref, source_account_ref) in self._grants


def _is_registration_ref(value: object) -> bool:
    if not isinstance(value, ExternalRef):
        return False
    return _non_empty_text(value.owner) and _non_empty_text(value.id)


def _non_empty_text(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _grant_key(
    organization_id: str, registration_ref: ExternalRef, source_account_ref: ExternalRef
) -> tuple[str, str, str, str, str]:
    return (
        organization_id,
        registration_ref.owner,
        registration_ref.id,
        source_account_ref.owner,
        source_account_ref.id,
    )
