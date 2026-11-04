from datetime import UTC, datetime, timedelta
from itertools import count

import pytest
from pydantic import ValidationError

from app.modules.evidence_collection.contracts import (
    Provenance,
    RecordManualEvidence,
    RecordObservationEventEvidence,
)
from app.modules.evidence_collection.errors import (
    EvidenceNotFound,
    EvidenceServiceConfigurationError,
    InvalidEvidenceInput,
    UnsupportedEvidenceRelationship,
    UnverifiedContentReference,
)
from app.modules.evidence_collection.repository import InMemoryEvidenceRepository
from app.modules.evidence_collection.service import EvidenceService
from app.modules.incidents.context import IncidentRequestContext
from app.modules.incidents.contracts import CreateIncident
from app.modules.incidents.errors import IncidentNotFound
from app.modules.incidents.repository import InMemoryIncidentRepository
from app.modules.incidents.service import IncidentService
from app.shared.identifiers import as_external_ref, as_team4_entity_id

ORG = "org-1"
OTHER_ORG = "org-2"
ACTOR = as_external_ref("team1.user", "user-1")
START = datetime(2026, 10, 1, 9, 30, tzinfo=UTC)


class IdFactory:
    def __init__(self, prefix: str) -> None:
        self._ids = count(1)
        self.prefix = prefix
        self.issued: list[str] = []

    def __call__(self) -> str:
        value = f"{self.prefix}-{next(self._ids)}"
        self.issued.append(value)
        return value


class Clock:
    def __init__(self, current: datetime = START) -> None:
        self.current = current

    def __call__(self) -> datetime:
        value = self.current
        self.current += timedelta(minutes=1)
        return value


class FakeVerifier:
    """Verifier test double. `checked` records (content_ref, organization_id) pairs."""

    def __init__(self, accepted: set[str] | None = None) -> None:
        self.accepted = accepted or set()
        self.checked: list[tuple[str, str]] = []

    def verify(self, content_ref: str, *, organization_id: str) -> bool:
        self.checked.append((content_ref, organization_id))
        return content_ref in self.accepted


class TenantScopedVerifier:
    """Verifier whose accepted references differ per organization."""

    def __init__(self, accepted_by_org: dict[str, set[str]]) -> None:
        self.accepted_by_org = accepted_by_org
        self.checked: list[tuple[str, str]] = []

    def verify(self, content_ref: str, *, organization_id: str) -> bool:
        self.checked.append((content_ref, organization_id))
        return content_ref in self.accepted_by_org.get(organization_id, set())


class RaisingVerifier:
    """Verifier double that always fails; the service must wrap this, not leak it."""

    def verify(self, content_ref: str, *, organization_id: str) -> bool:
        raise RuntimeError(f"storage backend unreachable for {content_ref}/{organization_id}")


class NonBooleanVerifier:
    """Verifier double that violates the ContentReferenceVerifier contract."""

    def verify(self, content_ref: str, *, organization_id: str) -> object:
        return "yes"


def context(org: str = ORG, correlation: str | None = "corr-1") -> IncidentRequestContext:
    return IncidentRequestContext(organization_id=org, actor_ref=ACTOR, correlation_id=correlation)


def make_incident_service() -> IncidentService:
    return IncidentService(
        InMemoryIncidentRepository(),
        id_factory=IdFactory("incident"),
        clock=Clock(START - timedelta(minutes=1)),
    )


def create_incident(service: IncidentService, ctx: IncidentRequestContext):
    return service.create_incident(
        CreateIncident(title="Checkout error", severity="high", external_refs=[]),
        ctx,
    )


def command(**overrides: object) -> RecordManualEvidence:
    values: dict[str, object] = {
        "incident_id": as_team4_entity_id("incident-1"),
        "evidence_type": "other",
        "description": "Screenshot of the checkout error.",
        "source_label": "Operations desk upload",
        "external_source_ref": None,
        "content_ref": None,
        "captured_at": START,
        "availability": "unavailable",
    }
    values.update(overrides)
    return RecordManualEvidence(**values)  # type: ignore[arg-type]


