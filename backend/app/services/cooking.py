from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import (
    CookingEvent, CookingStep, CookingTimer, Dish, HouseholdPreference, Meal,
    MealPlanRevision, MealStatus, StepDependency, StepStatus, TimerStatus,
)
from app.schemas import MealCreate


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _meal_query(meal_id: str):
    return select(Meal).where(Meal.id == meal_id).options(
        selectinload(Meal.dishes).selectinload(Dish.steps).selectinload(CookingStep.dependencies),
        selectinload(Meal.dishes).selectinload(Dish.steps).selectinload(CookingStep.timers),
        selectinload(Meal.events),
    )


def _event(db: Session, meal: Meal, event_type: str, payload: dict[str, Any],
           source: str = "api", confirmed: bool = False, key: str | None = None) -> None:
    db.add(CookingEvent(user_id=meal.user_id, meal_id=meal.id, event_type=event_type,
                        payload=payload, source=source, confirmed=confirmed,
                        idempotency_key=key))


def create_meal(db: Session, user_id: str, data: MealCreate, is_demo: bool = False) -> Meal:
    meal = Meal(user_id=user_id, name=data.name, target_serving_at=data.target_serving_at,
                status=MealStatus.ACTIVE, is_demo=is_demo)
    db.add(meal)
    db.flush()
    all_steps: list[list[CookingStep]] = []
    for dish_index, dish_data in enumerate(data.dishes):
        dish = Dish(meal_id=meal.id, name=dish_data.name, display_order=dish_index)
        db.add(dish)
        db.flush()
        steps_for_dish: list[CookingStep] = []
        for sequence, step_data in enumerate(dish_data.steps):
            if any(dep < 0 or dep >= sequence for dep in step_data.depends_on):
                raise HTTPException(status_code=422, detail={
                    "code": "INVALID_DEPENDENCY", "message": "Dependencies must reference earlier steps in the same dish."
                })
            step = CookingStep(dish_id=dish.id, sequence=sequence, title=step_data.title,
                               instruction=step_data.instruction,
                               duration_minutes=step_data.duration_minutes,
                               status=StepStatus.PENDING,
                               requires_physical_confirmation=step_data.requires_physical_confirmation)
            db.add(step)
            db.flush()
            steps_for_dish.append(step)
        all_steps.append(steps_for_dish)
        for sequence, step_data in enumerate(dish_data.steps):
            for dependency_index in step_data.depends_on:
                db.add(StepDependency(step_id=steps_for_dish[sequence].id,
                                      depends_on_step_id=steps_for_dish[dependency_index].id))
    db.flush()
    for dish_steps in all_steps:
        for step in dish_steps:
            deps = list(db.scalars(select(StepDependency).where(StepDependency.step_id == step.id)))
            if not deps:
                step.status = StepStatus.READY
    _event(db, meal, "meal_started", {"name": meal.name, "dish_count": len(data.dishes)}, confirmed=True)
    db.commit()
    return db.scalar(_meal_query(meal.id))  # type: ignore[return-value]


def get_meal(db: Session, meal_id: str, user_id: str | None = None) -> Meal:
    query = _meal_query(meal_id)
    if user_id is not None:
        query = query.where(Meal.user_id == user_id)
    meal = db.scalar(query)
    if meal is None:
        raise HTTPException(status_code=404, detail={"code": "MEAL_NOT_FOUND", "message": "Meal not found."})
    return meal


def _is_ready(db: Session, step: CookingStep) -> bool:
    dependencies = list(db.scalars(select(StepDependency).where(StepDependency.step_id == step.id)))
    if step.status == StepStatus.COMPLETED:
        return False
    if not dependencies:
        return True
    completed_ids = set(db.scalars(
        select(CookingStep.id).where(
            CookingStep.id.in_([dep.depends_on_step_id for dep in dependencies]),
            CookingStep.status == StepStatus.COMPLETED,
        )
    ))
    return len(completed_ids) == len(dependencies)


def get_next_action(db: Session, meal: Meal) -> dict[str, Any]:
    steps = [step for dish in meal.dishes for step in dish.steps]
    ready = [step for step in steps if _is_ready(db, step)]
    if not ready:
        return {"action": None, "reason": "no_eligible_steps", "clarification_required": False}
    ready.sort(key=lambda s: (s.dish.display_order, s.sequence))
    step = ready[0]
    if step.requires_physical_confirmation:
        return {"action": {"step_id": step.id, "dish": step.dish.name, "title": step.title},
                "reason": "physical_confirmation_required", "clarification_required": True,
                "question": "Please confirm the current physical conditions before proceeding."}
    return {"action": {"step_id": step.id, "dish": step.dish.name, "title": step.title,
                       "instruction": step.instruction, "estimated_minutes": step.duration_minutes},
            "reason": "eligible_step", "clarification_required": False}


