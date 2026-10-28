"""Team 4 record ids and references to ids owned by other teams.

These are different types: a Team 4 id is a distinct string type, and an external
reference is an opaque id plus the owning team. Neither is a foreign key.
"""

from typing import NewType

from pydantic import BaseModel, ConfigDict

Team4EntityId = NewType("Team4EntityId", str)
"""Identifier of a record this repository owns."""


class ExternalRef(BaseModel):
    """Canonical reference to a record owned outside Team 4."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    owner: str
    id: str


def as_team4_entity_id(value: str) -> Team4EntityId:
    return Team4EntityId(value)


def as_external_ref(owner: str, value: str) -> ExternalRef:
    return ExternalRef(owner=owner, id=value)
