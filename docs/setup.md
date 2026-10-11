# Local setup

## Prerequisites

- Python 3.11+
- `uv`
- PostgreSQL 15+ or a Neon development database
- Node.js LTS and npm
- AI provider credentials are optional; deterministic cooking services do not require them.

## Backend (PowerShell)

From the repository root:

```powershell
cd backend
uv sync --extra dev
Copy-Item .env.example .env
```

Set `DATABASE_URL` in `backend/.env` to a development PostgreSQL connection string. Do not commit `.env`.

Apply migrations and start the API:

```powershell
uv run alembic upgrade head
$env:PYTHONPATH = (Resolve-Path .).Path
uv run --project . python ../scripts/seed_demo.py
uv run uvicorn app.main:app --reload --port 8000
```

Open `http://127.0.0.1:8000/docs`. `/health` checks process health; `/ready` checks database connectivity.

## Tests

```powershell
cd backend
uv sync --extra dev
uv run pytest
uv run ruff check .
```

The initial service tests use isolated in-memory SQLite for speed. PostgreSQL migration and transaction compatibility must be verified before release.

## MCP

From `backend/`, run `uv run python -m app.mcp_server` after configuring the database. The MCP server uses Streamable HTTP and the same application services, but currently runs as a separate process. Its demo identity is not suitable for public deployment. Verify initialization, discovery and calls with MCP Inspector before claiming protocol compliance.

## Frontend

```powershell
cd frontend
npm install
Copy-Item .env.example .env
npm run dev
```

Set `VITE_API_BASE_URL=http://127.0.0.1:8000`. Frontend dependencies will be locked once the first local npm install is performed; commit `package-lock.json` before relying on `npm ci` in CI.
