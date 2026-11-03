import pytest

from app.modules.evidence_collection.contracts import Provenance
from app.modules.ingestion.contracts import Observation
from app.modules.ingestion.errors import (
    IngestionConfigurationError,
    InvalidConnectorContext,
    InvalidObservationRequest,
    ObservationAuthorizationDenied,
)
from app.modules.ingestion.ports import (
    AuthenticatedConnectorContext,
    InMemorySourceAccountAuthorizer,
)
from app.modules.ingestion.validation import Stage1Result, validate_observation_stage1
from app.shared.identifiers import ExternalRef, as_external_ref
from tests.unit.ingestion.test_contracts import observation_payload, provenance

ORG = "org_synth_0001"
OTHER_ORG = "org_synth_9999"
REGISTRATION = as_external_ref("team5.connector", "conn_synth_monitor_01")
REPLACEMENT = as_external_ref("team5.connector", "conn_synth_monitor_02")
ACCOUNT = as_external_ref("synthetic-monitor", "acct_synth_0001")
OTHER_ACCOUNT = as_external_ref("synthetic-monitor", "acct_synth_0099")
_DENIAL = "The observation was denied."


class RecordingAuthorizer:
    def __init__(self, grants: set[tuple[str, ExternalRef, ExternalRef]]) -> None:
        self.grants = set(grants)
        self.calls: list[tuple[str, str, str]] = []

    def is_authorized(
        self,
        registration_ref: ExternalRef,
        source_account_ref: ExternalRef,
        organization_id: str,
    ) -> bool:
        self.calls.append((organization_id, registration_ref.id, source_account_ref.id))
        return (organization_id, registration_ref, source_account_ref) in self.grants


def observation(**overrides: object) -> Observation:
    return Observation.model_validate(observation_payload(**overrides))


def context(
    organization_id: str = ORG, registration: ExternalRef = REGISTRATION
) -> AuthenticatedConnectorContext:
    return AuthenticatedConnectorContext(
        organization_id=organization_id, registration_ref=registration
    )


def authorizer(*grants: tuple[str, ExternalRef, ExternalRef]) -> RecordingAuthorizer:
    if not grants:
        grants = ((ORG, REGISTRATION, ACCOUNT),)
    return RecordingAuthorizer(set(grants))


def test_authorized_observation_passes_stage1_without_a_receipt() -> None:
    checker = authorizer()

    result = validate_observation_stage1(observation(), context(), checker)

    assert result == Stage1Result(organization_id=ORG)
    assert not hasattr(result, "delivery_id")
    assert checker.calls == [(ORG, REGISTRATION.id, ACCOUNT.id)]


def test_wrong_provenance_origin_is_an_invalid_request_and_does_not_authorize() -> None:
    built = observation()
    values = built.model_dump()
    values["provenance"] = Provenance(
        origin_type="manual",
        provider=None,
        source_event_id=None,
        source_account_ref=None,
        collector_ref=REGISTRATION,
    )
    bypassed = Observation.model_construct(**values)
    checker = authorizer()

    with pytest.raises(InvalidObservationRequest):
        validate_observation_stage1(bypassed, context(), checker)

    assert checker.calls == []


def test_substituted_collector_is_denied_without_consulting_the_authorizer() -> None:
    substituted = observation(
        provenance=provenance(
            collectorRef={"owner": "team5.connector", "id": "conn_synth_monitor_99"}
        )
    )
    checker = authorizer()

    with pytest.raises(ObservationAuthorizationDenied) as caught:
        validate_observation_stage1(substituted, context(), checker)

    assert str(caught.value) == _DENIAL
    assert "conn_synth_monitor_99" not in str(caught.value)
    assert checker.calls == []


def test_provenance_source_account_mismatch_is_denied() -> None:
    mismatched = observation(
        provenance=provenance(
            sourceAccountRef={"owner": "synthetic-monitor", "id": "acct_synth_0002"}
        )
    )

    checker = authorizer()

    with pytest.raises(ObservationAuthorizationDenied) as caught:
        validate_observation_stage1(mismatched, context(), checker)

    assert str(caught.value) == _DENIAL
    assert "acct_synth_0002" not in str(caught.value)
    assert checker.calls == []


def test_unauthorized_source_account_is_denied_without_disclosing_it() -> None:
    unauthorized = observation(
        sourceAccountRef={"owner": OTHER_ACCOUNT.owner, "id": OTHER_ACCOUNT.id},
        provenance=provenance(
            sourceAccountRef={"owner": OTHER_ACCOUNT.owner, "id": OTHER_ACCOUNT.id}
        ),
    )

    with pytest.raises(ObservationAuthorizationDenied) as caught:
        validate_observation_stage1(unauthorized, context(), authorizer())

    assert str(caught.value) == _DENIAL
    assert OTHER_ACCOUNT.id not in str(caught.value)
    assert ORG not in str(caught.value)


