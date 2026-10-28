# Database migrations

No product migrations exist yet. The Team 4 ERD was not available when this foundation was created. Confirm relationships and lifecycle rules in `docs/erd/team4-erd.md` before adding migrations.

Migrations are managed by Alembic in [`api/alembic/`](../../api/alembic/README.md). This directory does not hold migrations; it is kept for this note only.

## Unresolved decisions

These stay open for tech-lead confirmation. No product model or migration was added with the identifier corrections.

- Confirm the entity list, foreign keys, and lifecycle states in `docs/erd/team4-erd.md` before creating tables.
- `incident_timeline` may be a stored entity or a derived view. That choice is still open.
- `InvestigationId` is a type owned by incident management. The proposed `rca_investigation` record, its keys, and its relationship to an incident are not approved.
- Tenant isolation and authentication remain platform decisions. This repository does not implement them.
