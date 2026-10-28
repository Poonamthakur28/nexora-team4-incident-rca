"""Import point for ORM models so Alembic sees the full metadata. Intentionally empty for now."""

from app.db.base import Base

__all__ = ["Base"]
