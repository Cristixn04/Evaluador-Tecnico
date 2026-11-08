"""Modelos SQLAlchemy para la persistencia durable de S4 (Semana de Carga)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import Base
from src.s4.enums import S4RunStatus, S4TaskStatus, S4TaskType

if TYPE_CHECKING:
    from src.db.models.interview import LLMUsageRecord


class S4LoadRun(Base):
    """Entidad que representa una corrida de carga de larga duración en S4."""

    __tablename__ = "s4_load_runs"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=S4RunStatus.PLANNED.value,
        server_default=text("'planned'"),
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        index=True,
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    target_tasks: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1000,
        server_default=text("1000"),
    )
    completed_tasks: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    failed_tasks: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    cancelled_tasks: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    budget_limit_usd: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=50.0,
        server_default=text("50.0"),
    )
    total_cost_usd: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.0,
        server_default=text("0.0"),
    )
    meta: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
        server_default=text("'{}'"),
    )

    task_executions: Mapped[list[S4TaskExecution]] = relationship(
        "S4TaskExecution",
        back_populates="load_run",
        cascade="all, delete-orphan",
        order_by="S4TaskExecution.task_number",
    )

    def __repr__(self) -> str:
        return f"<S4LoadRun id={self.id} status={self.status} completed={self.completed_tasks}/{self.target_tasks}>"


class S4TaskExecution(Base):
    """Entidad que representa una unidad de trabajo técnica individual en S4."""

    __tablename__ = "s4_task_executions"
    __table_args__ = (
        UniqueConstraint("run_id", "task_number", name="uq_s4_task_run_number"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("s4_load_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    task_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    task_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default=S4TaskType.GENERAL_TECHNICAL.value,
        server_default=text("'general_technical'"),
        index=True,
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=S4TaskStatus.QUEUED.value,
        server_default=text("'queued'"),
        index=True,
    )
    input_sanitized: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    result_summary: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    validation_passed: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
    )
    worker_id: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )
    lease_token: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )
    lease_generation: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        server_default=text("1"),
    )
    heartbeat_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )
    attempt_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        server_default=text("1"),
    )
    model_calls: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    input_tokens: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    output_tokens: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    cost_usd: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.0,
        server_default=text("0.0"),
    )
    error_sanitized: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    recovery_events: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON,
        nullable=False,
        default=list,
        server_default=text("'[]'"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        index=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    load_run: Mapped[S4LoadRun] = relationship(
        "S4LoadRun",
        back_populates="task_executions",
    )
    llm_usage_records: Mapped[list[LLMUsageRecord]] = relationship(
        "LLMUsageRecord",
        back_populates="s4_task_execution",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<S4TaskExecution id={self.id} run_id={self.run_id} num={self.task_number} status={self.status}>"

