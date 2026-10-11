from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator


class StepCreate(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    instruction: str = Field(min_length=1, max_length=2000)
    duration_minutes: int = Field(ge=1, le=360)
    depends_on: list[int] = Field(default_factory=list)
    requires_physical_confirmation: bool = False


class DishCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    steps: list[StepCreate] = Field(min_length=1, max_length=40)


class MealCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    target_serving_at: datetime
    dishes: list[DishCreate] = Field(min_length=1, max_length=12)

    @field_validator("target_serving_at")
    @classmethod
    def target_must_be_timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("target_serving_at must include a timezone")
        return value


class InterruptionCreate(BaseModel):
    reason: str = Field(min_length=1, max_length=240)
    details: dict[str, Any] = Field(default_factory=dict)


class CompleteStepRequest(BaseModel):
    idempotency_key: str | None = Field(default=None, max_length=160)
    user_confirmed: bool = True


class PhysicalConfirmation(BaseModel):
    condition: str = Field(min_length=1, max_length=100)
    value: str = Field(min_length=1, max_length=120)
    confirmed_by_user: bool = True


class PreferenceWrite(BaseModel):
    value: dict[str, Any]
    locale: str = Field(default="en-IN", max_length=16)


class ConversationRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    meal_id: str | None = None
