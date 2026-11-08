from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum,
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
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import Base
from src.db.enums import InterviewPhase, InterviewStatus, TurnSpeaker

if TYPE_CHECKING:
    from src.db.models.invitation import Invitation
    from src.db.models.problem import Problem
    from src.db.models.s4 import S4TaskExecution
    from src.db.models.vacancy import Vacancy


class Interview(Base):
    __tablename__ = "interviews"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    vacancy_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("vacancies.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    problem_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("problems.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    candidate_email: Mapped[str] = mapped_column(String(255), nullable=False)
    candidate_name: Mapped[str] = mapped_column(String(255), nullable=False)
    access_token: Mapped[str | None] = mapped_column(String(255), nullable=True, unique=True)
    status: Mapped[InterviewStatus] = mapped_column(
        Enum(
            InterviewStatus,
            name="interview_status",
            native_enum=False,
            length=20,
            values_callable=lambda enum: [item.value for item in enum],
        ),
        nullable=False,
        default=InterviewStatus.PENDING,
        server_default=text("'pending'"),
        index=True,
    )
    phase: Mapped[InterviewPhase] = mapped_column(
        Enum(
            InterviewPhase,
            name="interview_phase",
            native_enum=False,
            length=20,
            values_callable=lambda enum: [item.value for item in enum],
        ),
        nullable=False,
        default=InterviewPhase.INTRO,
        server_default=text("'INTRO'"),
        index=True,
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    hint_level: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    last_hint_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    hint_reserved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    hint_reservation_token: Mapped[UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
    )

    vacancy: Mapped[Vacancy] = relationship(back_populates="interviews")
    problem: Mapped[Problem | None] = relationship(back_populates="interviews")
    invitation: Mapped[Invitation | None] = relationship(back_populates="interview")
    turns: Mapped[list[Turn]] = relationship(
        back_populates="interview",
        cascade="all, delete-orphan",
    )
    snapshots: Mapped[list[Snapshot]] = relationship(
        back_populates="interview",
        cascade="all, delete-orphan",
    )
    evaluation: Mapped[Evaluation] = relationship(back_populates="interview", uselist=False)
    llm_usage_records: Mapped[list[LLMUsageRecord]] = relationship(
        back_populates="interview",
        cascade="all, delete-orphan",
        order_by="LLMUsageRecord.created_at",
    )


class Turn(Base):
    __tablename__ = "turns"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    interview_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("interviews.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    speaker: Mapped[TurnSpeaker] = mapped_column(
        Enum(
            TurnSpeaker,
            name="turn_speaker",
            native_enum=False,
            length=20,
            values_callable=lambda enum: [item.value for item in enum],
        ),
        nullable=False,
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    interview: Mapped[Interview] = relationship(back_populates="turns")


class Snapshot(Base):
    __tablename__ = "snapshots"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    interview_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("interviews.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    code: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    phase: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        server_default="INTRO",
    )
    language: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        server_default="python",
    )
    reason: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        server_default="legacy",
    )
    tests_passed: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    total_tests: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    execution_status: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )

    interview: Mapped[Interview] = relationship(back_populates="snapshots")

class Evaluation(Base):
    """Evaluación definitiva de una entrevista tras la fase EVALUATE.

    Almacena la rúbrica de 5 dimensiones (1-5), la puntuación general,
    la recomendación y la evidencia citada (turnos, snapshots, ejecuciones).
    """
    __tablename__ = "evaluations"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    interview_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("interviews.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True,
    )
    overall_score: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.0,
    )
    recommendation: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="borderline",
    )
    needs_human_review: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )
    discrepancy_note: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )
    model_name: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )
    prompt_version: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
    )
    tokens_prompt: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    tokens_completion: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    cost_usd: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
    )
    evaluated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    interview: Mapped[Interview] = relationship(back_populates="evaluation")

    dimensions: Mapped[list[EvaluationDimension]] = relationship(back_populates="evaluation")
    evidences: Mapped[list[EvaluationEvidence]] = relationship(back_populates="evaluation")

    def __repr__(self) -> str:
        return f"<Evaluation interview_id={self.interview_id} score={self.overall_score} recommendation={self.recommendation}>"


class EvaluationDimension(Base):
    """Una dimensión de la rúbrica (1-5) con su razonamiento."""
    __tablename__ = "evaluation_dimensions"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    evaluation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("evaluations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )
    score: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    reasoning: Mapped[str] = mapped_column(
        Text,
        nullable=True,
    )

    evaluation: Mapped[Evaluation] = relationship(back_populates="dimensions")

    __table_args__ = (
        UniqueConstraint("evaluation_id", "name", name="uq_evaluation_dimension"),
    )

    def __repr__(self) -> str:
        return f"<EvaluationDimension evaluation_id={self.evaluation_id} name={self.name} score={self.score}>"


class EvaluationEvidence(Base):
    """Evidencia citada para una dimensión en particular.

    Referencia a turnos, snapshots o ejecuciones de la entrevista.
    """
    __tablename__ = "evaluation_evidence"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    evaluation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("evaluations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    dimension_name: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )
    turn_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("turns.id", ondelete="SET NULL"),
        nullable=True,
    )
    snapshot_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("snapshots.id", ondelete="SET NULL"),
        nullable=True,
    )
    execution_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("snapshots.id", ondelete="SET NULL"),
        nullable=True,
    )
    quote: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    reasoning: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    evaluation: Mapped[Evaluation] = relationship(back_populates="evidences")

    __table_args__ = (
        UniqueConstraint("evaluation_id", "turn_id", name="uq_evidence_turn"),
        UniqueConstraint("evaluation_id", "snapshot_id", name="uq_evidence_snapshot"),
    )

    def __repr__(self) -> str:
        return f"<EvaluationEvidence evaluation_id={self.evaluation_id} dimension={self.dimension_name} turn_id={self.turn_id is not None}>"


class LLMUsageRecord(Base):
    """Registro persistente de consumo de tokens y costes de LLM por llamada (S3.1).
    
    Permite auditar y reconstruir el costo de la tarea de forma durable tras reinicio
    del proceso, sin doble contabilidad y distinguiendo el estado de medición.
    """

    __tablename__ = "llm_usage_records"
    __table_args__ = (
        UniqueConstraint("s4_task_execution_id", "call_sequence", name="uq_llm_usage_task_call_seq"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    interview_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("interviews.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    turn_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("turns.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    s4_task_execution_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("s4_task_executions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    call_sequence: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        server_default=text("1"),
    )
    gateway_request_id: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        index=True,
    )
    gateway_metadata: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
        server_default=text("'{}'"),
    )
    stage: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="conversational",
        index=True,
    )
    provider: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="openai-compatible",
    )
    model: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )
    tokens_input: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    tokens_output: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    tokens_total: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    cost_usd: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )
    measurement_status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="measured",
        server_default=text("'measured'"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        index=True,
    )

    interview: Mapped[Interview | None] = relationship("Interview", back_populates="llm_usage_records")
    turn: Mapped[Turn | None] = relationship("Turn")
    s4_task_execution: Mapped[S4TaskExecution | None] = relationship(
        "S4TaskExecution",
        back_populates="llm_usage_records",
    )

    def __repr__(self) -> str:
        return (
            f"<LLMUsageRecord interview_id={self.interview_id} stage={self.stage} "
            f"model={self.model} cost_usd={self.cost_usd} status={self.measurement_status}>"
        )

