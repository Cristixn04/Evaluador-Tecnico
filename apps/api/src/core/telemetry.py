"""Módulo de telemetría estructurada para herramientas del agente, costos de LLM y latencia (S-26).

Proporciona:
- Rastreo de ciclo de vida de herramientas de agente ([AGENT_TOOL_CALL:START/SUCCESS/ERROR]).
- Registro estructurado de costo y tokens de LLM por entrevista ([METRICS:INTERVIEW_COST]).
- Métricas y alertas estructuradas de latencia ([METRICS:LATENCY], [ALERT:HIGH_LATENCY]).
- Protección estricta contra filtraciones (Anti-Leak).

Reglas estrictas de seguridad (Anti-Leak):
- PROHIBIDO registrar tokens, JWT, contraseñas, API keys.
- PROHIBIDO registrar PII (emails, nombres de candidatos).
- PROHIBIDO registrar código completo, prompts completos o respuestas del candidato.
"""

from __future__ import annotations

import logging
import re
import time
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from src.core.config import settings
from src.evaluation.pricing import calculate_llm_cost

logger = logging.getLogger("agent.telemetry")

_SENSITIVE_PATTERNS = [
    re.compile(r"bearer\s+[a-zA-Z0-9_\-\.]+", re.IGNORECASE),
    re.compile(r"[a-zA-Z0-9_\.\+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-\.]+"),
    re.compile(r"sk-[a-zA-Z0-9]{15,}"),
    re.compile(r"ey[a-zA-Z0-9_\-]{10,}(\.[a-zA-Z0-9_\-]+)*"),
    re.compile(r"(?:api[-_]?key|password|secret|token)\s*[:=]\s*[^\s,]+", re.IGNORECASE),
]


def _sanitize_value(val: Any) -> str:
    """Sanitiza y formatea un valor para el log de telemetría, asegurando Anti-Leak."""
    if val is None:
        return "none"
    if isinstance(val, bool):
        return "true" if val else "false"
    if isinstance(val, (int, float)):
        return str(val)
    if isinstance(val, UUID):
        return str(val)

    s = str(val).strip().replace("\n", " ").replace("\r", "").replace("\t", " ")
    for pattern in _SENSITIVE_PATTERNS:
        s = pattern.sub("[REDACTED]", s)

    if '"' in s:
        s = s.replace('"', "'")
    if " " in s:
        if len(s) > 50:
            s = s[:47] + "..."
        return f'"{s}"'
    if len(s) > 50:
        s = s[:47] + "..."
    return s


# -----------------------------------------------------------------------------
# 1. Alertas y Métricas de Latencia
# -----------------------------------------------------------------------------

def get_latency_threshold(operation: str) -> float:
    """Obtiene el umbral configurado de latencia (en ms) según el tipo de operación.

    Defaults documentados y justificados:
    - LLM (5000 ms): Tiempo aceptable para interacción conversacional sin romper fluidez.
    - Sandbox (3000 ms): Acorde a los límites de compilación y ejecución controlada.
    - WebSocket (1000 ms): Límite superior para eventos en tiempo real e interactividad.
    """
    op_lower = operation.lower()
    if "llm" in op_lower:
        return float(getattr(settings, "LLM_LATENCY_ALERT_MS", 5000.0))
    if "sandbox" in op_lower or "exec" in op_lower:
        return float(getattr(settings, "SANDBOX_LATENCY_ALERT_MS", 3000.0))
    if "websocket" in op_lower or "ws" in op_lower:
        return float(getattr(settings, "WEBSOCKET_LATENCY_ALERT_MS", 1000.0))
    return 3000.0


