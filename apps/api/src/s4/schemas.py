"""Esquemas Pydantic v2 para el contrato de unidad de trabajo y exportación de S4."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from src.s4.enums import S4RunStatus, S4TaskStatus, S4TaskType


class S4RecoveryEvent(BaseModel):
    """Registro de evento de reintento o recuperación dentro de una tarea."""

    model_config = ConfigDict(extra="forbid")

    timestamp: datetime
    event_type: str = Field(description="Tipo de recuperación (ej. 'transient_retry', 'tool_fallback')")
    attempt: int = Field(ge=1, description="Número de intento en el momento de la recuperación")
    details: str = Field(description="Descripción sanitizada del incidente o acción tomada")


class S4TaskInput(BaseModel):
    """Contrato formal de entrada para una unidad de trabajo S4."""

    model_config = ConfigDict(extra="allow")

    task_type: S4TaskType = Field(default=S4TaskType.GENERAL_TECHNICAL)
    scenario_id: str = Field(description="Identificador del escenario o prueba técnica")
    problem_slug: str | None = Field(default=None, description="Slug del problema del catálogo si aplica")
    parameters: dict[str, Any] = Field(default_factory=dict, description="Parámetros técnicos de ejecución")


class S4TaskResult(BaseModel):
    """Contrato formal de resultado verificado de una unidad de trabajo S4."""

    model_config = ConfigDict(extra="allow")

    validation_passed: bool = Field(description="Si la tarea cumplió estrictamente los criterios de aceptación")
    summary: str = Field(description="Resumen técnico del resultado obtenido")
    metrics: dict[str, Any] = Field(default_factory=dict, description="Métricas de ejecución (ej. score, tests)")
    artifacts: dict[str, Any] = Field(default_factory=dict, description="Artefactos generados (código, hash)")


class S4TaskExecutionRecord(BaseModel):
    """Representación serializada de una ejecución de tarea individual."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    run_id: UUID
    task_number: int
    task_type: str
    status: S4TaskStatus
    validation_passed: bool
    input_sanitized: str
    result_summary: str | None
    worker_id: str | None = None
    lease_token: str | None = None
    lease_generation: int = 1
    heartbeat_at: datetime | None = None
    started_at: datetime | None
    finished_at: datetime | None
    duration_seconds: float | None = None
    attempt_count: int
    model_calls: int
    input_tokens: int
    output_tokens: int
    total_tokens: int
    cost_usd: float
    error_sanitized: str | None
    recovery_events: list[dict[str, Any]] = Field(default_factory=list)
    gateway_request_ids: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class S4LoadRunSummary(BaseModel):
    """Resumen consolidado y estadísticas agregadas de una corrida de carga S4."""

    model_config = ConfigDict(from_attributes=True)

    run_id: UUID
    status: S4RunStatus
    target_tasks: int
    completed_tasks: int
    failed_tasks: int
    cancelled_tasks: int
    total_tasks_recorded: int
    success_rate_percent: float
    budget_limit_usd: float
    total_cost_usd: float
    average_cost_per_task_usd: float
    total_input_tokens: int
    total_output_tokens: int
    total_model_calls: int
    started_at: datetime | None
    finished_at: datetime | None
    duration_seconds: float | None
    throughput_tasks_per_hour: float | None
    first_llm_call_at: datetime | None = None
    last_llm_call_at: datetime | None = None
    llm_activity_duration_seconds: float | None = None
    effective_llm_activity_seconds: float | None = None
    calls_with_usage: int = 0
    max_gap_seconds_between_calls: float | None = None
    inactivity_exceeded_count: int = 0
    max_inactivity_threshold_seconds: float = 120.0
    longest_continuous_window_seconds: float | None = None
    continuous_window_valid: bool = False
    interruption_count: int = 0
    uncertain_liabilities_usd: float = 0.0
    active_reservations_usd: float = 0.0
    total_exposure_usd: float = 0.0
    hourly_distribution: dict[str, int] = Field(default_factory=dict)


class S4LLMCallExportRecord(BaseModel):
    """Registro individual de llamada LLM auditable y conciliable contra el proveedor."""

    call_id: UUID
    task_id: UUID | None
    task_number: int | None
    call_sequence: int
    created_at: datetime
    model: str
    tokens_input: int | None
    tokens_output: int | None
    tokens_total: int | None
    cost_usd: float | None
    measurement_status: str
    gateway_request_id: str | None
    response_body_id: str | None = None
    provider_request_id: str | None = None
    cf_ray: str | None = None
    gateway_metadata: dict[str, Any] = Field(default_factory=dict)


class S4LLMCallExportRow(BaseModel):
    """Fila CSV para exportación individual de llamadas LLM conciliables con el proveedor."""

    call_id: str
    task_id: str
    task_number: str
    call_sequence: int
    created_at: str
    model: str
    tokens_input: str
    tokens_output: str
    tokens_total: str
    cost_usd: str
    measurement_status: str
    gateway_request_id: str
    response_body_id: str = ""
    provider_request_id: str
    cf_ray: str


class S4TaskExportRow(BaseModel):
    """Fila estructurada para exportación de la bitácora en formato CSV."""

    run_id: str
    task_id: str
    task_number: int
    task_type: str
    status: str
    validation_passed: bool
    started_at: str
    finished_at: str
    duration_seconds: str
    attempt_count: int
    model_calls: int
    input_tokens: int
    output_tokens: int
    total_tokens: int
    cost_usd: str
    gateway_request_ids: str
    error_sanitized: str
    recovery_events_count: int
    input_preview: str
    result_preview: str


class S4RunExportJSON(BaseModel):
    """Estructura completa para exportación auditable de la corrida en formato JSON."""

    run: S4LoadRunSummary
    tasks: list[S4TaskExecutionRecord]
    llm_calls: list[S4LLMCallExportRecord] = Field(default_factory=list)

