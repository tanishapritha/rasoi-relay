# Alexa Custom Skill setup

## Current scope

Rasoi Relay exposes a verified Alexa Custom Skill endpoint at `POST /api/v1/alexa`. It supports status, next action, interruption, resume confirmation, step completion and saved cooking timers. It uses the same deterministic application services as the REST API.

This is an initial integration, not a published skill. A saved Rasoi Relay timer is not an Alexa device alarm and does not currently trigger a spoken notification. Timer expiry never proves food is ready. Alexa identities are currently separate from web accounts; account linking is not implemented. Production multi-user access must remain disabled until the full authentication and authorization design is complete.

## Local prerequisites

- Python 3.11 or newer
- `uv`
- A development PostgreSQL database, or the repository's supported test database setup
- An Alexa Developer Console account
- A publicly reachable HTTPS backend for simulator/device requests

## Configure the backend

From `backend/`:

1. Install the project dependencies with `uv sync --extra dev`.
2. Copy `backend/.env.example` to `.env` if you have not already.
3. Set `ALEXA_SKILL_ID` to the skill ID shown in the Alexa Developer Console.
4. Set `DATABASE_URL` to a development database. Do not use a production database for first-time skill tests.
5. Start the API with `uv run uvicorn app.main:app --reload --port 8000`.

The endpoint will return HTTP 503 until `ALEXA_SKILL_ID` is configured. Request signature and timestamp verification remain enabled; do not disable them for a public endpoint.

## Configure the skill

1. Open the [Alexa Developer Console](https://developer.amazon.com/alexa/console/ask).
2. Create a Custom skill named Rasoi Relay.
3. Select English (India) if that is the locale you intend to test first.
4. Open the JSON editor for the interaction model and import `alexa/interaction-model.en-IN.json` from the repository root.
5. Build the model.
6. In the endpoint configuration, select HTTPS and enter the deployed backend URL ending in `/api/v1/alexa`.
7. Select the certificate option appropriate to your hosting provider and region. The endpoint must use a valid HTTPS certificate.
8. Test first in the Developer Console simulator.

## First test flow

1. Enable the skill in the simulator.
2. Invoke `rasoi relay`.
3. Say `start a sample meal` to create a sample session owned by the Alexa identity.
4. Ask `what should I do next` or `how is dinner going`.
5. Test interruption and recovery. After an interruption, physically check the stove before telling the skill whether it is on or off.
6. Try a step that requires physical confirmation. The voice integration must not bypass the existing confirmation requirement.
7. Inspect backend logs and database state after each state-changing request. The web app currently uses a separate development identity, so the Alexa-created meal will not appear in the web UI until account linking is implemented.

## Known limitations

- The Alexa identity maps to a separate Rasoi Relay user until account linking is implemented.
- Multiple active or paused meals cause the skill to ask the user to resolve the ambiguity in the app.
- A saved timer does not create a native Alexa alarm or a proactive announcement.
- The endpoint verifies Alexa request signatures, timestamps and configured skill ID, but does not replace application account-linking or production authorization.
- The app's current production mode intentionally rejects ordinary API requests while authentication is unconfigured. Validate the intended environment and deployment before exposing the skill publicly.