def evidence_service(
    incident_lookup: IncidentService,
    *,
    verifier: FakeVerifier | None = None,
    ids: IdFactory | None = None,
    clock: Clock | None = None,
) -> tuple[EvidenceService, InMemoryEvidenceRepository, IdFactory, Clock]:
    repository = InMemoryEvidenceRepository()
    ids = ids or IdFactory("evidence")
    clock = clock or Clock()
    return (
        EvidenceService(
            repository,
            incident_lookup,
            content_verifier=verifier,
            id_factory=ids,
            clock=clock,
        ),
        repository,
        ids,
        clock,
    )


def test_records_manual_evidence_with_trusted_provenance_and_audit_intent() -> None:
    incidents = make_incident_service()
    incident = create_incident(incidents, context())
    service, repository, ids, _ = evidence_service(incidents)

    evidence = service.record_manual_evidence(command(incident_id=incident.id), context())

    assert evidence.id == "evidence-1"
    assert evidence.incident_id == incident.id
    assert evidence.provenance.origin_type == "manual"
    assert evidence.provenance.provider is None
    assert evidence.provenance.source_event_id is None
    assert evidence.provenance.source_account_ref is None
    assert evidence.provenance.collector_ref == ACTOR
    assert evidence.collected_at == START
    assert repository.get(evidence.id, ORG) == evidence
    intent = repository.list_audit_intents(evidence.id, ORG)[0]
    assert intent.event_id == "evidence-2"
    assert intent.event_type == "evidence.recorded"
    assert intent.organization_id == ORG
    assert intent.actor_ref == ACTOR
    assert intent.resource_id == evidence.id
    assert intent.correlation_id == "corr-1"
    assert intent.data.evidence_type == evidence.evidence_type
    assert intent.data.availability == evidence.availability
    assert ids.issued == ["evidence-1", "evidence-2"]


@pytest.mark.parametrize(
    ("availability", "content_ref", "verified"),
    [
        ("available", "content-1", True),
        ("partial", "content-1", True),
    ],
)
def test_verified_available_or_partial_content_succeeds(
    availability: str, content_ref: str, verified: bool
) -> None:
    incidents = make_incident_service()
    incident = create_incident(incidents, context())
    verifier = FakeVerifier({content_ref} if verified else set())
    service, _, _, _ = evidence_service(incidents, verifier=verifier)

    evidence = service.record_manual_evidence(
        command(
            incident_id=incident.id,
            availability=availability,
            content_ref=content_ref,
            description="The log window is partial; the final minute is missing.",
        ),
        context(),
    )

    assert evidence.content_ref == content_ref
    assert verifier.checked == [(content_ref, ORG)]


def test_unverified_or_unconfigured_content_ref_stores_nothing() -> None:
    incidents = make_incident_service()
    incident = create_incident(incidents, context())
    service, repository, ids, _ = evidence_service(incidents, verifier=FakeVerifier())

    with pytest.raises(UnverifiedContentReference):
        service.record_manual_evidence(
            command(incident_id=incident.id, availability="available", content_ref="missing"),
            context(),
        )
    assert repository.list_for_incident(incident.id, ORG) == ()
    assert ids.issued == []

    unconfigured, unconfigured_repo, _, _ = evidence_service(incidents)
    with pytest.raises(EvidenceServiceConfigurationError):
        unconfigured.record_manual_evidence(
            command(incident_id=incident.id, availability="partial", content_ref="content-1"),
            context(),
        )
    assert unconfigured_repo.list_for_incident(incident.id, ORG) == ()


def test_content_verification_is_scoped_to_the_authenticated_organization() -> None:
    """M1: the verifier must receive the trusted organization, not a command field.

    A reference accepted for one organization must not be treated as accepted
    for another, and the verifier must observe the authenticated organization id
    that actually requested each check.
    """
    incidents = make_incident_service()
    incident_a = create_incident(incidents, context(ORG))
    incident_b = create_incident(incidents, context(OTHER_ORG))
    verifier = TenantScopedVerifier({ORG: {"shared-ref"}})
    service, repository, ids, _ = evidence_service(incidents, verifier=verifier)

    evidence = service.record_manual_evidence(
        command(incident_id=incident_a.id, availability="available", content_ref="shared-ref"),
        context(ORG),
    )
    assert evidence.content_ref == "shared-ref"
    assert verifier.checked[-1] == ("shared-ref", ORG)

    with pytest.raises(UnverifiedContentReference):
        service.record_manual_evidence(
            command(incident_id=incident_b.id, availability="available", content_ref="shared-ref"),
            context(OTHER_ORG),
        )
    assert verifier.checked[-1] == ("shared-ref", OTHER_ORG)
    assert repository.list_for_incident(incident_b.id, OTHER_ORG) == ()
    assert ids.issued == ["evidence-1", "evidence-2"]


