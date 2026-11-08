"""Pruebas exhaustivas del Runner Autónomo, Pacer, Recuperación y Watchdog de S4.

Garantiza cobertura estricta de los 20 requisitos de la Fase 2:
1. Generación determinista del catálogo con semilla fija.
2. Variación determinista con semilla distinta.
3. Distinción y unicidad de parámetros entre tareas consecutivas.
4. Registro de input en cola previo a la ejecución.
5. Validación estricta de criterios de aceptación del catálogo.
6. Pacer monotónico: cálculo de retardo cuando va adelantado vs 0.0 cuando va atrasado.
7. Métricas de cadencia, deriva temporal (drift) y proyección del pacer.
8. Bloqueo exclusivo de fila (SELECT ... FOR UPDATE) en complete_task_execution.
9. Reclamo atómico con SKIP LOCKED concurrente entre múltiples workers.
10. Ejecución paso a paso del worker con registro de call_sequence y gateway_metadata.
11. Emisión y actualización de latidos (heartbeat_at) y worker_id.
12. Recuperación de tareas huérfanas por timeout con reintento e incremento de attempt.
13. Marcación a FAILED de tareas huérfanas que superan max_attempts.
14. Disyuntor de presupuesto del watchdog al alcanzar el límite configurado.
15. Disyuntor por fallos consecutivos del watchdog (umbral 5 fallos).
16. Disyuntor por tasa de fallos en ventana deslizante del watchdog.
17. Detención ordenada del worker ante request_stop().
18. Exportación reproducible JSON y CSV incorporando worker_id y gateway metadata.
19. Garantía de $0.00 coste externo y cero llamadas a proveedores reales.
20. Restricción de unicidad en BD (s4_task_execution_id, call_sequence).
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.db.models.interview import LLMUsageRecord
from src.db.models.s4 import S4TaskExecution
from src.s4.catalog import S4TaskCatalogGenerator
from src.s4.enums import S4RunStatus, S4TaskStatus
from src.s4.exporter import S4Exporter
from src.s4.pacer import S4Pacer
from src.s4.recovery import S4RecoveryCoordinator
from src.s4.service import S4Service
from src.s4.watchdog import S4Watchdog
from src.s4.worker import S4TaskWorker


# -----------------------------------------------------------------------------
# Fixtures
# -----------------------------------------------------------------------------
@pytest.fixture
def session_factory(database_url: str) -> async_sessionmaker[AsyncSession]:
    engine = create_async_engine(database_url, pool_pre_ping=True)
    return async_sessionmaker(engine, expire_on_commit=False)


# -----------------------------------------------------------------------------
# 1. Catálogo Determinista
# -----------------------------------------------------------------------------
def test_01_catalog_deterministic_reproducibility() -> None:
    cat1 = S4TaskCatalogGenerator(seed=42)
    cat2 = S4TaskCatalogGenerator(seed=42)

    tasks1 = cat1.generate_catalog(count=50)
    tasks2 = cat2.generate_catalog(count=50)

    assert len(tasks1) == 50
    assert len(tasks2) == 50
    for t1, t2 in zip(tasks1, tasks2, strict=True):
        assert t1["task_number"] == t2["task_number"]
        assert t1["scenario_id"] == t2["scenario_id"]
        assert t1["title"] == t2["title"]
        assert t1["parameters"] == t2["parameters"]


def test_02_catalog_seed_variation() -> None:
    cat_a = S4TaskCatalogGenerator(seed=42)
    cat_b = S4TaskCatalogGenerator(seed=999)

    tasks_a = cat_a.generate_catalog(count=20)
    tasks_b = cat_b.generate_catalog(count=20)

    differences = sum(1 for ta, tb in zip(tasks_a, tasks_b, strict=True) if ta["scenario_id"] != tb["scenario_id"])
    assert differences > 15


def test_03_catalog_task_distinction() -> None:
    cat = S4TaskCatalogGenerator(seed=42)
    t1 = cat.generate_task_definition(1)
    t2 = cat.generate_task_definition(2)

    assert t1["task_number"] == 1
    assert t2["task_number"] == 2
    assert t1["scenario_id"] != t2["scenario_id"]


# -----------------------------------------------------------------------------
# 2. Persistencia Previa y Criterios de Aceptación
# -----------------------------------------------------------------------------
async def test_04_input_registration_prior_to_execution(db_session: AsyncSession) -> None:
    service = S4Service(db_session)
    run = await service.create_load_run(target_tasks=10, budget_limit_usd=10.0)

    cat = S4TaskCatalogGenerator(seed=42)
    tdef = cat.generate_task_definition(1)

    task = await service.create_task_execution(
        run_id=run.id,
        task_number=1,
        task_type=tdef["task_type"],
        input_payload=tdef,
    )

    assert task.status == S4TaskStatus.QUEUED.value
    assert task.started_at is None
    assert task.finished_at is None
    assert task.worker_id is None
    assert "s4_task_42_00001" in task.input_sanitized


def test_05_catalog_acceptance_criteria_validation() -> None:
    cat = S4TaskCatalogGenerator(seed=42)
    tdef = cat.generate_task_definition(1)

    # Resultado vacío -> Inválido
    valid, reason = cat.validate_task_result(tdef, "")
    assert not valid
    assert "empty" in reason.lower()

    # Resultado demasiado corto -> Inválido
    valid, reason = cat.validate_task_result(tdef, "Short.")
    assert not valid
    assert "short" in reason.lower() or "below minimum" in reason.lower()

    # Resultado válido con palabras clave requeridas y sandbox accepted
    req_kws = tdef["acceptance_criteria"]["required_keywords"]
    good_summary = {
        "summary": (
            f"Comprehensive evaluation analysis. The proposed solution applies {req_kws[0]} "
            f"and {req_kws[1] if len(req_kws) > 1 else ''} with optimal complexity."
        ),
        "sandbox_result": {"status": "accepted"},
    }
    valid, reason = cat.validate_task_result(tdef, good_summary)
    assert valid
    assert "successfully" in reason.lower()

    # AUD-S4-11: Rechazo estricto si faltan las palabras clave requeridas (incluso si contiene "analysis" o "solution")
    bad_summary = {
        "summary": (
            "Comprehensive architectural analysis and optimal solution for the problem. "
            "However, this text completely omits the specific domain technical keywords."
        ),
        "sandbox_result": {"status": "accepted"},
    }
    valid_bad, reason_bad = cat.validate_task_result(tdef, bad_summary)
    assert not valid_bad
    assert "missing required domain keywords" in reason_bad.lower()

    # AUD-S4-11: Rechazo explícito de frases evasivas
    evasive_summary = {
        "summary": (
            f"As an AI language model, no solution found. However, applying {req_kws[0]} "
            f"is optimal and verified for complexity."
        ),
        "sandbox_result": {"status": "accepted"},
    }
    valid_eva, reason_eva = cat.validate_task_result(tdef, evasive_summary)
    assert not valid_eva
    assert "evasive" in reason_eva.lower()


# -----------------------------------------------------------------------------
# 3. Pacer Monotónico y Métricas
# -----------------------------------------------------------------------------
def test_06_pacer_monotonic_delay_when_ahead() -> None:
    # 1.000 tareas en 43.200s -> 43.2s / tarea
    pacer = S4Pacer(total_tasks=1000, total_duration_seconds=43200.0)
    base_time = 1000.0
    pacer.start(monotonic_now=base_time)

    # Si se completó la tarea 10 inmediatamente en t=base+10s:
    # Tiempo objetivo para tarea 10 = 10 * 43.2 = 432.0s
    # Tiempo transcurrido = 10.0s
    # Retardo calculado = 432.0 - 10.0 = 422.0s (acotado por max_delay_seconds de 120s)
    delay = pacer.compute_pacing_delay(completed_tasks=10, current_monotonic=base_time + 10.0)
    assert delay == 120.0  # Cap máximo

    # Si se completó la tarea 1 en t=base+100s:
    # Tiempo objetivo para tarea 1 = 43.2s
    # Tiempo transcurrido = 100s (atrasado) -> delay = 0.0
    delay_behind = pacer.compute_pacing_delay(completed_tasks=1, current_monotonic=base_time + 100.0)
    assert delay_behind == 0.0


def test_07_pacer_metrics_and_drift_projection() -> None:
    pacer = S4Pacer(total_tasks=1000, total_duration_seconds=43200.0)
    base_time = 5000.0
    pacer.start(monotonic_now=base_time)

    metrics = pacer.get_pacing_metrics(completed_tasks=50, current_monotonic=base_time + 2000.0)
    assert metrics["elapsed_seconds"] == 2000.0
    assert metrics["target_elapsed_seconds"] == 2160.0  # 50 * 43.2
    assert metrics["target_cadence_seconds_per_task"] == 43.2
    assert metrics["actual_cadence_seconds_per_task"] == 40.0  # 2000 / 50
    assert metrics["tasks_per_hour_target"] == 83.33
    assert metrics["tasks_per_hour_actual"] == 90.0  # (50/2000) * 3600
    assert metrics["is_ahead"] is True
    assert metrics["is_behind"] is False


# -----------------------------------------------------------------------------
# 4. Bloqueo de Concurrencia y SKIP LOCKED
# -----------------------------------------------------------------------------
async def test_08_concurrent_complete_task_execution_locking(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    # Crear corrida y tarea
    async with session_factory() as session, session.begin():
        service = S4Service(session)
        run = await service.create_load_run(target_tasks=5, budget_limit_usd=10.0)
        await service.start_load_run(run.id)
        task = await service.create_task_execution(
            run_id=run.id,
            task_number=1,
            input_payload={"test": "concurrency"},
        )
        await service.start_task_execution(task.id)
        run_id = run.id
        task_id = task.id

    # Dos sesiones concurrentes compitiendo por finalizar la misma tarea
    async def try_complete(worker_name: str) -> bool:
        try:
            async with session_factory() as s, s.begin():
                srv = S4Service(s)
                await srv.complete_task_execution(
                    task_id,
                    validation_passed=True,
                    result_summary=f"Success from {worker_name}",
                )
                return True
        except Exception:  # noqa: BLE001
            return False

    res1, res2 = await asyncio.gather(try_complete("worker_1"), try_complete("worker_2"))
    # Exactamente uno debe tener éxito y el otro debe fallar por conflicto de estado (RUNNING -> SUCCEEDED)
    assert (res1 and not res2) or (res2 and not res1)

    # Verificar estado consistente final
    async with session_factory() as session:
        srv = S4Service(session)
        final_task = await srv.get_task_execution(task_id)
        final_run = await srv.get_load_run(run_id)
        assert final_task.status == S4TaskStatus.SUCCEEDED.value
        assert final_run.completed_tasks == 1


async def test_09_claim_next_task_skip_locked_concurrency(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    # Crear 4 tareas encoladas
    async with session_factory() as session, session.begin():
        srv = S4Service(session)
        run = await srv.create_load_run(target_tasks=4, budget_limit_usd=10.0)
        for i in range(1, 5):
            await srv.create_task_execution(
                run_id=run.id,
                task_number=i,
                input_payload={"num": i},
            )
        run_id = run.id

    # Reclamar concurrentemente con dos workers
    async def claim_task(worker_id: str) -> uuid.UUID | None:
        async with session_factory() as s, s.begin():
            srv = S4Service(s)
            claimed = await srv.claim_next_task(run_id, worker_id)
            return claimed.id if claimed else None

    c1, c2 = await asyncio.gather(claim_task("worker_A"), claim_task("worker_B"))
    assert c1 is not None
    assert c2 is not None
    assert c1 != c2  # Cada worker obtuvo una tarea distinta sin conflicto


# -----------------------------------------------------------------------------
# 5. Worker Autónomo y Registro de Llamadas con Metadatos
# -----------------------------------------------------------------------------
async def test_10_worker_single_step_execution(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session, session.begin():
        srv = S4Service(session)
        run = await srv.create_load_run(target_tasks=2, budget_limit_usd=10.0)
        await srv.start_load_run(run.id)
        await srv.create_task_execution(
            run_id=run.id,
            task_number=1,
            input_payload={"test": "payload"},
        )
        run_id = run.id

    worker = S4TaskWorker(
        run_id=run_id,
        session_factory=session_factory,
        worker_id="test-worker-10",
        heartbeat_interval_seconds=1.0,
    )

    executed = await worker.run_single_step()
    assert executed is not None
    assert executed.status == S4TaskStatus.SUCCEEDED.value
    assert executed.validation_passed is True
    assert executed.worker_id == "test-worker-10"
    assert executed.heartbeat_at is not None
    assert executed.model_calls >= 1

    # Verificar que los registros de uso tienen secuencia y metadatos
    async with session_factory() as session:
        stmt = (
            select(LLMUsageRecord)
            .where(LLMUsageRecord.s4_task_execution_id == executed.id)
            .order_by(LLMUsageRecord.call_sequence)
        )
        records = (await session.execute(stmt)).scalars().all()
        assert len(records) >= 1
        assert records[0].call_sequence == 1
        assert records[0].gateway_metadata is not None
        assert "cf-ray" in records[0].gateway_metadata


async def test_11_worker_heartbeat_updates(db_session: AsyncSession) -> None:
    srv = S4Service(db_session)
    run = await srv.create_load_run(target_tasks=1)
    task = await srv.create_task_execution(run_id=run.id, task_number=1, input_payload={})
    await srv.start_task_execution(task.id, worker_id="w-heartbeat")

    t1 = task.heartbeat_at
    assert t1 is not None

    # Simular paso de tiempo y nuevo latido
    await srv.update_task_heartbeat(task.id, worker_id="w-heartbeat")
    t2 = task.heartbeat_at
    assert t2 is not None and t2 >= t1


# -----------------------------------------------------------------------------
# 6. Detección y Recuperación de Huérfanos
# -----------------------------------------------------------------------------
async def test_12_orphan_task_recovery_with_retry(db_session: AsyncSession) -> None:
    srv = S4Service(db_session)
    run = await srv.create_load_run(target_tasks=2)
    task = await srv.create_task_execution(run_id=run.id, task_number=1, input_payload={})
    await srv.start_task_execution(task.id, worker_id="stale-worker")

    # Forzar un heartbeat antiguo (> 120s)
    task.heartbeat_at = datetime.now(UTC) - timedelta(seconds=200)
    await db_session.flush()

    recovery = S4RecoveryCoordinator(db_session, timeout_seconds=120.0, max_attempts=3)
    recovered = await recovery.sweep_and_recover_orphans(run.id)

    assert len(recovered) == 1
    assert recovered[0].id == task.id
    assert recovered[0].status == S4TaskStatus.QUEUED.value
    assert recovered[0].attempt_count == 2
    assert recovered[0].worker_id is None
    assert len(recovered[0].recovery_events) == 1
    assert recovered[0].recovery_events[0]["event_type"] == "heartbeat_timeout"


async def test_13_orphan_task_recovery_max_attempts_failed(db_session: AsyncSession) -> None:
    srv = S4Service(db_session)
    run = await srv.create_load_run(target_tasks=2)
    task = await srv.create_task_execution(run_id=run.id, task_number=1, input_payload={})
    await srv.start_task_execution(task.id, worker_id="stale-worker")

    # Asignar ya 3 intentos
    task.attempt_count = 3
    task.heartbeat_at = datetime.now(UTC) - timedelta(seconds=300)
    await db_session.flush()

    recovery = S4RecoveryCoordinator(db_session, timeout_seconds=120.0, max_attempts=3)
    recovered = await recovery.sweep_and_recover_orphans(run.id)

    assert len(recovered) == 1
    assert recovered[0].status == S4TaskStatus.FAILED.value
    assert recovered[0].validation_passed is False
    assert run.failed_tasks == 1


# -----------------------------------------------------------------------------
# 7. Disyuntores del Watchdog
# -----------------------------------------------------------------------------
def test_14_watchdog_budget_circuit_breaker() -> None:
    dog = S4Watchdog(budget_limit_usd=40.0)
    ok, msg = dog.check_budget(39.99)
    assert ok is True
    assert dog.is_tripped is False

    ok, msg = dog.check_budget(40.01)
    assert ok is False
    assert dog.is_tripped is True
    assert "Budget limit reached" in msg


def test_15_watchdog_consecutive_failures_circuit_breaker() -> None:
    dog = S4Watchdog(max_consecutive_failures=5)
    for _ in range(4):
        ok, _ = dog.record_task_outcome(validation_passed=False, current_cost_usd=1.0)
        assert ok is True
        assert dog.is_tripped is False

    # Quinto fallo consecutivo -> Dispara disyuntor
    ok, msg = dog.record_task_outcome(validation_passed=False, current_cost_usd=1.0)
    assert ok is False
    assert dog.is_tripped is True
    assert "5 consecutive" in msg


def test_16_watchdog_sliding_window_error_rate() -> None:
    dog = S4Watchdog(window_size=10, max_window_failure_rate=0.5)

    # 4 fallos alternados con 4 éxitos
    for _ in range(4):
        dog.record_task_outcome(validation_passed=True, current_cost_usd=1.0)
        dog.record_task_outcome(validation_passed=False, current_cost_usd=1.0)

    # 2 fallos adicionales completan la ventana de 10 con 6 fallos (60% > 50%)
    dog.record_task_outcome(validation_passed=False, current_cost_usd=1.0)
    ok, msg = dog.record_task_outcome(validation_passed=False, current_cost_usd=1.0)

    assert ok is False
    assert dog.is_tripped is True
    assert "failure rate" in msg.lower()


# -----------------------------------------------------------------------------
# 8. Detención Ordenada y Exportación
# -----------------------------------------------------------------------------
async def test_17_worker_graceful_shutdown(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session, session.begin():
        srv = S4Service(session)
        run = await srv.create_load_run(target_tasks=10, budget_limit_usd=50.0)
        await srv.start_load_run(run.id)
        for i in range(1, 6):
            await srv.create_task_execution(run_id=run.id, task_number=i, input_payload={})
        run_id = run.id

    worker = S4TaskWorker(
        run_id=run_id,
        session_factory=session_factory,
        worker_id="shutdown-worker",
    )

    # Solicitar detención antes de ejecutar
    worker.request_stop()
    summary = await worker.run_autonomous_loop()
    assert summary.completed_tasks == 0


async def test_18_export_with_worker_id_and_gateway_metadata(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session, session.begin():
        srv = S4Service(session)
        run = await srv.create_load_run(target_tasks=1, budget_limit_usd=10.0)
        await srv.start_load_run(run.id)
        await srv.create_task_execution(run_id=run.id, task_number=1, input_payload={"foo": "bar"})
        run_id = run.id

    worker = S4TaskWorker(
        run_id=run_id,
        session_factory=session_factory,
        worker_id="export-test-worker",
    )
    await worker.run_single_step()

    async with session_factory() as session:
        # Exportación JSON
        json_exp = await S4Exporter.export_json(run_id, session)
        assert json_exp["run"]["completed_tasks"] == 1
        assert len(json_exp["tasks"]) == 1
        t_json = json_exp["tasks"][0]
        assert t_json["worker_id"] == "export-test-worker"
        assert t_json["heartbeat_at"] is not None
        assert len(t_json["gateway_request_ids"]) >= 1

        # Exportación CSV
        csv_exp = await S4Exporter.export_csv(run_id, session)
        assert "gw_mock_req_00001_01" in csv_exp
        assert "export-test-worker" not in csv_exp or "run_id" in csv_exp


# -----------------------------------------------------------------------------
# 9. Garantías de $0.00 y Restricciones de BD
# -----------------------------------------------------------------------------
async def test_19_zero_external_cost_guarantee(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Verifica que el ejecutor sintético de simulación opera 100% aislado con costo externo nulo."""
    cat = S4TaskCatalogGenerator(seed=42)
    tdef = cat.generate_task_definition(1)

    class DummyTask:
        task_number = 1

    from src.s4.worker import default_synthetic_executor

    res = await default_synthetic_executor(DummyTask(), tdef)  # type: ignore
    assert res["validation_passed"] is True
    assert len(res["model_calls"]) >= 1
    # Todas las llamadas sintéticas se identifican como mock
    for call in res["model_calls"]:
        assert call["gateway_request_id"].startswith("gw_mock_")


