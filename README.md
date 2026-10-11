# Rasoi Relay

**A voice-first kitchen companion that remembers where cooking stopped and helps people safely resume.**

Rasoi Relay focuses on persistent cooking context across multiple dishes, interruptions, timers and household preferences. The assistant retrieves confirmed state, distinguishes estimates from facts, and asks for confirmation when a physical condition is unknown.

> Alexa+ experience is simulated unless a real integration is authorized and verified. Rasoi Relay is a cooking guidance tool, not a certified safety device.

## Current implementation status

- **Implemented in repository:** SQLAlchemy domain models; initial Alembic migration; deterministic meal creation, dependency-aware next action, step completion, interruption recovery and explicit resume, plan revision, preference storage, absolute timer deadlines, serving-time feasibility estimates and bounded household timing adaptation; FastAPI endpoints; official Python MCP SDK tool adapter; React dashboard; real browser MCP client calls for recovery, optional browser speech recognition/synthesis; scoped demo load/reset; initial unit tests; CI and deployment scaffolding.
- **Not yet verified:** dependency installation, lockfile generation, local test execution, Alembic against PostgreSQL, browser build, MCP Inspector, deployed endpoints and latency.
- **Not production-ready:** real authentication and MCP principal propagation are not implemented. Production mode rejects user API calls and MCP tools rather than accepting the demo identity. Do not deploy publicly for normal use until this is completed.
- **Not implemented yet:** hosted AI provider integration, richer intent handling, frontend end-to-end tests and verified deployment. Browser speech support is implemented as an optional progressive enhancement but remains untested.

See `docs/build-log.md` for the current verification status.

## Architecture

- Frontend: React, Vite, TypeScript, TanStack Query, Lucide icons and a warm responsive design.
- Backend: FastAPI, Pydantic, SQLAlchemy 2, Alembic and PostgreSQL.
- MCP: official Python MCP SDK using Streamable HTTP, mounted under `/mcp` in the FastAPI ASGI service.
- Database: Neon PostgreSQL in hosted environments; isolated SQLite databases are used for fast service unit tests only.
- Hosting target: Vercel frontend, Render API/MCP, Neon database.

The Python MCP SDK dependency is constrained to the 1.x line that supports the 2025-11-25 protocol revision; the TypeScript client SDK is likewise constrained to its 1.x line. Actual negotiation still needs verification with MCP Inspector. The REST API and MCP adapter call the same application service functions. PostgreSQL is the source of truth. AI output never directly mutates the database or establishes physical facts.

## Local setup

Prerequisites: Python 3.11+, `uv`, PostgreSQL or a Neon development database, Node.js 20+ and npm.

### Backend

```powershell
cd backend
uv sync --extra dev
Copy-Item .env.example .env
```

Set `DATABASE_URL` in `backend/.env` to a development PostgreSQL URL using the `postgresql+psycopg://` scheme. Then run:

```powershell
uv run alembic upgrade head
$env:PYTHONPATH = (Resolve-Path .).Path
uv run --project . python ../scripts/seed_demo.py
uv run uvicorn app.main:app --reload --port 8000
```

API docs: `http://127.0.0.1:8000/docs`.
Health: `http://127.0.0.1:8000/health`.
Readiness: `http://127.0.0.1:8000/ready`.
MCP endpoint: `http://127.0.0.1:8000/mcp/`.

### Frontend

In a second terminal:

```powershell
cd frontend
npm install
Copy-Item .env.example .env
npm run dev
```

Set `VITE_API_BASE_URL=http://127.0.0.1:8000` in `frontend/.env`. Open the Vite URL printed by the command. The demo uses a development-only identity header and must not be exposed as a public authenticated product.

### Tests

```powershell
cd backend
uv run pytest
uv run ruff check .
```

In another terminal:

```powershell
cd frontend
npm run lint
npm run test
npm run build
```

Generate and commit `backend/uv.lock` and `frontend/package-lock.json` after installing dependencies locally. Until those lockfiles are committed, dependency installation is not fully reproducible and CI currently resolves package versions from the declared ranges.

## MCP tools

The REST API also exposes a deterministic conversation endpoint at `POST /api/v1/conversation` and cooking issue reporting. Intent classification currently uses a rules-based English/Hinglish fallback; no hosted model provider is connected yet.

The MCP adapter exposes `start_meal`, `get_meal_status`, `get_next_action`, `complete_cooking_step`, `report_interruption`, `recover_meal`, `report_cooking_issue`, `revise_meal_plan`, `save_household_preference`, `get_household_preferences`, and `start_cooking_timer`.

Use MCP Inspector to verify initialization, tool discovery and state-changing calls against the local endpoint. The endpoint and tool behavior have not yet been manually verified in this environment.

## Safety and privacy

- Never assume a stove is on/off or that food is cooked from elapsed time.
- Physical-confirmation-required steps reject completion/timer start without explicit confirmation.
- Use server-side secrets only. Never put database credentials or AI keys in Vite variables.
- The development identity is not authentication. Production mode refuses API and MCP operations until a real auth design is implemented.
- Demo reset deletes only records explicitly marked as demo and owned by the demo identity.

## Alexa integration

See [Alexa Custom Skill setup](docs/alexa-setup.md) for the initial voice integration, interaction model, and local/deployment setup. The endpoint is not a native Alexa alarm integration, and account linking is not implemented yet.

## Documentation

- [Setup](docs/setup.md)
- [Architecture](docs/architecture.md)
- [MCP tools](docs/mcp-tools.md)
- [Security](docs/security.md)
- [Testing](docs/testing.md)
- [Deployment](docs/deployment.md)
- [Demo script](docs/demo-script.md)
- [Build log](docs/build-log.md)

## License

No license has been selected. All rights reserved by default until a license is added.
