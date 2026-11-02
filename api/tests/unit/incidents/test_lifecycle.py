import pytest

from app.modules.incidents.errors import InvalidLifecycleTransition, SameStatusTransition
from app.modules.incidents.lifecycle import ALLOWED_TRANSITIONS, validate_transition


def test_transition_table_matches_the_proposed_lifecycle() -> None:
    assert dict(ALLOWED_TRANSITIONS) == {
        "open": frozenset({"investigating"}),
        "investigating": frozenset({"resolved"}),
        "resolved": frozenset({"investigating", "closed"}),
        "closed": frozenset(),
    }


@pytest.mark.parametrize(
    ("current", "target"),
    [
        ("open", "investigating"),
        ("investigating", "resolved"),
        ("resolved", "investigating"),
        ("resolved", "closed"),
    ],
)
def test_allowed_transitions(current: str, target: str) -> None:
    assert validate_transition(current, target) is None


@pytest.mark.parametrize(
    ("current", "target"),
    [
        ("open", "resolved"),
        ("open", "closed"),
        ("investigating", "open"),
        ("investigating", "closed"),
        ("resolved", "open"),
        ("closed", "open"),
        ("closed", "investigating"),
        ("closed", "resolved"),
    ],
)
def test_invalid_transitions_are_rejected(current: str, target: str) -> None:
    with pytest.raises(InvalidLifecycleTransition) as caught:
        validate_transition(current, target)

    assert caught.value.current == current
    assert caught.value.target == target


@pytest.mark.parametrize("target", ["open", "investigating", "resolved"])
def test_closed_is_terminal(target: str) -> None:
    with pytest.raises(InvalidLifecycleTransition) as caught:
        validate_transition("closed", target)

    assert caught.value.current == "closed"
    assert caught.value.target == target


@pytest.mark.parametrize("status", ["open", "investigating", "resolved", "closed"])
def test_same_status_transition_is_rejected(status: str) -> None:
    with pytest.raises(SameStatusTransition) as caught:
        validate_transition(status, status)

    assert caught.value.status == status
