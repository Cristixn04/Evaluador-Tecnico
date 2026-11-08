"""Pruebas rigurosas de pacing temporal, prevención de ráfagas, inactividad y concurrencia S4."""

from __future__ import annotations

import asyncio
import csv
import io
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.db.models.interview import LLMUsageRecord
from src.db.models.s4 import S4TaskExecution
from src.s4.catalog import S4TaskCatalogGenerator
from src.s4.enums import S4TaskStatus
from src.s4.exporter import S4Exporter
from src.s4.pacer import S4Pacer
from src.s4.recovery import S4RecoveryCoordinator
from src.s4.service import S4Service


@pytest.fixture
def session_factory(database_url: str) -> async_sessionmaker[AsyncSession]:
    engine = create_async_engine(database_url, echo=False)
    return async_sessionmaker(engine, expire_on_commit=False)


# =============================================================================
# 1. PRUEBAS DE PACER CON RELOJ SIMULADO (TEMPORALIDAD Y PREVENCIÓN DE RÁFAGAS)
# =============================================================================

def test_pacer_fast_task_respects_nominal_cadence() -> None:
    """1. Tarea rápida (2s): El pacer espera el tiempo restante (~41.2s) para no adelantarse."""
    pacer = S4Pacer(total_tasks=1000, total_duration_seconds=43200.0, min_interval_seconds=5.0)
    # T0: Inicio y despacho de tarea 1
    t0 = 1000.0
    pacer.start(monotonic_now=t0)
    pacer.record_dispatch(monotonic_now=t0)

    # Tarea 1 finaliza en 2 segundos (t0 + 2.0)
    t_finish = t0 + 2.0
    delay = pacer.compute_pacing_delay(completed_tasks=1, current_monotonic=t_finish)

    # Cadencia esperada: 43.2s. 43.2 - 2.0 = 41.2s
    assert round(delay, 1) == 41.2


def test_pacer_slow_task_prevents_burst_and_enforces_floor() -> None:
    """2. Tarea lenta (100s): No genera ráfaga (delay=0). Aplica el suelo anti-ráfagas min_interval_seconds."""
    pacer = S4Pacer(total_tasks=1000, total_duration_seconds=43200.0, min_interval_seconds=5.0)
    t0 = 2000.0
    pacer.start(monotonic_now=t0)
    pacer.record_dispatch(monotonic_now=t0)

    # Tarea tarda 100s (> 43.2s)
    t_finish = t0 + 100.0
    delay = pacer.compute_pacing_delay(completed_tasks=1, current_monotonic=t_finish)

    # El pacer NO devuelve 0.0 ni permite ráfaga inmediata; exige al menos 5.0s
    assert delay == 5.0


def test_pacer_failed_task_maintains_cadence() -> None:
    """3. Tarea fallida (rápida o lenta): Respeta el mismo control de cadencia sin aceleración."""
    pacer = S4Pacer(total_tasks=1000, total_duration_seconds=43200.0, min_interval_seconds=5.0)
    t0 = 3000.0
    pacer.start(monotonic_now=t0)
    pacer.record_dispatch(monotonic_now=t0)

    # Fallo rápido tras 3s
    t_fail = t0 + 3.0
    delay = pacer.compute_pacing_delay(completed_tasks=1, current_monotonic=t_fail)
    assert round(delay, 1) == 40.2


def test_pacer_task_with_corrections_maintains_cadence() -> None:
    """4. Tarea con correcciones (demora 30s): Espera los 13.2s restantes sin ráfagas."""
    pacer = S4Pacer(total_tasks=1000, total_duration_seconds=43200.0, min_interval_seconds=5.0)
    t0 = 4000.0
    pacer.start(monotonic_now=t0)
    pacer.record_dispatch(monotonic_now=t0)

    # Tarea inicial + correcciones consumen 30 segundos
    t_done = t0 + 30.0
    delay = pacer.compute_pacing_delay(completed_tasks=1, current_monotonic=t_done)
    assert round(delay, 1) == 13.2


def test_pacer_resumption_after_pause_does_not_burst() -> None:
    """5. Reanudación después de pausa (10 min): No ejecuta ráfagas de 'desquite' para compensar."""
    pacer = S4Pacer(total_tasks=1000, total_duration_seconds=43200.0, max_delay_seconds=120.0, min_interval_seconds=5.0)
    t0 = 5000.0
    pacer.start(monotonic_now=t0)
    pacer.record_dispatch(monotonic_now=t0)

    # Pausa de 600 segundos (10 minutos)
    t_resume = t0 + 600.0
    delay = pacer.compute_pacing_delay(completed_tasks=1, current_monotonic=t_resume)

    # El pacer detecta que se superó max_delay_seconds y no intenta comprimir 14 tareas en 0s
    assert delay == 5.0


