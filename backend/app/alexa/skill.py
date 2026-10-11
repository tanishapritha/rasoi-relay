"""Alexa intent handlers backed by Rasoi Relay's deterministic services."""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from ask_sdk_core.dispatch_components import AbstractExceptionHandler, AbstractRequestHandler
from ask_sdk_core.handler_input import HandlerInput
from ask_sdk_core.skill_builder import SkillBuilder
from ask_sdk_core.utils import is_intent_name, is_request_type
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.db.session import SessionLocal
from app.models import ExternalIdentity, Meal, MealStatus, User
from app.schemas import DishCreate, MealCreate, StepCreate
from app.services.cooking import (
    complete_step,
    create_meal,
    get_meal,
    get_next_action,
    meal_status,
    recover_meal,
    report_interruption,
    resume_meal,
    start_timer,
)

logger = logging.getLogger("rasoi.alexa")
sb = SkillBuilder()


def _response(
    handler_input: HandlerInput,
    speech: str,
    reprompt: str | None = None,
    end_session: bool = False,
) -> dict[str, Any]:
    builder = handler_input.response_builder.speak(speech)
    if reprompt:
        builder = builder.ask(reprompt)
    if end_session:
        builder = builder.set_should_end_session(True)
    return builder.response


def _slot(handler_input: HandlerInput, name: str) -> str | None:
    request = handler_input.request_envelope.request
    intent = getattr(request, "intent", None)
    slots = getattr(intent, "slots", None) or {}
    slot = slots.get(name)
    value = getattr(slot, "value", None)
    return str(value).strip() if value is not None else None


def _alexa_user_id(handler_input: HandlerInput) -> str:
    system = getattr(handler_input.request_envelope.context, "system", None)
    user = getattr(system, "user", None)
    user_id = getattr(user, "user_id", None)
    if not user_id:
        raise HTTPException(
            status_code=401,
            detail={"code": "ALEXA_USER_UNAVAILABLE", "message": "Alexa user identity is unavailable."},
        )
    return str(user_id)


def _resolve_user(db: Any, alexa_user_id: str) -> str:
    identity = db.scalar(
        select(ExternalIdentity).where(
            ExternalIdentity.provider == "alexa",
            ExternalIdentity.provider_subject == alexa_user_id,
        )
    )
    if identity is not None:
        user = db.get(User, identity.user_id)
        if user is None or user.account_status != "active":
            raise HTTPException(
                status_code=403,
                detail={"code": "ALEXA_ACCOUNT_INACTIVE", "message": "This Rasoi Relay account is unavailable."},
            )
        return user.id

    user = User(id=str(uuid.uuid4()), display_name="Alexa household", account_status="active")
    db.add(user)
    db.flush()
    db.add(ExternalIdentity(
        user_id=user.id,
        provider="alexa",
        provider_subject=alexa_user_id,
    ))
    try:
        db.commit()
        return user.id
    except IntegrityError:
        # Two first requests can race to create the same external identity.
        db.rollback()
        identity = db.scalar(
            select(ExternalIdentity).where(
                ExternalIdentity.provider == "alexa",
                ExternalIdentity.provider_subject == alexa_user_id,
            )
        )
        if identity is None:
            raise
        return identity.user_id


def _user_id(db: Any, handler_input: HandlerInput) -> str:
    return _resolve_user(db, _alexa_user_id(handler_input))


def _active_meal(db: Any, user_id: str) -> tuple[Meal | None, str | None]:
    meals = list(db.scalars(
        select(Meal)
        .where(Meal.user_id == user_id, Meal.status.in_([MealStatus.ACTIVE, MealStatus.PAUSED]))
        .order_by(Meal.updated_at.desc())
        .limit(2)
    ).all())
    if not meals:
        return None, "I couldn't find an active or paused meal for this Alexa account. Start a meal in the Rasoi Relay app first."
    if len(meals) > 1:
        return None, "I found more than one active or paused meal. Please select or finish a session in the Rasoi Relay app before using voice controls."
    return get_meal(db, meals[0].id, user_id), None


