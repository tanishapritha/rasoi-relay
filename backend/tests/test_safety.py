from datetime import UTC, datetime, timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.schemas import DishCreate, MealCreate, StepCreate
from app.services.cooking import complete_step, create_meal


def test_sensitive_step_requires_explicit_confirmation():
    engine = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    try:
        with factory() as db:
            meal = create_meal(db, 'safety-user', MealCreate(
                name='Safety test', target_serving_at=datetime.now(UTC) + timedelta(hours=1),
                dishes=[DishCreate(name='Rice', steps=[StepCreate(
                    title='Cook rice', instruction='Check the cooking conditions.', duration_minutes=10,
                    requires_physical_confirmation=True,
                )])],
            ))
            step_id = meal.dishes[0].steps[0].id
            with pytest.raises(HTTPException) as exc:
                complete_step(db, meal, step_id)
            assert exc.value.status_code == 409
            assert exc.value.detail['code'] == 'PHYSICAL_CONFIRMATION_REQUIRED'
            result = complete_step(db, meal, step_id, physical_condition_confirmed=True)
            assert result['status'] == 'completed'
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()
