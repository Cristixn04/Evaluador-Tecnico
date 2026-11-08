"""Pruebas offline exhaustivas para auditoría del incidente y recuperación de la corrida oficial S4.

Cubre:
1. Configuración de timeout de lectura de 90 segundos.
2. ReadTimeout clasificado como incierto sin auto-retry.
3. Conservación de pasivos inciertos tras reinicio.
4. Recuperación del circuit breaker mediante --resume (transición segura a PROBING).
5. Reanudación sin duplicar tareas completadas.
6. Límite estricto de presupuesto de $35.00 USD en CLI y watchdog.
7. Bloqueo por exposición superior al presupuesto.
8. Judge0 con soporte robusto de caracteres UTF-8 arbitrarios (base64).
9. Semántica de consistencia de tokens (prompt, completion, total con reasoning).
10. Persistencia y exportación de bitácoras.
"""

from __future__ import annotations

import base64
import uuid
from typing import Any

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.core.config import Settings, settings
from src.db.models.s4 import S4RunStatus, S4TaskStatus
from src.evaluation.pricing import calculate_llm_cost
from src.llm.exceptions import LLMTimeoutError
from src.llm.factory import create_llm_client
from src.llm.openai_compatible import OpenAICompatibleClient
from src.llm.types import ChatMessage
from src.s4.exporter import S4Exporter
from src.s4.service import S4Service
from src.s4.watchdog import S4CircuitState, S4Watchdog
from src.sandbox.judge0 import Judge0Adapter
from src.sandbox.types import ExecutionStatus, RunRequest


@pytest.fixture
def session_factory() -> async_sessionmaker[AsyncSession]:
    engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)
    return async_sessionmaker(engine, expire_on_commit=False)


# =============================================================================
# 1. TIMEOUT DE LECTURA DE 90 SEGUNDOS
# =============================================================================

def test_llm_factory_and_client_configured_with_90s_timeout() -> None:
    """1.1 Verifica que el cliente OpenAICompatibleClient hereda y configura 90s de timeout de lectura."""
    custom_settings = Settings(
        LLM_API_KEY="test-key",
        LLM_BASE_URL="https://api.reto.pltk.mx/v1",
        LLM_MODEL="grok-4.6",
        LLM_TIMEOUT_SECONDS=90.0,
        USE_MOCK_LLM=False,
    )
    client = create_llm_client(custom_settings)
    assert isinstance(client, OpenAICompatibleClient)
    assert client._timeout == 90.0
    # Inspeccionar timeouts configurados en httpx.AsyncClient interno
    assert client._client.timeout.read == 90.0
    assert client._client.timeout.connect == 10.0
    assert client._client.timeout.write == 10.0
    assert client._client.timeout.pool == 5.0


# =============================================================================
# 2. READTIMEOUT INCIERTO SIN AUTO-RETRY
# =============================================================================

@pytest.mark.asyncio
async def test_read_timeout_raises_uncertain_without_retry() -> None:
    """2.1 Un ReadTimeout tras enviar el payload eleva LLMTimeoutError incierto con exactamente 1 intento HTTP."""
    request_count = 0

    def mock_handler(request: httpx.Request) -> httpx.Response:
        nonlocal request_count
        request_count += 1
        raise httpx.ReadTimeout("Read timed out after 90.0s", request=request)

    transport = httpx.MockTransport(mock_handler)
    http_client = httpx.AsyncClient(transport=transport)
    client = OpenAICompatibleClient(
        api_key="test-key",
        base_url="https://api.reto.pltk.mx/v1",
        model="grok-4.6",
        timeout_seconds=90.0,
        max_retries=3,  # Aun con max_retries=3, ReadTimeout NO debe reintentarse
        client=http_client,
    )

    with pytest.raises(LLMTimeoutError) as exc_info:
        await client.complete(messages=[ChatMessage(role="user", content="Ping")])

    assert exc_info.value.is_uncertain is True
    assert "payload already sent; billing uncertain" in str(exc_info.value)
    # Probar que NO se reintentó
    assert request_count == 1
    await http_client.aclose()


# =============================================================================
# 3. CONSERVACIÓN DE PASIVOS TRAS REINICIO
# =============================================================================

def test_watchdog_preserves_uncertain_liabilities_on_restart() -> None:
    """3.1 El watchdog conserva intactos los pasivos inciertos de PostgreSQL ($1.10 USD)."""
    meta: dict[str, Any] = {
        "uncertain_liabilities_usd": 1.10,
        "watchdog_tripped": True,
        "circuit_state": "permanent_trip",
        "watchdog_trip_reason": "Circuit breaker permanent failure: probe failed after 3 cooldown cycles.",
    }
    watchdog = S4Watchdog(budget_limit_usd=35.0)
    watchdog.rehydrate_circuit_state(meta, is_manual_resume=True)

    assert watchdog.uncertain_liabilities_usd == 1.10
    assert watchdog.total_exposure_usd(current_cost_usd=0.10062) == 1.20062


