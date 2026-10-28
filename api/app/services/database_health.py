import logging

from sqlalchemy import Engine, text
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)


def is_database_reachable(engine: Engine) -> bool:
    """Run `SELECT 1`. Failures are logged without the connection URL and reported as False."""
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        logger.warning("Database connectivity check failed", extra={"error_type": type(exc).__name__})
        return False
    return True
