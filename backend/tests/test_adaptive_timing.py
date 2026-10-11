from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.models import CookingEvent
from app.schemas import DishCreate, MealCreate, StepCreate
from app.services.cooking import create_meal, get_next_action


def test_timing_estimate_uses_household_history_after_three_observations():
    engine = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    try:
        with factory() as db:
            meal = create_meal(db, 'adaptive-user', MealCreate(
                name='Adaptive test', target_serving_at=datetime.now(timezone.utc) + timedelta(hours=1),
                dishes=[DishCreate(name='Rice', steps=[StepCreate(
                    title='Wash rice', instruction='Rinse rice.', duration_minutes=5,
                )])],
            ))
            for duration in (7, 9, 11):
                db.add(CookingEvent(user_id='adaptive-user', meal_id=meal.id, event_type='step_completed',
                                    payload={'title': 'Wash rice', 'actual_duration_minutes': duration},
                                    confirmed=True))
            db.commit()
            action = get_next_action(db, meal)['action']
            assert action['estimated_minutes'] == 9
            assert action['estimate_source'] == 'household_history'
            assert action['timed_observations'] == 3
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()
