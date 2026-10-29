"""Tests para observabilidad, métricas de costos de tokens por entrevista,

alertas de latencia y protección estricta Anti-Leak (S-26).
"""

import asyncio
import logging
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import ScalarResult

from src.agent.service import InterviewAgent
from src.core.config import settings
from src.core.telemetry import (
    _sanitize_value,
    async_measure_latency,
    get_interview_cost_summary,
    get_latency_threshold,
    interview_cost_tracker,
    measure_latency,
    record_interview_cost,
    record_latency,
    tool_telemetry,
)
from src.db.enums import Difficulty, InterviewPhase
from src.db.models import Interview, Problem, Vacancy
from src.interview.service import InterviewService
from src.llm.types import ChatCompletion, TokenUsage
from src.problems.selector import ProblemSelector
from src.ws.manager import MessageDispatcher


@pytest.fixture(autouse=True)
def reset_cost_tracker():
    """Limpia el estado del tracker de costos antes y después de cada prueba."""
    interview_cost_tracker.clear()
    yield
    interview_cost_tracker.clear()


@pytest.fixture
def telemetry_caplog(caplog: pytest.LogCaptureFixture):
    """Captura logs del canal agent.telemetry a nivel INFO."""
    caplog.set_level(logging.INFO, logger="agent.telemetry")
    return caplog


# -----------------------------------------------------------------------------
# 1. Tests de Métricas de Costo y Tokens por Entrevista
# -----------------------------------------------------------------------------

def test_record_interview_cost_calculates_correct_pricing(telemetry_caplog):
    """Verifica el cálculo determinista del costo con tarifas soportadas (grok-4.6)."""
    interview_id = str(uuid.uuid4())
    # grok-4.6: $5.00 prompt / $15.00 completion por millón
    # 10,000 prompt tokens -> $0.05
    # 2,000 completion tokens -> $0.03
    # Total esperado: $0.08
    record = record_interview_cost(
        interview_id=interview_id,
        model="grok-4.6",
        input_tokens=10_000,
        output_tokens=2_000,
    )

    assert record.interview_id == interview_id
    assert record.model == "grok-4.6"
    assert record.input_tokens == 10_000
    assert record.output_tokens == 2_000
    assert record.total_tokens == 12_000
    assert record.estimated_cost == 0.08

    # Verificar log estructurado
    logs = [r.message for r in telemetry_caplog.records if "[METRICS:INTERVIEW_COST]" in r.message]
    assert len(logs) == 1
    log_msg = logs[0]
    assert f"interview_id={interview_id}" in log_msg
    assert "model=grok-4.6" in log_msg
    assert "input_tokens=10000" in log_msg
    assert "output_tokens=2000" in log_msg
    assert "total_tokens=12000" in log_msg
    assert "estimated_cost=0.080000" in log_msg


def test_record_interview_cost_accumulation_across_calls(telemetry_caplog):
    """Verifica la agregación de múltiples llamadas para una misma entrevista."""
    interview_id = str(uuid.uuid4())

    # Llamada 1 (grok-4.6)
    record_interview_cost(
        interview_id=interview_id,
        model="grok-4.6",
        input_tokens=5_000,
        output_tokens=1_000,
    )
    # Llamada 2 (gpt-4o-mini: $0.15 / $0.60 por millón)
    # 20,000 prompt -> $0.003
    # 5,000 completion -> $0.003
    # Costo llamada 2 = $0.006
    record_interview_cost(
        interview_id=interview_id,
        model="gpt-4o-mini",
        input_tokens=20_000,
        output_tokens=5_000,
    )

    summary = get_interview_cost_summary(interview_id)
    assert summary.call_count == 2
    assert summary.total_input_tokens == 25_000
    assert summary.total_output_tokens == 6_000
    assert summary.total_tokens == 31_000
    # Costo 1: (5000*5 + 1000*15)/1e6 = 0.04
    # Costo 2: (20000*0.15 + 5000*0.60)/1e6 = 0.006
    # Total: 0.046
    assert summary.total_estimated_cost == pytest.approx(0.046, rel=1e-5)
    assert summary.models == ["gpt-4o-mini", "grok-4.6"]