# =============================================================================
# 4. RECUPERACIÓN MANUAL DEL CIRCUIT BREAKER
# =============================================================================

def test_watchdog_manual_resume_transitions_to_probing_when_not_budget_trip() -> None:
    """4.1 La reanudación manual (--resume) transiciona de permanent_trip a PROBING si la causa no fue presupuesto."""
    meta: dict[str, Any] = {
        "uncertain_liabilities_usd": 1.10,
        "watchdog_tripped": True,
        "circuit_state": "permanent_trip",
        "circuit_cooldown_cycles": 3,
        "watchdog_trip_reason": "Circuit breaker permanent failure: probe failed after 3 cooldown cycles. Last error: LLM read timed out after 30.0s",
    }
    watchdog = S4Watchdog(budget_limit_usd=35.0)
    # Reanudación manual del operador
    watchdog.rehydrate_circuit_state(meta, is_manual_resume=True)

    assert watchdog.circuit_state == S4CircuitState.PROBING
    assert watchdog.is_permanent_trip is False
    assert watchdog.cooldown_cycles == 0
    assert watchdog._consecutive_failures == 0


def test_watchdog_manual_resume_retains_permanent_trip_if_budget_exhausted() -> None:
    """4.2 Si la causa fue presupuesto o el presupuesto está excedido, mantiene permanent_trip."""
    meta: dict[str, Any] = {
        "uncertain_liabilities_usd": 36.00,
        "watchdog_tripped": True,
        "circuit_state": "permanent_trip",
        "watchdog_trip_reason": "Presupuesto de corrida agotado: $36.00 >= $35.00 USD",
    }
    watchdog = S4Watchdog(budget_limit_usd=35.0)
    watchdog.rehydrate_circuit_state(meta, is_manual_resume=True)

    assert watchdog.circuit_state == S4CircuitState.PERMANENT_TRIP
    assert watchdog.is_permanent_trip is True


# =============================================================================
# 5. REANUDACIÓN SIN DUPLICAR TAREAS
# =============================================================================

