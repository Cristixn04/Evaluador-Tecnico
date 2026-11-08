"""Pruebas rigurosas de los 12 escenarios de fallo, incertidumbre de costes y recuperación para S4 Fase 3.1.

Cero llamadas a proveedores externos reales ($0.00 USD).
Todos los escenarios utilizan mocks locales y transportes simulados en memoria.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.llm.exceptions import (
    LLMProviderError,
    LLMTimeoutError,
)
from src.llm.openai_compatible import OpenAICompatibleClient
from src.llm.types import ChatMessage
from src.s4.enums import S4TaskStatus
from src.s4.recovery import S4RecoveryCoordinator
from src.s4.service import S4Service, S4TaskValidationError
from src.s4.watchdog import S4Watchdog
from src.s4.worker import S4TaskWorker


@pytest.fixture
def session_factory(database_url: str) -> async_sessionmaker[AsyncSession]:
    engine = create_async_engine(database_url, pool_pre_ping=True)
    return async_sessionmaker(engine, expire_on_commit=False)


# -----------------------------------------------------------------------------
# Escenario 1: Timeout tras enviar la petición (ReadTimeout)
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_scenario_01_timeout_after_sending_request() -> None:
    """Verifica que un ReadTimeout se clasifica como resultado incierto (is_uncertain=True)

    y NO se reintenta automáticamente, protegiendo de cobros duplicados.
    """
    attempts = 0

    async def mock_handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        raise httpx.ReadTimeout("Request timed out waiting for response body")

    client = OpenAICompatibleClient(
        api_key="mock-key",
        base_url="https://api.reto.pltk.mx/v1",
        model="grok-beta",
        max_retries=3,
        client=httpx.AsyncClient(transport=httpx.MockTransport(mock_handler)),
    )

    with pytest.raises(LLMTimeoutError) as exc_info:
        await client.complete([ChatMessage(role="user", content="Ping")])

    assert exc_info.value.is_uncertain is True
    assert "uncertain" in str(exc_info.value).lower()
    # CRÍTICO: Debe haberse ejecutado exactamente 1 intento (sin reintentos)
    assert attempts == 1


# -----------------------------------------------------------------------------
# Escenario 2: Timeout sin identificador de solicitud
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_scenario_02_timeout_without_request_id(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Verifica que si un timeout ocurre antes de recibir cabeceras HTTP,

    se registra gateway_request_id=None con measurement_status='timeout_uncertain'.
    """
    async with session_factory() as session, session.begin():
        srv = S4Service(session)
        run = await srv.create_load_run(target_tasks=1)
        task = await srv.create_task_execution(run_id=run.id, task_number=1, input_payload={"task": "t2"})
        await srv.claim_next_task(run.id, "worker-01")

        record = await srv.record_task_llm_call(
            task.id,
            model="grok-beta",
            input_tokens=None,
            output_tokens=None,
            measurement_status="timeout_uncertain",
            gateway_request_id=None,
            gateway_metadata={"error": "LLM read timed out after 45.0s (payload already sent; billing uncertain)"},
        )
        assert record.gateway_request_id is None
        assert record.measurement_status == "timeout_uncertain"
        assert record.cost_usd is None
        assert "uncertain" in str(record.gateway_metadata)


# -----------------------------------------------------------------------------
# Escenario 3: Error HTTP con metadatos de la pasarela
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_scenario_03_http_error_with_gateway_metadata() -> None:
    """Verifica que si el proveedor devuelve un error 502/503/429 con cabeceras

    (x-request-id, cf-ray, retry-after), estos metadatos son capturados y preservados.
    """
    async def error_handler(request: httpx.Request) -> httpx.Response:
        headers = {
            "x-request-id": "req-gw-err-12345",
            "cf-ray": "ray-abcde-MEX",
            "retry-after": "5",
        }
        return httpx.Response(503, headers=headers, json={"error": "Service Temporarily Unavailable"})

    client = OpenAICompatibleClient(
        api_key="mock-key",
        base_url="https://api.reto.pltk.mx/v1",
        model="grok-beta",
        max_retries=0,
        client=httpx.AsyncClient(transport=httpx.MockTransport(error_handler)),
    )

    with pytest.raises(LLMProviderError) as exc_info:
        await client.complete([ChatMessage(role="user", content="Ping")])

    err = exc_info.value
    assert err.status_code == 503
    assert err.gateway_metadata.get("x-request-id") == "req-gw-err-12345"
    assert err.gateway_metadata.get("cf-ray") == "ray-abcde-MEX"
    assert err.gateway_metadata.get("retry-after") == "5"