def test_pacer_beyond_1000_tasks_maintains_smooth_cadence() -> None:
    """6. Más de 1.000 tareas por reposición: Mantiene cadencia nominal, sin colapsar a 0s."""
    pacer = S4Pacer(total_tasks=1000, total_duration_seconds=43200.0, min_interval_seconds=5.0)
    t0 = 10000.0
    pacer.start(monotonic_now=t0)

    # Simular tarea 1005 despachada
    t_disp = t0 + 43200.0
    pacer.record_dispatch(monotonic_now=t_disp)

    # Finaliza en 10s
    t_fin = t_disp + 10.0
    delay = pacer.compute_pacing_delay(completed_tasks=1005, current_monotonic=t_fin)

    # Respeta el espacio de 43.2s entre despachos: 43.2 - 10.0 = 33.2s
    assert round(delay, 1) == 33.2


# =============================================================================
# 2. POLÍTICA DE INACTIVIDAD MÁXIMA (>120s) Y ACTIVIDAD LLM REAL
# =============================================================================

@pytest.mark.asyncio
async def test_inactivity_interval_exceeding_120s_deducted_from_effective_activity(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """7. Intervalo de inactividad superior a 120s: El exceso se registra y se descuenta de la actividad efectiva."""
    run_id = uuid.uuid4()
    base_time = datetime.now(UTC) - timedelta(hours=2)

    async with session_factory() as session, session.begin():
        srv = S4Service(session)
        run = await srv.create_load_run(run_id=run_id, target_tasks=10)
        await srv.start_load_run(run.id)

        t1 = await srv.create_task_execution(run_id=run.id, task_number=1, input_payload={})
        t2 = await srv.create_task_execution(run_id=run.id, task_number=2, input_payload={})

        # Llamada 1 en t=0
        rec1 = LLMUsageRecord(
            s4_task_execution_id=t1.id,
            model="grok-beta",
            tokens_input=100,
            tokens_output=50,
            tokens_total=150,
            cost_usd=0.001,
            call_sequence=1,
            created_at=base_time,
        )
        # Llamada 2 después de 300 segundos (inactividad de 300s > 120s; exceso = 180s)
        rec2 = LLMUsageRecord(
            s4_task_execution_id=t2.id,
            model="grok-beta",
            tokens_input=120,
            tokens_output=60,
            tokens_total=180,
            cost_usd=0.0012,
            call_sequence=1,
            created_at=base_time + timedelta(seconds=300),
        )
        session.add_all([rec1, rec2])

    async with session_factory() as session:
        srv = S4Service(session)
        summary = await srv.get_run_statistics(run_id)

        assert summary.llm_activity_duration_seconds == 300.0
        # Brecha > 120s interrumpe la ventana continua; la ventana continua resultante es 0.0s
        assert summary.inactivity_exceeded_count == 1
        assert summary.interruption_count == 1
        assert summary.effective_llm_activity_seconds == 0.0
        assert summary.continuous_window_valid is False
        assert summary.max_inactivity_threshold_seconds == 120.0


# =============================================================================
# 3. REPOSICIÓN SEGURA: CONCURRENCIA, IDEMPOTENCIA Y LEASES
# =============================================================================

@pytest.mark.asyncio
async def test_concurrency_two_transactions_allocate_next_task(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """8. Concurrencia: Dos transacciones intentan generar la siguiente tarea simultáneamente.
    Bajo el bloqueo transaccional, una genera la tarea y la otra detecta la tarea pendiente y retorna None.
    """
    cat = S4TaskCatalogGenerator(seed=999)
    run_id = uuid.uuid4()

    async with session_factory() as session, session.begin():
        srv = S4Service(session)
        run = await srv.create_load_run(run_id=run_id, target_tasks=5)
        await srv.start_load_run(run.id)

    async def worker_allocation() -> S4TaskExecution | None:
        async with session_factory() as s, s.begin():
            service = S4Service(s)
            return await service.allocate_replenishment_task(
                run_id=run_id,
                catalog=cat,
                min_duration_seconds=0.0,
            )

    # Ejecutar ambas peticiones simultáneamente
    res1, res2 = await asyncio.gather(worker_allocation(), worker_allocation())

    # Exactamente una transacción debió crear la tarea; la otra vio la tarea pendiente y retornó None
    created = [r for r in (res1, res2) if r is not None]
    assert len(created) == 1
    assert created[0].task_number == 1

    # Verificar unicidad en PostgreSQL
    async with session_factory() as session:
        stmt = select(S4TaskExecution).where(S4TaskExecution.run_id == run_id)
        tasks = (await session.execute(stmt)).scalars().all()
        assert len(tasks) == 1
        assert tasks[0].task_number == 1


@pytest.mark.asyncio
async def test_replenishment_refuses_when_pending_queued_or_running_exist(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """9. No crear reemplazos si ya existen tareas QUEUED o RUNNING suficientes."""
    cat = S4TaskCatalogGenerator(seed=888)
    run_id = uuid.uuid4()

    async with session_factory() as session, session.begin():
        srv = S4Service(session)
        run = await srv.create_load_run(run_id=run_id, target_tasks=5)
        await srv.start_load_run(run.id)
        # Crear una tarea en estado QUEUED
        await srv.create_task_execution(run_id=run_id, task_number=1, input_payload={})

    async with session_factory() as session, session.begin():
        srv = S4Service(session)
        task = await srv.allocate_replenishment_task(run_id=run_id, catalog=cat)
        # No debe crear tarea porque ya hay una QUEUED
        assert task is None


@pytest.mark.asyncio
async def test_restarting_process_with_orphaned_running_task(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """10. Reinicio con tarea RUNNING huérfana: Es recuperada con incremento de intento sin colisiones."""
    cat = S4TaskCatalogGenerator(seed=777)
    run_id = uuid.uuid4()

    async with session_factory() as session, session.begin():
        srv = S4Service(session)
        run = await srv.create_load_run(run_id=run_id, target_tasks=3)
        await srv.start_load_run(run.id)
        t = await srv.create_task_execution(run_id=run_id, task_number=1, input_payload={})
        t.status = S4TaskStatus.RUNNING.value
        t.lease_token = "old-worker-lease"
        t.heartbeat_at = datetime.now(UTC) - timedelta(minutes=10)

    # Recuperar huérfana
    async with session_factory() as session, session.begin():
        rec = S4RecoveryCoordinator(session, timeout_seconds=60.0)
        recovered = await rec.sweep_and_recover_orphans(run_id)
        assert len(recovered) == 1
        assert recovered[0].status == S4TaskStatus.QUEUED.value
        assert recovered[0].attempt_count == 2
        assert recovered[0].lease_token is None

    # Intentar asignar reposición: debe retornar None porque la tarea recuperada ya está QUEUED
    async with session_factory() as session, session.begin():
        srv = S4Service(session)
        repl = await srv.allocate_replenishment_task(run_id=run_id, catalog=cat)
        assert repl is None


# =============================================================================
# 4. EVIDENCIA EXPORTADA AUDITABLE Y CONCILIABLE CON GROK
# =============================================================================

@pytest.mark.asyncio
async def test_export_includes_individual_llm_calls_and_provider_reconciliation(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """11 & 12. Exportación JSON y CSV con desglose individual de llamadas LLM y metadatos de pasarela."""
    run_id = uuid.uuid4()

    async with session_factory() as session, session.begin():
        srv = S4Service(session)
        run = await srv.create_load_run(run_id=run_id, target_tasks=1)
        await srv.start_load_run(run.id)
        task = await srv.create_task_execution(run_id=run_id, task_number=1, input_payload={})

        rec = LLMUsageRecord(
            s4_task_execution_id=task.id,
            model="grok-beta",
            tokens_input=150,
            tokens_output=80,
            tokens_total=230,
            cost_usd=0.002,
            gateway_request_id="chatcmpl-test-uuid-01",
            gateway_metadata={
                "provider_id": "chatcmpl-test-uuid-01",
                "cf_ray": "8abcdef12345-BOG",
                "x-ratelimit-remaining-tokens": 980000,
            },
            measurement_status="measured",
            call_sequence=1,
            created_at=datetime.now(UTC),
        )
        session.add(rec)

    async with session_factory() as session:
        json_data = await S4Exporter.export_json(run_id, session)
        calls_csv = await S4Exporter.export_calls_csv(run_id, session)

    # 1. Verificación JSON
    assert "llm_calls" in json_data
    assert len(json_data["llm_calls"]) == 1
    call_json = json_data["llm_calls"][0]
    assert call_json["model"] == "grok-beta"
    assert call_json["tokens_input"] == 150
    assert call_json["tokens_output"] == 80
    assert call_json["provider_request_id"] == "chatcmpl-test-uuid-01"
    assert call_json["cf_ray"] == "8abcdef12345-BOG"

    # 2. Verificación CSV de llamadas individuales
    reader = csv.DictReader(io.StringIO(calls_csv))
    rows = list(reader)
    assert len(rows) == 1
    assert rows[0]["provider_request_id"] == "chatcmpl-test-uuid-01"
    assert rows[0]["cf_ray"] == "8abcdef12345-BOG"
    assert rows[0]["tokens_total"] == "230"
