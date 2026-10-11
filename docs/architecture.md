# Architecture

## Components

- `backend/app/main.py`: FastAPI routes and readiness checks.
- `backend/app/services/cooking.py`: deterministic cooking application services.
- `backend/app/models.py`: relational persistence models.
- `backend/app/mcp_server.py`: MCP adapter using the same application services.
- `backend/migrations/`: Alembic schema migration.
- `scripts/`: deterministic demo seed and scoped reset.
- `frontend/`: browser UI, API client and demo workflow.

## Data flow

The frontend calls FastAPI for dashboard reads and mutations. The MCP adapter calls the same application service functions, so MCP-triggered changes can be read through REST. PostgreSQL is the durable source of truth.

## Trust boundaries

AI output is never an authority for persisted state or physical observations. The backend validates step transitions and dependencies. Stove and food state must be user-confirmed or supported by a real, tested sensor integration. The current development identity is not production authentication; production API routes reject requests until authentication is implemented.

## Scheduling assumptions

The initial scheduler is deterministic and dependency-aware. It chooses the first eligible step in dish display order and sequence. It does not yet optimize burner conflicts or prove the serving deadline feasible. Durations are estimates, not evidence that food is cooked.
