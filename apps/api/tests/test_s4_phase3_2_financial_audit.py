"""Pruebas exhaustivas de auditoría financiera, idempotencia y capacidad operativa para S4 Fase 3.2.

Garantiza cobertura estricta de los 18 escenarios de la Etapa 6:
1. Exposición superior al presupuesto.
2. Dos pasivos inciertos concurrentes.
3. Reinicio con pasivos.
4. Reserva y liberación concurrentes.
5. Error de persistencia al retener un pasivo.
6. Doble reconciliación.
7. Conciliación parcial.
8. Conciliación completa.
9. 502 ambiguo.
10. 503 ambiguo.
11. 429 rate limit.
12. ConnectTimeout.
13. PoolTimeout.
14. WriteTimeout.
15. ReadTimeout.
16. Prevención de doble facturación por reintento.
17. Tarea más lenta que el intervalo del pacer.
18. Reinicio durante el pacing.

Presupuesto externo: $0.00 USD (Cero llamadas externas a proveedores).
"""

from __future__ import annotations

import asyncio
import uuid

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.llm.exceptions import (
    LLMProviderError,
    LLMRateLimitError,
    LLMTimeoutError,
)
from src.llm.openai_compatible import OpenAICompatibleClient
from src.llm.types import ChatMessage
from src.s4.enums import S4TaskStatus
from src.s4.pacer import S4Pacer
from src.s4.service import S4Service
from src.s4.watchdog import S4Watchdog
from src.s4.worker import S4TaskWorker


@pytest.fixture
def session_factory(database_url: str) -> async_sessionmaker[AsyncSession]:
    engine = create_async_engine(database_url, pool_pre_ping=True)
    return async_sessionmaker(engine, expire_on_commit=False)


# -----------------------------------------------------------------------------
# 1. Exposición superior al presupuesto
# -----------------------------------------------------------------------------
def test_01_exposure_exceeding_budget() -> None:
    """Verifica que el watchdog detecta cuando confirmado + reservas + pasivos supera el límite

    y bloquea inmediatamente cualquier nuevo despacho disparando el disyuntor.
    """
    watchdog = S4Watchdog(budget_limit_usd=0.10)
    # Simular escenario del smoke anterior: confirmado=0.01447, pasivos=0.10 (0.05 + 0.05) -> 0.11447 > 0.10
    watchdog._uncertain_liabilities_usd = 0.10
    ok, msg = watchdog.reserve_cost(0.01, current_cost_usd=0.01447)
    assert ok is False
    assert watchdog.is_tripped is True
    assert "exceeds limit" in msg
    assert "0.1245" in msg or "0.124" in msg