def test_record_interview_cost_missing_or_unknown_model_preserves_none(telemetry_caplog):
    """Si el modelo no tiene tarifa oficial o faltan tokens, el costo es None sin fabricar datos."""
    interview_id = str(uuid.uuid4())

    # Modelo desconocido
    record_unknown = record_interview_cost(
        interview_id=interview_id,
        model="unsupported-exotic-model",
        input_tokens=1_000,
        output_tokens=500,
    )
    assert record_unknown.estimated_cost is None
    assert record_unknown.total_tokens == 1500

    # Tokens faltantes (None)
    record_none_tokens = record_interview_cost(
        interview_id=interview_id,
        model="grok-4.6",
        input_tokens=None,
        output_tokens=None,
    )
    assert record_none_tokens.estimated_cost is None
    assert record_none_tokens.total_tokens is None

    # Resumen refleja None si algún componente no pudo auditarse
    summary = get_interview_cost_summary(interview_id)
    assert summary.total_estimated_cost is None
    assert summary.call_count == 2


def test_record_interview_cost_invalid_inputs_handled_safely():
    """Valores inválidos (booleanos, strings, negativos) no provocan crash ni datos falsos."""
    interview_id = "test-inv-safe"
    record = record_interview_cost(
        interview_id=interview_id,
        model="grok-4.6",
        input_tokens=True,  # type: ignore[arg-type]
        output_tokens=-10,
    )
    assert record.input_tokens is None
    assert record.output_tokens is None
    assert record.total_tokens is None
    assert record.estimated_cost is None


# -----------------------------------------------------------------------------
# 2. Tests de Latencia y Alertas
# -----------------------------------------------------------------------------

def test_latency_recording_below_threshold_emits_metric(telemetry_caplog):
    """Una operación debajo del umbral emite METRICS:LATENCY y no genera alerta."""
    alert = record_latency(
        operation="llm_agent_complete",
        duration_ms=1200.0,
        interview_id="inv-latency-1",
        threshold_ms=5000.0,
    )
    assert alert is False

    metric_logs = [r.message for r in telemetry_caplog.records if "[METRICS:LATENCY]" in r.message]
    alert_logs = [r.message for r in telemetry_caplog.records if "[ALERT:HIGH_LATENCY]" in r.message]

    assert len(metric_logs) == 1
    assert len(alert_logs) == 0
    assert "operation=llm_agent_complete" in metric_logs[0]
    assert "duration_ms=1200.00" in metric_logs[0]
    assert "threshold_ms=5000.00" in metric_logs[0]
    assert "interview_id=inv-latency-1" in metric_logs[0]


def test_latency_recording_above_threshold_emits_alert(telemetry_caplog):
    """Una operación que supera el umbral emite ALERT:HIGH_LATENCY."""
    alert = record_latency(
        operation="llm_agent_complete",
        duration_ms=7500.5,
        interview_id="inv-latency-2",
        threshold_ms=5000.0,
    )
    assert alert is True

    alert_logs = [r.message for r in telemetry_caplog.records if "[ALERT:HIGH_LATENCY]" in r.message]
    assert len(alert_logs) == 1
    assert "operation=llm_agent_complete" in alert_logs[0]
    assert "duration_ms=7500.50" in alert_logs[0]
    assert "threshold_ms=5000.00" in alert_logs[0]
    assert "interview_id=inv-latency-2" in alert_logs[0]


