# Deployment

Target topology: Vercel frontend, Render Python service, Neon PostgreSQL. Never put database credentials or AI keys in frontend environment variables.

Before deploying:
1. Create a dedicated Neon production database/branch and restricted credentials.
2. Configure Render environment variables from `backend/.env.example`, including `DATABASE_URL`, `APP_ENV=production`, exact `CORS_ORIGINS`, and secrets.
3. Implement and verify production authentication before making user-specific API or MCP tools public. The current app intentionally rejects production requests until auth exists.
4. Run `alembic upgrade head` as a controlled release step, not destructive startup logic.
5. Configure Vercel `VITE_API_BASE_URL` to the deployed API URL.
6. Verify health, readiness, meal creation, MCP tool execution, dashboard refresh, logs, and actual MCP latency.
7. Document rollback and database restore procedures for the selected hosting plans.

No deployment has been performed yet.
