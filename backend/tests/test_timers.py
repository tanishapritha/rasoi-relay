from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.schemas import DishCreate, MealCreate, StepCreate
from app.services.cooking import create_meal, start_timer


def test_timer_persists_absolute_deadline_and_requires_confirmation():
    engine = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    try:
        with factory() as db:
            meal = create_meal(db, 'timer-user', MealCreate(
                name='Timer test', target_serving_at=datetime.now(timezone.utc) + timedelta(hours=1),
                dishes=[DishCreate(name='Rice', steps=[StepCreate(
                    title='Cook rice', instruction='Check current conditions.', duration_minutes=12,
                    requires_physical_confirmation=True,
                )])],
            ))
            step_id = meal.dishes[0].steps[0].id
            with pytest.raises(HTTPException) as exc:
                start_timer(db, meal, step_id)
            assert exc.value.detail['code'] == 'PHYSICAL_CONFIRMATION_REQUIRED'
            result = start_timer(db, meal, step_id, physical_condition_confirmed=True)
            deadline = datetime.fromisoformat(result['deadline_at'])
            assert result['status'] == 'active'
            assert deadline > datetime.now(timezone.utc)
            second = start_timer(db, meal, step_id, physical_condition_confirmed=True)
            assert second['already_running'] is True
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()