def test_verifier_exception_is_a_controlled_configuration_error_and_stores_nothing() -> None:
    incidents = make_incident_service()
    incident = create_incident(incidents, context())
    service, repository, ids, _ = evidence_service(incidents, verifier=RaisingVerifier())

    with pytest.raises(EvidenceServiceConfigurationError) as caught:
        service.record_manual_evidence(
            command(incident_id=incident.id, availability="available", content_ref="content-1"),
            context(),
        )

    assert str(caught.value) == "The content verifier failed."
    assert isinstance(caught.value.__cause__, RuntimeError)
    assert repository.list_for_incident(incident.id, ORG) == ()
    assert ids.issued == []


def test_verifier_non_boolean_result_is_a_controlled_configuration_error_and_stores_nothing() -> None:
    incidents = make_incident_service()
    incident = create_incident(incidents, context())
    service, repository, ids, _ = evidence_service(incidents, verifier=NonBooleanVerifier())

    with pytest.raises(EvidenceServiceConfigurationError):
        service.record_manual_evidence(
            command(incident_id=incident.id, availability="available", content_ref="content-1"),
            context(),
        )

    assert repository.list_for_incident(incident.id, ORG) == ()
    assert ids.issued == []


def test_partial_evidence_with_an_unverified_reference_stores_nothing() -> None:
    incidents = make_incident_service()
    incident = create_incident(incidents, context())
    service, repository, ids, _ = evidence_service(incidents, verifier=FakeVerifier())

    with pytest.raises(UnverifiedContentReference):
        service.record_manual_evidence(
            command(
                incident_id=incident.id,
                availability="partial",
                content_ref="content-1",
                description="The log window is partial; the final minute is missing.",
            ),
            context(),
        )

    assert repository.list_for_incident(incident.id, ORG) == ()
    assert ids.issued == []


def test_whitespace_only_content_ref_is_rejected_before_any_service_work() -> None:
    """L2/M2: an opaque, whitespace-only content_ref must not reach the verifier.

    RecordManualEvidence validates content_ref at construction, so a caller
    cannot even build a command carrying a blank reference. No id is issued and
    no verifier call occurs.
    """
    incidents = make_incident_service()
    incident = create_incident(incidents, context())
    verifier = FakeVerifier({"content-1"})
    _, repository, ids, _ = evidence_service(incidents, verifier=verifier)

    with pytest.raises(ValidationError):
        command(incident_id=incident.id, availability="available", content_ref="   ")

    assert verifier.checked == []
    assert repository.list_for_incident(incident.id, ORG) == ()
    assert ids.issued == []


def test_missing_or_cross_organization_incident_is_not_found_and_stores_nothing() -> None:
    incidents = make_incident_service()
    incident = create_incident(incidents, context())
    service, repository, ids, _ = evidence_service(incidents)

    with pytest.raises(IncidentNotFound):
        service.record_manual_evidence(command(incident_id=as_team4_entity_id("missing")), context())
    with pytest.raises(IncidentNotFound):
        service.record_manual_evidence(command(incident_id=incident.id), context(OTHER_ORG))

    assert repository.list_for_incident(incident.id, ORG) == ()
    assert ids.issued == []


