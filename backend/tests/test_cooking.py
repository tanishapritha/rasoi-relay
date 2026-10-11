from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.models import CookingEvent, StepStatus
from app.schemas import DishCreate, MealCreate, StepCreate
from app.services.cooking import complete_step, create_meal, get_meal, get_next_action, recover_meal, report_interruption


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with factory() as session:
        yield session
    Base.metadata.drop_all(engine)
    engine.dispose()


def meal_payload():
    return MealCreate(
        name="Dinner", target_serving_at=datetime.now(timezone.utc) + timedelta(hours=1),
        dishes=[
            DishCreate(name="Rice", steps=[
                StepCreate(title="Wash rice", instruction="Rinse the rice.", duration_minutes=3),
                StepCreate(title="Cook rice", instruction="Cook using the usual method.", duration_minutes=15, depends_on=[0]),
            ]),
            DishCreate(name="Dal", steps=[StepCreate(title="Rinse dal", instruction="Rinse the dal.", duration_minutes=2)]),
        ],
    )


def test_create_meal_and_select_eligible_action(db):
    meal = create_meal(db, "user-a", meal_payload())
    assert meal.name == "Dinner"
    assert get_next_action(db, meal)["action"]["title"] == "Wash rice"


def test_blocked_step_cannot_be_completed(db):
    meal = create_meal(db, "user-a", meal_payload())
    rice = next(dish for dish in meal.dishes if dish.name == "Rice")
    with pytest.raises(HTTPException) as exc:
        complete_step(db, meal, rice.steps[1].id)
    assert exc.value.status_code == 409
    assert exc.value.detail["code"] == "STEP_BLOCKED"


def test_completion_is_persisted_and_idempotent(db):
    meal = create_meal(db, "user-a", meal_payload())
    step = meal.dishes[0].steps[0]
    first = complete_step(db, meal, step.id, "test-key-1")
    second = complete_step(db, meal, step.id, "test-key-1")
    assert first["status"] == "completed"
    assert second["status"] == "already_processed"
    assert db.query(CookingEvent).filter_by(idempotency_key="test-key-1").count() == 1


def test_interruption_preserves_progress_and_unknown_stove(db):
    meal = create_meal(db, "user-a", meal_payload())
    step = meal.dishes[0].steps[0]
    complete_step(db, meal, step.id)
    result = report_interruption(db, meal, "phone call", {"stove_state": "unknown"})
    assert result["clarification_required"] is True
    assert "stove_state" in result["unknown_conditions"]
    persisted = get_meal(db, meal.id, "user-a")
    assert persisted.dishes[0].steps[0].status == StepStatus.COMPLETED
    assert recover_meal(db, persisted)["clarification_required"] is True


def test_user_cannot_read_another_users_meal(db):
    meal = create_meal(db, "user-a", meal_payload())
    with pytest.raises(HTTPException) as exc:
        get_meal(db, meal.id, "user-b")
    assert exc.value.status_code == 404
