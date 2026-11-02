"""Proposed incident lifecycle (CT-04 §6.3, D-06).

The allowed pairs live here so the incident service does not own the table.
D-06 is Proposed and is not an agreed contract.
"""

from collections.abc import Mapping
from types import MappingProxyType

from app.modules.incidents.contracts import IncidentStatus
from app.modules.incidents.errors import InvalidLifecycleTransition, SameStatusTransition

ALLOWED_TRANSITIONS: Mapping[IncidentStatus, frozenset[IncidentStatus]] = MappingProxyType(
    {
        "open": frozenset({"investigating"}),
        "investigating": frozenset({"resolved"}),
        "resolved": frozenset({"investigating", "closed"}),
        "closed": frozenset(),
    }
)


def validate_transition(current: IncidentStatus, target: IncidentStatus) -> None:
    """Accept one allowed status change.

    Repeating the current status raises SameStatusTransition.
    Every other pair, including any move out of closed, raises InvalidLifecycleTransition.
    """
    if current == target:
        raise SameStatusTransition(current)
    allowed = ALLOWED_TRANSITIONS.get(current)
    if allowed is None or target not in allowed:
        raise InvalidLifecycleTransition(current, target)