def test_evidence_reads_and_incident_listings_are_organization_scoped() -> None:
    incidents = make_incident_service()
    incident = create_incident(incidents, context())
    service, _, _, _ = evidence_service(incidents)
    evidence = service.record_manual_evidence(command(incident_id=incident.id), context())

    with pytest.raises(EvidenceNotFound):
        service.get_evidence(evidence.id, context(OTHER_ORG))
    with pytest.raises(IncidentNotFound):
        service.list_incident_evidence(incident.id, context(OTHER_ORG))
    assert service.list_incident_evidence(incident.id, context()) == (evidence,)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("investigation_id", as_team4_entity_id("investigation-1")),
        ("triggered_by_observation_id", as_team4_entity_id("observation-1")),
    ],
)
def test_unimplemented_relationships_are_rejected_before_id_allocation(field: str, value: object) -> None:
    incidents = make_incident_service()
    incident = create_incident(incidents, context())
    service, repository, ids, _ = evidence_service(incidents)

    with pytest.raises(UnsupportedEvidenceRelationship):
        service.record_manual_evidence(command(incident_id=incident.id, **{field: value}), context())

    assert repository.list_for_incident(incident.id, ORG) == ()
    assert ids.issued == []


def test_recording_evidence_does_not_mutate_incident() -> None:
    incidents = make_incident_service()
    incident = create_incident(incidents, context())
    before = incidents.get_incident(incident.id, context())
    service, _, _, _ = evidence_service(incidents)

    service.record_manual_evidence(command(incident_id=incident.id), context())

    assert incidents.get_incident(incident.id, context()) == before


def test_manual_submissions_have_no_duplicate_suppression() -> None:
    incidents = make_incident_service()
    incident = create_incident(incidents, context())
    service, _, _, _ = evidence_service(incidents)

    first = service.record_manual_evidence(command(incident_id=incident.id), context())
    second = service.record_manual_evidence(command(incident_id=incident.id), context())

    assert first.id != second.id
    assert service.list_incident_evidence(incident.id, context()) == (first, second)


def test_invalid_injected_id_and_clock_are_controlled_errors() -> None:
    incidents = make_incident_service()
    incident = create_incident(incidents, context())
    bad_ids, _, _, _ = evidence_service(incidents, ids=lambda: " ")  # type: ignore[arg-type]
    with pytest.raises(EvidenceServiceConfigurationError):
        bad_ids.record_manual_evidence(command(incident_id=incident.id), context())

    bad_clock, _, _, _ = evidence_service(
        incidents,
        clock=lambda: datetime(2026, 10, 1),  # type: ignore[arg-type]
    )
    with pytest.raises(EvidenceServiceConfigurationError):
        bad_clock.record_manual_evidence(command(incident_id=incident.id), context())


def test_defensive_copies_prevent_mutation_of_stored_evidence() -> None:
    incidents = make_incident_service()
    incident = create_incident(incidents, context())
    service, repository, _, _ = evidence_service(incidents)
    evidence = service.record_manual_evidence(command(incident_id=incident.id), context())

    fetched = service.get_evidence(evidence.id, context())
    fetched.description = "mutated"
    listed = service.list_incident_evidence(incident.id, context())
    listed[0].source_label = "mutated"

    assert service.get_evidence(evidence.id, context()).description == "Screenshot of the checkout error."
    assert repository.list_for_incident(incident.id, ORG)[0].source_label == "Operations desk upload"


def test_service_has_no_update_or_delete_operations() -> None:
    incidents = make_incident_service()
    service, _, _, _ = evidence_service(incidents)
    assert not hasattr(service, "update_evidence")
    assert not hasattr(service, "delete_evidence")


def test_can_verify_content_references_reports_injected_verifier() -> None:
    incidents = make_incident_service()
    without_verifier, _, _, _ = evidence_service(incidents)
    with_verifier, _, _, _ = evidence_service(incidents, verifier=FakeVerifier())

    assert without_verifier.can_verify_content_references() is False
    assert with_verifier.can_verify_content_references() is True


COLLECTOR = as_external_ref("team5.connector", "conn_synth_monitor_01")
ACCOUNT = as_external_ref("synthetic-monitor", "acct_synth_0001")
CONTENT_REF = "content_synth_0051"


def observation_provenance(**overrides: object) -> Provenance:
    values: dict[str, object] = {
        "origin_type": "observation",
        "provider": "synthetic-monitor",
        "source_event_id": "evt-10005",
        "source_account_ref": ACCOUNT,
        "collector_ref": COLLECTOR,
    }
    values.update(overrides)
    return Provenance(**values)  # type: ignore[arg-type]