@pytest.mark.asyncio
async def test_resumed_run_does_not_duplicate_completed_tasks(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """5.1 Al reanudar, las tareas SUCCEEDED existentes se preservan y el reclamo toma solo tareas en QUEUED."""
    run_id = uuid.uuid4()
    async with session_factory() as session, session.begin():
        srv = S4Service(session)
        run = await srv.create_load_run(run_id=run_id, target_tasks=5, budget_limit_usd=35.0)
        await srv.start_load_run(run.id)

        # Crear 3 tareas: tarea 1 exitosa, tarea 2 fallida, tarea 3 encolada
        t1 = await srv.create_task_execution(run_id=run_id, task_number=1, input_payload={"task": 1})
        t1.status = S4TaskStatus.RUNNING.value
        await srv.complete_task_execution(t1.id, validation_passed=True, result_summary="Optimal")

        t2 = await srv.create_task_execution(run_id=run_id, task_number=2, input_payload={"task": 2})
        t2.status = S4TaskStatus.RUNNING.value
        await srv.complete_task_execution(t2.id, validation_passed=False, result_summary="Failed")

        await srv.create_task_execution(run_id=run_id, task_number=3, input_payload={"task": 3})

        # Pausar corrida
        await srv.pause_load_run(run_id)

    # Reanudar corrida
    async with session_factory() as session, session.begin():
        srv = S4Service(session)
        resumed_run = await srv.start_load_run(run_id)
        assert resumed_run.status == S4RunStatus.ACTIVE.value
        assert resumed_run.completed_tasks == 1
        assert resumed_run.failed_tasks == 1

        # Reclamar siguiente tarea
        claimed = await srv.claim_next_task(run_id, worker_id="worker-test")
        assert claimed is not None
        assert claimed.task_number == 3


# =============================================================================
# 6 y 7. LÍMITE DE PRESUPUESTO DE $35 Y BLOQUEO POR EXPOSICIÓN
# =============================================================================

def test_budget_limit_blocks_when_exposure_exceeds_35_usd() -> None:
    """6.1 y 7.1 El watchdog bloquea reservas cuando la exposición (coste + pasivos + reserva) supera $35.00 USD."""
    watchdog = S4Watchdog(budget_limit_usd=35.0, initial_uncertain_liabilities_usd=1.10)
    current_cost = 33.85

    # Reserva de $0.06 llevaría la exposición a: 33.85 + 1.10 + 0.06 = 35.01 > 35.00
    ok, msg = watchdog.reserve_cost(amount_usd=0.06, current_cost_usd=current_cost)
    assert ok is False
    assert "exceeds limit" in msg
    assert watchdog.is_permanent_trip is True


def test_budget_limit_allows_when_exposure_within_35_usd() -> None:
    """6.2 El watchdog permite reservas cuando la exposición total está estrictamente dentro de $35.00 USD."""
    watchdog = S4Watchdog(budget_limit_usd=35.0, initial_uncertain_liabilities_usd=1.10)
    current_cost = 0.10062

    # Reserva de $0.05: 0.10062 + 1.10 + 0.05 = 1.25062 <= 35.00
    ok, _ = watchdog.reserve_cost(amount_usd=0.05, current_cost_usd=current_cost)
    assert ok is True
    assert watchdog.is_permanent_trip is False


# =============================================================================
# 8. JUDGE0 CON CARACTERES UTF-8 ARBITRARIOS (BASE64)
# =============================================================================

@pytest.mark.asyncio
async def test_judge0_adapter_base64_handles_utf8_and_unicode_symbols() -> None:
    """8.1 Judge0Adapter codifica en base64 y decodifica caracteres UTF-8 como '…', tildes y símbolos."""
    captured_request = {}

    unicode_code = 'print("Código con tildes y elipsis: …")\n'
    raw_stdout_b64 = base64.b64encode("Resultado: éxito …\n".encode()).decode("ascii")
    raw_stderr_b64 = base64.b64encode("Advertencia: token=[RED…]\n".encode()).decode("ascii")

    async def mock_handler(request: httpx.Request) -> httpx.Response:
        import json
        if "submissions" in str(request.url) and "submissions/" not in str(request.url):
            assert "base64_encoded=true" in str(request.url)
            captured_request.update(json.loads(request.content.decode("utf-8")))
            return httpx.Response(200, json={"token": "tok-utf8-123"})
        else:
            assert "base64_encoded=true" in str(request.url)
            return httpx.Response(
                200,
                json={
                    "status": {"id": 3, "description": "Accepted"},
                    "stdout": raw_stdout_b64,
                    "stderr": raw_stderr_b64,
                    "compile_output": None,
                    "time": 0.05,
                    "memory": 12000,
                    "exit_code": 0,
                },
            )

    client = httpx.AsyncClient(transport=httpx.MockTransport(mock_handler))
    adapter = Judge0Adapter(base_url="http://localhost:2358", client=client, base64_encoded=True)

    res = await adapter.run(RunRequest(language="python", source=unicode_code))

    assert res.status == ExecutionStatus.ACCEPTED
    # El payload enviado debe ser base64 válido
    decoded_sent = base64.b64decode(captured_request["source_code"]).decode("utf-8")
    assert decoded_sent == unicode_code
    # Las salidas deben decodificarse correctamente preservando caracteres UTF-8
    assert res.stdout == "Resultado: éxito …\n"
    assert res.stderr == "Advertencia: token=[RED…]\n"

    await client.aclose()


# =============================================================================
# 9. CONSISTENCIA DE TOKENS (PROMPT, COMPLETION, TOTAL CON REASONING)
# =============================================================================

def test_token_usage_consistency_and_pricing_calculation() -> None:
    """9.1 Demuestra que el coste se calcula deterministamente con prompt y completion sin adulterar total_tokens."""
    prompt_tokens = 1041
    completion_tokens = 1270
    reasoning_tokens = 759
    total_tokens_reported = prompt_tokens + completion_tokens + reasoning_tokens  # 3070

    cost = calculate_llm_cost("grok-4.6", prompt_tokens, completion_tokens)
    assert cost is not None
    # 1041 * 5e-6 + 1270 * 15e-6 = 0.005205 + 0.019050 = 0.024255 USD
    assert round(cost, 6) == 0.024255

    # La diferencia exacta corresponde a los tokens internos de razonamiento
    assert total_tokens_reported - (prompt_tokens + completion_tokens) == reasoning_tokens


# =============================================================================
# 10. PERSISTENCIA Y EXPORTACIÓN
# =============================================================================

@pytest.mark.asyncio
async def test_persistence_and_export_handles_resumed_run(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """10.1 S4Exporter exporta fielmente los costes confirmados, metadatos y tareas de una corrida reanudada."""
    run_id = uuid.uuid4()
    async with session_factory() as session, session.begin():
        srv = S4Service(session)
        run = await srv.create_load_run(
            run_id=run_id,
            target_tasks=1,
            budget_limit_usd=35.0,
            meta={"uncertain_liabilities_usd": 1.10},
        )
        await srv.start_load_run(run.id)
        t = await srv.create_task_execution(run_id=run_id, task_number=8, input_payload={})
        t.status = S4TaskStatus.RUNNING.value

        await srv.record_task_llm_call(
            task_id=t.id,
            model="grok-4.6",
            input_tokens=1041,
            output_tokens=918,
            total_tokens=2356,
            gateway_request_id="gw-test-123",
            measurement_status="measured",
        )
        await srv.complete_task_execution(t.id, validation_passed=True, result_summary="Verified")

    async with session_factory() as session:
        json_data = await S4Exporter.export_json(run_id, session)
        csv_data = await S4Exporter.export_csv(run_id, session)
        calls_csv = await S4Exporter.export_calls_csv(run_id, session)

    assert json_data["run"]["budget_limit_usd"] == 35.0
    assert json_data["run"]["completed_tasks"] == 1
    assert "gw-test-123" in calls_csv
    assert "verified" in csv_data.lower()