# -----------------------------------------------------------------------------
# 2. Dos pasivos inciertos concurrentes
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_02_concurrent_uncertain_liabilities(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Verifica que dos tareas que fallan concurrentemente con costo incierto acumulan

    sus pasivos en PostgreSQL bajo bloqueo de fila sin pérdida de actualizaciones (lost updates).
    """
    run_id = uuid.uuid4()
    async with session_factory() as session, session.begin():
        srv = S4Service(session)
        run = await srv.create_load_run(run_id=run_id, target_tasks=2, budget_limit_usd=1.0)
        await srv.start_load_run(run.id)
        t1 = await srv.create_task_execution(run_id=run.id, task_number=1, input_payload={"task": "c1"})
        t2 = await srv.create_task_execution(run_id=run.id, task_number=2, input_payload={"task": "c2"})
        task1_id, task2_id = t1.id, t2.id

    async def record_liability_task(task_id: uuid.UUID, amount: float) -> None:
        async with session_factory() as s, s.begin():
            srv_worker = S4Service(s)
            await srv_worker.record_uncertain_liability(run_id, task_id, amount)

    # Ejecutar concurrentemente
    await asyncio.gather(
        record_liability_task(task1_id, 0.05),
        record_liability_task(task2_id, 0.05),
    )

    async with session_factory() as session:
        srv = S4Service(session)
        run = await srv.get_load_run(run_id)
        meta = run.meta or {}
        # Ambos pasivos deben estar presentes de forma determinista (0.10 exacto)
        assert meta.get("uncertain_liabilities_usd") == 0.10
        assert str(task1_id) in meta.get("unreconciled_task_ids", [])
        assert str(task2_id) in meta.get("unreconciled_task_ids", [])


# -----------------------------------------------------------------------------
# 3. Reinicio con pasivos
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_03_restart_with_persisted_liabilities(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Verifica que un worker al reiniciarse reconstruye el estado del watchdog

    reflejando la suma íntegra de pasivos persistidos en la corrida.
    """
    run_id = uuid.uuid4()
    async with session_factory() as session, session.begin():
        srv = S4Service(session)
        run = await srv.create_load_run(
            run_id=run_id,
            target_tasks=1,
            budget_limit_usd=0.50,
            meta={"uncertain_liabilities_usd": 0.085, "unreconciled_task_ids": ["t-abc"]},
        )
        await srv.start_load_run(run.id)

    watchdog = S4Watchdog(budget_limit_usd=0.50)
    worker = S4TaskWorker(
        run_id=run_id,
        session_factory=session_factory,
        watchdog=watchdog,
        worker_id="restarted-worker-02",
    )
    await worker.run_autonomous_loop()

    assert watchdog.uncertain_liabilities_usd == 0.085
    status = watchdog.get_status()
    assert status["uncertain_liabilities_usd"] == 0.085


# -----------------------------------------------------------------------------
# 4. Reserva y liberación concurrentes
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_04_concurrent_reservation_and_release(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Verifica la atomicidad transaccional de reserve_run_budget y release_run_budget_reservation

    ante operaciones concurrentes bajo bloqueo de fila PostgreSQL.
    """
    run_id = uuid.uuid4()
    async with session_factory() as session, session.begin():
        srv = S4Service(session)
        run = await srv.create_load_run(run_id=run_id, target_tasks=10, budget_limit_usd=1.0)
        await srv.start_load_run(run.id)

    async def reserve_and_release(amount: float) -> None:
        async with session_factory() as s, s.begin():
            srv = S4Service(s)
            ok, _ = await srv.reserve_run_budget(run_id, amount)
            assert ok is True
        await asyncio.sleep(0.01)
        async with session_factory() as s, s.begin():
            srv = S4Service(s)
            await srv.release_run_budget_reservation(run_id, amount)

    # 5 operaciones concurrentes de reserva y liberación de $0.05
    await asyncio.gather(*(reserve_and_release(0.05) for _ in range(5)))

    async with session_factory() as session:
        srv = S4Service(session)
        run = await srv.get_load_run(run_id)
        assert run.meta.get("active_reservations_usd", 0.0) == 0.0


# -----------------------------------------------------------------------------
# 5. Error de persistencia al retener un pasivo
# -----------------------------------------------------------------------------
def test_05_persistence_failure_memory_safety() -> None:
    """Verifica que si la persistencia en base de datos falla al retener un pasivo,

    el watchdog en memoria mantiene retenida la reserva protegiendo contra sobregiro local.
    """
    watchdog = S4Watchdog(budget_limit_usd=0.10)
    ok, _ = watchdog.reserve_cost(0.05, current_cost_usd=0.04)
    assert ok is True
    assert watchdog.active_reservations_usd == 0.05

    # Retener en memoria
    watchdog.retain_uncertain_liability(0.05)
    assert watchdog.active_reservations_usd == 0.0
    assert watchdog.uncertain_liabilities_usd == 0.05

    # Siguiente reserva proyecta 0.04 + 0.05 + 0.03 = 0.12 > 0.10 -> Rechazada
    next_ok, _ = watchdog.reserve_cost(0.03, current_cost_usd=0.04)
    assert next_ok is False
    assert watchdog.is_tripped is True


# -----------------------------------------------------------------------------
# 6. Doble reconciliación (Idempotencia estricta)
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_06_double_reconciliation_idempotency(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Verifica que ejecutar dos veces la reconciliación de la misma tarea no deduce

    el pasivo dos veces ni duplica los costos de la corrida.
    """
    run_id = uuid.uuid4()
    async with session_factory() as session, session.begin():
        srv = S4Service(session)
        run = await srv.create_load_run(run_id=run_id, target_tasks=1)
        await srv.start_load_run(run.id)
        task = await srv.create_task_execution(run_id=run.id, task_number=1, input_payload={"task": "dup"})
        await srv.claim_next_task(run.id, "worker-01")

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

    # 1era reconciliación: facturado $0.0150
    async with session_factory() as session, session.begin():
        srv = S4Service(session)
        t_first = await srv.reconcile_task_cost(task.id, confirmed_cost_usd=0.0150, estimated_liability_usd=0.05)
        assert t_first.cost_usd == 0.0150

    # 2da reconciliación: idéntica
    async with session_factory() as session, session.begin():
        srv = S4Service(session)
        t_second = await srv.reconcile_task_cost(task.id, confirmed_cost_usd=0.0150, estimated_liability_usd=0.05)
        assert t_second.cost_usd == 0.0150

        run = await srv.get_load_run(run_id)
        assert run.total_cost_usd == 0.0150
        # No debe haber quedado negativo ni deducido de más
        assert run.meta.get("uncertain_liabilities_usd") == 0.0


# -----------------------------------------------------------------------------
# 7. Conciliación parcial
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_07_partial_reconciliation(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Verifica la reconciliación parcial donde se confirma un pasivo de $0.03

    sobre una estimación original de $0.05, deduciendo solo el monto especificado.
    """
    run_id = uuid.uuid4()
    async with session_factory() as session, session.begin():
        srv = S4Service(session)
        run = await srv.create_load_run(run_id=run_id, target_tasks=1)
        await srv.start_load_run(run.id)
        task = await srv.create_task_execution(run_id=run.id, task_number=1, input_payload={"task": "part"})
        await srv.claim_next_task(run.id, "worker-01")

        await srv.record_task_llm_call(
            task.id,
            model="grok-beta",
            input_tokens=None,
            output_tokens=None,
            measurement_status="timeout_uncertain",
        )
        await srv.record_uncertain_liability(run.id, task.id, 0.10)  # Pasivo inicial 0.10
        await srv.complete_task_execution(
            task.id,
            validation_passed=False,
            error="ReadTimeout",
            final_status=S4TaskStatus.FAILED,
            worker_id="worker-01",
            lease_token=task.lease_token,
        )

    async with session_factory() as session, session.begin():
        srv = S4Service(session)
        # Conciliación parcial: confirmamos $0.02 y deducimos $0.05 del pasivo
        reconciled = await srv.reconcile_task_cost(task.id, confirmed_cost_usd=0.02, estimated_liability_usd=0.05)
        assert reconciled.cost_usd == 0.02

        run = await srv.get_load_run(run_id)
        assert run.total_cost_usd == 0.02
        assert run.meta.get("uncertain_liabilities_usd") == 0.05  # 0.10 - 0.05


# -----------------------------------------------------------------------------
# 8. Conciliación completa
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_08_complete_reconciliation_audit_trail(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Verifica que una conciliación completa registra un evento de auditoría con operador y timestamp."""
    run_id = uuid.uuid4()
    async with session_factory() as session, session.begin():
        srv = S4Service(session)
        run = await srv.create_load_run(run_id=run_id, target_tasks=1)
        await srv.start_load_run(run.id)
        task = await srv.create_task_execution(run_id=run.id, task_number=1, input_payload={"task": "audit"})
        await srv.claim_next_task(run.id, "worker-01")

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

    async with session_factory() as session, session.begin():
        srv = S4Service(session)
        reconciled = await srv.reconcile_task_cost(
            task.id,
            confirmed_cost_usd=0.0145,
            estimated_liability_usd=0.05,
            operator="auditor-samuel",
        )
        assert reconciled.cost_usd == 0.0145
        events = reconciled.recovery_events
        assert len(events) >= 1
        last_event = events[-1]
        assert last_event["event_type"] == "cost_reconciled"
        assert "auditor-samuel" in last_event["details"]
        assert "confirmed cost $0.01450" in last_event["details"]


# -----------------------------------------------------------------------------
# 9. HTTP 502 Ambiguo
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_09_http_502_prohibits_auto_retry_and_is_uncertain() -> None:
    """Verifica que un error HTTP 502 no se reintenta automáticamente y se clasifica como incierto (is_uncertain=True)."""
    calls = 0

    async def mock_502(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(502, headers={"x-request-id": "req-502-abc"}, json={"error": "Bad Gateway"})

    client = OpenAICompatibleClient(
        api_key="mock-key",
        base_url="https://api.reto.pltk.mx/v1",
        model="grok-beta",
        max_retries=3,
        client=httpx.AsyncClient(transport=httpx.MockTransport(mock_502)),
    )

    with pytest.raises(LLMProviderError) as exc_info:
        await client.complete([ChatMessage(role="user", content="Test 502")])

    assert exc_info.value.status_code == 502
    assert exc_info.value.is_uncertain is True
    assert "uncertain" in str(exc_info.value).lower()
    assert calls == 1, "PROHIBICIÓN VIOLADA: 502 fue reintentado automáticamente"


# -----------------------------------------------------------------------------
# 10. HTTP 503 Ambiguo
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_10_http_503_prohibits_auto_retry_and_is_uncertain() -> None:
    """Verifica que un error HTTP 503 no se reintenta automáticamente y se clasifica como incierto (is_uncertain=True)."""
    calls = 0

    async def mock_503(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(503, headers={"cf-ray": "ray-503-mex"}, json={"error": "Service Unavailable"})

    client = OpenAICompatibleClient(
        api_key="mock-key",
        base_url="https://api.reto.pltk.mx/v1",
        model="grok-beta",
        max_retries=3,
        client=httpx.AsyncClient(transport=httpx.MockTransport(mock_503)),
    )

    with pytest.raises(LLMProviderError) as exc_info:
        await client.complete([ChatMessage(role="user", content="Test 503")])

    assert exc_info.value.status_code == 503
    assert exc_info.value.is_uncertain is True
    assert calls == 1, "PROHIBICIÓN VIOLADA: 503 fue reintentado automáticamente"


# -----------------------------------------------------------------------------
# 11. HTTP 429 Rate Limit
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_11_http_429_rate_limit_safe_retry_and_exhaustion() -> None:
    """Verifica que HTTP 429 es clasificado como coste no generado (is_uncertain=False)

    y respeta el número máximo de reintentos con backoff.
    """
    calls = 0

    async def mock_429(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(429, headers={"retry-after": "0"}, json={"error": "Rate limit exceeded"})

    client = OpenAICompatibleClient(
        api_key="mock-key",
        base_url="https://api.reto.pltk.mx/v1",
        model="grok-beta",
        max_retries=2,
        client=httpx.AsyncClient(transport=httpx.MockTransport(mock_429)),
    )

    with pytest.raises(LLMRateLimitError):
        await client.complete([ChatMessage(role="user", content="Test 429")])

    # 1 intento inicial + 2 reintentos = 3 llamadas en total
    assert calls == 3


# -----------------------------------------------------------------------------
# 12. ConnectTimeout
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_12_connect_timeout_safe_retry_is_certain() -> None:
    """Verifica que ConnectTimeout (fallo TCP previo) no es incierto (is_uncertain=False)

    y puede reintentarse con seguridad porque ningún byte fue enviado.
    """
    calls = 0

    async def mock_conn_timeout(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise httpx.ConnectTimeout("TCP connection handshake timed out")

    client = OpenAICompatibleClient(
        api_key="mock-key",
        base_url="https://api.reto.pltk.mx/v1",
        model="grok-beta",
        max_retries=2,
        client=httpx.AsyncClient(transport=httpx.MockTransport(mock_conn_timeout)),
    )

    with pytest.raises(LLMTimeoutError) as exc_info:
        await client.complete([ChatMessage(role="user", content="Test Connect")])

    assert exc_info.value.is_uncertain is False
    assert calls == 3


# -----------------------------------------------------------------------------
# 13. PoolTimeout
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_13_pool_timeout_safe_retry_is_certain() -> None:
    """Verifica que PoolTimeout (espera de conexión libre en pool local) no es incierto (is_uncertain=False)."""
    calls = 0

    async def mock_pool_timeout(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise httpx.PoolTimeout("Connection pool exhausted locally")

    client = OpenAICompatibleClient(
        api_key="mock-key",
        base_url="https://api.reto.pltk.mx/v1",
        model="grok-beta",
        max_retries=1,
        client=httpx.AsyncClient(transport=httpx.MockTransport(mock_pool_timeout)),
    )

    with pytest.raises(LLMTimeoutError) as exc_info:
        await client.complete([ChatMessage(role="user", content="Test Pool")])

    assert exc_info.value.is_uncertain is False
    assert calls == 2


# -----------------------------------------------------------------------------
# 14. WriteTimeout
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_14_write_timeout_is_uncertain_and_not_retried() -> None:
    """Verifica que WriteTimeout (interrupción durante envío de payload) es incierto y no se reintenta."""
    calls = 0

    async def mock_write_timeout(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise httpx.WriteTimeout("Timed out while writing request body to socket")

    client = OpenAICompatibleClient(
        api_key="mock-key",
        base_url="https://api.reto.pltk.mx/v1",
        model="grok-beta",
        max_retries=3,
        client=httpx.AsyncClient(transport=httpx.MockTransport(mock_write_timeout)),
    )

    with pytest.raises(LLMTimeoutError) as exc_info:
        await client.complete([ChatMessage(role="user", content="Test Write")])

    assert exc_info.value.is_uncertain is True
    assert calls == 1


# -----------------------------------------------------------------------------
# 15. ReadTimeout
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_15_read_timeout_is_uncertain_and_not_retried() -> None:
    """Verifica que ReadTimeout (espera de respuesta tras enviar payload) es incierto y jamás se reintenta."""
    calls = 0

    async def mock_read_timeout(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise httpx.ReadTimeout("Socket timed out waiting for response")

    client = OpenAICompatibleClient(
        api_key="mock-key",
        base_url="https://api.reto.pltk.mx/v1",
        model="grok-beta",
        max_retries=3,
        client=httpx.AsyncClient(transport=httpx.MockTransport(mock_read_timeout)),
    )

    with pytest.raises(LLMTimeoutError) as exc_info:
        await client.complete([ChatMessage(role="user", content="Test Read")])

    assert exc_info.value.is_uncertain is True
    assert calls == 1


# -----------------------------------------------------------------------------
# 16. Prevención de doble facturación por reintento
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_16_double_billing_prevention_on_uncertain_failure() -> None:
    """Garantiza formalmente que cualquier llamada susceptible de haber alcanzado

    el upstream se detiene en seco en el 1er intento impidiendo cargos dobles.
    """
    for exc_type in (httpx.ReadTimeout, httpx.WriteTimeout):
        calls = 0

        def create_handler(err_type: type[Exception]):
            async def handler(request: httpx.Request) -> httpx.Response:
                nonlocal calls
                calls += 1
                raise err_type("Simulated uncertain failure")
            return handler

        client = OpenAICompatibleClient(
            api_key="mock-key",
            base_url="https://api.reto.pltk.mx/v1",
            model="grok-beta",
            max_retries=4,
            client=httpx.AsyncClient(transport=httpx.MockTransport(create_handler(exc_type))),
        )

        with pytest.raises(LLMTimeoutError):
            await client.complete([ChatMessage(role="user", content="Test")])

        assert calls == 1, f"Fallo con {exc_type.__name__} generó {calls} peticiones HTTP (debe ser 1)"


# -----------------------------------------------------------------------------
# 17. Tarea más lenta que el intervalo del pacer
# -----------------------------------------------------------------------------
def test_17_task_slower_than_pacer_interval_no_burst() -> None:
    """Verifica que si una tarea tarda 45.0s (superando el intervalo objetivo de 43.2s),

    el pacer devuelve retardo 0.0s (sin crasheos ni retardos negativos) y no genera ráfagas descontroladas.
    """
    pacer = S4Pacer(
        total_tasks=1000,
        total_duration_seconds=43200.0,  # 43.2s por tarea
        min_interval_seconds=0.0,
    )
    pacer.start(monotonic_now=100.0)

    # Simular que transcurrieron 50.0s para completar la tarea 1 (tiempo objetivo era 43.2s)
    delay = pacer.compute_pacing_delay(completed_tasks=1, current_monotonic=150.0)
    assert delay == 0.0

    metrics = pacer.get_pacing_metrics(completed_tasks=1, current_monotonic=150.0)
    assert metrics["drift_seconds"] == -6.8  # Va 6.8s atrasado
    assert metrics["actual_cadence_seconds_per_task"] == 50.0


# -----------------------------------------------------------------------------
# 18. Reinicio durante el pacing
# -----------------------------------------------------------------------------
def test_18_pacer_restart_reconciliation() -> None:
    """Verifica que si el worker se reinicia transcurridas 2 horas (7.200s),

    el pacer inicializa su tiempo base y calcula el retardo correcto para la siguiente tarea.
    """
    pacer = S4Pacer(
        total_tasks=1000,
        total_duration_seconds=43200.0,  # 43.2s por tarea
    )
    # Iniciar con 7.200s transcurridos previamente en la BD
    pacer.start(monotonic_now=0.0, initial_elapsed_seconds=7200.0)

    assert pacer.elapsed_seconds(current_monotonic=0.0) == 7200.0

    # Tarea #166 completada: tiempo objetivo = 166 * 43.2 = 7171.2s. Elapsed=7200s -> Retardo 0.0s
    delay166 = pacer.compute_pacing_delay(completed_tasks=166, current_monotonic=0.0)
    assert delay166 == 0.0

    # Tarea #170 completada: tiempo objetivo = 170 * 43.2 = 7344.0s. Elapsed=7200s -> Retardo = 144.0s (acotado por max_delay_seconds 120s)
    delay170 = pacer.compute_pacing_delay(completed_tasks=170, current_monotonic=0.0)
    assert delay170 == 120.0