def observation_command(**overrides: object) -> RecordObservationEventEvidence:
    values: dict[str, object] = {
        "incident_id": as_team4_entity_id("incident-1"),
        "description": "All synthetic checks failing for 3 minutes.",
        "source_label": "synthetic-monitor",
        "content_ref": CONTENT_REF,
        "captured_at": START,
        "provenance": observation_provenance(),
    }
    values.update(overrides)
    return RecordObservationEventEvidence(**values)  # type: ignore[arg-type]


def test_records_observation_origin_event_evidence_with_audit_intent() -> None:
    incidents = make_incident_service()
    incident = create_incident(incidents, context())
    verifier = FakeVerifier({CONTENT_REF})
    service, repository, ids, _ = evidence_service(incidents, verifier=verifier)

    evidence = service.record_observation_event_evidence(
        observation_command(incident_id=incident.id), context()
    )

    assert evidence.id == "evidence-1"
    assert evidence.incident_id == incident.id
    assert evidence.evidence_type == "event"
    assert evidence.availability == "available"
    assert evidence.content_ref == CONTENT_REF
    assert evidence.triggered_by_observation_id is None
    assert evidence.provenance.origin_type == "observation"
    assert evidence.provenance.provider == "synthetic-monitor"
    assert evidence.provenance.source_event_id == "evt-10005"
    assert evidence.provenance.source_account_ref == ACCOUNT
    assert evidence.provenance.collector_ref == COLLECTOR
    assert evidence.collected_at == START
    assert verifier.checked == [(CONTENT_REF, ORG)]
    intent = repository.list_audit_intents(evidence.id, ORG)[0]
    assert intent.event_type == "evidence.recorded"
    assert intent.event_id == "evidence-2"
    assert intent.organization_id == ORG
    assert intent.actor_ref == ACTOR
    assert intent.resource_id == evidence.id
    assert intent.correlation_id == "corr-1"
    assert intent.data.evidence_type == "event"
    assert intent.data.availability == "available"
    assert len(repository.list_audit_intents(evidence.id, ORG)) == 1
    assert ids.issued == ["evidence-1", "evidence-2"]


def test_observation_provenance_is_copied_and_trimmed_without_using_top_level_source_event_id() -> None:
    from app.modules.ingestion.contracts import Observation
    from tests.unit.ingestion.test_contracts import observation_payload, provenance

    observation = Observation.model_validate(
        observation_payload(
            sourceEventId=" evt-10005 ",
            provenance=provenance(sourceEventId=" evt-10005 "),
        )
    )
    assert observation.source_event_id == " evt-10005 "
    assert observation.provenance.source_event_id == "evt-10005"

    incidents = make_incident_service()
    incident = create_incident(incidents, context())
    service, _, _, _ = evidence_service(incidents, verifier=FakeVerifier({CONTENT_REF}))

    evidence = service.record_observation_event_evidence(
        observation_command(incident_id=incident.id, provenance=observation.provenance),
        context(),
    )

    assert evidence.provenance.source_event_id == "evt-10005"
    assert evidence.provenance.source_event_id != observation.source_event_id
    assert evidence.provenance.provider == observation.provenance.provider
    assert evidence.provenance.source_account_ref == observation.provenance.source_account_ref
    assert evidence.provenance.collector_ref == observation.provenance.collector_ref
    assert evidence.triggered_by_observation_id is None


def test_observation_event_unverified_or_unconfigured_content_ref_stores_nothing() -> None:
    incidents = make_incident_service()
    incident = create_incident(incidents, context())
    service, repository, ids, _ = evidence_service(incidents, verifier=FakeVerifier())

    with pytest.raises(UnverifiedContentReference):
        service.record_observation_event_evidence(
            observation_command(incident_id=incident.id), context()
        )
    assert repository.list_for_incident(incident.id, ORG) == ()
    assert ids.issued == []

    unconfigured, unconfigured_repo, _, _ = evidence_service(incidents)
    with pytest.raises(EvidenceServiceConfigurationError):
        unconfigured.record_observation_event_evidence(
            observation_command(incident_id=incident.id), context()
        )
    assert unconfigured_repo.list_for_incident(incident.id, ORG) == ()


