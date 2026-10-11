from datetime import datetime, timedelta, timezone

from app.db.session import SessionLocal
from app.models import Meal
from app.schemas import DishCreate, MealCreate, StepCreate
from app.services.cooking import create_meal

DEMO_USER = "demo-user"


def payload() -> MealCreate:
    return MealCreate(
        name="Dal, rice & aloo sabzi",
        target_serving_at=datetime.now(timezone.utc) + timedelta(minutes=60),
        dishes=[
            DishCreate(name="Rice", steps=[
                StepCreate(title="Wash rice", instruction="Rinse rice until the water is clearer.", duration_minutes=3),
                StepCreate(title="Cook rice", instruction="Cook using the usual method and confirm current conditions.", duration_minutes=18, depends_on=[0], requires_physical_confirmation=True),
                StepCreate(title="Rest rice", instruction="Let the rice rest and check texture.", duration_minutes=5, depends_on=[1]),
            ]),
            DishCreate(name="Dal", steps=[
                StepCreate(title="Rinse dal", instruction="Rinse the dal.", duration_minutes=2),
                StepCreate(title="Pressure cook dal", instruction="Follow the pressure cooker's instructions; never open it while pressurized.", duration_minutes=20, depends_on=[0], requires_physical_confirmation=True),
                StepCreate(title="Temper dal", instruction="Prepare tempering carefully and combine with the dal.", duration_minutes=5, depends_on=[1]),
            ]),
            DishCreate(name="Aloo sabzi", steps=[
                StepCreate(title="Chop potatoes", instruction="Wash and chop potatoes.", duration_minutes=8),
                StepCreate(title="Sauté spices", instruction="Heat oil carefully and sauté spices.", duration_minutes=3, depends_on=[0], requires_physical_confirmation=True),
                StepCreate(title="Cook potatoes", instruction="Cook until done; elapsed time alone is not proof.", duration_minutes=15, depends_on=[1], requires_physical_confirmation=True),
            ]),
        ],
    )


def main() -> None:
    with SessionLocal() as db:
        existing = db.query(Meal).filter_by(user_id=DEMO_USER, is_demo=True, name="Dal, rice & aloo sabzi").first()
        if existing:
            print(f"Demo meal already exists: {existing.id}")
            return
        meal = create_meal(db, DEMO_USER, payload(), is_demo=True)
        print(f"Created demo meal: {meal.id}")


if __name__ == "__main__":
    main()
