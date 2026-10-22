# Local setup

## Prerequisites

- Node.js 20 or newer and npm.
- Docker Desktop / Docker Compose v2 for local PostgreSQL.

## Install and configure

```sh
npm install
Copy-Item .env.example .env # PowerShell; on macOS/Linux use: cp .env.example .env
```

The API uses port 3000, the UI uses Vite port 5173, and PostgreSQL uses 5432 by default. The example database URL matches the Compose defaults and is for local development only. Set `VITE_API_BASE_URL` to change the browser API endpoint.

## Run

```sh
docker compose up -d postgres
npm run dev:api
npm run dev:ui
```

Or use `npm run dev` to start both app processes together. Check `http://localhost:3000/health`, `http://localhost:3000/api/v1/health`, and `http://localhost:3000/docs`.

`npm install` at the repository root installs the `api` and `ui` workspaces. Copy `.env.example` to `.env` at the repository root. The API reads that file when it is started from `api/`, and Vite reads UI variables from the same root file.

## Verify and build

```sh
npm run lint
npm run typecheck
npm test
npm run build
```

Prisma is configured for PostgreSQL in `api/prisma/schema.prisma`, but the ERD has not been confirmed and no product schema is present. Do not create or deploy domain migrations until relationship decisions in [the ERD document](../erd/team4-erd.md) are resolved. `npm run db:generate` only becomes useful after confirmed models exist.

## Troubleshooting

- If port 5432 is in use, change the host port in Compose and update `DATABASE_URL`.
- If the UI cannot call the API, make sure `CORS_ORIGIN` matches its origin and set `VITE_API_BASE_URL` correctly.
- If local changes to environment variables do not take effect, restart the affected process.
- The mock RCA agent requires no credentials and is deterministic scaffolding, not a real analysis service.
