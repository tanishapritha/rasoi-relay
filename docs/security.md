# Security

- Never commit `.env`, tokens, API keys, database URLs or private keys.
- Keep AI provider credentials server-side; never expose them through `VITE_` variables.
- Persisted backend state is authoritative. Unknown physical conditions require clarification.
- Timer expiry is not proof that food is cooked.
- No appliance-control or camera integration is implemented.
- `X-Demo-User` is a development-only identity mechanism, not authentication. Production mode rejects API requests until auth is configured.
- Before public MCP deployment, propagate an authenticated principal into each tool call, validate ownership, rate-limit mutations and test cross-user denial.
- Demo reset is scoped to rows explicitly marked `is_demo` and owned by the demo identity.
- Review structured logs to ensure credentials and unnecessary private conversation content are not logged.
