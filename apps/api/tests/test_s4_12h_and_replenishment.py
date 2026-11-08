"""Pruebas de verificación de los 16 escenarios obligatorios de S4:
Actividad real de 12 horas, reposición dinámica, resiliencia y telemetría de proveedor.
"""

from __future__ import annotations

import csv
import io
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.db.models.interview import LLMUsageRecord
from src.db.models.s4 import S4TaskExecution
from src.llm.types import ChatCompletion, TokenUsage
from src.s4.agent_executor import create_real_agent_executor
from src.s4.catalog import S4TaskCatalogGenerator
from src.s4.enums import S4RunStatus, S4TaskStatus, S4TaskType
from src.s4.exporter import S4Exporter
from src.s4.recovery import S4RecoveryCoordinator
from src.s4.service import S4RunIncompleteError, S4RunPrematureCompletionError, S4Service
from src.s4.watchdog import S4CircuitState, S4Watchdog
from src.s4.worker import S4TaskWorker, default_synthetic_executor
from src.sandbox.types import ExecutionStatus, RunRequest, RunResult


@pytest.fixture
def session_factory(database_url: str) -> async_sessionmaker[AsyncSession]:
    engine = create_async_engine(database_url, echo=False)
    return async_sessionmaker(engine, expire_on_commit=False)


