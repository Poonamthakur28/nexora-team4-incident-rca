# Nexora Team 4 — Incident Management & AI Root Cause Analysis

Independent Team 4 modular-monolith foundation for incident investigation, evidence handling, AI-assisted root cause candidates, human review, and audit history.

## Status

This is an initial repository setup, not a complete product. It includes an Express health API, versioned route base, OpenAPI/Swagger foundation, structured logging, React navigation shell, Team 4 module contracts, a deterministic mock RCA agent, PostgreSQL Compose configuration, and CI. Domain persistence/workflows, AI model calls, and integrations are not implemented.

No Team 4 ERD was found in the workspace. The expected entity inventory and unconfirmed relationship decisions are documented in [docs/erd/team4-erd.md](docs/erd/team4-erd.md); no product models or migrations have been finalized.

## Prerequisites

- Node.js 20+ and npm
- Docker Desktop with Compose v2 for PostgreSQL

## Setup and commands

```sh
npm install
Copy-Item .env.example .env # PowerShell; use cp .env.example .env on macOS/Linux
docker compose up -d postgres
npm run dev:api
npm run dev:ui
```

Or run both application processes using `npm run dev`.

| Purpose | Command |
|---|---|
| Install dependencies | `npm install` |
| Start PostgreSQL | `docker compose up -d postgres` |
| Stop PostgreSQL | `docker compose down` |
| Run API | `npm run dev:api` |
| Run UI | `npm run dev:ui` |
| Run API and UI | `npm run dev` |
| Lint | `npm run lint` |
| Type check | `npm run typecheck` |
| Unit tests | `npm test` |
| Integration tests | `npm run test:integration` |
| Build | `npm run build` |

API: `http://localhost:3000`; health: `/health` and `/api/v1/health`; Swagger UI: `/docs`; OpenAPI JSON: `/openapi.json`. UI: `http://localhost:5173`.

The root package is an npm workspace. Install once from the repository root. API scripts live in `api/package.json`; UI scripts live in `ui/package.json`.

## Structure

```text
api/src/                Express app and 12 Team 4 modules
api/tests/              API unit, integration, and e2e test locations
api/prisma/             PostgreSQL datasource; no unapproved domain models
ui/                     React + Vite navigation shell
database/               Migrations, seeds, and local fixtures
docs/                   Architecture, ERD decisions, module catalog, setup
.github/workflows/      CI lint, types, tests, and builds
```

See the [module catalog](docs/module-specifications/module-catalog.md), [system overview](docs/architecture/system-overview.md), and [local setup guide](docs/development-guide/local-setup.md).

## Decisions awaiting confirmation

- Team 4 ERD, foreign-key cardinalities, and deletion/retention rules.
- Whether `incident_timeline` is a stored entity or derived view.
- Lifecycle states and transitions for incidents, investigations, candidates, reviews, fixes, tests, and resolutions.
- Ownership and external-reference model for remediation tasks and proposed code changes.
- Tenant key and isolation policy, to be clarified with the platform owner.
- Query patterns that should determine final indexes.

## Security and scope

This repository does not include other teams' systems, shared authentication, cross-team clients/adapters, or external observability integrations. Use opaque external references and synthetic fixtures. Keep `.env` local and never commit secrets. Human review is required for AI-generated root-cause candidates and fix proposals.

## Verification record

Commands and their observed outcomes are recorded in the completion report for this setup. Re-run the commands above after changes.
