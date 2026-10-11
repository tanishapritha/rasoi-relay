from app.db.session import SessionLocal
from app.models import Meal


def main() -> None:
    with SessionLocal() as db:
        demos = db.query(Meal).filter_by(user_id="demo-user", is_demo=True).all()
        count = len(demos)
        for meal in demos:
            db.delete(meal)
        db.commit()
        print(f"Deleted {count} designated demo meal(s); non-demo data was untouched.")


if __name__ == "__main__":
    main()