def test_grant_for_another_organization_does_not_authorize_this_context() -> None:
    checker = authorizer((OTHER_ORG, REGISTRATION, ACCOUNT))

    with pytest.raises(ObservationAuthorizationDenied) as caught:
        validate_observation_stage1(observation(), context(ORG), checker)

    assert str(caught.value) == _DENIAL
    assert OTHER_ORG not in str(caught.value)
    assert checker.calls == [(ORG, REGISTRATION.id, ACCOUNT.id)]


def test_replacement_registration_authorized_for_the_same_account_passes() -> None:
    replaced = observation(
        provenance=provenance(collectorRef={"owner": REPLACEMENT.owner, "id": REPLACEMENT.id})
    )
    checker = authorizer((ORG, REPLACEMENT, ACCOUNT))

    result = validate_observation_stage1(replaced, context(registration=REPLACEMENT), checker)

    assert result.organization_id == ORG
    assert checker.calls == [(ORG, REPLACEMENT.id, ACCOUNT.id)]


def test_stage1_does_not_reject_provider_or_source_event_mismatch() -> None:
    provider_mismatch = observation(provenance=provenance(provider="other-monitor"))
    event_mismatch = observation(provenance=provenance(sourceEventId="evt-other"))

    assert validate_observation_stage1(provider_mismatch, context(), authorizer()) == Stage1Result(
        ORG
    )
    assert validate_observation_stage1(event_mismatch, context(), authorizer()) == Stage1Result(
        ORG
    )
    assert provider_mismatch.provenance.provider != provider_mismatch.source
    assert event_mismatch.provenance.source_event_id != event_mismatch.source_event_id


def test_clock_skew_is_not_a_stage1_failure() -> None:
    future = observation(occurredAt="2099-01-01T00:00:00Z")

    assert validate_observation_stage1(future, context(), authorizer()) == Stage1Result(ORG)


def test_allow_list_authorizer_matches_only_the_granted_triple() -> None:
    grants = InMemorySourceAccountAuthorizer([(ORG, REGISTRATION, ACCOUNT)])

    assert grants.is_authorized(REGISTRATION, ACCOUNT, ORG) is True
    assert grants.is_authorized(REGISTRATION, ACCOUNT, OTHER_ORG) is False
    assert grants.is_authorized(REPLACEMENT, ACCOUNT, ORG) is False
    assert grants.is_authorized(REGISTRATION, OTHER_ACCOUNT, ORG) is False


def test_blank_connector_organization_is_rejected() -> None:
    with pytest.raises(InvalidConnectorContext):
        context(organization_id="   ")


def test_blank_registration_owner_is_rejected() -> None:
    with pytest.raises(InvalidConnectorContext) as caught:
        AuthenticatedConnectorContext(
            organization_id=ORG,
            registration_ref=as_external_ref(" ", "conn_synth_monitor_01"),
        )
    assert str(caught.value) == "A trusted connector registration is required."
    assert "conn_synth_monitor_01" not in str(caught.value)


def test_blank_registration_id_is_rejected() -> None:
    with pytest.raises(InvalidConnectorContext) as caught:
        AuthenticatedConnectorContext(
            organization_id=ORG,
            registration_ref=as_external_ref("team5.connector", ""),
        )
    assert str(caught.value) == "A trusted connector registration is required."
    assert "team5.connector" not in str(caught.value)


def test_organization_id_is_stripped() -> None:
    built = context(organization_id="  org_synth_0001 \t")
    assert built.organization_id == ORG
    assert built.registration_ref == REGISTRATION


def test_authorizer_failure_is_a_configuration_error_not_a_denial() -> None:
    class RaisingAuthorizer:
        def is_authorized(
            self,
            registration_ref: ExternalRef,
            source_account_ref: ExternalRef,
            organization_id: str,
        ) -> bool:
            raise RuntimeError(f"secret registry path for {source_account_ref.id}")

    with pytest.raises(IngestionConfigurationError) as caught:
        validate_observation_stage1(observation(), context(), RaisingAuthorizer())

    assert str(caught.value) == "The source-account authorizer failed."
    assert isinstance(caught.value.__cause__, RuntimeError)
    assert "secret" not in str(caught.value)


def test_non_boolean_authorizer_result_is_a_configuration_error() -> None:
    class NonBooleanAuthorizer:
        def is_authorized(
            self,
            registration_ref: ExternalRef,
            source_account_ref: ExternalRef,
            organization_id: str,
        ) -> object:
            return "yes"

    with pytest.raises(IngestionConfigurationError):
        validate_observation_stage1(observation(), context(), NonBooleanAuthorizer())


def test_stage1_uses_the_in_memory_authorizer() -> None:
    grants = InMemorySourceAccountAuthorizer([(ORG, REGISTRATION, ACCOUNT)])

    assert validate_observation_stage1(observation(), context(), grants) == Stage1Result(ORG)
