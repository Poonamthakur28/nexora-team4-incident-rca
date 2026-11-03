from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.modules.timeline.contracts import TimelineEntry

OCCURRED = "2026-10-01T09:15:04Z"


def entry_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "id": "tl:incident.opened:incident-1",
        "organizationId": "org_synth_0001",
        "incidentId": "incident-1",
        "category": "incident.opened",
        "sourceKind": "incident",
        "sourceId": "incident-1",
        "occurredAt": OCCURRED,
        "recordedAt": OCCURRED,
        "label": "Incident opened",
        "detail": "Checkout API error rate above threshold",
    }
    payload.update(overrides)
    return payload


def test_timeline_entry_serializes_with_camel_case() -> None:
    entry = TimelineEntry.model_validate(entry_payload())

    dumped = entry.model_dump(by_alias=True, mode="json")

    assert set(dumped) == {
        "id",
        "organizationId",
        "incidentId",
        "category",
        "sourceKind",
        "sourceId",
        "occurredAt",
        "recordedAt",
        "label",
        "detail",
    }
    assert dumped["organizationId"] == "org_synth_0001"
    assert dumped["sourceKind"] == "incident"
    assert dumped["occurredAt"] == OCCURRED
    assert dumped["recordedAt"] == OCCURRED
    assert "organization_id" not in dumped


def test_timeline_entry_rejects_unknown_category_and_extra_fields() -> None:
    with pytest.raises(ValidationError):
        TimelineEntry.model_validate(entry_payload(category="observation.bound"))
    with pytest.raises(ValidationError):
        TimelineEntry.model_validate(entry_payload(auditIntentId="event-1"))
    with pytest.raises(ValidationError):
        TimelineEntry.model_validate(entry_payload(occurredAt=datetime(2026, 10, 1, 9, 15, 4)))