def complete_step(db: Session, meal: Meal, step_id: str, idempotency_key: str | None = None,
                  physical_condition_confirmed: bool = False) -> dict[str, Any]:
    if idempotency_key:
        existing = db.scalar(select(CookingEvent).where(CookingEvent.idempotency_key == idempotency_key))
        if existing:
            if existing.meal_id != meal.id or existing.payload.get("step_id") != step_id:
                raise HTTPException(status_code=409, detail={"code": "IDEMPOTENCY_KEY_REUSED", "message": "Key belongs to another operation."})
            return {"status": "already_processed", "meal_id": meal.id, "step_id": step_id}
    step = db.scalar(select(CookingStep).join(Dish).where(CookingStep.id == step_id, Dish.meal_id == meal.id))
    if step is None:
        raise HTTPException(status_code=404, detail={"code": "STEP_NOT_FOUND", "message": "Step not found in this meal."})
    if step.status == StepStatus.COMPLETED:
        return {"status": "already_completed", "meal_id": meal.id, "step_id": step.id}
    if step.requires_physical_confirmation and not physical_condition_confirmed:
        raise HTTPException(status_code=409, detail={"code": "PHYSICAL_CONFIRMATION_REQUIRED", "message": "Confirm the current physical conditions before completing this step."})
    if not _is_ready(db, step):
        raise HTTPException(status_code=409, detail={"code": "STEP_BLOCKED", "message": "Prerequisite steps are not complete."})
    step.status = StepStatus.COMPLETED
    step.completed_at = _now()
    for candidate in db.scalars(select(CookingStep).join(Dish).where(Dish.meal_id == meal.id)):
        if candidate.status == StepStatus.PENDING and _is_ready(db, candidate):
            candidate.status = StepStatus.READY
    _event(db, meal, "step_completed", {"step_id": step.id, "title": step.title,
                                      "physical_condition_confirmed": physical_condition_confirmed},
           confirmed=True, key=idempotency_key)
    db.commit()
    return {"status": "completed", "meal_id": meal.id, "step_id": step.id,
            "next_action": get_next_action(db, get_meal(db, meal.id, meal.user_id))}


def report_interruption(db: Session, meal: Meal, reason: str, details: dict[str, Any]) -> dict[str, Any]:
    meal.status = MealStatus.PAUSED
    _event(db, meal, "interruption_reported", {"reason": reason, "details": details}, confirmed=True)
    db.commit()
    return recover_meal(db, get_meal(db, meal.id, meal.user_id))


def recover_meal(db: Session, meal: Meal) -> dict[str, Any]:
    events = sorted(meal.events, key=lambda event: event.created_at or _now())
    last_confirmed = next((event for event in reversed(events) if event.confirmed), None)
    unknown_conditions = []
    if last_confirmed and last_confirmed.event_type == "interruption_reported":
        details = last_confirmed.payload.get("details", {})
        if details.get("stove_state") in (None, "unknown"):
            unknown_conditions.append("stove_state")
    return {
        "meal_id": meal.id, "meal_name": meal.name, "status": meal.status.value,
        "last_confirmed_event": None if last_confirmed is None else {
            "type": last_confirmed.event_type, "payload": last_confirmed.payload,
            "created_at": last_confirmed.created_at.isoformat() if last_confirmed.created_at else None,
        },
        "unknown_conditions": unknown_conditions,
        "clarification_required": bool(unknown_conditions),
        "clarification_question": "Please check and confirm whether the stove is off." if "stove_state" in unknown_conditions else None,
        "next_action": get_next_action(db, meal),
    }


def revise_plan(db: Session, meal: Meal, reason: str, delay_minutes: int = 0) -> dict[str, Any]:
    if delay_minutes < 0 or delay_minutes > 720:
        raise HTTPException(status_code=422, detail={"code": "INVALID_DELAY", "message": "Delay must be between 0 and 720 minutes."})
    previous = {"target_serving_at": meal.target_serving_at.isoformat(), "reason": reason}
    meal.target_serving_at = meal.target_serving_at + timedelta(minutes=delay_minutes)
    revised = {"target_serving_at": meal.target_serving_at.isoformat(), "delay_minutes": delay_minutes}
    db.add(MealPlanRevision(meal_id=meal.id, previous_snapshot=previous,
                            revised_snapshot=revised, reason=reason))
    _event(db, meal, "plan_revised", revised, confirmed=True)
    db.commit()
    return {"meal_id": meal.id, "target_serving_at": meal.target_serving_at.isoformat(),
            "delay_minutes": delay_minutes, "reason": reason}