# =============================================================================
# ESCENARIOS 1 & 7: Reposición dinámica ante fallos y cola vacía
# =============================================================================
@pytest.mark.asyncio
async def test_scenario_01_and_07_dynamic_replenishment_until_target_successes(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Escenario 1 & 7: Corrida con objetivo de 5 éxitos y 2 fallos.
    La cola se vacía con 3 éxitos y 2 fallos; el worker repone dinámicamente tareas
    adicionales hasta alcanzar los 5 éxitos requeridos.
    """
    cat = S4TaskCatalogGenerator(seed=42)

    # Simular: tareas 2 y 4 fallan deliberadamente; las demás ejecutan con default_synthetic_executor
    async def mock_executor(task: S4TaskExecution, task_def: Any, *args: Any, **kwargs: Any) -> dict[str, Any]:
        if task.task_number in (2, 4):
            return {
                "validation_passed": False,
                "summary": "Task failed deliberate validation check.",
                "error_sanitized": "AssertionError: expected output mismatch",
                "model_calls": [{"model": "grok-beta", "input_tokens": 100, "output_tokens": 50}],
            }
        return await default_synthetic_executor(task, task_def)

    dog = S4Watchdog(budget_limit_usd=35.0)

    async with session_factory() as session, session.begin():
        srv = S4Service(session)
        # Target: 5 éxitos
        run = await srv.create_load_run(target_tasks=5)
        await srv.start_load_run(run.id)
        # Encolar inicialmente solo 5 tareas
        for i in range(1, 6):
            tdef = cat.generate_task_definition(i)
            await srv.create_task_execution(
                run_id=run.id,
                task_number=i,
                task_type=tdef["task_type"],
                input_payload=tdef,
            )
        run_id = run.id

    worker = S4TaskWorker(
        run_id=run_id,
        session_factory=session_factory,
        catalog=cat,
        watchdog=dog,
        executor=mock_executor,
        min_duration_seconds=0.0,
    )

    summary = await worker.run_autonomous_loop()

    # Debe haber alcanzado exactamente 5 éxitos, procesando 7 tareas en total (5 éxitos + 2 fallos)
    assert summary.completed_tasks == 5
    assert summary.failed_tasks == 2
    assert summary.total_tasks_recorded == 7

    async with session_factory() as session:
        stmt = select(S4TaskExecution).where(S4TaskExecution.run_id == run_id)
        tasks = (await session.execute(stmt)).scalars().all()
        assert len(tasks) == 7
        succeeded = [t for t in tasks if t.status == S4TaskStatus.SUCCEEDED.value]
        failed = [t for t in tasks if t.status == S4TaskStatus.FAILED.value]
        assert len(succeeded) == 5
        assert len(failed) == 2


# =============================================================================
# ESCENARIO 2: Corrida alcanza 1.000 éxitos antes de 12h: continúa hasta 12h
# =============================================================================
@pytest.mark.asyncio
async def test_scenario_02_continues_replenishing_if_duration_not_met(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Escenario 2: Si completed_tasks >= target_tasks pero elapsed < min_duration_seconds,
    el bucle continúa generando tareas y no se detiene prematuramente.
    """
    cat = S4TaskCatalogGenerator(seed=101)
    dog = S4Watchdog(budget_limit_usd=35.0)

    async with session_factory() as session, session.begin():
        srv = S4Service(session)
        run = await srv.create_load_run(target_tasks=3)
        await srv.start_load_run(run.id)
        for i in range(1, 4):
            tdef = cat.generate_task_definition(i)
            await srv.create_task_execution(
                run_id=run.id,
                task_number=i,
                task_type=tdef["task_type"],
                input_payload=tdef,
            )
        run_id = run.id

    # min_duration_seconds = 43200s (12h).
    # Con max_tasks=5, el bucle debe seguir hasta 5 tareas a pesar de que target_tasks=3 ya se cumplió.
    worker = S4TaskWorker(
        run_id=run_id,
        session_factory=session_factory,
        catalog=cat,
        watchdog=dog,
        executor=default_synthetic_executor,
        min_duration_seconds=43200.0,
    )

    summary = await worker.run_autonomous_loop(max_tasks=5)

    assert summary.completed_tasks == 5
    assert summary.total_tasks_recorded == 5


# =============================================================================
# ESCENARIO 3: Corrida alcanza 12h con 970 éxitos: continúa hasta 1.000 éxitos
# =============================================================================
@pytest.mark.asyncio
async def test_scenario_03_continues_if_success_target_not_met_even_after_12h(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Escenario 3: Si transcurrieron las 12 horas pero los éxitos < objetivo,
    el bucle continúa generando tareas hasta alcanzar los éxitos requeridos.
    """
    cat = S4TaskCatalogGenerator(seed=202)
    dog = S4Watchdog(budget_limit_usd=35.0)

    # Creamos un run cuya fecha de inicio fue hace 13 horas (46800s > 43200s)
    # con ventana continua de llamadas LLM >= 12h, pero solo tiene 2 éxitos contra un target de 4.
    now_utc = datetime.now(UTC)
    started_13h_ago = now_utc - timedelta(hours=13)
    window_start = now_utc - timedelta(seconds=43300)

    async with session_factory() as session, session.begin():
        srv = S4Service(session)
        run = await srv.create_load_run(target_tasks=4)
        run_db = await srv.get_load_run(run.id, for_update=True)
        run_db.status = S4RunStatus.ACTIVE.value
        run_db.started_at = started_13h_ago
        # Inicializamos con solo 2 tareas encoladas
        created_tasks = []
        for i in range(1, 3):
            tdef = cat.generate_task_definition(i)
            t_exec = await srv.create_task_execution(
                run_id=run.id,
                task_number=i,
                task_type=tdef["task_type"],
                input_payload=tdef,
            )
            created_tasks.append(t_exec)
        # Sembrar ventana continua ininterrumpida (>= 43.200s, gaps de 100s <= 120s) hasta now_utc
        for seq_idx in range(434):
            session.add(
                LLMUsageRecord(
                    interview_id=None,
                    s4_task_execution_id=created_tasks[0].id,
                    model="grok-beta",
                    tokens_input=50,
                    tokens_output=25,
                    tokens_total=75,
                    cost_usd=0.0001,
                    measurement_status="measured",
                    call_sequence=seq_idx + 10,
                    created_at=window_start + timedelta(seconds=seq_idx * 100),
                )
            )
        run_id = run.id

    worker = S4TaskWorker(
        run_id=run_id,
        session_factory=session_factory,
        catalog=cat,
        watchdog=dog,
        executor=default_synthetic_executor,
        min_duration_seconds=43200.0,
    )

    summary = await worker.run_autonomous_loop()

    # Aunque ya pasaron 13 horas, no terminó en 2 sino que repuso hasta alcanzar los 4 éxitos requeridos
    assert summary.completed_tasks == 4
    assert summary.total_tasks_recorded == 4


# =============================================================================
# ESCENARIO 4: Procesamiento de más de 1.000 tareas sin duplicar task_number
# =============================================================================
@pytest.mark.asyncio
async def test_scenario_04_no_duplicate_task_numbers_above_1000(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Escenario 4: get_next_task_number es atómico y garantiza unicidad estricta
    incluso cuando se superan las 1.000 tareas.
    """
    cat = S4TaskCatalogGenerator(seed=303)

    async with session_factory() as session, session.begin():
        srv = S4Service(session)
        run = await srv.create_load_run(target_tasks=1000)
        # Simulamos que ya existen tareas hasta la 1005
        for i in [1, 500, 1000, 1001, 1002, 1003, 1004, 1005]:
            tdef = cat.generate_task_definition(i)
            await srv.create_task_execution(
                run_id=run.id,
                task_number=i,
                task_type=tdef["task_type"],
                input_payload=tdef,
            )
        run_id = run.id

    async with session_factory() as session:
        srv = S4Service(session)
        next_num_1 = await srv.get_next_task_number(run_id)
        assert next_num_1 == 1006

    async with session_factory() as session, session.begin():
        srv = S4Service(session)
        tdef = cat.generate_task_definition(next_num_1)
        await srv.create_task_execution(
            run_id=run_id,
            task_number=next_num_1,
            task_type=tdef["task_type"],
            input_payload=tdef,
        )

    async with session_factory() as session:
        srv = S4Service(session)
        next_num_2 = await srv.get_next_task_number(run_id)
        assert next_num_2 == 1007


# =============================================================================
# ESCENARIO 5: Reanudación con tareas en QUEUED, RUNNING, SUCCEEDED y FAILED
# =============================================================================
@pytest.mark.asyncio
async def test_scenario_05_resumption_with_all_states(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Escenario 5: Reanudación de corrida con tareas en QUEUED, RUNNING, SUCCEEDED y FAILED.
    RUNNING vencida es recuperada a QUEUED; SUCCEEDED y FAILED se preservan intactas.
    """
    cat = S4TaskCatalogGenerator(seed=404)

    async with session_factory() as session, session.begin():
        srv = S4Service(session)
        run = await srv.create_load_run(target_tasks=4)
        await srv.start_load_run(run.id)

        # 1. SUCCEEDED
        t1 = await srv.create_task_execution(
            run_id=run.id,
            task_number=1,
            task_type=S4TaskType.GENERAL_TECHNICAL,
            input_payload=cat.generate_task_definition(1),
        )
        t1.status = S4TaskStatus.SUCCEEDED.value
        t1.validation_passed = True

        # 2. FAILED
        t2 = await srv.create_task_execution(
            run_id=run.id,
            task_number=2,
            task_type=S4TaskType.BENCHMARK_EVALUATION,
            input_payload=cat.generate_task_definition(2),
        )
        t2.status = S4TaskStatus.FAILED.value
        t2.validation_passed = False

        # 3. RUNNING vencida (hace 10 minutos)
        t3 = await srv.create_task_execution(
            run_id=run.id,
            task_number=3,
            task_type=S4TaskType.AUTONOMOUS_CODING,
            input_payload=cat.generate_task_definition(3),
        )
        t3.status = S4TaskStatus.RUNNING.value
        t3.heartbeat_at = datetime.now(UTC) - timedelta(minutes=10)
        t3.lease_token = "expired-token"

        # 4. QUEUED
        t4 = await srv.create_task_execution(
            run_id=run.id,
            task_number=4,
            task_type=S4TaskType.ADVERSARIAL_SECURITY,
            input_payload=cat.generate_task_definition(4),
        )
        t4.status = S4TaskStatus.QUEUED.value

        run_id = run.id

    # Recuperación con S4RecoveryCoordinator
    async with session_factory() as session, session.begin():
        rec = S4RecoveryCoordinator(session, timeout_seconds=60.0)
        recovered = await rec.sweep_and_recover_orphans(run_id)
        assert len(recovered) == 1

    async with session_factory() as session:
        stmt = select(S4TaskExecution).where(S4TaskExecution.run_id == run_id)
        tasks = (await session.execute(stmt)).scalars().all()
        task_map = {t.task_number: t for t in tasks}
        assert task_map[1].status == S4TaskStatus.SUCCEEDED.value
        assert task_map[2].status == S4TaskStatus.FAILED.value
        assert task_map[3].status == S4TaskStatus.QUEUED.value  # recuperada
        assert task_map[4].status == S4TaskStatus.QUEUED.value


# =============================================================================
# ESCENARIO 6: Reinicio del proceso sin perder medición de actividad previa
# =============================================================================
@pytest.mark.asyncio
async def test_scenario_06_process_restart_preserves_activity_metrics(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Escenario 6: Al reiniciar el proceso, get_run_statistics y rehydrate_circuit_state
    reconstruyen fielmente first_llm_call_at, last_llm_call_at, pasivos y llamadas LLM.
    """
    run_id = uuid.uuid4()
    first_time = datetime.now(UTC) - timedelta(hours=6)
    last_time = datetime.now(UTC) - timedelta(minutes=15)

    async with session_factory() as session, session.begin():
        srv = S4Service(session)
        await srv.create_load_run(
            run_id=run_id,
            target_tasks=10,
            meta={"uncertain_liabilities_usd": 0.10, "circuit_state": "COOLING_DOWN"},
        )
        task = await srv.create_task_execution(
            run_id=run_id,
            task_number=1,
            task_type=S4TaskType.GENERAL_TECHNICAL,
            input_payload={},
        )

        call1 = LLMUsageRecord(
            interview_id=None,
            s4_task_execution_id=task.id,
            model="grok-beta",
            tokens_input=100,
            tokens_output=50,
            tokens_total=150,
            cost_usd=0.005,
            gateway_request_id="gw_req_001",
            call_sequence=1,
            created_at=first_time,
        )
        call2 = LLMUsageRecord(
            interview_id=None,
            s4_task_execution_id=task.id,
            model="grok-beta",
            tokens_input=150,
            tokens_output=80,
            tokens_total=230,
            cost_usd=0.008,
            gateway_request_id="gw_req_002",
            call_sequence=2,
            created_at=last_time,
        )
        session.add_all([call1, call2])

    async with session_factory() as session:
        srv = S4Service(session)
        summary = await srv.get_run_statistics(run_id)

        assert summary.calls_with_usage == 2
        assert summary.first_llm_call_at is not None
        assert summary.last_llm_call_at is not None
        assert summary.llm_activity_duration_seconds is not None
        assert summary.llm_activity_duration_seconds > 20000.0  # ~5.75 horas
        assert len(summary.hourly_distribution) >= 1

    dog = S4Watchdog(budget_limit_usd=35.0)
    dog.rehydrate_circuit_state({"circuit_state": "COOLING_DOWN"}, is_manual_resume=True)
    assert dog.circuit_state == S4CircuitState.PROBING


# =============================================================================
# ESCENARIOS 8 & 9: Circuit Breaker cooldown, recuperación segura y PERMANENT_TRIP
# =============================================================================
def test_scenario_08_and_09_watchdog_cooldown_recovery_and_permanent_trip() -> None:
    """Escenarios 8 & 9: El watchdog entra en COOLING_DOWN ante fallos repetidos,
    se recupera a HEALTHY si la sonda es exitosa, pero entra en PERMANENT_TRIP
    si se agotan los ciclos máximos de enfriamiento.
    """
    dog = S4Watchdog(
        budget_limit_usd=35.0,
        max_consecutive_failures=3,
        cooldown_seconds=0.05,
        max_cooldown_cycles=2,
    )

    # 1. Registrar 3 fallos consecutivos -> entra en COOLING_DOWN (ciclo 1)
    for _ in range(3):
        dog.record_task_outcome(validation_passed=False, current_cost_usd=0.0, error_details="Gateway 504")

    assert dog.circuit_state == S4CircuitState.COOLING_DOWN
    assert dog._cooldown_cycles == 1

    # Avanzar a PROBING
    dog._last_cooldown_started_at = datetime.now(UTC) - timedelta(seconds=1)
    can_probe, _ = dog.check_and_advance_cooldown()
    assert can_probe is True
    assert dog.circuit_state == S4CircuitState.PROBING

    # Si la sonda tiene éxito, se restablece a HEALTHY
    dog.record_task_outcome(validation_passed=True, current_cost_usd=0.0)
    assert dog.circuit_state == S4CircuitState.HEALTHY
    assert dog._consecutive_failures == 0

    # 2. Provocar nuevo disparo y agotar ciclos de cooldown hasta PERMANENT_TRIP
    for _ in range(3):
        dog.record_task_outcome(validation_passed=False, current_cost_usd=0.0, error_details="Gateway 504")
    assert dog.circuit_state == S4CircuitState.COOLING_DOWN
    assert dog._cooldown_cycles == 1

    dog._last_cooldown_started_at = datetime.now(UTC) - timedelta(seconds=1)
    dog.check_and_advance_cooldown()
    # Sonda 1 falla -> re-dispara cooldown (ciclo 2)
    dog.record_task_outcome(validation_passed=False, current_cost_usd=0.0, error_details="Probe 1 failed")
    assert dog.circuit_state == S4CircuitState.COOLING_DOWN
    assert dog._cooldown_cycles == 2

    dog._last_cooldown_started_at = datetime.now(UTC) - timedelta(seconds=1)
    dog.check_and_advance_cooldown()
    # Sonda 2 falla -> agota ciclos máximos -> PERMANENT_TRIP
    dog.record_task_outcome(validation_passed=False, current_cost_usd=0.0, error_details="Probe 2 failed")
    assert dog.circuit_state == S4CircuitState.PERMANENT_TRIP
    assert dog.is_permanent_trip is True


# =============================================================================
# ESCENARIO 10: Presupuesto agotado en llamada inicial: tarea abortada sin llamada
# =============================================================================
@pytest.mark.asyncio
async def test_scenario_10_budget_exhausted_aborts_task_cleanly() -> None:
    """Escenario 10: Si el presupuesto total está agotado, el watchdog bloquea la reserva
    y la corrida se detiene limpiamente sin llamadas fantasmas.
    """
    dog = S4Watchdog(budget_limit_usd=1.00)
    # Gastar $0.98 de $1.00; una reserva estimada en $0.05 excede el presupuesto
    reserved_ok, msg = dog.reserve_cost(0.05, current_cost_usd=0.98)
    assert reserved_ok is False
    assert "exceeds limit" in msg


# =============================================================================
# ESCENARIO 11: Presupuesto insuficiente para corrección: conserva error sin llamada
# =============================================================================
@pytest.mark.asyncio
async def test_scenario_11_insufficient_budget_aborts_correction_preserving_error(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Escenario 11: Si hay error en sandbox pero el presupuesto no alcanza para la corrección,
    se aborta el bucle de corrección conservando el código con error y sin hacer llamada LLM adicional.
    """
    call_count = 0

    class MockLLM:
        def __init__(self) -> None:
            self._model = "grok-mock"

        async def complete(self, messages: list[Any], **kwargs: Any) -> ChatCompletion:
            nonlocal call_count
            call_count += 1
            code = "def find_duplicates(items):\n    syntax error"
            return ChatCompletion(
                content=f"Initial code.\n```python\n{code}\n```\noptimal complexity verified.",
                model=self._model,
                usage=TokenUsage(prompt_tokens=100, completion_tokens=30, total_tokens=130),
            )

    class FailingSandbox:
        async def run(self, request: RunRequest) -> RunResult:
            return RunResult(
                status=ExecutionStatus.COMPILE_ERROR,
                stdout="",
                stderr="SyntaxError",
                compile_output="SyntaxError",
                exit_code=1,
            )

    # Watchdog con límite de $0.05. La reserva para corrección será rechazada.
    tight_dog = S4Watchdog(budget_limit_usd=0.05)
    executor = create_real_agent_executor(llm_client=MockLLM(), sandbox_client=FailingSandbox())  # type: ignore

    async with session_factory() as session, session.begin():
        srv = S4Service(session)
        run = await srv.create_load_run(target_tasks=1, budget_limit_usd=0.05)
        await srv.start_load_run(run.id)
        await srv.create_task_execution(
            run_id=run.id,
            task_number=1,
            task_type=S4TaskType.GENERAL_TECHNICAL,
            input_payload={},
        )
        run_id = run.id

    worker = S4TaskWorker(
        run_id=run_id,
        session_factory=session_factory,
        watchdog=tight_dog,
        executor=executor,
    )

    step = await worker.run_single_step()
    assert step is not None
    assert step.validation_passed is False
    # Verificamos que no se realizó llamada LLM adicional para corrección (exactamente 1 llamada inicial)
    assert call_count == 1
    assert "compile_error" in str(step.error_sanitized).lower()


# =============================================================================
# ESCENARIO 12: ReadTimeout retiene pasivo incierto y bloquea reintento inmediato
# =============================================================================
def test_scenario_12_read_timeout_retains_uncertain_liability() -> None:
    """Escenario 12: Ante ReadTimeout / WriteTimeout, el watchdog retiene un pasivo
    incierto estimado de $0.05 y bloquea reintentos ciegos.
    """
    dog = S4Watchdog(budget_limit_usd=0.10)
    assert dog.uncertain_liabilities_usd == 0.0

    dog.reserve_cost(0.05, current_cost_usd=0.0)
    dog.retain_uncertain_liability(0.05)
    assert dog.uncertain_liabilities_usd == 0.05
    assert dog.total_exposure_usd(current_cost_usd=0.0) == 0.05

    # Un segundo timeout acumula otro pasivo
    dog.reserve_cost(0.05, current_cost_usd=0.0)
    dog.retain_uncertain_liability(0.05)
    assert dog.uncertain_liabilities_usd == 0.10
    assert dog.total_exposure_usd(current_cost_usd=0.0) == 0.10

    # Ahora el presupuesto ($0.10) está totalmente comprometido con pasivos inciertos
    reserved_ok, msg = dog.reserve_cost(0.01, current_cost_usd=0.0)
    assert reserved_ok is False
    assert "exceeds limit" in msg


# =============================================================================
# ESCENARIOS 13 & 14: Exportación CSV/JSON con >1.000 tareas y evidencia temporal 12h
# =============================================================================
@pytest.mark.asyncio
async def test_scenario_13_and_14_export_and_12h_telemetry_evidence(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Escenarios 13 & 14: Exportación JSON/CSV con más de 1.000 tareas y comprobación
    de la evidencia temporal de 12 horas (first_llm_call_at, last_llm_call_at,
    llm_activity_duration_seconds, llamadas con uso y distribución horaria).
    """
    cat = S4TaskCatalogGenerator(seed=505)
    run_id = uuid.uuid4()
    base_time = datetime.now(UTC) - timedelta(hours=12, minutes=5)

    async with session_factory() as session, session.begin():
        srv = S4Service(session)
        run = await srv.create_load_run(run_id=run_id, target_tasks=1000)
        await srv.start_load_run(run.id)

        # Insertar 1.005 tareas con llamadas distribuidas en las 12 horas
        for i in range(1, 1006):
            tdef = cat.generate_task_definition(i)
            task = await srv.create_task_execution(
                run_id=run_id,
                task_number=i,
                task_type=tdef["task_type"],
                input_payload=tdef,
            )
            task.status = S4TaskStatus.SUCCEEDED.value
            task.validation_passed = True
            call_time = base_time + timedelta(seconds=i * 43.2)  # distribuido a lo largo de 12h (> 43200s)

            rec = LLMUsageRecord(
                interview_id=None,
                s4_task_execution_id=task.id,
                model="grok-beta",
                tokens_input=100,
                tokens_output=50,
                tokens_total=150,
                cost_usd=0.001,
                gateway_request_id=f"gw_req_{i:05d}",
                call_sequence=1,
                created_at=call_time,
            )
            session.add(rec)

        # Actualizar contadores y estado final
        run_db = await srv.get_load_run(run.id, for_update=True)
        run_db.status = S4RunStatus.COMPLETED.value
        run_db.started_at = base_time
        run_db.finished_at = datetime.now(UTC)
        run_db.completed_tasks = 1005

    # Verificar exportación JSON y CSV
    async with session_factory() as session:
        json_data = await S4Exporter.export_json(run_id, session)
        csv_str = await S4Exporter.export_csv(run_id, session)

    assert json_data["run"]["completed_tasks"] == 1005
    assert len(json_data["tasks"]) == 1005
    assert json_data["run"]["calls_with_usage"] == 1005
    assert json_data["run"]["llm_activity_duration_seconds"] is not None
    assert json_data["run"]["llm_activity_duration_seconds"] >= 43200.0  # >= 12 horas
    assert len(json_data["run"]["hourly_distribution"]) >= 12

    # CSV debe tener encabezado + 1005 filas
    lines = csv_str.strip().split("\n")
    assert len(lines) == 1006
    reader = csv.DictReader(io.StringIO(csv_str))
    rows = list(reader)
    assert len(rows) == 1005
    assert "gw_req_00001" in rows[0]["gateway_request_ids"]
    assert "gw_req_01005" in rows[-1]["gateway_request_ids"]


# =============================================================================
# ESCENARIO 15: Finalizar con 1.000 éxitos pero < 12h es rechazado
# =============================================================================
@pytest.mark.asyncio
async def test_scenario_15_finish_run_under_12h_is_rejected(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Escenario 15: Si la corrida tiene 1.000 éxitos pero duró menos de 12 horas,
    finish_load_run DEBE rechazar la finalización con S4RunPrematureCompletionError.
    """
    async with session_factory() as session, session.begin():
        srv = S4Service(session)
        run = await srv.create_load_run(target_tasks=1000)
        await srv.start_load_run(run.id)
        run_db = await srv.get_load_run(run.id, for_update=True)
        run_db.completed_tasks = 1000
        # Inició hace solo 1 hora (3600s < 43200s)
        run_db.started_at = datetime.now(UTC) - timedelta(hours=1)
        run_id = run.id

    async with session_factory() as session, session.begin():
        srv = S4Service(session)
        with pytest.raises(S4RunPrematureCompletionError) as exc_info:
            await srv.finish_load_run(run_id, status=S4RunStatus.COMPLETED, min_duration_seconds=43200.0)

        assert "less than required minimum duration" in str(exc_info.value)
        assert "43200" in str(exc_info.value)


# =============================================================================
# ESCENARIO 16: Finalizar con 12h pero < 1.000 éxitos es rechazado
# =============================================================================
@pytest.mark.asyncio
async def test_scenario_16_finish_run_under_1000_successes_is_rejected(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Escenario 16: Si la corrida duró 12 horas pero solo completó 970 éxitos,
    finish_load_run DEBE rechazar la finalización con S4RunIncompleteError.
    """
    async with session_factory() as session, session.begin():
        srv = S4Service(session)
        run = await srv.create_load_run(target_tasks=1000)
        await srv.start_load_run(run.id)
        run_db = await srv.get_load_run(run.id, for_update=True)
        run_db.completed_tasks = 970
        run_db.failed_tasks = 30
        # Inició hace 13 horas (> 43200s)
        run_db.started_at = datetime.now(UTC) - timedelta(hours=13)
        run_id = run.id

    async with session_factory() as session, session.begin():
        srv = S4Service(session)
        with pytest.raises(S4RunIncompleteError) as exc_info:
            await srv.finish_load_run(run_id, status=S4RunStatus.COMPLETED, min_duration_seconds=43200.0)

        assert "completed 970 of 1000 target tasks" in str(exc_info.value)


# =============================================================================
# PRUEBAS DE CORRECCIÓN OPERATIVA FASES 2, 3, 4 Y 5 (CLASIFICACIÓN, PACER Y REPOSICIÓN)
# =============================================================================


@pytest.mark.asyncio
async def test_phase2_non_executable_tasks_never_call_judge0_even_with_python_def_in_llm_output(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Verifica que las tareas no ejecutables (#41, #54, #62, #71, #74, #78) jamás invocan Judge0
    ni entran en bucles de corrección aunque el LLM devuelva un bloque ```python def ...```."""
    cat = S4TaskCatalogGenerator(seed=42)
    sandbox_calls = 0

    class SpySandbox:
        async def run(self, req: RunRequest) -> RunResult:
            nonlocal sandbox_calls
            sandbox_calls += 1
            return RunResult(
                status=ExecutionStatus.RUNTIME_ERROR,
                stdout="",
                stderr="ModuleNotFoundError: No module named 'redis'",
                compile_output="",
                exit_code=1,
            )

    class VerboseCodeLLM:
        def __init__(self) -> None:
            self._model = "grok-4.6"
            self.received_max_tokens: list[int | None] = []

        async def complete(self, messages: list[Any], **kwargs: Any) -> ChatCompletion:
            self.received_max_tokens.append(kwargs.get("max_tokens"))
            # Simula que el modelo devuelve un bloque python con def y librerías externas que fallarían en Judge0
            content = (
                "Diagnóstico técnico exhaustivo: aplicamos estrategia cache-aside con ttl de 300s "
                "para evitar pool exhaustion y connection leak mediante generator y context manager "
                "con complejidad O(N) en tiempo y espacio.\n"
                "```python\nimport redis\ndef bad_cache():\n    return redis.Redis()\n```\n"
                "Veredicto: optimal / verified."
            )
            return ChatCompletion(
                content=content,
                model=self._model,
                usage=TokenUsage(prompt_tokens=200, completion_tokens=150, total_tokens=350),
                request_id="req_non_exec_test",
            )

    llm = VerboseCodeLLM()
    executor = create_real_agent_executor(llm_client=llm, sandbox_client=SpySandbox())  # type: ignore

    # Probar con las tareas reales del incidente (#41, #54, #62, #71, #74, #78)
    incident_non_exec_nums = [41, 54, 62, 71, 74, 78]
    async with session_factory() as session, session.begin():
        srv = S4Service(session)
        run = await srv.create_load_run(target_tasks=len(incident_non_exec_nums))
        await srv.start_load_run(run.id)
        for tnum in incident_non_exec_nums:
            tdef = cat.generate_task_definition(tnum)
            await srv.create_task_execution(
                run_id=run.id,
                task_number=tnum,
                task_type=tdef["task_type"],
                input_payload=tdef,
            )
        run_id = run.id

    worker = S4TaskWorker(
        run_id=run_id,
        session_factory=session_factory,
        catalog=cat,
        executor=executor,
        min_duration_seconds=0.0,
    )

    for _ in incident_non_exec_nums:
        done = await worker.run_single_step()
        assert done is not None
        assert done.status == S4TaskStatus.SUCCEEDED.value
        assert done.validation_passed is True
        assert done.model_calls == 1

    # Judge0 NUNCA debió ser invocado
    assert sandbox_calls == 0
    assert all(mt == 2000 for mt in llm.received_max_tokens)


@pytest.mark.asyncio
async def test_phase2_executable_tasks_29_and_65_never_bypass_judge0_with_not_applicable(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Verifica que las tareas ejecutables (#29, #65) jamás omiten Judge0 con status='not_applicable',
    incluso si el LLM devuelve código sin 'def '."""
    cat = S4TaskCatalogGenerator(seed=42)
    sandbox_runs: list[str] = []

    class RecordingSandbox:
        async def run(self, req: RunRequest) -> RunResult:
            sandbox_runs.append(req.source)
            return RunResult(
                status=ExecutionStatus.ACCEPTED,
                stdout="OK\n",
                stderr="",
                compile_output="",
                exit_code=0,
            )

    class InlineCodeLLM:
        def __init__(self) -> None:
            self._model = "grok-4.6"

        async def complete(self, messages: list[Any], **kwargs: Any) -> ChatCompletion:
            # Devuelve un bloque python SIN 'def ' (lo que antes provocaba status='not_applicable')
            content = (
                "Solución con parameterized query, prepared statement, sanitization, atomic lock y for update. "
                "Complejidad temporal y espacial O(N).\n"
                "```python\nitems = [1, 2, 2, 3]\nseen = set(items)\nassert len(seen) == 3\n```\n"
                "Veredicto: optimal / verified."
            )
            return ChatCompletion(
                content=content,
                model=self._model,
                usage=TokenUsage(prompt_tokens=200, completion_tokens=120, total_tokens=320),
                request_id="req_exec_29_65",
            )

    executor = create_real_agent_executor(llm_client=InlineCodeLLM(), sandbox_client=RecordingSandbox())  # type: ignore

    async with session_factory() as session, session.begin():
        srv = S4Service(session)
        run = await srv.create_load_run(target_tasks=2)
        await srv.start_load_run(run.id)
        for tnum in (29, 65):
            tdef = cat.generate_task_definition(tnum)
            await srv.create_task_execution(
                run_id=run.id,
                task_number=tnum,
                task_type=tdef["task_type"],
                input_payload=tdef,
            )
        run_id = run.id

    worker = S4TaskWorker(
        run_id=run_id,
        session_factory=session_factory,
        catalog=cat,
        executor=executor,
        min_duration_seconds=0.0,
    )

    t29 = await worker.run_single_step()
    t65 = await worker.run_single_step()

    assert t29 is not None and t29.status == S4TaskStatus.SUCCEEDED.value
    assert t65 is not None and t65.status == S4TaskStatus.SUCCEEDED.value
    assert len(sandbox_runs) == 2


def test_phase4_pacer_skips_delay_after_failed_or_timeout_task() -> None:
    """Verifica que S4Pacer retorna 0.0s tras una tarea fallida/timeout para evitar brechas > 120s."""
    from src.s4.pacer import S4Pacer

    pacer = S4Pacer(total_tasks=1000, total_duration_seconds=22000.0, min_interval_seconds=5.0)
    t0 = 1000.0
    pacer.start(monotonic_now=t0)
    pacer.record_dispatch(monotonic_now=t0)

    # Si hubo fallo o timeout a los 90s, had_failure_or_timeout=True devuelve 0.0s inmediatamente
    delay_after_timeout = pacer.compute_pacing_delay(
        completed_tasks=50,
        current_monotonic=t0 + 90.0,
        had_failure_or_timeout=True,
    )
    assert delay_after_timeout == 0.0


@pytest.mark.asyncio
async def test_phase5_replenishment_continues_if_wall_clock_12h_met_but_effective_llm_activity_under_12h(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Verifica que allocate_replenishment_task NO detiene la reposición si elapsed >= 12h y
    completed_tasks >= target_tasks pero effective_llm_activity_seconds < 12h."""
    cat = S4TaskCatalogGenerator(seed=42)
    now_utc = datetime.now(UTC)

    async with session_factory() as session, session.begin():
        srv = S4Service(session)
        run = await srv.create_load_run(target_tasks=2)
        run_db = await srv.get_load_run(run.id, for_update=True)
        run_db.status = S4RunStatus.ACTIVE.value
        # Wall-clock hace 14 horas (> 43200s) y completed_tasks == target_tasks (2 >= 2)
        run_db.started_at = now_utc - timedelta(hours=14)
        run_db.completed_tasks = 2

        t1 = await srv.create_task_execution(run_id=run.id, task_number=1, input_payload={})
        t1.status = S4TaskStatus.SUCCEEDED.value
        t1.validation_passed = True

        # Solo 60 segundos de actividad continua confirmada (< 43200s)
        session.add_all(
            [
                LLMUsageRecord(
                    s4_task_execution_id=t1.id,
                    model="grok-4.6",
                    tokens_input=100,
                    tokens_output=50,
                    tokens_total=150,
                    cost_usd=0.001,
                    measurement_status="measured",
                    call_sequence=1,
                    created_at=now_utc - timedelta(seconds=60),
                ),
                LLMUsageRecord(
                    s4_task_execution_id=t1.id,
                    model="grok-4.6",
                    tokens_input=100,
                    tokens_output=50,
                    tokens_total=150,
                    cost_usd=0.001,
                    measurement_status="measured",
                    call_sequence=2,
                    created_at=now_utc,
                ),
            ]
        )
        run_id = run.id

    async with session_factory() as session, session.begin():
        srv = S4Service(session)
        replenished = await srv.allocate_replenishment_task(
            run_id=run_id,
            catalog=cat,
            min_duration_seconds=43200.0,
        )
        # DEBE generar la tarea #2 porque effective_llm_activity_seconds (60s) < 43200s
        assert replenished is not None
        assert replenished.task_number == 2