def _action_speech(result: dict[str, Any]) -> str:
    if result.get("clarification_required"):
        return str(result.get("question") or "I need you to confirm a physical condition before continuing.")
    action = result.get("action")
    if not action:
        return "There is no eligible cooking step right now. Check the Rasoi Relay app for the current meal state."
    instruction = action.get("instruction")
    minutes = action.get("estimated_minutes")
    estimate = f" The estimated time is {minutes} minutes." if minutes else ""
    if instruction:
        return f"Next, {action.get('dish', 'your dish')}: {action.get('title', 'the next step')}. {instruction}{estimate}"
    return (
        f"The next step is {action.get('title', 'the next step')} for {action.get('dish', 'your dish')}. "
        "This step requires a physical confirmation in the Rasoi Relay app before proceeding."
    )


def _http_error_speech(exc: HTTPException) -> str:
    detail = exc.detail
    if isinstance(detail, dict):
        code = detail.get("code")
        message = str(detail.get("message", "I couldn't complete that cooking action."))
    else:
        code, message = None, str(detail)
    if code in {"PHYSICAL_CONFIRMATION_REQUIRED", "PHYSICAL_STATE_UNCONFIRMED", "RESUME_CONFIRMATION_REQUIRED"}:
        return f"I can't safely continue yet. {message} Please check the cooking conditions in person."
    if code in {"STEP_BLOCKED", "STEP_NOT_FOUND", "MEAL_NOT_FOUND"}:
        return f"I couldn't complete that action. {message}"
    return "I couldn't complete that cooking action. Please check Rasoi Relay and try again."


def _pending(handler_input: HandlerInput) -> dict[str, Any]:
    return handler_input.attributes_manager.session_attributes


def _save_pending(handler_input: HandlerInput, attributes: dict[str, Any]) -> None:
    handler_input.attributes_manager.session_attributes = attributes


class LaunchRequestHandler(AbstractRequestHandler):
    def can_handle(self, handler_input: HandlerInput) -> bool:
        return is_request_type("LaunchRequest")(handler_input)

    def handle(self, handler_input: HandlerInput) -> dict[str, Any]:
        return _response(
            handler_input,
            "Welcome to Rasoi Relay. You can ask how dinner is going, what to do next, report an interruption, or start a cooking timer. Create your meal in the Rasoi Relay app first.",
            "Try saying, what should I do next?",
        )


class StartSampleMealIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input: HandlerInput) -> bool:
        return is_intent_name("StartSampleMealIntent")(handler_input)

    def handle(self, handler_input: HandlerInput) -> dict[str, Any]:
        try:
            with SessionLocal() as db:
                user_id = _user_id(db, handler_input)
                existing, error = _active_meal(db, user_id)
                if error:
                    if "couldn't find an active or paused meal" not in error:
                        return _response(handler_input, error)
                if existing is not None:
                    return _response(handler_input, f"You already have a cooking session called {existing.name}. Ask what you should do next.")
                data = MealCreate(
                    name="Dal, rice and aloo sabzi",
                    target_serving_at=datetime.now(timezone.utc) + timedelta(minutes=60),
                    dishes=[
                        DishCreate(name="Rice", steps=[
                            StepCreate(title="Wash rice", instruction="Rinse rice until the water is clearer.", duration_minutes=3),
                            StepCreate(title="Cook rice", instruction="Cook using your usual method after checking the current conditions.", duration_minutes=18, depends_on=[0], requires_physical_confirmation=True),
                            StepCreate(title="Rest rice", instruction="Let rice rest and check its texture.", duration_minutes=5, depends_on=[1]),
                        ]),
                        DishCreate(name="Dal", steps=[
                            StepCreate(title="Rinse dal", instruction="Rinse the dal.", duration_minutes=2),
                            StepCreate(title="Pressure cook dal", instruction="Follow the pressure cooker's instructions. Never open it while pressurized.", duration_minutes=20, depends_on=[0], requires_physical_confirmation=True),
                            StepCreate(title="Temper dal", instruction="Prepare the tempering carefully and combine with the dal.", duration_minutes=5, depends_on=[1]),
                        ]),
                        DishCreate(name="Aloo sabzi", steps=[
                            StepCreate(title="Chop potatoes", instruction="Wash and chop the potatoes.", duration_minutes=8),
                            StepCreate(title="Sauté spices", instruction="Check the cooking area before heating oil, then sauté the spices.", duration_minutes=3, depends_on=[0], requires_physical_confirmation=True),
                            StepCreate(title="Cook potatoes", instruction="Cook until done and check texture; elapsed time alone is not proof.", duration_minutes=15, depends_on=[1], requires_physical_confirmation=True),
                        ]),
                    ],
                )
                meal = create_meal(db, user_id, data, source="alexa")
                return _response(
                    handler_input,
                    f"I've started a sample cooking session for {meal.name}. I'll guide you through the steps, and I'll ask you to check physical conditions before safety-sensitive steps. Ask what you should do next.",
                    "Ask, what should I do next?",
                )
        except HTTPException as exc:
            return _response(handler_input, _http_error_speech(exc))


class MealStatusIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input: HandlerInput) -> bool:
        return is_intent_name("MealStatusIntent")(handler_input)

    def handle(self, handler_input: HandlerInput) -> dict[str, Any]:
        try:
            with SessionLocal() as db:
                user_id = _user_id(db, handler_input)
                meal, error = _active_meal(db, user_id)
                if error:
                    return _response(handler_input, error)
                assert meal is not None
                status = meal_status(db, meal)
                progress = status["progress"]
                next_action = status.get("next_action") or {}
                next_step = (next_action.get("action") or {}).get("title")
                speech = (
                    f"{meal.name} is {meal.status.value}. "
                    f"{progress['completed']} of {progress['total']} cooking steps are complete."
                )
                if next_step:
                    speech += f" The next step is {next_step}."
                return _response(handler_input, speech, "Ask what you should do next.")
        except HTTPException as exc:
            return _response(handler_input, _http_error_speech(exc))


class NextActionIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input: HandlerInput) -> bool:
        return is_intent_name("NextActionIntent")(handler_input)

    def handle(self, handler_input: HandlerInput) -> dict[str, Any]:
        try:
            with SessionLocal() as db:
                user_id = _user_id(db, handler_input)
                meal, error = _active_meal(db, user_id)
                if error:
                    return _response(handler_input, error)
                assert meal is not None
                return _response(handler_input, _action_speech(get_next_action(db, meal)), "Ask for the next step again whenever you're ready.")
        except HTTPException as exc:
            return _response(handler_input, _http_error_speech(exc))


class ReportInterruptionIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input: HandlerInput) -> bool:
        return is_intent_name("ReportInterruptionIntent")(handler_input)

    def handle(self, handler_input: HandlerInput) -> dict[str, Any]:
        try:
            with SessionLocal() as db:
                user_id = _user_id(db, handler_input)
                meal, error = _active_meal(db, user_id)
                if error:
                    return _response(handler_input, error)
                assert meal is not None
                report_interruption(
                    db, meal, "User reported leaving the kitchen",
                    {"stove_state": "unknown"}, source="alexa",
                )
                attributes = _pending(handler_input)
                attributes["pending_resume_meal_id"] = meal.id
                attributes["pending_resume_needs_stove"] = True
                _save_pending(handler_input, attributes)
                return _response(
                    handler_input,
                    "I've paused the cooking session. Please check the stove in person. When you're ready, tell me whether the stove is on or off. I won't assume its state.",
                    "Say, the stove is on, or the stove is off.",
                )
        except HTTPException as exc:
            return _response(handler_input, _http_error_speech(exc))


class ResumeMealIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input: HandlerInput) -> bool:
        return is_intent_name("ResumeMealIntent")(handler_input)

    def handle(self, handler_input: HandlerInput) -> dict[str, Any]:
        try:
            with SessionLocal() as db:
                user_id = _user_id(db, handler_input)
                meal, error = _active_meal(db, user_id)
                if error:
                    return _response(handler_input, error)
                assert meal is not None
                recovered = recover_meal(db, meal)
                attributes = _pending(handler_input)
                attributes["pending_resume_meal_id"] = meal.id
                attributes["pending_resume_needs_stove"] = bool(recovered.get("clarification_required"))
                _save_pending(handler_input, attributes)
                if recovered.get("clarification_required"):
                    return _response(
                        handler_input,
                        "Before resuming, please check the stove in person. Then say, the stove is on, or the stove is off.",
                        "Tell me whether the stove is on or off after checking it in person.",
                    )
                return _response(
                    handler_input,
                    "The session is ready to resume. Are you ready to continue cooking? Say yes to confirm.",
                    "Say yes to resume, or no to leave the meal paused.",
                )
        except HTTPException as exc:
            return _response(handler_input, _http_error_speech(exc))


class ConfirmStoveStateIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input: HandlerInput) -> bool:
        return is_intent_name("ConfirmStoveStateIntent")(handler_input)

    def handle(self, handler_input: HandlerInput) -> dict[str, Any]:
        state = (_slot(handler_input, "stove_state") or "").lower()
        if state not in {"on", "off"}:
            return _response(
                handler_input,
                "Please check the stove in person, then say either, the stove is on, or the stove is off.",
                "Say, the stove is on, or the stove is off.",
            )
        attributes = _pending(handler_input)
        meal_id = attributes.get("pending_resume_meal_id")
        if not meal_id:
            return _response(handler_input, "First ask me to resume cooking, then confirm the stove state.")
        try:
            with SessionLocal() as db:
                user_id = _user_id(db, handler_input)
                meal = get_meal(db, str(meal_id), user_id)
                resume_meal(db, meal, user_confirmed=True, confirmed_conditions={"stove_state": state})
                attributes.pop("pending_resume_meal_id", None)
                attributes.pop("pending_resume_needs_stove", None)
                _save_pending(handler_input, attributes)
                return _response(handler_input, f"Thanks for checking. I've resumed {meal.name}. Ask what you should do next.")
        except HTTPException as exc:
            return _response(handler_input, _http_error_speech(exc))


class YesIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input: HandlerInput) -> bool:
        return is_intent_name("AMAZON.YesIntent")(handler_input)

    def handle(self, handler_input: HandlerInput) -> dict[str, Any]:
        attributes = _pending(handler_input)
        meal_id = attributes.get("pending_resume_meal_id")
        if not meal_id:
            return _response(handler_input, "I don't have a pending confirmation. Ask what you should do next.")
        if attributes.get("pending_resume_needs_stove"):
            return _response(handler_input, "Please check the stove in person first. Then tell me whether it is on or off.")
        try:
            with SessionLocal() as db:
                user_id = _user_id(db, handler_input)
                meal = get_meal(db, str(meal_id), user_id)
                resume_meal(db, meal, user_confirmed=True)
                attributes.pop("pending_resume_meal_id", None)
                attributes.pop("pending_resume_needs_stove", None)
                _save_pending(handler_input, attributes)
                return _response(handler_input, f"You're back in. I've resumed {meal.name}. Ask what you should do next.")
        except HTTPException as exc:
            return _response(handler_input, _http_error_speech(exc))


class NoIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input: HandlerInput) -> bool:
        return is_intent_name("AMAZON.NoIntent")(handler_input)

    def handle(self, handler_input: HandlerInput) -> dict[str, Any]:
        attributes = _pending(handler_input)
        attributes.pop("pending_resume_meal_id", None)
        attributes.pop("pending_resume_needs_stove", None)
        _save_pending(handler_input, attributes)
        return _response(handler_input, "Okay. I'll leave the cooking session paused.")


class StartTimerIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input: HandlerInput) -> bool:
        return is_intent_name("StartTimerIntent")(handler_input)

    def handle(self, handler_input: HandlerInput) -> dict[str, Any]:
        raw_duration = _slot(handler_input, "duration_minutes")
        try:
            duration = int(raw_duration) if raw_duration is not None else None
        except ValueError:
            duration = None
        if duration is None or duration < 1 or duration > 360:
            return _response(handler_input, "Please repeat the command with a duration from one to 360 minutes, such as, set a timer for five minutes.")
        try:
            with SessionLocal() as db:
                user_id = _user_id(db, handler_input)
                meal, error = _active_meal(db, user_id)
                if error:
                    return _response(handler_input, error)
                assert meal is not None
                next_action = get_next_action(db, meal)
                action = next_action.get("action") or {}
                if next_action.get("clarification_required") or not action.get("step_id"):
                    return _response(handler_input, _action_speech(next_action))
                result = start_timer(
                    db, meal, action["step_id"], duration_minutes=duration,
                    physical_condition_confirmed=False, source="alexa",
                )
                title = action.get("title", "the next step")
                return _response(
                    handler_input,
                    f"I've recorded a Rasoi Relay timer for {duration} minutes for {title}. This is a saved cooking timer, not an Alexa device alarm, so keep using a reliable timer you can hear. Timer expiry does not mean the food is ready.",
                )
        except HTTPException as exc:
            return _response(handler_input, _http_error_speech(exc))


class CompleteStepIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input: HandlerInput) -> bool:
        return is_intent_name("CompleteStepIntent")(handler_input)

    def handle(self, handler_input: HandlerInput) -> dict[str, Any]:
        try:
            with SessionLocal() as db:
                user_id = _user_id(db, handler_input)
                meal, error = _active_meal(db, user_id)
                if error:
                    return _response(handler_input, error)
                assert meal is not None
                next_action = get_next_action(db, meal)
                action = next_action.get("action") or {}
                if next_action.get("clarification_required") or not action.get("step_id"):
                    return _response(handler_input, _action_speech(next_action))
                request_id = getattr(handler_input.request_envelope.request, "request_id", None) or str(uuid.uuid4())
                result = complete_step(
                    db, meal, action["step_id"],
                    idempotency_key=f"alexa:{request_id}:{action['step_id']}",
                    physical_condition_confirmed=False,
                    source="alexa",
                )
                if result.get("status") in {"completed", "already_completed", "already_processed"}:
                    return _response(handler_input, "I've updated the cooking progress. " + _action_speech(result.get("next_action") or get_next_action(db, meal)))
                return _response(handler_input, "I couldn't confirm that step was completed. Check Rasoi Relay before continuing.")
        except HTTPException as exc:
            return _response(handler_input, _http_error_speech(exc))


class HelpIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input: HandlerInput) -> bool:
        return is_intent_name("AMAZON.HelpIntent")(handler_input)

    def handle(self, handler_input: HandlerInput) -> dict[str, Any]:
        return _response(
            handler_input,
            "You can ask how dinner is going, what to do next, report leaving the kitchen, ask to resume cooking, say you finished the next step, or set a saved Rasoi Relay timer.",
            "Try saying, what should I do next?",
        )


class StopIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input: HandlerInput) -> bool:
        return is_intent_name("AMAZON.StopIntent")(handler_input) or is_intent_name("AMAZON.CancelIntent")(handler_input)

    def handle(self, handler_input: HandlerInput) -> dict[str, Any]:
        return _response(handler_input, "Okay. Rasoi Relay is stopping. Your saved cooking progress remains available.", end_session=True)


class FallbackIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input: HandlerInput) -> bool:
        return is_intent_name("AMAZON.FallbackIntent")(handler_input)

    def handle(self, handler_input: HandlerInput) -> dict[str, Any]:
        return _response(
            handler_input,
            "I didn't understand that cooking request. Try asking what to do next, or how dinner is going.",
            "Ask, what should I do next?",
        )


class SessionEndedRequestHandler(AbstractRequestHandler):
    def can_handle(self, handler_input: HandlerInput) -> bool:
        return is_request_type("SessionEndedRequest")(handler_input)

    def handle(self, handler_input: HandlerInput) -> dict[str, Any]:
        return handler_input.response_builder.response


class SkillExceptionHandler(AbstractExceptionHandler):
    def can_handle(self, handler_input: HandlerInput, exception: Exception) -> bool:
        return True

    def handle(self, handler_input: HandlerInput, exception: Exception) -> dict[str, Any]:
        logger.error("alexa_skill_handler_failed", exc_info=(type(exception), exception, exception.__traceback__))
        return _response(
            handler_input,
            "Something went wrong while checking your cooking session. Your last saved progress has not been intentionally changed by this response. Please check Rasoi Relay before continuing.",
        )


for request_handler in (
    LaunchRequestHandler(),
    StartSampleMealIntentHandler(),
    MealStatusIntentHandler(),
    NextActionIntentHandler(),
    ReportInterruptionIntentHandler(),
    ResumeMealIntentHandler(),
    ConfirmStoveStateIntentHandler(),
    YesIntentHandler(),
    NoIntentHandler(),
    StartTimerIntentHandler(),
    CompleteStepIntentHandler(),
    HelpIntentHandler(),
    StopIntentHandler(),
    FallbackIntentHandler(),
    SessionEndedRequestHandler(),
):
    sb.add_request_handler(request_handler)

sb.add_exception_handler(SkillExceptionHandler())
skill = sb.create()