def record_latency(
    operation: str,
    duration_ms: float,
    interview_id: Any = None,
    threshold_ms: float | None = None,
) -> bool:
    """Registra la latencia de una operación y emite una alerta si supera el umbral.

    Retorna True si se activó la alerta, False en caso contrario.
    Garantiza que ningún prompt ni código se filtre en los logs.
    """
    safe_duration = max(0.0, float(duration_ms))
    effective_threshold = float(
        threshold_ms if threshold_ms is not None else get_latency_threshold(operation)
    )

    clean_op = _sanitize_value(operation)
    clean_iid = _sanitize_value(interview_id)

    if safe_duration > effective_threshold:
        msg = (
            f"[ALERT:HIGH_LATENCY] operation={clean_op} "
            f"duration_ms={safe_duration:.2f} "
            f"threshold_ms={effective_threshold:.2f} "
            f"interview_id={clean_iid}"
        )
        logger.warning(msg)
        return True
    else:
        msg = (
            f"[METRICS:LATENCY] operation={clean_op} "
            f"duration_ms={safe_duration:.2f} "
            f"threshold_ms={effective_threshold:.2f} "
            f"interview_id={clean_iid}"
        )
        logger.info(msg)
        return False


@contextmanager
def measure_latency(
    operation: str,
    interview_id: Any = None,
    threshold_ms: float | None = None,
) -> Iterator[dict[str, Any]]:
    """Context manager sincrónico para medir y alertar sobre latencia de una operación."""
    start = time.perf_counter()
    ctx: dict[str, Any] = {}
    try:
        yield ctx
    finally:
        duration_ms = (time.perf_counter() - start) * 1000.0
        alert_triggered = record_latency(
            operation=operation,
            duration_ms=duration_ms,
            interview_id=interview_id,
            threshold_ms=threshold_ms,
        )
        ctx["duration_ms"] = duration_ms
        ctx["alert_triggered"] = alert_triggered