def test_latency_threshold_resolution_by_operation_type():
    """Verifica resolución automática de umbrales según tipo de operación."""
    # LLM usa settings.LLM_LATENCY_ALERT_MS (default 5000)
    assert get_latency_threshold("llm_stream") == settings.LLM_LATENCY_ALERT_MS
    # Sandbox usa settings.SANDBOX_LATENCY_ALERT_MS (default 3000)
    assert get_latency_threshold("sandbox_execution") == settings.SANDBOX_LATENCY_ALERT_MS
    assert get_latency_threshold("code_exec") == settings.SANDBOX_LATENCY_ALERT_MS
    # WebSocket usa settings.WEBSOCKET_LATENCY_ALERT_MS (default 1000)
    assert get_latency_threshold("websocket_process") == settings.WEBSOCKET_LATENCY_ALERT_MS
    assert get_latency_threshold("ws_event") == settings.WEBSOCKET_LATENCY_ALERT_MS


def test_measure_latency_context_manager(telemetry_caplog):
    """Verifica context manager sincrónico de latencia."""
    with measure_latency("test_sync_op", interview_id="inv-ctx", threshold_ms=100.0) as ctx:
        # Simular trabajo
        pass

    assert "duration_ms" in ctx
    assert "alert_triggered" in ctx
    assert ctx["duration_ms"] >= 0


@pytest.mark.asyncio
async def test_async_measure_latency_context_manager(telemetry_caplog):
    """Verifica context manager asíncrono de latencia."""
    async with async_measure_latency("test_async_op", interview_id="inv-actx", threshold_ms=100.0) as ctx:
        await asyncio.sleep(0.01)

    assert "duration_ms" in ctx
    assert ctx["duration_ms"] >= 10.0


def test_tool_telemetry_triggers_latency_alert(telemetry_caplog):
    """ToolCallTelemetry emite alerta de latencia si la herramienta supera su umbral."""
    tel = tool_telemetry("code_execution_sandbox", "execute_code")
    tel.start()
    # Modificar start_time artificialmente para simular lentitud (> 3000ms sandbox threshold)
    tel._start_time = (tel._start_time or 0) - 4.5
    tel.success(interview_id="inv-tool-slow")

    alert_logs = [r.message for r in telemetry_caplog.records if "[ALERT:HIGH_LATENCY]" in r.message]
    assert len(alert_logs) == 1
    assert "operation=code_execution_sandbox.execute_code" in alert_logs[0]
    assert "interview_id=inv-tool-slow" in alert_logs[0]


# -----------------------------------------------------------------------------
# 3. Tests Estrictos Anti-Leak
# -----------------------------------------------------------------------------

def test_anti_leak_sanitizer_redacts_credentials_tokens_and_pii(telemetry_caplog):
    """Garantiza que nunca se emitan credenciales, JWT, emails ni API keys en logs."""
    record_interview_cost(
        interview_id="inv-clean-1",
        model="grok-4.6",
        input_tokens=100,
        output_tokens=50,
    )

    # Inyección de datos sensibles a través de parámetros
    record_latency(
        operation="llm_leak_test",
        duration_ms=6000.0,
        interview_id="candidato.secreto@empresa.com",
        threshold_ms=5000.0,
    )

    raw_jwt = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.abc"
    raw_api_key = "sk-1234567890abcdef1234567890"

    sanitized_jwt = _sanitize_value(f"token={raw_jwt}")
    sanitized_key = _sanitize_value(f"api_key={raw_api_key}")
    sanitized_email = _sanitize_value("juan.perez@example.org")

    assert raw_jwt not in sanitized_jwt
    assert raw_api_key not in sanitized_key
    assert "juan.perez@example.org" not in sanitized_email
    assert "[REDACTED]" in sanitized_jwt
    assert "[REDACTED]" in sanitized_key
    assert "[REDACTED]" in sanitized_email

    # Verificar que en los registros de log capturados no exista PII
    all_logs = " ".join(r.message for r in telemetry_caplog.records)
    assert "candidato.secreto@empresa.com" not in all_logs
    assert "[REDACTED]" in all_logs