def test_observation_event_content_verification_is_scoped_to_the_authenticated_organization() -> None:
    incidents = make_incident_service()
    incident_a = create_incident(incidents, context(ORG))
    incident_b = create_incident(incidents, context(OTHER_ORG))
    verifier = TenantScopedVerifier({ORG: {CONTENT_REF}})
    service, repository, ids, _ = evidence_service(incidents, verifier=verifier)

    evidence = service.record_observation_event_evidence(
        observation_command(incident_id=incident_a.id), context(ORG)
    )
    assert evidence.content_ref == CONTENT_REF
    assert verifier.checked[-1] == (CONTENT_REF, ORG)

    with pytest.raises(UnverifiedContentReference):
        service.record_observation_event_evidence(
            observation_command(incident_id=incident_b.id), context(OTHER_ORG)
        )
    assert verifier.checked[-1] == (CONTENT_REF, OTHER_ORG)
    assert repository.list_for_incident(incident_b.id, OTHER_ORG) == ()
    assert ids.issued == ["evidence-1", "evidence-2"]


def test_observation_event_missing_or_cross_organization_incident_stores_nothing() -> None:
    incidents = make_incident_service()
    incident = create_incident(incidents, context())
    service, repository, ids, _ = evidence_service(incidents, verifier=FakeVerifier({CONTENT_REF}))

    with pytest.raises(IncidentNotFound):
        service.record_observation_event_evidence(
            observation_command(incident_id=as_team4_entity_id("missing")), context()
        )
    with pytest.raises(IncidentNotFound):
        service.record_observation_event_evidence(
            observation_command(incident_id=incident.id), context(OTHER_ORG)
        )

    assert repository.list_for_incident(incident.id, ORG) == ()
    assert ids.issued == []


def test_observation_event_command_has_no_caller_controlled_identity() -> None:
    assert "organization_id" not in RecordObservationEventEvidence.model_fields
    assert "actor_ref" not in RecordObservationEventEvidence.model_fields
    assert "triggered_by_observation_id" not in RecordObservationEventEvidence.model_fields


def test_manual_evidence_still_rejects_observation_triggers() -> None:
    incidents = make_incident_service()
    incident = create_incident(incidents, context())
    service, repository, ids, _ = evidence_service(incidents)

    with pytest.raises(UnsupportedEvidenceRelationship):
        service.record_manual_evidence(
            command(
                incident_id=incident.id,
                triggered_by_observation_id=as_team4_entity_id("observation-1"),
            ),
            context(),
        )

    assert repository.list_for_incident(incident.id, ORG) == ()
    assert ids.issued == []


def test_observation_and_manual_evidence_are_append_only_on_the_same_incident() -> None:
    incidents = make_incident_service()
    incident = create_incident(incidents, context())
    service, repository, _, _ = evidence_service(incidents, verifier=FakeVerifier({CONTENT_REF}))

    manual = service.record_manual_evidence(command(incident_id=incident.id), context())
    event = service.record_observation_event_evidence(
        observation_command(incident_id=incident.id), context()
    )
    again = service.record_observation_event_evidence(
        observation_command(incident_id=incident.id), context()
    )

    assert manual.id != event.id != again.id
    assert service.list_incident_evidence(incident.id, context()) == (manual, event, again)
    with pytest.raises(InvalidEvidenceInput):
        repository.add(
            event,
            organization_id=ORG,
            audit_intent=repository.list_audit_intents(event.id, ORG)[0],
        )
    assert not hasattr(repository, "save")
    assert not hasattr(repository, "delete")
    assert not hasattr(service, "update_evidence")


def test_observation_event_audit_actor_comes_from_context_not_collector() -> None:
    incidents = make_incident_service()
    incident = create_incident(incidents, context())
    service, repository, _, _ = evidence_service(incidents, verifier=FakeVerifier({CONTENT_REF}))

    evidence = service.record_observation_event_evidence(
        observation_command(incident_id=incident.id), context()
    )
    intent = repository.list_audit_intents(evidence.id, ORG)[0]

    assert evidence.provenance.collector_ref == COLLECTOR
    assert intent.actor_ref == ACTOR
    assert intent.actor_ref != evidence.provenance.collector_ref