@asynccontextmanager
async def async_measure_latency(
    operation: str,
    interview_id: Any = None,
    threshold_ms: float | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """Context manager asíncrono para medir y alertar sobre latencia de una operación."""
    start = time.perf_counter()
    ctx: dict[str, Any] = {}
    try:
        yield ctx
    finally:
        duration_ms = (time.perf_counter() - start) * 1000.0
        alert_triggered = record_latency(
            operation=operation,
            duration_ms=duration_ms,
            interview_id=interview_id,
            threshold_ms=threshold_ms,
        )
        ctx["duration_ms"] = duration_ms
        ctx["alert_triggered"] = alert_triggered


# -----------------------------------------------------------------------------
# 2. Registro Estructurado de Costos y Tokens por Entrevista
# -----------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class TokenCostRecord:
    """Registro inmutable de una llamada LLM asociada a una entrevista."""

    interview_id: str
    model: str
    input_tokens: int | None
    output_tokens: int | None
    total_tokens: int | None
    estimated_cost: float | None
    timestamp: float


@dataclass(frozen=True, slots=True)
class InterviewCostSummary:
    """Resumen consolidado de consumo de tokens y costo por entrevista."""

    interview_id: str
    total_input_tokens: int | None
    total_output_tokens: int | None
    total_tokens: int | None
    total_estimated_cost: float | None
    call_count: int
    models: list[str]


class InterviewCostTracker:
    """Rastreador en memoria para auditar y calcular costos y tokens por entrevista."""

    def __init__(self) -> None:
        self._records: dict[str, list[TokenCostRecord]] = {}

    def record_call(
        self,
        interview_id: Any,
        model: str | None,
        input_tokens: int | None,
        output_tokens: int | None,
        total_tokens: int | None = None,
    ) -> TokenCostRecord:
        """Registra una llamada LLM, calcula su costo mediante pricing y emite telemetría.

        Reglas Anti-Leak:
        - Solo se persisten identificadores de entrevista, nombre de modelo y conteos numéricos.
        - Nunca se registra contenido de prompts, respuestas ni fragmentos de código.
        """
        clean_iid = str(interview_id) if interview_id is not None else "unknown"
        safe_model = str(model).strip() if model else "unknown"

        # Validación estricta de tokens
        valid_in = (
            input_tokens
            if isinstance(input_tokens, int) and not isinstance(input_tokens, bool) and input_tokens >= 0
            else None
        )
        valid_out = (
            output_tokens
            if isinstance(output_tokens, int) and not isinstance(output_tokens, bool) and output_tokens >= 0
            else None
        )

        # Determinar total de tokens sin fabricar datos
        if total_tokens is not None and isinstance(total_tokens, int) and not isinstance(total_tokens, bool) and total_tokens >= 0:
            calc_total: int | None = total_tokens
        elif valid_in is not None and valid_out is not None:
            calc_total = valid_in + valid_out
        else:
            calc_total = None

        # Cálculo de costo mediante módulo unificado de pricing
        cost = calculate_llm_cost(safe_model, valid_in, valid_out)

        record = TokenCostRecord(
            interview_id=clean_iid,
            model=safe_model,
            input_tokens=valid_in,
            output_tokens=valid_out,
            total_tokens=calc_total,
            estimated_cost=cost,
            timestamp=time.time(),
        )

        if clean_iid not in self._records:
            self._records[clean_iid] = []
        self._records[clean_iid].append(record)

        # Emisión de log estructurado Anti-Leak
        in_str = str(valid_in) if valid_in is not None else "none"
        out_str = str(valid_out) if valid_out is not None else "none"
        tot_str = str(calc_total) if calc_total is not None else "none"
        cost_str = f"{cost:.6f}" if cost is not None else "none"

        msg = (
            f"[METRICS:INTERVIEW_COST] interview_id={_sanitize_value(clean_iid)} "
            f"model={_sanitize_value(safe_model)} "
            f"input_tokens={in_str} "
            f"output_tokens={out_str} "
            f"total_tokens={tot_str} "
            f"estimated_cost={cost_str}"
        )
        logger.info(msg)
        return record

    def get_summary(self, interview_id: Any) -> InterviewCostSummary:
        """Calcula el resumen agregado de tokens y costo para una entrevista.

        Si para alguna llamada el costo es desconocido (None), el costo total se
        reporta deterministamente como None para evitar emitir costos parciales
        engañosos en la auditoría.
        """
        clean_iid = str(interview_id) if interview_id is not None else "unknown"
        records = self._records.get(clean_iid, [])

        if not records:
            return InterviewCostSummary(
                interview_id=clean_iid,
                total_input_tokens=0,
                total_output_tokens=0,
                total_tokens=0,
                total_estimated_cost=0.0,
                call_count=0,
                models=[],
            )

        sum_in = 0
        sum_out = 0
        sum_total = 0
        sum_cost = 0.0
        has_unknown_tokens = False
        has_unknown_cost = False
        models: set[str] = set()

        for r in records:
            models.add(r.model)
            if r.input_tokens is not None:
                sum_in += r.input_tokens
            else:
                has_unknown_tokens = True

            if r.output_tokens is not None:
                sum_out += r.output_tokens
            else:
                has_unknown_tokens = True

            if r.total_tokens is not None:
                sum_total += r.total_tokens
            else:
                has_unknown_tokens = True

            if r.estimated_cost is not None:
                sum_cost += r.estimated_cost
            else:
                has_unknown_cost = True

        total_cost = None if has_unknown_cost else round(sum_cost, 6)
        tot_in = None if has_unknown_tokens and sum_in == 0 else sum_in
        tot_out = None if has_unknown_tokens and sum_out == 0 else sum_out
        tot_tokens = None if has_unknown_tokens and sum_total == 0 else sum_total

        return InterviewCostSummary(
            interview_id=clean_iid,
            total_input_tokens=tot_in,
            total_output_tokens=tot_out,
            total_tokens=tot_tokens,
            total_estimated_cost=total_cost,
            call_count=len(records),
            models=sorted(models),
        )

    def clear(self) -> None:
        """Limpia todos los registros acumulados en memoria."""
        self._records.clear()


# Instancia única del tracker de costos
interview_cost_tracker = InterviewCostTracker()


def record_interview_cost(
    interview_id: Any,
    model: str | None,
    input_tokens: int | None,
    output_tokens: int | None,
    total_tokens: int | None = None,
) -> TokenCostRecord:
    """Helper global para registrar el costo y consumo de tokens de una entrevista."""
    return interview_cost_tracker.record_call(
        interview_id=interview_id,
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
    )


def get_interview_cost_summary(interview_id: Any) -> InterviewCostSummary:
    """Helper global para obtener el resumen agregado de costos de una entrevista."""
    return interview_cost_tracker.get_summary(interview_id)


# -----------------------------------------------------------------------------
# 3. Herramientas del Agente (Lifecycle)
# -----------------------------------------------------------------------------

class ToolCallTelemetry:
    """Rastreador de ciclo de vida de invocación de una herramienta."""

    def __init__(self, tool: str, operation: str) -> None:
        self.tool = tool
        self.operation = operation
        self._start_time: float | None = None
        self._completed = False

    def start(self, **kwargs: Any) -> None:
        """Emite el evento de inicio [AGENT_TOOL_CALL:START]."""
        self._start_time = time.perf_counter()
        params = [f"tool={self.tool}", f"operation={self.operation}"]
        for k, v in kwargs.items():
            params.append(f"{k}={_sanitize_value(v)}")
        msg = f"[AGENT_TOOL_CALL:START] {' '.join(params)}"
        logger.info(msg)

    def success(self, **kwargs: Any) -> None:
        """Emite el evento de éxito [AGENT_TOOL_CALL:SUCCESS] y valida latencia."""
        if self._completed:
            return
        self._completed = True
        duration_ms = self._calc_duration_ms()
        params = [f"tool={self.tool}", f"operation={self.operation}"]
        for k, v in kwargs.items():
            params.append(f"{k}={_sanitize_value(v)}")
        if duration_ms is not None:
            params.append(f"duration_ms={duration_ms}")
        msg = f"[AGENT_TOOL_CALL:SUCCESS] {' '.join(params)}"
        logger.info(msg)

        # Alerta de latencia automática si supera el umbral de la herramienta
        if duration_ms is not None:
            threshold = get_latency_threshold(self.tool)
            if duration_ms > threshold:
                alert_msg = (
                    f"[ALERT:HIGH_LATENCY] operation={self.tool}.{self.operation} "
                    f"duration_ms={float(duration_ms):.2f} "
                    f"threshold_ms={threshold:.2f} "
                    f"interview_id={_sanitize_value(kwargs.get('interview_id'))}"
                )
                logger.warning(alert_msg)

    def error(self, error: Exception | str, **kwargs: Any) -> None:
        """Emite el evento de error [AGENT_TOOL_CALL:ERROR] y valida latencia."""
        if self._completed:
            return
        self._completed = True
        duration_ms = self._calc_duration_ms()
        err_msg = str(error)
        params = [
            f"tool={self.tool}",
            f"operation={self.operation}",
            f"error={_sanitize_value(err_msg)}",
        ]
        for k, v in kwargs.items():
            params.append(f"{k}={_sanitize_value(v)}")
        if duration_ms is not None:
            params.append(f"duration_ms={duration_ms}")
        msg = f"[AGENT_TOOL_CALL:ERROR] {' '.join(params)}"
        logger.error(msg)

        # Alerta de latencia automática si supera el umbral de la herramienta
        if duration_ms is not None:
            threshold = get_latency_threshold(self.tool)
            if duration_ms > threshold:
                alert_msg = (
                    f"[ALERT:HIGH_LATENCY] operation={self.tool}.{self.operation} "
                    f"duration_ms={float(duration_ms):.2f} "
                    f"threshold_ms={threshold:.2f} "
                    f"interview_id={_sanitize_value(kwargs.get('interview_id'))}"
                )
                logger.warning(alert_msg)

    def _calc_duration_ms(self) -> int | None:
        if self._start_time is None:
            return None
        return max(0, int((time.perf_counter() - self._start_time) * 1000))


def tool_telemetry(tool: str, operation: str) -> ToolCallTelemetry:
    """Factory helper para instanciar el rastreador de telemetría."""
    return ToolCallTelemetry(tool, operation)