def test_anti_leak_prohibits_full_prompts_and_candidate_code(telemetry_caplog):
    """Verifica que el sanitizador trunque y neutralice prompts y código extensos."""
    multiline_code = (
        "def solution(arr):\n"
        "    # Candidato code here\n"
        "    secret_algorithm = [x * 2 for x in arr]\n"
        "    return secret_algorithm\n"
    )
    long_prompt = "Instrucción de evaluación secreta " * 10

    sanitized_code = _sanitize_value(multiline_code)
    sanitized_prompt = _sanitize_value(long_prompt)

    # No debe contener saltos de línea ni código completo
    assert "\n" not in sanitized_code
    assert "\n" not in sanitized_prompt
    assert len(sanitized_code) <= 60
    assert len(sanitized_prompt) <= 60


# -----------------------------------------------------------------------------
# 4. Tests de Integración Conversacional (F-S26-01)
# -----------------------------------------------------------------------------

@pytest.fixture
def agent_test_setup():
    """Configura un InterviewAgent con mocks para pruebas de turnos conversacionales."""
    session = AsyncMock()
    mock_scalar = MagicMock(spec=ScalarResult)
    mock_scalar.all.return_value = []
    session.scalars.return_value = mock_scalar
    session.flush = AsyncMock()
    session.add = MagicMock()

    interview_id = uuid.uuid4()
    vacancy_id = uuid.uuid4()
    problem_id = uuid.uuid4()

    interview = Interview(
        id=interview_id,
        vacancy_id=vacancy_id,
        problem_id=problem_id,
        candidate_name="Test Dev",
        candidate_email="test.dev@example.com",
        phase=InterviewPhase.CODING,
    )
    vacancy = Vacancy(id=vacancy_id, title="Backend Developer", raw_description="Backend Dev Role")
    problem = Problem(
        id=problem_id,
        title="Test Problem",
        scenario_preview="Solve this",
        difficulty=Difficulty.JUNIOR,
        language="python",
    )

    session.get = AsyncMock(side_effect=[interview, vacancy, problem])

    mock_llm = AsyncMock()
    mock_interview_service = MagicMock(spec=InterviewService)
    mock_problem_selector = MagicMock(spec=ProblemSelector)

    agent = InterviewAgent(session, mock_interview_service, mock_problem_selector, llm_client=mock_llm)
    return agent, mock_llm, interview_id


@pytest.mark.asyncio
async def test_conversational_turn_records_interview_cost(agent_test_setup, telemetry_caplog):
    """Caso 1: Un turno conversacional con prompt y completion tokens registra el coste."""
    agent, mock_llm, interview_id = agent_test_setup

    # 10,000 prompt, 2,000 completion en grok-4.6 -> $0.08
    mock_llm.complete.return_value = ChatCompletion(
        content="Respuesta del asistente",
        model="grok-4.6",
        usage=TokenUsage(prompt_tokens=10_000, completion_tokens=2_000, total_tokens=12_000),
    )

    chunks = []
    async for chunk in agent.stream_response(interview_id, "Hola, tengo una pregunta"):
        chunks.append(chunk)

    assert "".join(chunks) == "Respuesta del asistente"

    summary = get_interview_cost_summary(interview_id)
    assert summary.call_count == 1
    assert summary.total_input_tokens == 10_000
    assert summary.total_output_tokens == 2_000
    assert summary.total_tokens == 12_000
    assert summary.total_estimated_cost == 0.08
    assert summary.models == ["grok-4.6"]

    # Verificar emisión estructurada en telemetría
    cost_logs = [r.message for r in telemetry_caplog.records if "[METRICS:INTERVIEW_COST]" in r.message]
    assert len(cost_logs) == 1
    assert f"interview_id={interview_id}" in cost_logs[0]
    assert "input_tokens=10000" in cost_logs[0]
    assert "output_tokens=2000" in cost_logs[0]
    assert "estimated_cost=0.080000" in cost_logs[0]


