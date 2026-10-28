# Local setup

## Prerequisites

- Python 3.11 or newer.
- Node.js 20 or newer and npm.
- Docker Desktop / Docker Compose v2 for local PostgreSQL.

## Install and configure

```sh
Copy-Item .env.example .env # PowerShell; on macOS/Linux use: cp .env.example .env
cd api
py -3.11 -m venv .venv      # macOS/Linux: python3 -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements-dev.txt   # macOS/Linux: .venv/bin/python -m pip ...
cd ..
npm install
```

The API uses port 8000, the UI uses Vite port 5173, and PostgreSQL uses 5432 by default. The example database URL matches the Compose defaults and is for local development only. Set `VITE_API_BASE_URL` to change the browser API endpoint.

The API reads the root `.env`, then `api/.env` (which overrides it). Vite reads UI variables from the root `.env`.

## Run

```sh
docker compose up -d postgres
npm run dev:api
npm run dev:ui
```

Or use `npm run dev` to start both app processes together. Check `http://localhost:8000/health`, `http://localhost:8000/api/v1/health`, `http://localhost:8000/api/v1/health/database`, and `http://localhost:8000/docs`.

## Verify and build

```sh
npm test            # pytest (backend)
npm run lint        # ESLint (frontend)
npm run typecheck   # TypeScript (frontend)
npm run build       # Vite production build
```

SQLAlchemy and Alembic are configured for PostgreSQL in `api/app/db/` and `api/alembic/`, but the ERD has not been confirmed and no product schema is present. Do not create or deploy domain migrations until relationship decisions in [the ERD document](../erd/team4-erd.md) are resolved.

## Troubleshooting

- If port 5432 is in use, change the host port in Compose and update `DATABASE_URL`.
- If the UI cannot call the API, make sure `CORS_ORIGINS` includes the UI origin and `VITE_API_BASE_URL` points at the API.
- If `npm run dev:api` reports that no virtual environment was found, create `api/.venv` as shown above.
- `GET /api/v1/health/database` returning 503 means PostgreSQL is not reachable at `DATABASE_URL`. `GET /health` does not depend on the database.
- If local changes to environment variables do not take effect, restart the affected process.
- The mock RCA agent requires no credentials and is deterministic scaffolding, not a real analysis service.
