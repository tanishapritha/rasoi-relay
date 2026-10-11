import contextlib
from datetime import datetime, timedelta, timezone

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db, engine
from app.models import Meal
from app.mcp_server import mcp
from app.schemas import CompleteStepRequest, DishCreate, InterruptionCreate, MealCreate, PreferenceWrite, StepCreate
from app.services.cooking import (
    complete_step, create_meal, get_meal, get_next_action, get_preferences,
    meal_status, recover_meal, report_interruption, revise_plan, save_preference,
)

settings = get_settings()
mcp_asgi_app = mcp.streamable_http_app(streamable_http_path="/", json_response=True, stateless_http=True)


@contextlib.asynccontextmanager
async def lifespan(_app: FastAPI):
    async with mcp.session_manager.run():
        yield


app = FastAPI(title="Rasoi Relay API", version="0.1.0",
              description="Stateful cooking recovery API. Alexa+ experience is simulated unless verified.",
              lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origin_list,
                   allow_credentials=True, allow_methods=["GET", "POST", "PUT", "OPTIONS"],
                   allow_headers=["Authorization", "Content-Type", "Idempotency-Key", "X-Demo-User", "Mcp-Session-Id", "Mcp-Protocol-Version", "Last-Event-ID"],
                   expose_headers=["Mcp-Session-Id"])


def current_user(x_demo_user: str | None = Header(default=None, alias="X-Demo-User")) -> str:
    # Explicit demo identity only; production authentication must replace this dependency.
    if settings.app_env == "production":
        raise HTTPException(status_code=401, detail={"code": "AUTH_REQUIRED", "message": "Production authentication is not configured."})
    return x_demo_user or "demo-user"


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "rasoi-relay-api"}


@app.get("/ready")
def ready() -> dict[str, str]:
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return {"status": "ready", "database": "available"}
    except Exception as exc:
        raise HTTPException(status_code=503, detail={"code": "DATABASE_UNAVAILABLE", "message": "Database is unavailable."}) from exc


@app.get("/api/v1/meals")
def list_meals(db: Session = Depends(get_db), user_id: str = Depends(current_user)) -> list[dict]:
    meals = db.query(Meal).filter(Meal.user_id == user_id).order_by(Meal.created_at.desc()).limit(50).all()
    return [{"id": m.id, "name": m.name, "status": m.status.value,
             "target_serving_at": m.target_serving_at.isoformat()} for m in meals]


@app.post("/api/v1/meals", status_code=201)
def post_meal(data: MealCreate, db: Session = Depends(get_db), user_id: str = Depends(current_user)) -> dict:
    meal = create_meal(db, user_id, data)
    return meal_status(db, meal)


@app.get("/api/v1/meals/{meal_id}")
def read_meal(meal_id: str, db: Session = Depends(get_db), user_id: str = Depends(current_user)) -> dict:
    return meal_status(db, get_meal(db, meal_id, user_id))


@app.get("/api/v1/meals/{meal_id}/status")
def read_status(meal_id: str, db: Session = Depends(get_db), user_id: str = Depends(current_user)) -> dict:
    return meal_status(db, get_meal(db, meal_id, user_id))


@app.get("/api/v1/meals/{meal_id}/next-action")
def next_action(meal_id: str, db: Session = Depends(get_db), user_id: str = Depends(current_user)) -> dict:
    return get_next_action(db, get_meal(db, meal_id, user_id))


@app.post("/api/v1/meals/{meal_id}/steps/{step_id}/complete")
def post_complete(meal_id: str, step_id: str, data: CompleteStepRequest,
                  db: Session = Depends(get_db), user_id: str = Depends(current_user),
                  idempotency_key: str | None = Header(default=None, alias="Idempotency-Key")) -> dict:
    meal = get_meal(db, meal_id, user_id)
    return complete_step(db, meal, step_id, idempotency_key or data.idempotency_key, data.physical_condition_confirmed)


@app.post("/api/v1/meals/{meal_id}/interruptions")
def post_interruption(meal_id: str, data: InterruptionCreate, db: Session = Depends(get_db),
                      user_id: str = Depends(current_user)) -> dict:
    meal = get_meal(db, meal_id, user_id)
    return report_interruption(db, meal, data.reason, data.details)