@pytest.mark.asyncio
async def test_conversational_turn_multiple_calls_accumulates_correctly(agent_test_setup):
    """Caso 2: Múltiples turnos para una misma entrevista acumulan correctamente tokens y costes."""
    agent, mock_llm, interview_id = agent_test_setup

    # Turno 1
    mock_llm.complete.return_value = ChatCompletion(
        content="Respuesta 1",
        model="grok-4.6",
        usage=TokenUsage(prompt_tokens=5_000, completion_tokens=1_000, total_tokens=6_000),
    )
    async for _ in agent.stream_response(interview_id, "Mensaje 1"):
        pass

    # Turno 2 (reconfigurar side_effect de get para las entidades)
    agent._session.get = AsyncMock(side_effect=[
        Interview(id=interview_id, vacancy_id=uuid.uuid4(), problem_id=uuid.uuid4(), phase=InterviewPhase.CODING),
        Vacancy(title="Backend Dev"),
        Problem(title="Test Prob", scenario_preview="Preview", difficulty=Difficulty.JUNIOR, language="python"),
    ])
    mock_llm.complete.return_value = ChatCompletion(
        content="Respuesta 2",
        model="grok-4.6",
        usage=TokenUsage(prompt_tokens=8_000, completion_tokens=1_500, total_tokens=9_500),
    )
    async for _ in agent.stream_response(interview_id, "Mensaje 2"):
        pass

    summary = get_interview_cost_summary(interview_id)
    assert summary.call_count == 2
    assert summary.total_input_tokens == 13_000
    assert summary.total_output_tokens == 2_500
    assert summary.total_tokens == 15_500
    # Costo 1 = (5000*5 + 1000*15)/1e6 = 0.04
    # Costo 2 = (8000*5 + 1500*15)/1e6 = 0.0625
    # Total = 0.1025
    assert summary.total_estimated_cost == pytest.approx(0.1025, rel=1e-5)


@pytest.mark.asyncio
async def test_conversational_turn_missing_usage_preserves_none(agent_test_setup):
    """Caso 3: Proveedor sin datos de usage no genera métricas inventadas."""
    agent, mock_llm, interview_id = agent_test_setup

    mock_llm.complete.return_value = ChatCompletion(
        content="Respuesta sin usage",
        model="grok-4.6",
        usage=TokenUsage(),  # prompt_tokens y completion_tokens son None
    )
    async for _ in agent.stream_response(interview_id, "Mensaje"):
        pass

    summary = get_interview_cost_summary(interview_id)
    assert summary.call_count == 1
    assert summary.total_input_tokens is None
    assert summary.total_output_tokens is None
    assert summary.total_tokens is None
    assert summary.total_estimated_cost is None


@pytest.mark.asyncio
async def test_conversational_turn_unknown_model_preserves_none_cost(agent_test_setup):
    """Caso 4: Modelo no registrado en pricing mantiene coste None pero preserva tokens."""
    agent, mock_llm, interview_id = agent_test_setup

    mock_llm.complete.return_value = ChatCompletion(
        content="Respuesta modelo desconocido",
        model="exotic-llm-v1",
        usage=TokenUsage(prompt_tokens=1_000, completion_tokens=500, total_tokens=1_500),
    )
    async for _ in agent.stream_response(interview_id, "Mensaje"):
        pass

    summary = get_interview_cost_summary(interview_id)
    assert summary.call_count == 1
    assert summary.total_input_tokens == 1_000
    assert summary.total_output_tokens == 500
    assert summary.total_tokens == 1_500
    assert summary.total_estimated_cost is None


@pytest.mark.asyncio
async def test_conversational_turn_anti_leak_no_candidate_code_or_prompt_in_logs(agent_test_setup, telemetry_caplog):
    """Caso 5: No se registran prompts, respuestas completas ni código del candidato en telemetría."""
    agent, mock_llm, interview_id = agent_test_setup

    sensitive_code = "def secreto_candidato(): return 'CLAVE_SUPER_SECRETA_XYZ'"
    mock_llm.complete.return_value = ChatCompletion(
        content="Respuesta con análisis seguro",
        model="grok-4.6",
        usage=TokenUsage(prompt_tokens=500, completion_tokens=100, total_tokens=600),
    )

    async for _ in agent.stream_response(interview_id, f"Mira mi código: {sensitive_code}"):
        pass

    all_logs = " ".join(r.message for r in telemetry_caplog.records)
    assert "CLAVE_SUPER_SECRETA_XYZ" not in all_logs
    assert "secreto_candidato" not in all_logs
    assert "Respuesta con análisis seguro" not in all_logs


