# System overview

## Scope

This repository is the independent implementation boundary for Nexora Team 4: incident management and AI-assisted root cause analysis. It does not implement HRMS, project/task management, repository or deployment management, shared authentication, platform administration, cross-team adapters, or external observability integrations. References to externally owned records are opaque, typed IDs with an owner label. Local fixture data supports independent work.

## Architecture

Use a TypeScript modular monolith. The Express process in `api/` exposes REST under `/api/v1`; Team 4 modules own their services and data contracts; PostgreSQL is the intended persistence store through Prisma in `api/prisma`. The React/Vite application in `ui/` provides the Team 4 interface. Module boundaries are logical and do not imply separate deployment or separate databases. The root `package.json` is the npm workspace that runs both applications.

```text
React web ── REST /api/v1 ── Express application
                                  ├── Team 4 module contracts
                                  ├── Prisma client (connection configured)
                                  └── PostgreSQL (local Compose)
```

The health endpoints are `/health` and `/api/v1/health`. OpenAPI foundation is served at `/openapi.json` and `/docs`. Request bodies should be validated at route boundaries with Zod; errors are returned through centralized middleware and request logs use Pino.

## Data and security boundaries

- Team 4 owns the incident investigation entities listed in [the ERD foundation](../erd/team4-erd.md).
- Other-team identifiers remain references; this repository does not recreate their entities or databases.
- No secrets belong in source or fixtures. Use environment configuration and keep `.env` untracked.
- Tenant isolation must be designed once ownership, tenant key, and authentication claims are confirmed. No organization or authentication system is implemented here.
- AI output is an untrusted proposal with evidence links, uncertainty, missing information, and mandatory human review. A score cannot make a candidate confirmed.

## Current implementation status

The API bootstraps and answers health checks. The frontend supplies navigation and a reusable shell. Module directories contain initial typed contracts; only the AI RCA interface has a mock implementation. There are no finalized domain models, persistence repositories, business workflows, external integrations, or live AI calls.