@app.post("/api/v1/meals/{meal_id}/recover")
def post_recover(meal_id: str, db: Session = Depends(get_db), user_id: str = Depends(current_user)) -> dict:
    return recover_meal(db, get_meal(db, meal_id, user_id))


@app.post("/api/v1/meals/{meal_id}/revise-plan")
def post_revise(meal_id: str, data: dict, db: Session = Depends(get_db),
                user_id: str = Depends(current_user)) -> dict:
    meal = get_meal(db, meal_id, user_id)
    return revise_plan(db, meal, str(data.get("reason", "user delay")), int(data.get("delay_minutes", 0)))


@app.get("/api/v1/preferences")
def read_preferences(db: Session = Depends(get_db), user_id: str = Depends(current_user)) -> list[dict]:
    return get_preferences(db, user_id)


@app.put("/api/v1/preferences/{key}")
def put_preference(key: str, data: PreferenceWrite, db: Session = Depends(get_db),
                   user_id: str = Depends(current_user)) -> dict:
    return save_preference(db, user_id, key, data.value, data.locale)


@app.post("/api/v1/demo/load", status_code=200)
def load_demo(db: Session = Depends(get_db), user_id: str = Depends(current_user)) -> dict:
    if not settings.demo_mode:
        raise HTTPException(status_code=403, detail={"code": "DEMO_DISABLED", "message": "Demo mode is disabled."})
    existing = db.query(Meal).filter(Meal.user_id == user_id, Meal.is_demo.is_(True), Meal.name == "Dal, rice & aloo sabzi").first()
    if existing is not None:
        from app.services.cooking import get_meal
        return meal_status(db, get_meal(db, existing.id, user_id))
    data = MealCreate(
        name="Dal, rice & aloo sabzi",
        target_serving_at=datetime.now(timezone.utc) + timedelta(minutes=60),
        dishes=[
            DishCreate(name="Rice", steps=[
                StepCreate(title="Wash rice", instruction="Rinse rice until the water is clearer.", duration_minutes=3),
                StepCreate(title="Cook rice", instruction="Cook using your usual method; confirm current conditions first.", duration_minutes=18, depends_on=[0], requires_physical_confirmation=True),
                StepCreate(title="Rest rice", instruction="Let rice rest and check texture.", duration_minutes=5, depends_on=[1]),
            ]),
            DishCreate(name="Dal", steps=[
                StepCreate(title="Rinse dal", instruction="Rinse the dal.", duration_minutes=2),
                StepCreate(title="Pressure cook dal", instruction="Follow pressure cooker instructions; never open it while pressurized.", duration_minutes=20, depends_on=[0], requires_physical_confirmation=True),
                StepCreate(title="Temper dal", instruction="Prepare tempering carefully and combine with dal.", duration_minutes=5, depends_on=[1]),
            ]),
            DishCreate(name="Aloo sabzi", steps=[
                StepCreate(title="Chop potatoes", instruction="Wash and chop potatoes.", duration_minutes=8),
                StepCreate(title="Sauté spices", instruction="Heat oil carefully and sauté spices.", duration_minutes=3, depends_on=[0], requires_physical_confirmation=True),
                StepCreate(title="Cook potatoes", instruction="Cook until done; elapsed time alone is not proof.", duration_minutes=15, depends_on=[1], requires_physical_confirmation=True),
            ]),
        ],
    )
    return meal_status(db, create_meal(db, user_id, data, is_demo=True))


@app.post("/api/v1/demo/reset")
def reset_demo(db: Session = Depends(get_db), user_id: str = Depends(current_user)) -> dict:
    if not settings.demo_mode:
        raise HTTPException(status_code=403, detail={"code": "DEMO_DISABLED", "message": "Demo mode is disabled."})
    demo_meals = db.query(Meal).filter(Meal.user_id == user_id, Meal.is_demo.is_(True)).all()
    for meal in demo_meals:
        db.delete(meal)
    db.commit()
    return {"status": "reset", "deleted_demo_meals": len(demo_meals)}


# Mount last so the MCP sub-application cannot shadow the REST routes above.
app.mount("/mcp", mcp_asgi_app)
