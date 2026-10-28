from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field


class HealthQuery(BaseModel):
    """The health endpoints accept no query parameters."""

    model_config = ConfigDict(extra="forbid")


class HealthResponse(BaseModel):
    status: Literal["ok"] = Field(description="The API process is running and serving requests.")
    service: str = Field(examples=["nexora-team4-incident-rca"])
    timestamp: AwareDatetime = Field(description="Server time in UTC (ISO 8601).")


class DatabaseHealthResponse(BaseModel):
    status: Literal["ok", "unavailable"]
    database: Literal["reachable", "unreachable"]
    timestamp: AwareDatetime = Field(description="Server time in UTC (ISO 8601).")
