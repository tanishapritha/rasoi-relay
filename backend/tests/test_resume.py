from datetime import UTC, datetime, timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.schemas import DishCreate, MealCreate, StepCreate
from app.services.cooking import create_meal, get_meal, report_interruption, resume_meal


def test_resume_requires_user_and_stove_confirmation():
    engine = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    try:
        with factory() as db:
            meal = create_meal(db, 'resume-user', MealCreate(
                name='Resume test', target_serving_at=datetime.now(UTC) + timedelta(hours=1),
                dishes=[DishCreate(name='Rice', steps=[StepCreate(title='Wash rice', instruction='Rinse.', duration_minutes=2)])],
            ))
            report_interruption(db, meal, 'phone call', {'stove_state': 'unknown'})
            with pytest.raises(HTTPException) as no_user_confirm:
                resume_meal(db, meal, False, {'stove_state': 'off'})
            assert no_user_confirm.value.status_code == 409
            with pytest.raises(HTTPException) as no_state_confirm:
                resume_meal(db, meal, True, {})
            assert no_state_confirm.value.detail['code'] == 'PHYSICAL_STATE_UNCONFIRMED'
            result = resume_meal(db, meal, True, {'stove_state': 'off'})
            assert result['status'] == 'active'
            assert get_meal(db, meal.id, 'resume-user').status.value == 'active'
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()
