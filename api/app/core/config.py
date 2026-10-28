from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

API_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = API_ROOT.parent

LogLevel = Literal["CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"]

_POSTGRES_SCHEMES = {"postgres", "postgresql", "postgresql+psycopg"}


class Settings(BaseSettings):
    """Process configuration from the environment, then `api/.env`, then the repository `.env`."""

    model_config = SettingsConfigDict(
        # Later files take precedence, so `api/.env` overrides the repository `.env`.
        env_file=(REPO_ROOT / ".env", API_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: Literal["development", "test", "production"] = "development"
    api_host: str = "127.0.0.1"
    api_port: int = Field(default=8000, ge=1, le=65535)
    log_level: LogLevel = "INFO"
    database_url: str = "postgresql+psycopg://nexora:nexora@localhost:5432/nexora_team4"
    database_connect_timeout_seconds: int = Field(default=3, ge=1, le=60)
    cors_origins: Annotated[list[str], NoDecode] = ["http://localhost:5173"]

    @field_validator("log_level", mode="before")
    @classmethod
    def _normalize_log_level(cls, value: object) -> object:
        return value.upper() if isinstance(value, str) else value

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_cors_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @field_validator("cors_origins")
    @classmethod
    def _reject_wildcard_origin(cls, value: list[str]) -> list[str]:
        if "*" in value:
            raise ValueError("CORS_ORIGINS must list explicit origins; '*' is not allowed")
        return value

    @field_validator("database_url")
    @classmethod
    def _normalize_database_url(cls, value: str) -> str:
        parts = urlsplit(value)
        if parts.scheme not in _POSTGRES_SCHEMES:
            raise ValueError("DATABASE_URL must be a PostgreSQL URL (postgresql+psycopg://...)")
        # Prisma-style `?schema=` is not a libpq parameter and would be rejected by psycopg.
        query = urlencode([(k, v) for k, v in parse_qsl(parts.query) if k != "schema"])
        return urlunsplit(("postgresql+psycopg", parts.netloc, parts.path, query, parts.fragment))


@lru_cache
def get_settings() -> Settings:
    return Settings()
