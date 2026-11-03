"""Stage 2 observation assessment (CT-04 §8.5 / §9.3, Proposed, not agreed).

Provider and sourceEventId consistency stay here (D-21). Service resolution
and severity mapping are injected mocks (D-03, D-05). This module does not
create an Incident or a processing attempt.
"""

from dataclasses import dataclass
from typing import Literal

from app.modules.incidents.contracts import IncidentSeverity
from app.modules.ingestion.contracts import Observation
from app.modules.ingestion.errors import IngestionConfigurationError
from app.modules.ingestion.ports import (
    ServiceResolution,
    ServiceResolver,
    SeverityMapper,
    SeverityMapping,
)
from app.shared.identifiers import ExternalRef

Stage2Kind = Literal[
    "ready",
    "provenance_mismatch",
    "service_unresolved",
    "severity_unmapped",
]


@dataclass(frozen=True, slots=True)
class Stage2Assessment:
    """Stable domain result of Stage 2. This is not a CT-04 processing attempt."""

    kind: Stage2Kind
    resolved_service_ref: ExternalRef | None
    mapped_severity: IncidentSeverity | None
    mapping_version: str | None
    error_code: str | None

    def __post_init__(self) -> None:
        ready_fields = (
            self.resolved_service_ref,
            self.mapped_severity,
            self.mapping_version,
        )
        if self.kind == "ready":
            if any(field is None for field in ready_fields) or self.error_code is not None:
                raise ValueError("A ready assessment requires a service, severity, and version.")
            return
        if any(field is not None for field in ready_fields) or self.error_code is None:
            raise ValueError("A domain failure must carry only an error code.")


def evaluate_stage2(
    observation: Observation,
    organization_id: str,
    resolver: ServiceResolver,
    mapper: SeverityMapper,
) -> Stage2Assessment:
    """Apply provenance, then service, then severity. Stop at the first domain miss.

    Stored Observation values are compared as they are. This function does not
    trim `sourceEventId` or re-run Stage 1 binding checks.
    """
    if not _provenance_consistent(observation):
        return _failure("provenance_mismatch", "PROVENANCE_MISMATCH")
    resolution = _resolve_service(resolver, observation.service_ref, organization_id)
    if not resolution.resolved or resolution.service_ref is None:
        return _failure("service_unresolved", "SERVICE_UNRESOLVED")
    mapping = _map_severity(mapper, observation.source, observation.external_severity)
    if not mapping.mapped or mapping.severity is None or mapping.version is None:
        return _failure("severity_unmapped", "SEVERITY_UNMAPPED")
    return Stage2Assessment(
        kind="ready",
        resolved_service_ref=resolution.service_ref,
        mapped_severity=mapping.severity,
        mapping_version=mapping.version,
        error_code=None,
    )


def _provenance_consistent(observation: Observation) -> bool:
    provenance = observation.provenance
    return (
        provenance.provider == observation.source
        and provenance.source_event_id == observation.source_event_id
    )


def _resolve_service(
    resolver: ServiceResolver,
    provider_service_ref: ExternalRef | None,
    organization_id: str,
) -> ServiceResolution:
    try:
        resolution = resolver.resolve(provider_service_ref, organization_id)
    except Exception as exc:
        raise IngestionConfigurationError("The service resolver failed.") from exc
    if not isinstance(resolution, ServiceResolution):
        raise IngestionConfigurationError("The service resolver must return a ServiceResolution.")
    return resolution


def _map_severity(
    mapper: SeverityMapper, source: str, external_severity: str | None
) -> SeverityMapping:
    try:
        mapping = mapper.map(source, external_severity)
    except Exception as exc:
        raise IngestionConfigurationError("The severity mapper failed.") from exc
    if not isinstance(mapping, SeverityMapping):
        raise IngestionConfigurationError("The severity mapper must return a SeverityMapping.")
    return mapping


def _failure(kind: Stage2Kind, error_code: str) -> Stage2Assessment:
    return Stage2Assessment(
        kind=kind,
        resolved_service_ref=None,
        mapped_severity=None,
        mapping_version=None,
        error_code=error_code,
    )
