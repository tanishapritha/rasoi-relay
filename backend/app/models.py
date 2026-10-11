from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class MealStatus(str, enum.Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class StepStatus(str, enum.Enum):
    PENDING = "pending"
    READY = "ready"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    BLOCKED = "blocked"


class TimerStatus(str, enum.Enum):
    ACTIVE = "active"
    FIRED = "fired"
    CANCELLED = "cancelled"


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    display_name: Mapped[str] = mapped_column(String(120), default="Household")
    email: Mapped[str | None] = mapped_column(String(320), nullable=True, unique=True)
    account_status: Mapped[str] = mapped_column(String(24), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    external_identities: Mapped[list[ExternalIdentity]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class ExternalIdentity(Base):
    __tablename__ = "external_identities"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    provider: Mapped[str] = mapped_column(String(80))
    provider_subject: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    user: Mapped[User] = relationship(back_populates="external_identities")
    __table_args__ = (
        UniqueConstraint("provider", "provider_subject", name="uq_external_identity_provider_subject"),
    )


class Meal(Base):
    __tablename__ = "meals"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    target_serving_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[MealStatus] = mapped_column(Enum(MealStatus), default=MealStatus.ACTIVE)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    dishes: Mapped[list[Dish]] = relationship(back_populates="meal", cascade="all, delete-orphan")
    events: Mapped[list[CookingEvent]] = relationship(back_populates="meal", cascade="all, delete-orphan")


class Dish(Base):
    __tablename__ = "dishes"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    meal_id: Mapped[str] = mapped_column(ForeignKey("meals.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    display_order: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(24), default="pending")
    meal: Mapped[Meal] = relationship(back_populates="dishes")
    steps: Mapped[list[CookingStep]] = relationship(back_populates="dish", cascade="all, delete-orphan", order_by="CookingStep.sequence")


class CookingStep(Base):
    __tablename__ = "cooking_steps"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    dish_id: Mapped[str] = mapped_column(ForeignKey("dishes.id", ondelete="CASCADE"), index=True)
    sequence: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(160))
    instruction: Mapped[str] = mapped_column(Text)
    duration_minutes: Mapped[int] = mapped_column(Integer)
    status: Mapped[StepStatus] = mapped_column(Enum(StepStatus), default=StepStatus.PENDING)
    requires_physical_confirmation: Mapped[bool] = mapped_column(Boolean, default=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    dish: Mapped[Dish] = relationship(back_populates="steps")
    dependencies: Mapped[list[StepDependency]] = relationship(
        foreign_keys="StepDependency.step_id", back_populates="step", cascade="all, delete-orphan"
    )
    timers: Mapped[list[CookingTimer]] = relationship(back_populates="step", cascade="all, delete-orphan")
    __table_args__ = (UniqueConstraint("dish_id", "sequence", name="uq_step_dish_sequence"),)


class StepDependency(Base):
    __tablename__ = "step_dependencies"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    step_id: Mapped[str] = mapped_column(ForeignKey("cooking_steps.id", ondelete="CASCADE"), index=True)
    depends_on_step_id: Mapped[str] = mapped_column(ForeignKey("cooking_steps.id", ondelete="CASCADE"), index=True)
    step: Mapped[CookingStep] = relationship(foreign_keys=[step_id], back_populates="dependencies")
    __table_args__ = (
        UniqueConstraint("step_id", "depends_on_step_id", name="uq_step_dependency"),
    )


class CookingTimer(Base):
    __tablename__ = "cooking_timers"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    step_id: Mapped[str] = mapped_column(ForeignKey("cooking_steps.id", ondelete="CASCADE"), index=True)
    deadline_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[TimerStatus] = mapped_column(Enum(TimerStatus), default=TimerStatus.ACTIVE)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    fired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    step: Mapped[CookingStep] = relationship(back_populates="timers")


class CookingEvent(Base):
    __tablename__ = "cooking_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    meal_id: Mapped[str] = mapped_column(ForeignKey("meals.id", ondelete="CASCADE"), index=True)
    event_type: Mapped[str] = mapped_column(String(64), index=True)
    source: Mapped[str] = mapped_column(String(32), default="api")
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    idempotency_key: Mapped[str | None] = mapped_column(String(160), nullable=True, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    meal: Mapped[Meal] = relationship(back_populates="events")
    __table_args__ = (Index("ix_event_meal_created", "meal_id", "created_at"),)


class HouseholdPreference(Base):
    __tablename__ = "household_preferences"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    key: Mapped[str] = mapped_column(String(80))
    value: Mapped[dict[str, Any]] = mapped_column(JSON)
    locale: Mapped[str] = mapped_column(String(16), default="en-IN")
    source: Mapped[str] = mapped_column(String(32), default="user_confirmed")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    __table_args__ = (UniqueConstraint("user_id", "key", name="uq_preference_user_key"),)


class MealPlanRevision(Base):
    __tablename__ = "meal_plan_revisions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    meal_id: Mapped[str] = mapped_column(ForeignKey("meals.id", ondelete="CASCADE"), index=True)
    previous_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON)
    revised_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON)
    reason: Mapped[str] = mapped_column(String(240))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
