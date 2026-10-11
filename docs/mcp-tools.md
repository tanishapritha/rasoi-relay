# MCP tools

The MCP adapter in `backend/app/mcp_server.py` uses the official Python MCP SDK and calls shared services in `app/services/cooking.py`.

| Tool | Purpose | State change |
|---|---|---|
| `start_meal` | Create a meal, dishes and ordered steps | Yes |
| `get_meal_status` | Read meal progress and timers | No |
| `get_next_action` | Select an eligible action | No |
| `complete_cooking_step` | Validate and complete a step | Yes |
| `report_interruption` | Preserve state and record interruption | Yes |
| `recover_meal` | Return confirmed state and unknown conditions | No |
| `report_cooking_issue` | Record an issue event | Yes |
| `revise_meal_plan` | Revise serving target | Yes |
| `save_household_preference` | Save explicit preference | Yes |
| `get_household_preferences` | Read household preferences | No |
| `start_cooking_timer` | Persist an absolute timer deadline | Yes |

Production authorization is not complete; do not expose MCP publicly until authenticated identity propagation and ownership checks are implemented. MCP Inspector and deployed protocol behavior have not yet been verified.
