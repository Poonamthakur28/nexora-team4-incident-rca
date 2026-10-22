# Database migrations

No product migrations exist yet. The Team 4 ERD was not available when this foundation was created. Confirm relationships and lifecycle rules in `docs/erd/team4-erd.md` before adding migrations.

## Unresolved decisions

These stay open for tech-lead confirmation. No product model or migration was added with the identifier corrections.

- Confirm the entity list, foreign keys, and lifecycle states in `docs/erd/team4-erd.md` before creating tables.
- Choose one migration home: Prisma Migrate under `api/prisma/migrations`, or SQL files in this directory. Do not maintain both.
- `incident_timeline` may be a stored entity or a derived view. That choice is still open.
- `InvestigationId` is a type owned by incident management. The proposed `rca_investigation` record, its keys, and its relationship to an incident are not approved.
- Tenant isolation and authentication remain platform decisions. This repository does not implement them.
