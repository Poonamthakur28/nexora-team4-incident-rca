# Nexora Team 4 — Incident Management & AI Root Cause Analysis

Independent Team 4 modular-monolith foundation for incident investigation, evidence handling, AI-assisted root cause candidates, human review, and audit history.

## Status

This is an initial repository setup, not a complete product. It includes:

- A FastAPI (Python) API with health endpoints, a versioned `/api/v1` route base, and generated OpenAPI/Swagger docs.
- Pydantic settings, structured JSON logging, and SQLAlchemy + Alembic configured for PostgreSQL.
- Team 4 module contracts as Pydantic models and a deterministic mock RCA agent.
- A React + Vite navigation shell, PostgreSQL Docker Compose configuration, and CI.

Domain persistence and workflows, AI model calls, background workers, and integrations are not implemented.

No Team 4 ERD was found in the workspace. The expected entity inventory and unconfirmed relationship decisions are documented in [docs/erd/team4-erd.md](docs/erd/team4-erd.md). No product tables or migrations have been created.

## Prerequisites

- Python 3.11 or newer (CI uses 3.11)
- Node.js 20+ and npm (CI uses Node 22)
- Docker Desktop with Compose v2, for PostgreSQL 16

## Setup

### 1. Environment file

Copy the example at the repository root. Skip this step if you already have a `.env`, and compare it with `.env.example` instead.

```sh
Copy-Item .env.example .env   # PowerShell
cp .env.example .env          # macOS/Linux
```

The API reads the root `.env`, then `api/.env` (which overrides it). Real environment variables win over both. Vite reads `VITE_*` variables from the root `.env`.

| Variable | Default | Purpose |
|---|---|---|
| `APP_ENV` | `development` | `development`, `test`, or `production` |
| `API_HOST` / `API_PORT` | `127.0.0.1` / `8000` | API bind address |
| `LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` |
| `DATABASE_URL` | `postgresql+psycopg://nexora:nexora@localhost:5432/nexora_team4` | PostgreSQL connection (local Compose defaults only) |
| `CORS_ORIGINS` | `http://localhost:5173` | Comma-separated allowed browser origins; `*` is rejected |
| `VITE_API_BASE_URL` | `http://localhost:8000/api/v1` | Browser API base URL |

If your `.env` was created for the earlier Express backend, rename `PORT` to `API_PORT` and `CORS_ORIGIN` to `CORS_ORIGINS`, and change `VITE_API_BASE_URL` to port 8000. An old Prisma-style `DATABASE_URL` (`postgresql://...?schema=public`) is still accepted and normalized.

### 2. Backend (Python virtual environment)

```sh
# PowerShell
cd api
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
cd ..

# macOS/Linux
cd api
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
cd ..
```

`requirements.txt` holds the runtime dependencies. `requirements-dev.txt` adds the test tools.

### 3. Frontend

```sh
npm install
```

The root `package.json` is an npm workspace containing `ui/`. The API is not an npm package. Root scripts that start or test it run `api/.venv`'s Python through `scripts/run-api.js`.

### 4. PostgreSQL

```sh
docker compose up -d postgres     # start (data persists in the team4-postgres-data volume)
docker compose ps                 # check health
docker compose stop postgres      # stop without removing anything
```

## Running

| Purpose | Command |
|---|---|
| API with auto-reload | `npm run dev:api` (or from `api/` with the venv active: `python -m app --reload`) |
| API without reload | `npm start` (or `python -m app`) |
| React UI | `npm run dev:ui` |
| API and UI together | `npm run dev` |

API: `http://localhost:8000`. UI: `http://localhost:5173`.

| Endpoint | Purpose |
|---|---|
| `GET /health` | Liveness. Does not touch PostgreSQL. |
| `GET /api/v1/health` | Versioned liveness, same response. |
| `GET /api/v1/health/database` | Runs `SELECT 1`; returns 200 when PostgreSQL is reachable, 503 otherwise. |
| `/docs` | Swagger UI |
| `/openapi.json` | OpenAPI schema |

Health response:

```json
{ "status": "ok", "service": "nexora-team4-incident-rca", "timestamp": "2026-01-01T00:00:00.000000Z" }
```

## Tests and checks

| Purpose | Command |
|---|---|
| Backend tests (pytest) | `npm test` (or from `api/` with the venv active: `python -m pytest`) |
| Backend unit / integration tests | `npm run test:unit` / `npm run test:integration` |
| Frontend lint | `npm run lint` |
| Frontend type check | `npm run typecheck` |
| Frontend build | `npm run build` |

Backend tests do not need PostgreSQL. They use an unreachable database URL and in-memory SQLite to exercise the connectivity check.

## Database migrations

Alembic in `api/alembic/` is the single migration home. There are no revisions yet.

```sh
npm run db:migrate     # alembic upgrade head (no-op until revisions exist)
npm run db:current     # show the applied revision
```

See [api/alembic/README.md](api/alembic/README.md). Do not add domain tables until the ERD is approved.

## Structure

```text
api/app/main.py         FastAPI application factory
api/app/core/           Settings, logging, error handlers
api/app/api/            Routers (/health, /api/v1) and dependencies
api/app/schemas/        API request/response models
api/app/services/       Application services (database connectivity check)
api/app/db/             SQLAlchemy base, engine and session setup; no domain models
api/app/modules/        Contracts for the 12 Team 4 modules (RCA-001 to RCA-012)
api/app/shared/         Team 4 ids and external references
api/alembic/            Migrations (none yet)
api/tests/              pytest unit and integration tests
ui/                     React + Vite navigation shell
scripts/run-api.js      Runs API commands with the api/.venv interpreter
database/               Seeds and local fixtures
docs/                   Architecture, ERD decisions, module catalog, setup
.github/workflows/      CI: pytest + Alembic check; UI lint, types, build
```

See the [module catalog](docs/module-specifications/module-catalog.md), [system overview](docs/architecture/system-overview.md), and [local setup guide](docs/development-guide/local-setup.md).

## Decisions awaiting confirmation

- Team 4 ERD, foreign-key cardinalities, and deletion/retention rules.
- Whether `incident_timeline` is a stored entity or derived view.
- Lifecycle states and transitions for incidents, investigations, candidates, reviews, fixes, tests, and resolutions.
- Ownership and external-reference model for remediation tasks and proposed code changes.
- Tenant key and isolation policy, to be clarified with the platform owner.
- Query patterns that should determine final indexes.
- Background job runner (Celery or arq with Redis) for a later phase.

## Security and scope

This repository does not include other teams' systems, shared authentication, cross-team clients/adapters, or external observability integrations. Use opaque external references and synthetic fixtures. Keep `.env` local and never commit secrets. Human review is required for AI-generated root-cause candidates and fix proposals.
