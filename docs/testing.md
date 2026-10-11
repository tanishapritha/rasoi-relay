# Testing

## Backend

```powershell
cd backend
uv sync --extra dev
uv run pytest
uv run ruff check .
```

Initial tests cover meal creation, eligible next action, blocked-step rejection, idempotent completion, interruption recovery, unknown stove state, user-scoped meal reads, explicit physical confirmation, absolute timer deadlines, bounded adaptive estimates, English/Hinglish intent parsing, and confirmed meal resumption.

## Required before release

- PostgreSQL migration and transaction integration tests on an isolated database.
- REST endpoint success, validation and cross-user tests.
- MCP Inspector initialization, tool discovery and real tool calls.
- Confirm MCP writes are visible through REST reads.
- Frontend unit and accessibility tests.
- Playwright recovery flow and MCP-to-REST flow.
- Production smoke tests and deployed MCP latency measurements.

Do not describe tests as passing until they have actually been executed.
