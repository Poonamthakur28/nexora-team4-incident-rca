from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Declarative base for Team 4 tables.

    No domain models are defined until the Team 4 ERD (docs/erd/team4-erd.md) is approved.
    Import new model modules in `app/db/models.py` so Alembic autogenerate can see them.
    """

    metadata = MetaData(naming_convention=NAMING_CONVENTION)
