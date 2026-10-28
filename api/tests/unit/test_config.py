from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.config import Settings


@pytest.fixture(autouse=True)
def _clear_settings_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("APP_ENV", "API_HOST", "API_PORT", "LOG_LEVEL", "DATABASE_URL", "CORS_ORIGINS"):
        monkeypatch.delenv(name, raising=False)


def test_defaults_match_local_compose_setup() -> None:
    settings = Settings(_env_file=None)

    assert settings.app_env == "development"
    assert settings.api_port == 8000
    assert settings.database_url == "postgresql+psycopg://nexora:nexora@localhost:5432/nexora_team4"
    assert settings.cors_origins == ["http://localhost:5173"]


def test_reads_environment_variables(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("API_PORT", "9001")
    monkeypatch.setenv("LOG_LEVEL", "debug")
    monkeypatch.setenv("CORS_ORIGINS", "http://localhost:5173, http://127.0.0.1:5173 ,")

    settings = Settings(_env_file=None)

    assert settings.api_port == 9001
    assert settings.log_level == "DEBUG"
    assert settings.cors_origins == ["http://localhost:5173", "http://127.0.0.1:5173"]


def test_api_env_file_overrides_repository_env_file(tmp_path: Path) -> None:
    repo_env = tmp_path / "repo.env"
    api_env = tmp_path / "api.env"
    repo_env.write_text("API_PORT=7000\nLOG_LEVEL=warning\n", encoding="utf-8")
    api_env.write_text("API_PORT=7001\n", encoding="utf-8")

    settings = Settings(_env_file=(repo_env, api_env))

    assert settings.api_port == 7001
    assert settings.log_level == "WARNING"


@pytest.mark.parametrize(
    ("given", "expected"),
    [
        (
            "postgresql://nexora:nexora@localhost:5432/nexora_team4?schema=public",
            "postgresql+psycopg://nexora:nexora@localhost:5432/nexora_team4",
        ),
        (
            "postgres://u:p@db:5432/x?sslmode=require&schema=public",
            "postgresql+psycopg://u:p@db:5432/x?sslmode=require",
        ),
    ],
)
def test_database_url_is_normalized_to_psycopg(given: str, expected: str) -> None:
    assert Settings(_env_file=None, database_url=given).database_url == expected


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("database_url", "mysql://user:pass@localhost/db"),
        ("database_url", "sqlite:///local.db"),
        ("api_port", 0),
        ("api_port", 70000),
        ("app_env", "staging"),
        ("log_level", "verbose"),
        ("cors_origins", "*"),
    ],
)
def test_rejects_invalid_values(field: str, value: object) -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **{field: value})


def test_invalid_environment_variable_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("API_PORT", "not-a-number")

    with pytest.raises(ValidationError):
        Settings(_env_file=None)
