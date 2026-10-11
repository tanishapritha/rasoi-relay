# Troubleshooting

- **Database connection fails:** confirm `DATABASE_URL` uses `postgresql+psycopg://` and the database is reachable.
- **Alembic cannot import `app`:** run the command from `backend/` with the backend project selected.
- **`/ready` returns 503:** check the database URL and provider availability; the endpoint intentionally returns a generic error.
- **MCP tools reject production calls:** expected until authenticated identity is implemented; do not bypass this guard.
- **Demo meal already exists:** seed is idempotent for the designated demo user and meal name; use the scoped reset script to recreate it.
- **A step is blocked:** complete prerequisites; do not force-complete a blocked step.
