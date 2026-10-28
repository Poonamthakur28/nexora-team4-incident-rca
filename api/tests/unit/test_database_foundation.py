from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine

from app.core.config import API_ROOT
from app.db.models import Base
from app.services.database_health import is_database_reachable


def test_no_domain_tables_are_defined_yet() -> None:
    assert Base.metadata.tables == {}


def test_alembic_is_configured_with_no_revisions() -> None:
    config = Config(str(API_ROOT / "alembic.ini"))

    assert ScriptDirectory.from_config(config).get_heads() == []


def test_connectivity_check_succeeds_for_working_engine() -> None:
    engine = create_engine("sqlite://")
    try:
        assert is_database_reachable(engine) is True
    finally:
        engine.dispose()


def test_connectivity_check_returns_false_instead_of_raising(tmp_path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'missing-dir' / 'db.sqlite'}")
    try:
        assert is_database_reachable(engine) is False
    finally:
        engine.dispose()