def save_preference(db: Session, user_id: str, key: str, value: dict[str, Any], locale: str = "en-IN") -> dict[str, Any]:
    pref = db.scalar(select(HouseholdPreference).where(HouseholdPreference.user_id == user_id,
                                                        HouseholdPreference.key == key))
    if pref is None:
        pref = HouseholdPreference(user_id=user_id, key=key, value=value, locale=locale)
        db.add(pref)
    else:
        pref.value, pref.locale = value, locale
    db.commit()
    return {"key": key, "value": pref.value, "locale": pref.locale}


def get_preferences(db: Session, user_id: str) -> list[dict[str, Any]]:
    prefs = db.scalars(select(HouseholdPreference).where(HouseholdPreference.user_id == user_id)).all()
    return [{"key": pref.key, "value": pref.value, "locale": pref.locale} for pref in prefs]


def meal_status(db: Session, meal: Meal) -> dict[str, Any]:
    dishes = []
    steps_total = steps_done = 0
    for dish in sorted(meal.dishes, key=lambda item: item.display_order):
        step_items = []
        for step in dish.steps:
            steps_total += 1
            steps_done += step.status == StepStatus.COMPLETED
            step_items.append({"id": step.id, "sequence": step.sequence, "title": step.title,
                               "instruction": step.instruction, "duration_minutes": step.duration_minutes,
                               "status": step.status.value, "requires_physical_confirmation": step.requires_physical_confirmation,
                               "timers": [{"deadline_at": timer.deadline_at.isoformat(), "status": timer.status.value}
                                          for timer in step.timers]})
        dishes.append({"id": dish.id, "name": dish.name, "status": dish.status, "steps": step_items})
    return {"id": meal.id, "name": meal.name, "status": meal.status.value,
            "target_serving_at": meal.target_serving_at.isoformat(), "dishes": dishes,
            "progress": {"completed": steps_done, "total": steps_total,
                         "fraction": steps_done / steps_total if steps_total else 0},
            "next_action": get_next_action(db, meal),
            "recent_events": [{"type": e.event_type, "payload": e.payload, "created_at": e.created_at.isoformat() if e.created_at else None}
                              for e in sorted(meal.events, key=lambda event: event.created_at or _now(), reverse=True)[:10]]}


def start_timer(db: Session, meal: Meal, step_id: str, duration_minutes: int | None = None,
                physical_condition_confirmed: bool = False) -> dict[str, Any]:
    step = db.scalar(select(CookingStep).join(Dish).where(CookingStep.id == step_id, Dish.meal_id == meal.id))
    if step is None:
        raise HTTPException(status_code=404, detail={"code": "STEP_NOT_FOUND", "message": "Step not found in this meal."})
    if not _is_ready(db, step):
        raise HTTPException(status_code=409, detail={"code": "STEP_BLOCKED", "message": "Prerequisite steps are not complete."})
    if step.requires_physical_confirmation and not physical_condition_confirmed:
        raise HTTPException(status_code=409, detail={"code": "PHYSICAL_CONFIRMATION_REQUIRED", "message": "Confirm the current physical conditions before starting this timer."})
    duration = duration_minutes if duration_minutes is not None else step.duration_minutes
    if duration < 1 or duration > 360:
        raise HTTPException(status_code=422, detail={"code": "INVALID_TIMER_DURATION", "message": "Timer duration must be between 1 and 360 minutes."})
    active = db.scalar(select(CookingTimer).where(CookingTimer.step_id == step.id, CookingTimer.status == TimerStatus.ACTIVE))
    if active is not None:
        return {"timer_id": active.id, "step_id": step.id, "deadline_at": active.deadline_at.isoformat(), "status": active.status.value, "already_running": True}
    now = _now()
    deadline = now + timedelta(minutes=duration)
    timer = CookingTimer(step_id=step.id, deadline_at=deadline, status=TimerStatus.ACTIVE)
    if step.started_at is None:
        step.started_at = now
    if step.status != StepStatus.COMPLETED:
        step.status = StepStatus.IN_PROGRESS
    db.add(timer)
    _event(db, meal, "timer_started", {"step_id": step.id, "duration_minutes": duration, "deadline_at": deadline.isoformat()}, confirmed=True)
    db.commit()
    return {"timer_id": timer.id, "step_id": step.id, "deadline_at": deadline.isoformat(), "status": timer.status.value, "already_running": False}