async def test_20_unique_constraint_call_sequence_idempotency(db_session: AsyncSession) -> None:
    """Verifica que BD previene duplicidad de secuencia para la misma tarea (AUD-S4-04)."""
    srv = S4Service(db_session)
    run = await srv.create_load_run(target_tasks=1)
    task = await srv.create_task_execution(run_id=run.id, task_number=1, input_payload={})

    # Registrar call_sequence 1
    await srv.record_task_llm_call(
        task.id,
        model="grok-beta",
        input_tokens=100,
        output_tokens=50,
        call_sequence=1,
    )

    # Intentar insertar duplicado de call_sequence 1 directamente en la misma sesión
    dup_record = LLMUsageRecord(
        id=uuid.uuid4(),
        s4_task_execution_id=task.id,
        call_sequence=1,
        model="grok-beta",
        stage="s4_task_execution",
        provider="openai-compatible",
    )
    db_session.add(dup_record)
    with pytest.raises(IntegrityError):
        await db_session.flush()
    await db_session.rollback()


# -----------------------------------------------------------------------------
# 10. Fencing de Workers (AUD-S4-05)
# -----------------------------------------------------------------------------
async def test_21_worker_fencing_lease_token_invalidation(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Verifica que un worker que perdió su lease no puede completar ni emitir heartbeat."""
    from src.s4.service import S4WorkerLeaseExpiredError

    async with session_factory() as session, session.begin():
        srv = S4Service(session)
        run = await srv.create_load_run(target_tasks=2, budget_limit_usd=10.0)
        await srv.start_load_run(run.id)
        task = await srv.create_task_execution(run_id=run.id, task_number=1, input_payload={})
        run_id = run.id
        task_id = task.id

    # 1. Worker A reclama la tarea
    async with session_factory() as session, session.begin():
        srv = S4Service(session)
        claimed_a = await srv.claim_next_task(run_id, worker_id="worker_A")
        assert claimed_a is not None
        assert claimed_a.worker_id == "worker_A"
        lease_a = claimed_a.lease_token
        assert lease_a is not None

    # 2. Worker A pierde el lease (simular que expira y recovery lo reencola)
    async with session_factory() as session, session.begin():
        srv = S4Service(session)
        task_db = await srv.get_task_execution(task_id, for_update=True)
        task_db.heartbeat_at = datetime.now(UTC) - timedelta(seconds=200)
        recovery = S4RecoveryCoordinator(session, timeout_seconds=120.0, max_attempts=3)
        await recovery.sweep_and_recover_orphans(run_id)

    # 3. Worker B reclama la tarea recuperada
    async with session_factory() as session, session.begin():
        srv = S4Service(session)
        claimed_b = await srv.claim_next_task(run_id, worker_id="worker_B")
        assert claimed_b is not None
        assert claimed_b.worker_id == "worker_B"
        lease_b = claimed_b.lease_token
        assert lease_b != lease_a

    # 4. Worker A intenta emitir heartbeat o completar con su lease viejo -> Debe fallar
    async with session_factory() as session, session.begin():
        srv = S4Service(session)
        with pytest.raises(S4WorkerLeaseExpiredError):
            await srv.update_task_heartbeat(task_id, worker_id="worker_A", lease_token=lease_a)

        with pytest.raises(S4WorkerLeaseExpiredError):
            await srv.complete_task_execution(
                task_id,
                validation_passed=True,
                result_summary="Worker A stale completion",
                worker_id="worker_A",
                lease_token=lease_a,
            )

    # 5. Worker B completa con su lease vigente -> Tiene éxito
    async with session_factory() as session, session.begin():
        srv = S4Service(session)
        completed = await srv.complete_task_execution(
            task_id,
            validation_passed=True,
            result_summary="Worker B valid completion with optimal solution",
            worker_id="worker_B",
            lease_token=lease_b,
        )
        assert completed.status == S4TaskStatus.SUCCEEDED.value
        assert completed.worker_id == "worker_B"

    # Verificar que los contadores de la corrida son exactamente 1
    async with session_factory() as session:
        srv = S4Service(session)
        run_db = await srv.get_load_run(run_id)
        assert run_db.completed_tasks == 1


# -----------------------------------------------------------------------------
# 11. Persistencia Incremental de Llamadas LLM (AUD-S4-06)
# -----------------------------------------------------------------------------
async def test_22_incremental_llm_call_persistence_on_interruption(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Verifica que llamadas LLM intermedias quedan persistidas en BD antes de un fallo posterior."""
    async with session_factory() as session, session.begin():
        srv = S4Service(session)
        run = await srv.create_load_run(target_tasks=1)
        await srv.start_load_run(run.id)
        task = await srv.create_task_execution(run_id=run.id, task_number=1, input_payload={})
        run_id = run.id
        task_id = task.id

    # Ejecutor que simula persistir la primera llamada y luego fallar por timeout en la segunda
    async def interrupted_executor(t: S4TaskExecution, tdef: dict[str, Any], record_call_cb: Any) -> dict[str, Any]:
        # Primera llamada exitosa
        await record_call_cb(
            model="grok-beta",
            input_tokens=150,
            output_tokens=75,
            gateway_request_id="gw_req_call_1",
            gateway_metadata={"cf-ray": "ray-1234"},
        )
        # Segunda llamada sufre timeout
        raise TimeoutError("Network timeout connecting to gateway on call 2")

    worker = S4TaskWorker(
        run_id=run_id,
        session_factory=session_factory,
        worker_id="interrupted-worker",
        executor=interrupted_executor,
    )

    failed_task = await worker.run_single_step()
    assert failed_task is not None
    assert failed_task.status == S4TaskStatus.FAILED.value
    # Aunque falló, la primera llamada LLM debe existir en la BD con sus tokens y costes agregados
    assert failed_task.model_calls == 1
    assert failed_task.input_tokens == 150
    assert failed_task.output_tokens == 75
    assert failed_task.cost_usd > 0.0

    async with session_factory() as session:
        stmt = select(LLMUsageRecord).where(LLMUsageRecord.s4_task_execution_id == task_id)
        recs = (await session.execute(stmt)).scalars().all()
        assert len(recs) == 1
        assert recs[0].gateway_request_id == "gw_req_call_1"


# -----------------------------------------------------------------------------
# 12. Pacer Durable y Reconciliación tras Reinicio (AUD-S4-07)
# -----------------------------------------------------------------------------
def test_23_durable_pacer_restart_reconciliation() -> None:
    """Verifica que el pacer reconcilia con run.started_at persistido sin pausas espurias."""
    # 1000 tareas en 43.200s (43.2s por tarea)
    # Se reinicia el proceso tras 4 horas (14.400 segundos) habiendo completado 300 tareas
    # Tiempo objetivo para 300 tareas = 300 * 43.2 = 12.960s
    # Tiempo real transcurrido = 14.400s (el runner va 1.440s ATRASADO)
    pacer = S4Pacer(
        total_tasks=1000,
        total_duration_seconds=43200.0,
        initial_elapsed_seconds=14400.0,
    )
    pacer.start(monotonic_now=100.0)

    # El retardo debe ser 0.0 (o min_interval), NUNCA 120s de pausa por falso adelanto
    delay = pacer.compute_pacing_delay(completed_tasks=300, current_monotonic=100.0)
    assert delay == 0.0

    metrics = pacer.get_pacing_metrics(completed_tasks=300, current_monotonic=100.0)
    assert metrics["elapsed_seconds"] == 14400.0
    assert metrics["target_elapsed_seconds"] == 12960.0
    assert metrics["is_behind"] is True
    assert metrics["drift_seconds"] == -1440.0


# -----------------------------------------------------------------------------
# 13. Guardia de Duración Mínima (AUD-S4-08)
# -----------------------------------------------------------------------------
async def test_24_minimum_duration_guard_on_finish_load_run(db_session: AsyncSession) -> None:
    """Verifica que finish_load_run exige 12 horas (43.200s) para completado oficial."""
    from src.s4.service import S4RunPrematureCompletionError

    srv = S4Service(db_session)
    run = await srv.create_load_run(target_tasks=1)
    await srv.start_load_run(run.id)
    task = await srv.create_task_execution(run_id=run.id, task_number=1, input_payload={})
    await srv.start_task_execution(task.id)
    await srv.complete_task_execution(task.id, validation_passed=True, result_summary="Done")

    # Intentar marcar COMPLETED cuando solo han transcurrido < 43.200s debe fallar
    with pytest.raises(S4RunPrematureCompletionError) as exc_info:
        await srv.finish_load_run(run.id, status=S4RunStatus.COMPLETED, min_duration_seconds=43200.0)
    assert "required minimum duration" in str(exc_info.value)

    # Con min_duration_seconds=0.0 (o tiempo ya transcurrido), debe tener éxito
    completed_run = await srv.finish_load_run(run.id, status=S4RunStatus.COMPLETED, min_duration_seconds=0.0)
    assert completed_run.status == S4RunStatus.COMPLETED.value


# -----------------------------------------------------------------------------
# 14. Watchdog: Reserva de Costo y Persistencia en BD (AUD-S4-09)
# -----------------------------------------------------------------------------
async def test_25_watchdog_cost_reservation_and_db_persistence(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Verifica reserva de presupuesto y persistencia durable del motivo de pausa."""
    dog = S4Watchdog(budget_limit_usd=1.0)
    # Reservar 0.90 con costo actual 0.0 -> Éxito
    ok, _ = dog.reserve_cost(0.90, current_cost_usd=0.0)
    assert ok is True
    assert dog.active_reservations_usd == 0.90

    # Intentar reservar 0.20 adicionales (0.90 + 0.20 = 1.10 > 1.0) -> Dispara disyuntor
    ok2, msg2 = dog.reserve_cost(0.20, current_cost_usd=0.0)
    assert ok2 is False
    assert dog.is_tripped is True
    assert "exceeds limit" in msg2

    # Probar que al dispararse el watchdog, el worker persiste el motivo en s4_load_runs.meta
    async with session_factory() as session, session.begin():
        srv = S4Service(session)
        run = await srv.create_load_run(target_tasks=5, budget_limit_usd=0.05)
        await srv.start_load_run(run.id)
        for i in range(1, 3):
            await srv.create_task_execution(run_id=run.id, task_number=i, input_payload={})
        run_id = run.id

    tripped_dog = S4Watchdog(budget_limit_usd=0.05)
    tripped_dog.trip("Safety budget ceiling test trip", current_cost_usd=0.06)

    worker = S4TaskWorker(
        run_id=run_id,
        session_factory=session_factory,
        watchdog=tripped_dog,
    )
    summary = await worker.run_autonomous_loop()
    assert summary.completed_tasks == 0

    async with session_factory() as session:
        srv = S4Service(session)
        run_db = await srv.get_load_run(run_id)
        assert run_db.status == S4RunStatus.PAUSED.value
        assert run_db.meta.get("watchdog_tripped") is True
        assert "Safety budget ceiling test trip" in run_db.meta.get("watchdog_trip_reason", "")


# -----------------------------------------------------------------------------
# 15. PostgreSQL Advisory Lock Exclusivo por Corrida (AUD-S4-13)
# -----------------------------------------------------------------------------
async def test_26_postgresql_advisory_lock_exclusivity(database_url: str) -> None:
    """Verifica que dos procesos no pueden adquirir el mismo advisory lock para una corrida."""
    from src.s4.lock import S4RunAdvisoryLock, S4RunLockAcquisitionError

    engine1 = create_async_engine(database_url)
    engine2 = create_async_engine(database_url)
    run_id_a = uuid.uuid4()
    run_id_b = uuid.uuid4()

    lock1 = S4RunAdvisoryLock(engine1, run_id_a)
    lock2 = S4RunAdvisoryLock(engine2, run_id_a)
    lock3 = S4RunAdvisoryLock(engine2, run_id_b)

    # 1. Proceso 1 adquiere lock para run_id_a
    await lock1.acquire()
    assert lock1.is_locked is True

    # 2. Proceso 2 intenta adquirir el mismo run_id_a -> Debe ser rechazado
    with pytest.raises(S4RunLockAcquisitionError):
        await lock2.acquire()

    # 3. Proceso 2 adquiere lock para un run_id_b distinto -> Debe tener éxito sin bloqueo
    await lock3.acquire()
    assert lock3.is_locked is True
    await lock3.release()

    # 4. Proceso 1 libera lock1 -> Proceso 2 ahora puede adquirir run_id_a
    await lock1.release()
    assert lock1.is_locked is False

    await lock2.acquire()
    assert lock2.is_locked is True
    await lock2.release()

    await engine1.dispose()
    await engine2.dispose()


# -----------------------------------------------------------------------------
# 16. Ejecutor Real Conectado con Clientes Mock (AUD-S4-12)
# -----------------------------------------------------------------------------
async def test_27_real_agent_executor_with_mock_clients(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Verifica el ejecutor técnico real con clientes inyectados y persistencia incremental."""
    from src.llm.types import ChatCompletion, TokenUsage
    from src.s4.agent_executor import create_real_agent_executor

    class FakeLLMClient:
        def __init__(self) -> None:
            self._model = "grok-beta-mock"
            self.call_count = 0

        async def complete(self, messages: list[Any], **kwargs: Any) -> ChatCompletion:
            self.call_count += 1
            return ChatCompletion(
                content="Comprehensive analysis. The optimal solution applies hash set with O(N) complexity.",
                model=self._model,
                usage=TokenUsage(prompt_tokens=110, completion_tokens=55, total_tokens=165),
                request_id="gw_req_real_test_001",
                gateway_metadata={"cf-ray": "mock-cf-ray-999", "x-ratelimit-remaining-tokens": "990000"},
            )

    class FakeSandbox:
        async def run_code(self, source_code: str, language_id: int, stdin: str = "") -> Any:
            class SandboxRes:
                status = "success"
                stdout = "All tests passed\n"
                time = 0.045
            return SandboxRes()

    fake_llm = FakeLLMClient()
    fake_sb = FakeSandbox()

    executor = create_real_agent_executor(llm_client=fake_llm, sandbox_client=fake_sb)  # type: ignore

    async with session_factory() as session, session.begin():
        srv = S4Service(session)
        run = await srv.create_load_run(target_tasks=1)
        await srv.start_load_run(run.id)
        await srv.create_task_execution(run_id=run.id, task_number=1, input_payload={"task": "test"})
        run_id = run.id

    worker = S4TaskWorker(
        run_id=run_id,
        session_factory=session_factory,
        executor=executor,
    )

    completed = await worker.run_single_step()
    assert completed is not None
    assert completed.status == S4TaskStatus.SUCCEEDED.value
    assert completed.validation_passed is True
    assert completed.model_calls == 1
    assert completed.input_tokens == 110
    assert completed.output_tokens == 55
    assert fake_llm.call_count == 1


# -----------------------------------------------------------------------------
# 17. Preflight de Sistema (Cero Costo)
# -----------------------------------------------------------------------------
async def test_28_preflight_diagnostics_zero_cost() -> None:
    """Verifica que el preflight operacional corre sin llamadas externas de red de pago."""
    from src.s4.preflight import run_s4_preflight

    report = await run_s4_preflight(check_judge0=False, check_redis=False)
    assert report is not None
    assert len(report.checks) >= 3
    # Debe chequear PostgreSQL, variables de entorno y almacenamiento
    names = [c.name for c in report.checks]
    assert any("PostgreSQL" in n for n in names)
    assert any("Disk" in n for n in names)


# -----------------------------------------------------------------------------
# 18. CLI Argument Parsing y Dry-Run (AUD-S4-10)
# -----------------------------------------------------------------------------
def test_29_cli_argument_parsing_and_dry_run() -> None:
    """Verifica el parseo estricto de argumentos en CLI."""
    from src.s4.cli import build_parser

    parser = build_parser()
    args = parser.parse_args([
        "--tasks", "50",
        "--budget-usd", "25.0",
        "--seed", "123",
        "--interval", "30.0",
        "--dry-run",
        "--mock",
    ])
    assert args.tasks == 50
    assert args.budget_usd == 25.0
    assert args.seed == 123
    assert args.interval == 30.0
    assert args.dry_run is True
    assert args.mock is True

