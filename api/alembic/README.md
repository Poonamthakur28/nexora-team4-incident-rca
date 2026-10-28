# Alembic migrations

This is the single migration home for the Team 4 PostgreSQL schema. `env.py` reads `DATABASE_URL` through `app.core.config` and targets `app.db.base.Base.metadata`.

No revisions exist yet. Do not add domain tables until the relationships in [the ERD document](../../docs/erd/team4-erd.md) are approved.

Run from `api/` with the virtual environment active:

```sh
alembic upgrade head                              # apply migrations (no-op today)
alembic revision --autogenerate -m "describe it"  # after approved models are added
alembic upgrade head --sql                        # print SQL without connecting
```
