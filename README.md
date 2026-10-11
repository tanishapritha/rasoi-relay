# Rasoi Relay

A voice-first kitchen companion that preserves confirmed cooking progress, recovers after interruptions, and recommends the next safe action. Alexa+ behavior is simulated unless a real integration is explicitly configured and verified.

## Status

Phase 1 foundation is being implemented first: deterministic cooking services, PostgreSQL persistence, migrations, demo data, and tests. See `docs/build-log.md` for verified progress.

## Planned stack

- React, Vite, TypeScript frontend
- FastAPI, Pydantic, SQLAlchemy 2, Alembic backend
- PostgreSQL (Neon in hosted environments)
- Official Python MCP SDK over Streamable HTTP
- Pytest, Ruff, Vitest, Playwright, GitHub Actions

## Safety principle

The application never infers the current physical state of a stove or food from elapsed time. Unknown conditions require user confirmation. This is a guidance tool, not a certified safety device.

## Development

See [docs/setup.md](docs/setup.md) for setup and [docs/architecture.md](docs/architecture.md) for the system design. Configuration examples contain placeholders only; never commit secrets.

## License

No license has been selected yet. All rights reserved by default until a license is added.
