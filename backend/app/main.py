import contextlib
import logging
import time
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import Response
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.ai.provider import get_intent_provider
from app.alexa.endpoint import router as alexa_router
from app.auth.dependencies import current_user
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.session import get_db, engine
from app.models import Meal, MealStatus
from app.mcp_server import mcp
from app.schemas import CookingIssueCreate, CompleteStepRequest, ConversationRequest, DishCreate, InterruptionCreate, MealCreate, PreferenceWrite, ResumeMealRequest, StepCreate, TimerStart
from app.services.cooking import (
    complete_step, create_meal, get_meal, get_next_action, get_preferences,
    meal_status, recover_meal, report_cooking_issue, report_interruption, resume_meal, revise_plan, save_preference, start_timer,
)

settings = get_settings()
configure_logging(settings.log_level)
logger = logging.getLogger("rasoi.request")
mcp.settings.streamable_http_path = "/"
mcp_asgi_app = mcp.streamable_http_app()


@contextlib.asynccontextmanager
async def lifespan(_app: FastAPI):
    async with mcp.session_manager.run():
        yield


app = FastAPI(title="Rasoi Relay API", version="0.1.0",
              description="Stateful cooking recovery API. Alexa+ experience is simulated unless verified.",
              lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origin_list,
                   allow_credentials=True, allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
                   allow_headers=["Authorization", "Content-Type", "Idempotency-Key", "X-Demo-User", "Mcp-Session-Id", "Mcp-Protocol-Version", "Last-Event-ID"],
                   expose_headers=["Mcp-Session-Id"])

app.include_router(alexa_router)

@app.middleware("http")
async def request_logging(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
    request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        logger.exception("request_failed", extra={"request_id": request_id, "method": request.method,
                                                  "path": request.url.path,
                                                  "duration_ms": round((time.perf_counter() - started) * 1000, 2)})
        raise
    response.headers["X-Request-ID"] = request_id
    logger.info("request_completed", extra={"request_id": request_id, "method": request.method,
                                             "path": request.url.path, "status_code": response.status_code,
                                             "duration_ms": round((time.perf_counter() - started) * 1000, 2)})
    return response




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


@app.post("/api/v1/meals/{meal_id}/steps/{step_id}/timer", status_code=201)
def post_timer(meal_id: str, step_id: str, data: TimerStart, db: Session = Depends(get_db),
               user_id: str = Depends(current_user)) -> dict:
    meal = get_meal(db, meal_id, user_id)
    return start_timer(db, meal, step_id, data.duration_minutes, data.physical_condition_confirmed)


@app.post("/api/v1/meals/{meal_id}/issues")
def post_issue(meal_id: str, data: CookingIssueCreate, db: Session = Depends(get_db),
               user_id: str = Depends(current_user)) -> dict:
    meal = get_meal(db, meal_id, user_id)
    return report_cooking_issue(db, meal, data.issue_type, data.description)


@app.post("/api/v1/meals/{meal_id}/interruptions")
def post_interruption(meal_id: str, data: InterruptionCreate, db: Session = Depends(get_db),
                      user_id: str = Depends(current_user)) -> dict:
    meal = get_meal(db, meal_id, user_id)
    return report_interruption(db, meal, data.reason, data.details)


@app.post("/api/v1/meals/{meal_id}/resume")
def post_resume(meal_id: str, data: ResumeMealRequest, db: Session = Depends(get_db),
                user_id: str = Depends(current_user)) -> dict:
    meal = get_meal(db, meal_id, user_id)
    return resume_meal(db, meal, data.user_confirmed, data.confirmed_conditions)


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
        target_serving_at=datetime.now(UTC) + timedelta(minutes=60),
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


@app.post("/api/v1/conversation")
def converse(data: ConversationRequest, db: Session = Depends(get_db), user_id: str = Depends(current_user)) -> dict:
    intent = get_intent_provider().classify(data.message)
    if data.meal_id:
        meal = get_meal(db, data.meal_id, user_id)
    else:
        candidates = db.query(Meal).filter(Meal.user_id == user_id, Meal.status.in_([MealStatus.ACTIVE, MealStatus.PAUSED])).order_by(Meal.created_at.desc()).limit(3).all()
        if len(candidates) == 0:
            return {"intent": intent.name, "response": "There is no active meal yet. Load or start a meal first.", "clarification_required": True}
        if len(candidates) > 1:
            return {"intent": intent.name, "response": "Which meal do you want to resume? Please select one from your dashboard.", "clarification_required": True, "meals": [{"id": meal.id, "name": meal.name} for meal in candidates]}
        meal = get_meal(db, candidates[0].id, user_id)
    if intent.name == "recover_meal":
        result = recover_meal(db, meal)
        response = "Your saved progress is recovered. Please confirm any unknown physical conditions before continuing." if result["clarification_required"] else "Your saved progress is recovered. Here is the next eligible action."
        return {"intent": intent.name, "response": response, "clarification_required": result["clarification_required"], "result": result}
    if intent.name == "get_meal_status":
        result = meal_status(db, meal)
        return {"intent": intent.name, "response": f"{result['progress']['completed']} of {result['progress']['total']} cooking steps are confirmed complete.", "clarification_required": False, "result": result}
    if intent.name == "report_uncertain_physical_state":
        result = report_interruption(db, meal, "user unsure about physical state", {"stove_state": "unknown", "source_message": "user-reported uncertainty"})
        return {"intent": intent.name, "response": "I cannot tell whether the stove is on or off. Please check it in person and confirm before resuming.", "clarification_required": True, "result": result}
    if intent.name == "report_interruption":
        result = report_interruption(db, meal, "user-reported interruption", {})
        return {"intent": intent.name, "response": "Interruption recorded. I preserved confirmed progress; tell me if any physical condition is uncertain.", "clarification_required": False, "result": result}
    if intent.name == "report_delay":
        return {"intent": intent.name, "response": "How many extra minutes should I plan for? I will revise the schedule only after you confirm the delay.", "clarification_required": True}
    return {"intent": intent.name, "response": intent.clarification or "Could you clarify what you need?", "clarification_required": True}


# Keep the MCP mount after REST routes so the API remains discoverable and reachable.
app.mount("/mcp", mcp_asgi_app)
