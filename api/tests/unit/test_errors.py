from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.errors import (
    ContentReferenceNotConfigured,
    map_evidence_domain_error,
    map_incident_domain_error,
)
from app.modules.evidence_collection.errors import (
    EvidenceNotFound,
    EvidenceServiceConfigurationError,
    InvalidEvidenceInput,
)
from app.main import create_app
from app.modules.incidents.errors import (
    IncidentNotFound,
    InvalidIncidentInput,
    InvalidLifecycleTransition,
    InvalidRequestContext,
    OrganizationScopeError,
    SameStatusTransition,
    UncertainIncidentCreate,
)


def test_unexpected_failure_returns_500_without_internal_details(settings: Settings) -> None:
    app = create_app(settings)

    @app.get("/boom")
    def boom() -> None:
        raise RuntimeError("database credential detail")

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/boom")

    assert response.status_code == 500
    assert response.json() == {
        "error": {"code": "INTERNAL_SERVER_ERROR", "message": "An unexpected error occurred."}
    }
    assert "database credential detail" not in response.text
    assert "Traceback" not in response.text


def test_wrong_method_returns_structured_error(settings: Settings) -> None:
    with TestClient(create_app(settings)) as client:
        response = client.post("/health")

    assert response.status_code == 405
    assert response.json()["error"]["code"] == "METHOD_NOT_ALLOWED"
    assert "allow" in response.headers


def test_incident_domain_errors_map_to_reviewed_http_codes() -> None:
    assert map_incident_domain_error(IncidentNotFound("id-1")) == (
        404,
        "INCIDENT_NOT_FOUND",
        "Incident id-1 was not found.",
    )
    assert map_incident_domain_error(InvalidLifecycleTransition("open", "closed"))[0:2] == (
        409,
        "INVALID_LIFECYCLE_TRANSITION",
    )
    assert map_incident_domain_error(SameStatusTransition("open"))[0:2] == (409, "SAME_STATUS_TRANSITION")
    assert map_incident_domain_error(OrganizationScopeError("missing org"))[0:2] == (
        400,
        "INVALID_REQUEST_CONTEXT",
    )
    assert map_incident_domain_error(InvalidRequestContext("missing actor"))[0:2] == (
        400,
        "INVALID_REQUEST_CONTEXT",
    )
    assert map_incident_domain_error(InvalidIncidentInput("empty assignment"))[0:2] == (
        400,
        "INVALID_INCIDENT_INPUT",
    )

    uncertain = UncertainIncidentCreate("secret-orphan-id")
    status_code, code, message = map_incident_domain_error(uncertain)
    assert (status_code, code, message) == (500, "INTERNAL_SERVER_ERROR", "An unexpected error occurred.")
    assert "secret-orphan-id" not in message


def test_evidence_domain_errors_map_to_http_codes() -> None:
    assert map_evidence_domain_error(EvidenceNotFound("ev-1")) == (
        404,
        "EVIDENCE_NOT_FOUND",
        "Evidence ev-1 was not found.",
    )
    assert map_evidence_domain_error(InvalidEvidenceInput("bad input"))[0:2] == (400, "INVALID_EVIDENCE_INPUT")
    assert map_evidence_domain_error(EvidenceServiceConfigurationError("clock")) == (
        500,
        "INTERNAL_SERVER_ERROR",
        "An unexpected error occurred.",
    )


def test_unconfigured_content_reference_returns_400_without_internal_details(
    settings: Settings,
) -> None:
    app = create_app(settings)

    @app.get("/content-ref-unconfigured")
    def unconfigured() -> None:
        raise ContentReferenceNotConfigured()

    with TestClient(app) as client:
        response = client.get("/content-ref-unconfigured")

    assert response.status_code == 400
    assert response.json() == {
        "error": {
            "code": "CONTENT_REFERENCE_NOT_CONFIGURED",
            "message": "Content-reference verification is not configured.",
        }
    }
    assert "content_verifier" not in response.text
    assert "Traceback" not in response.text