# -----------------------------------------------------------------------------
# Escenario 4: Reserva persistente tras timeout incierto
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_scenario_04_persistent_reservation_after_uncertain_timeout(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Verifica que el watchdog no libera a $0.00 una reserva tras un timeout incierto,

    sino que la transfiere a un pasivo incierto retenido (uncertain_liabilities_usd).
    """
    watchdog = S4Watchdog(budget_limit_usd=10.0)

    # 1. Simular reserva previa a la llamada
    reserved_amount = 0.05
    ok, _ = watchdog.reserve_cost(reserved_amount, current_cost_usd=1.0)
    assert ok is True
    assert watchdog.active_reservations_usd == 0.05
    assert watchdog.uncertain_liabilities_usd == 0.0

    # 2. Ocurre timeout incierto: se retiene como pasivo
    watchdog.retain_uncertain_liability(reserved_amount)
    assert watchdog.active_reservations_usd == 0.0
    assert watchdog.uncertain_liabilities_usd == 0.05
    # La exposición financiera total se mantiene en 1.05
    assert watchdog.total_exposure_usd(current_cost_usd=1.0) == 1.05


# -----------------------------------------------------------------------------
# Escenario 5: Reinicio del worker con reservas / pasivos pendientes
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_scenario_05_restart_with_pending_uncertain_liabilities(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Verifica que un worker nuevo restaura los pasivos inciertos de la corrida

    desde s4_load_runs.meta al inicializar el bucle autónomo.
    """
    run_id = uuid.uuid4()
    async with session_factory() as session, session.begin():
        srv = S4Service(session)
        run = await srv.create_load_run(
            run_id=run_id,
            target_tasks=10,
            budget_limit_usd=5.0,
            meta={"uncertain_liabilities_usd": 0.15, "unreconciled_task_ids": ["task-1", "task-2", "task-3"]},
        )
        await srv.start_load_run(run.id)

    watchdog = S4Watchdog(budget_limit_usd=5.0)
    worker = S4TaskWorker(
        run_id=run_id,
        session_factory=session_factory,
        watchdog=watchdog,
        worker_id="restarted-worker",
    )

    # Ejecutar bucle (cola vacía) para verificar sincronización en arranque
    await worker.run_autonomous_loop()

    assert watchdog.uncertain_liabilities_usd == 0.15
    status = watchdog.get_status()
    assert status["uncertain_liabilities_usd"] == 0.15


# -----------------------------------------------------------------------------
# Escenario 6: Prohibición estricta de reintentos automáticos tras ReadTimeout
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_scenario_06_prohibition_of_auto_retry_on_read_timeout() -> None:
    """Verifica formalmente que OpenAICompatibleClient no realiza múltiples peticiones

    cuando se produce un ReadTimeout (máximo 1 intento HTTP).
    """
    post_count = 0

    async def counting_timeout_handler(request: httpx.Request) -> httpx.Response:
        nonlocal post_count
        post_count += 1
        raise httpx.ReadTimeout("Read timed out on socket")

    client = OpenAICompatibleClient(
        api_key="mock-key",
        base_url="https://api.reto.pltk.mx/v1",
        model="grok-beta",
        max_retries=5,  # Configurado alto explícitamente
        client=httpx.AsyncClient(transport=httpx.MockTransport(counting_timeout_handler)),
    )

    with pytest.raises(LLMTimeoutError):
        await client.complete([ChatMessage(role="user", content="Test")])

    assert post_count == 1, "PROHIBICIÓN VIOLADA: Se reintentó una llamada con ReadTimeout"


# -----------------------------------------------------------------------------
# Escenario 7: Reconciliación manual de costos
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_scenario_07_cost_reconciliation(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Verifica que el operador puede reconciliar una tarea con coste incierto,

    disminuyendo el pasivo incierto y confirmando el coste auditado.
    """
    run_id = uuid.uuid4()
    async with session_factory() as session, session.begin():
        srv = S4Service(session)
        run = await srv.create_load_run(run_id=run_id, target_tasks=1)
        await srv.start_load_run(run.id)
        task = await srv.create_task_execution(run_id=run.id, task_number=1, input_payload={"task": "rec"})
        await srv.claim_next_task(run.id, "worker-01")

        # Registrar llamada incierta
        await srv.record_task_llm_call(
            task.id,
            model="grok-beta",
            input_tokens=None,
            output_tokens=None,
            measurement_status="timeout_uncertain",
        )
        await srv.record_uncertain_liability(run.id, task.id, 0.05)
        await srv.complete_task_execution(
            task.id,
            validation_passed=False,
            error="ReadTimeout",
            final_status=S4TaskStatus.FAILED,
            worker_id="worker-01",
            lease_token=task.lease_token,
        )

    # Reconciliar: proveedor facturó realmente $0.0125
    async with session_factory() as session, session.begin():
        srv = S4Service(session)
        reconciled_task = await srv.reconcile_task_cost(
            task.id,
            confirmed_cost_usd=0.0125,
            estimated_liability_usd=0.05,
        )
        assert reconciled_task.cost_usd == 0.0125
        run = await srv.get_load_run(run_id)
        assert run.total_cost_usd == 0.0125
        assert run.meta.get("uncertain_liabilities_usd") == 0.0
        assert str(task.id) not in run.meta.get("unreconciled_task_ids", [])


# -----------------------------------------------------------------------------
# Escenario 8: Presupuesto agotado con llamadas en vuelo / pasivos inciertos
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_scenario_08_budget_exhaustion_with_uncertain_liabilities() -> None:
    """Verifica que el watchdog bloquea nuevas reservas cuando la suma de

    confirmado + reservas activas + pasivos inciertos alcanza el límite de presupuesto.
    """
    watchdog = S4Watchdog(budget_limit_usd=1.0)

    # Costo confirmado: $0.80, Pasivo incierto retenido: $0.18 -> Total: $0.98
    watchdog._uncertain_liabilities_usd = 0.18

    # Intentar reservar $0.05 proyectaría $1.03 (> $1.00)
    reserved_ok, msg = watchdog.reserve_cost(0.05, current_cost_usd=0.80)
    assert reserved_ok is False
    assert "exceeds limit" in msg
    assert watchdog.is_tripped is True
    assert "Budget limit reservation rejected" in str(watchdog.trip_reason)


# -----------------------------------------------------------------------------
# Escenario 9: Respuesta recibida sin persistencia (Fallo de BD)
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_scenario_09_response_received_without_persistence(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Verifica que una falla de persistencia tras recibir una respuesta de red

    no deja la tarea en estado SUCCEEDED y hace rollback limpio.
    """
    run_id = uuid.uuid4()
    async with session_factory() as session, session.begin():
        srv = S4Service(session)
        run = await srv.create_load_run(run_id=run_id, target_tasks=1)
        await srv.start_load_run(run.id)
        task = await srv.create_task_execution(run_id=run.id, task_number=1, input_payload={"task": "crash"})
        await srv.claim_next_task(run.id, "worker-fail")

    # Intentar finalizar con summary vacío (debe fallar la validación y revertirse)
    async with session_factory() as session:
        srv = S4Service(session)
        with pytest.raises(S4TaskValidationError):
            async with session.begin():
                await srv.complete_task_execution(
                    task.id,
                    validation_passed=True,
                    result_summary="",  # Invalido para SUCCEEDED
                    worker_id="worker-fail",
                    lease_token=task.lease_token,
                )

    # Verificar que en base de datos la tarea no quedó como succeeded
    async with session_factory() as session:
        srv = S4Service(session)
        db_task = await srv.get_task_execution(task.id)
        assert db_task.status != S4TaskStatus.SUCCEEDED.value


# -----------------------------------------------------------------------------
# Escenario 10: Recuperación segura tras reinicio (Bloqueo de tareas inciertas)
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_scenario_10_safe_recovery_blocks_uncertain_orphan(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Verifica que una tarea huérfana con llamadas inciertas NO es reencolada

    automáticamente por el sweeper de huérfanos, sino marcada como FAILED
    para exigir reconciliación manual.
    """
    run_id = uuid.uuid4()
    async with session_factory() as session, session.begin():
        srv = S4Service(session)
        run = await srv.create_load_run(run_id=run_id, target_tasks=1)
        await srv.start_load_run(run.id)
        await srv.create_task_execution(run_id=run.id, task_number=1, input_payload={"task": "orphan"})
        claimed = await srv.claim_next_task(run.id, "worker-dead")
        assert claimed is not None

        # Asociar llamada incierta a la tarea
        await srv.record_task_llm_call(
            claimed.id,
            model="grok-beta",
            input_tokens=None,
            output_tokens=None,
            measurement_status="timeout_uncertain",
        )
        # Simular latido vencido en el pasado
        claimed.heartbeat_at = datetime.now(UTC) - timedelta(seconds=300)

    # Ejecutar barrido de huérfanos
    async with session_factory() as session, session.begin():
        recovery = S4RecoveryCoordinator(session, timeout_seconds=60.0, max_attempts=3)
        recovered = await recovery.sweep_and_recover_orphans(run_id)

    assert len(recovered) == 1
    rec_task = recovered[0]
    # NO debe estar en queued; debe marcarse como FAILED con bloqueo explícito
    assert rec_task.status == S4TaskStatus.FAILED.value
    assert "uncertain_recovery_blocked" in str(rec_task.recovery_events)
    assert "automatic requeue prohibited" in str(rec_task.error_sanitized)


# -----------------------------------------------------------------------------
# Escenario 11: Prevención de peticiones duplicadas y fencing
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_scenario_11_duplicate_request_prevention_and_fencing(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Verifica que si un worker con lease expirado intenta finalizar o reportar,

    el fencing por lease_token y worker_id rechaza la operación inmediatamente.
    """
    async with session_factory() as session, session.begin():
        srv = S4Service(session)
        run = await srv.create_load_run(target_tasks=1)
        await srv.start_load_run(run.id)
        task = await srv.create_task_execution(run_id=run.id, task_number=1, input_payload={"task": "fence"})
        claimed = await srv.claim_next_task(run.id, "worker-legit")
        assert claimed is not None
        valid_token = claimed.lease_token

    # Worker espurio o con token expirado
    async with session_factory() as session, session.begin():
        srv = S4Service(session)
        from src.s4.worker import S4WorkerLeaseExpiredError

        with pytest.raises(S4WorkerLeaseExpiredError):
            await srv.complete_task_execution(
                task.id,
                validation_passed=True,
                result_summary="stolen result",
                worker_id="worker-imposter",
                lease_token=valid_token,
            )

        with pytest.raises(S4WorkerLeaseExpiredError):
            await srv.complete_task_execution(
                task.id,
                validation_passed=True,
                result_summary="stolen result",
                worker_id="worker-legit",
                lease_token="expired-token-xyz",
            )


# -----------------------------------------------------------------------------
# Escenario 12: Estados terminales consistentes
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_scenario_12_consistent_terminal_states(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Verifica la consistencia estricta de estados terminales:

    - SUCCEEDED requiere validación estricta y resultado sanitizado no vacío.
    - FAILED preserva la sanitización de errores.
    """
    from src.s4.service import S4TaskValidationError

    async with session_factory() as session, session.begin():
        srv = S4Service(session)
        run = await srv.create_load_run(target_tasks=2)
        await srv.start_load_run(run.id)
        t1 = await srv.create_task_execution(run_id=run.id, task_number=1, input_payload={"task": "t1"})
        t2 = await srv.create_task_execution(run_id=run.id, task_number=2, input_payload={"task": "t2"})

        claimed1 = await srv.claim_next_task(run.id, "worker-term")
        assert claimed1 is not None

        # 1. Intentar marcar succeeded sin validation_passed debe fallar
        with pytest.raises(S4TaskValidationError):
            await srv.complete_task_execution(
                t1.id,
                validation_passed=False,
                final_status=S4TaskStatus.SUCCEEDED,
                result_summary="result",
                worker_id="worker-term",
                lease_token=claimed1.lease_token,
            )

        # 2. Finalizar exitosamente con resultado válido
        succ_task = await srv.complete_task_execution(
            t1.id,
            validation_passed=True,
            result_summary="Verified and optimal algorithm with hash map",
            worker_id="worker-term",
            lease_token=claimed1.lease_token,
        )
        assert succ_task.status == S4TaskStatus.SUCCEEDED.value
        assert succ_task.validation_passed is True

        # 3. Finalizar t2 como FAILED con error sanitizado
        claimed2 = await srv.claim_next_task(run.id, "worker-term")
        assert claimed2 is not None
        fail_task = await srv.complete_task_execution(
            t2.id,
            validation_passed=False,
            error={"secret_leak": "Bearer xai-secret-key-123", "detail": "Test failure"},
            final_status=S4TaskStatus.FAILED,
            worker_id="worker-term",
            lease_token=claimed2.lease_token,
        )
        assert fail_task.status == S4TaskStatus.FAILED.value
        assert "xai-secret-key-123" not in str(fail_task.error_sanitized)
        assert "[REDACTED" in str(fail_task.error_sanitized)
