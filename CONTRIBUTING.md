# Contributing

## Scope

Contributions must stay within Team 4's incident management and RCA ownership. Do not add cross-team service folders, integrations, copies of externally owned entities, or platform authentication/administration. See the [module catalog](docs/module-specifications/module-catalog.md) and [system overview](docs/architecture/system-overview.md).

## Branches and pull requests

- Branch from `main` using a short descriptive name such as `feat/evidence-contract` or `fix/timeline-validation`.
- Keep changes focused and explain the Team 4 module and behavior affected.
- Include migration rationale and updated ERD documentation for approved data model changes.
- Describe validation performed and call out unconfirmed assumptions.

## Code style

- Backend: Python 3.11+, FastAPI, Pydantic, SQLAlchemy, Alembic. Use type hints throughout.
- Frontend: TypeScript strict mode is enabled. Use Prettier and ESLint conventions.
- Backend code belongs in `api/`. Frontend code belongs in `ui/`. Keep routes thin; put business rules in module services and persistence behind repositories.
- Validate untrusted request data at boundaries with Pydantic models.
- Use typed external references instead of recreating other teams' entities.
- Keep AI candidates traceable to evidence and subject to human review.
- Use UTC timestamps and never commit secrets or real incident data.

## Checks

Run `npm test` (pytest), `npm run lint`, `npm run typecheck`, and `npm run build` before opening a pull request. Add tests for implemented behavior; do not create migrations for unresolved ERD hypotheses.