# -----------------------------------------------------------------------------
# 5. Tests de Latencia de Dispatch WebSocket (F-S26-02)
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_websocket_dispatch_normal_latency_metric(telemetry_caplog):
    """Prueba que el dispatch de un evento WebSocket bajo el umbral emite METRICS:LATENCY."""
    manager = AsyncMock()
    interview_service = MagicMock()
    agent = AsyncMock()
    exec_service = AsyncMock()
    dispatcher = MessageDispatcher(manager, interview_service, agent, exec_service)

    interview_id = uuid.uuid4()
    await dispatcher.dispatch(interview_id, {"type": "ping", "client_timestamp": 123456})

    logs = [r.message for r in telemetry_caplog.records if "[METRICS:LATENCY]" in r.message]
    assert len(logs) >= 1
    assert "operation=websocket_ping" in logs[0]
    assert f"interview_id={interview_id}" in logs[0]
    assert "threshold_ms=1000.00" in logs[0]


@pytest.mark.asyncio
async def test_websocket_dispatch_low_latency_no_alert(telemetry_caplog):
    """Prueba que el dispatch normal no genera falsas alertas de latencia."""
    manager = AsyncMock()
    interview_service = MagicMock()
    agent = AsyncMock()
    exec_service = AsyncMock()
    dispatcher = MessageDispatcher(manager, interview_service, agent, exec_service)

    interview_id = uuid.uuid4()
    await dispatcher.dispatch(interview_id, {"type": "ping", "client_timestamp": 123456})

    alerts = [r.message for r in telemetry_caplog.records if "[ALERT:HIGH_LATENCY]" in r.message]
    assert len(alerts) == 0


@pytest.mark.asyncio
async def test_websocket_dispatch_high_latency_alert(telemetry_caplog, monkeypatch):
    """Prueba que el dispatch de un evento WebSocket que supera 1000ms emite ALERT:HIGH_LATENCY."""
    manager = AsyncMock()
    interview_service = MagicMock()
    agent = AsyncMock()
    exec_service = AsyncMock()
    dispatcher = MessageDispatcher(manager, interview_service, agent, exec_service)

    interview_id = uuid.uuid4()

    # Simular retardo superior al umbral de 1000ms mediante mock determinista
    clock_values = [100.0, 101.5]
    monkeypatch.setattr("src.core.telemetry.time.perf_counter", lambda: clock_values.pop(0) if clock_values else 200.0)

    await dispatcher.dispatch(interview_id, {"type": "ping", "client_timestamp": 123456})

    alerts = [r.message for r in telemetry_caplog.records if "[ALERT:HIGH_LATENCY]" in r.message]
    assert len(alerts) >= 1
    assert "operation=websocket_ping" in alerts[0]
    assert f"interview_id={interview_id}" in alerts[0]
    assert "threshold_ms=1000.00" in alerts[0]
    assert "duration_ms=1500.00" in alerts[0]


@pytest.mark.asyncio
async def test_websocket_dispatch_anti_leak_no_sensitive_payload_in_logs(telemetry_caplog):
    """Prueba que los mensajes WebSocket con código o tokens no filtran contenido en telemetría."""
    manager = AsyncMock()
    interview_service = MagicMock()
    agent = AsyncMock()
    exec_service = AsyncMock()
    dispatcher = MessageDispatcher(manager, interview_service, agent, exec_service)

    interview_id = uuid.uuid4()
    secret_code = "def secreto_super_confidencial(): pass"
    await dispatcher.dispatch(interview_id, {
        "type": "run_code",
        "code": secret_code,
        "language": "python",
    })

    all_logs = " ".join(r.message for r in telemetry_caplog.records)
    assert "secreto_super_confidencial" not in all_logs
    assert "def " not in all_logs
    assert "operation=websocket_run_code" in all_logs
