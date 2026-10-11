"""MCP adapter sharing application services with the REST API."""
from datetime import datetime
from typing import Any

from mcp.server.fastmcp import FastMCP

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.schemas import DishCreate, MealCreate, StepCreate
from app.services.cooking import (
    complete_step, create_meal, get_meal, get_next_action as next_action_service,
    get_preferences, meal_status, recover_meal as recover_service, report_cooking_issue as report_issue_service,
    report_interruption as interruption_service, revise_plan, save_preference,
)

mcp = FastMCP("Rasoi Relay")
settings = get_settings()


def _user_id() -> str:
    if settings.app_env == "production":
        raise RuntimeError("MCP authentication is not configured; refusing demo identity in production.")
    return "demo-user"


@mcp.tool()
def start_meal(name: str, target_serving_at: str, dishes: list[dict[str, Any]]) -> dict[str, Any]:
    """Create a meal with ordered dishes and cooking steps. Use ISO-8601 time with timezone."""
    parsed_dishes = []
    for dish in dishes:
        parsed_steps = [StepCreate(**step) for step in dish.get("steps", [])]
        parsed_dishes.append(DishCreate(name=dish["name"], steps=parsed_steps))
    data = MealCreate(name=name, target_serving_at=datetime.fromisoformat(target_serving_at), dishes=parsed_dishes)
    with SessionLocal() as db:
        meal = create_meal(db, _user_id(), data, source="mcp")
        return meal_status(db, meal)


@mcp.tool()
def get_meal_status(meal_id: str) -> dict[str, Any]:
    """Read persisted progress, dishes, timers, events, and the next action."""
    with SessionLocal() as db:
        return meal_status(db, get_meal(db, meal_id, _user_id()))


@mcp.tool()
def get_next_action(meal_id: str) -> dict[str, Any]:
    """Find the next eligible action while respecting cooking-step dependencies."""
    with SessionLocal() as db:
        return next_action_service(db, get_meal(db, meal_id, _user_id()))


@mcp.tool()
def complete_cooking_step(meal_id: str, step_id: str, idempotency_key: str | None = None) -> dict[str, Any]:
    """Complete an eligible step. Safety-sensitive steps require confirmation through the app UI."""
    with SessionLocal() as db:
        return complete_step(db, get_meal(db, meal_id, _user_id()), step_id, idempotency_key, source="mcp")


@mcp.tool()
def report_interruption(meal_id: str, reason: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    """Record an interruption without assuming unconfirmed steps are complete."""
    with SessionLocal() as db:
        return interruption_service(db, get_meal(db, meal_id, _user_id()), reason, details or {}, source="mcp")


@mcp.tool()
def recover_meal(meal_id: str) -> dict[str, Any]:
    """Recover confirmed state and identify unknown physical conditions."""
    with SessionLocal() as db:
        return recover_service(db, get_meal(db, meal_id, _user_id()))


@mcp.tool()
def report_cooking_issue(meal_id: str, issue_type: str, description: str) -> dict[str, Any]:
    """Record a cooking issue such as delay, missing ingredient, or uncertain condition."""
    with SessionLocal() as db:
        meal = get_meal(db, meal_id, _user_id())
        return report_issue_service(db, meal, issue_type, description, source="mcp")


@mcp.tool()
def revise_meal_plan(meal_id: str, reason: str, delay_minutes: int = 0) -> dict[str, Any]:
    """Revise the serving target while preserving completed steps."""
    with SessionLocal() as db:
        return revise_plan(db, get_meal(db, meal_id, _user_id()), reason, delay_minutes, source="mcp")


@mcp.tool()
def save_household_preference(key: str, value: dict[str, Any], locale: str = "en-IN") -> dict[str, Any]:
    """Save an explicitly user-approved household preference."""
    with SessionLocal() as db:
        return save_preference(db, _user_id(), key, value, locale)


@mcp.tool()
def get_household_preferences() -> list[dict[str, Any]]:
    """Read preferences for the current demo household."""
    with SessionLocal() as db:
        return get_preferences(db, _user_id())


@mcp.tool()
def start_cooking_timer(meal_id: str, step_id: str, duration_minutes: int | None = None) -> dict[str, Any]:
    """Start a persisted timer. Safety-sensitive steps require confirmation through the app UI."""
    from app.services.cooking import start_timer
    with SessionLocal() as db:
        return start_timer(db, get_meal(db, meal_id, _user_id()), step_id, duration_minutes, source="mcp")

