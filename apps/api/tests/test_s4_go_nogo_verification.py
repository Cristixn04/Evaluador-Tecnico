"""Pruebas de verificación Go/No-Go definitivas para S4.

Demuestra rigurosamente:
1. Validación estricta de usage:
   - tokens_input > 0 y tokens_output == 0 -> excluido de calls_with_usage.
   - tokens_input == 0 y tokens_output > 0 -> excluido de calls_with_usage.
   - timeout_uncertain con tokens parciales -> excluido de calls_with_usage.
   - Tarea SUCCEEDED sin llamadas LLM válidas -> rechazo en finish_load_run.
   - Tarea 1 con múltiples llamadas y Tarea 2 sin llamadas válidas -> rechazo en finish_load_run.
2. Política estricta de inactividad:
   - Interrupción de 121s (brecha > 120s) rompe la ventana continua.
   - Interrupción de 10 minutos en corrida de 13 horas rechaza si ventana máxima < 43.200s.
   - Reconstrucción idéntica e inmutable desde PostgreSQL tras reinicio de sesión.
3. Distribución horaria:
   - 12 bloques no consecutivos -> rechazo con detalle de bloques faltantes.
   - 12 bloques consecutivos válidos sin brechas -> finalización exitosa.
4. Pacer y Reposición:
   - Reconciliación de last_dispatch desde PostgreSQL.
   - Cadencia con piso de 5.0s tras tarea lenta.
   - Unicidad UNIQUE(run_id, task_number).
5. Procedencia de Grok:
   - Exportación de response_body_id, gateway_request_id y cf_ray manteniendo metadatos inciertos.
"""

from __future__ import annotations

import csv
import io
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.core.config import settings
from src.db.models.interview import LLMUsageRecord
from src.db.models.s4 import S4TaskExecution
from src.s4.catalog import S4TaskCatalogGenerator
from src.s4.enums import S4RunStatus, S4TaskStatus
from src.s4.exporter import S4Exporter
from src.s4.pacer import S4Pacer
from src.s4.service import S4DuplicateTaskNumberError, S4RunPrematureCompletionError, S4Service
from src.s4.worker import S4TaskWorker, default_synthetic_executor


@pytest.fixture
def session_factory() -> async_sessionmaker[AsyncSession]:
    engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)
    return async_sessionmaker(engine, expire_on_commit=False)


# =============================================================================
# 1. VALIDACIÓN ESTRICTA DE USAGE Y TOKENS CONFIRMADOS
# =============================================================================

@pytest.mark.asyncio
async def test_usage_excludes_zero_output_tokens(session_factory: async_sessionmaker[AsyncSession]) -> None:
    """1.1 tokens_input positivo y tokens_output cero se excluye de calls_with_usage."""
    run_id = uuid.uuid4()
    async with session_factory() as session, session.begin():
        srv = S4Service(session)
        run = await srv.create_load_run(run_id=run_id, target_tasks=1)
        await srv.start_load_run(run.id)
        t = await srv.create_task_execution(run_id=run_id, task_number=1, input_payload={})
        rec = LLMUsageRecord(
            id=uuid.uuid4(),
            s4_task_execution_id=t.id,
            model="grok-4.6",
            tokens_input=150,
            tokens_output=0,  # Cero output
            tokens_total=150,
            measurement_status="measured",
        )
        session.add(rec)

    async with session_factory() as session:
        srv = S4Service(session)
        stats = await srv.get_run_statistics(run_id)
        assert stats.calls_with_usage == 0


@pytest.mark.asyncio
async def test_usage_excludes_zero_input_tokens(session_factory: async_sessionmaker[AsyncSession]) -> None:
    """1.2 tokens_input cero y tokens_output positivo se excluye de calls_with_usage."""
    run_id = uuid.uuid4()
    async with session_factory() as session, session.begin():
        srv = S4Service(session)
        run = await srv.create_load_run(run_id=run_id, target_tasks=1)
        await srv.start_load_run(run.id)
        t = await srv.create_task_execution(run_id=run_id, task_number=1, input_payload={})
        rec = LLMUsageRecord(
            id=uuid.uuid4(),
            s4_task_execution_id=t.id,
            model="grok-4.6",
            tokens_input=0,  # Cero input
            tokens_output=150,
            tokens_total=150,
            measurement_status="measured",
        )
        session.add(rec)

    async with session_factory() as session:
        srv = S4Service(session)
        stats = await srv.get_run_statistics(run_id)
        assert stats.calls_with_usage == 0


@pytest.mark.asyncio
async def test_usage_excludes_timeout_uncertain_with_partial_tokens(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """1.3 timeout_uncertain con tokens parciales se excluye de calls_with_usage."""
    run_id = uuid.uuid4()
    async with session_factory() as session, session.begin():
        srv = S4Service(session)
        run = await srv.create_load_run(run_id=run_id, target_tasks=1)
        await srv.start_load_run(run.id)
        t = await srv.create_task_execution(run_id=run_id, task_number=1, input_payload={})
        rec = LLMUsageRecord(
            id=uuid.uuid4(),
            s4_task_execution_id=t.id,
            model="grok-4.6",
            tokens_input=500,
            tokens_output=100,
            tokens_total=600,
            measurement_status="timeout_uncertain",  # Incierto
        )
        session.add(rec)

    async with session_factory() as session:
        srv = S4Service(session)
        stats = await srv.get_run_statistics(run_id)
        assert stats.calls_with_usage == 0


@pytest.mark.asyncio
async def test_finish_load_run_rejects_succeeded_task_without_valid_llm_calls(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """1.4 finish_load_run rechaza si una tarea SUCCEEDED con validation_passed=True no tiene llamadas LLM válidas."""
    run_id = uuid.uuid4()
    async with session_factory() as session, session.begin():
        srv = S4Service(session)
        run = await srv.create_load_run(run_id=run_id, target_tasks=1)
        await srv.start_load_run(run.id)
        run.completed_tasks = 1
        run.started_at = datetime.now(UTC) - timedelta(hours=13)
        t = await srv.create_task_execution(run_id=run_id, task_number=1, input_payload={})
        t.status = S4TaskStatus.SUCCEEDED.value
        t.validation_passed = True

    async with session_factory() as session, session.begin():
        srv = S4Service(session)
        with pytest.raises(S4RunPrematureCompletionError) as exc_info:
            await srv.finish_load_run(run_id, status=S4RunStatus.COMPLETED, min_duration_seconds=43200.0)
        assert "no LLM activity records found in PostgreSQL" in str(exc_info.value) or "lack confirmed LLM calls" in str(exc_info.value)


@pytest.mark.asyncio
async def test_finish_load_run_rejects_when_one_task_has_calls_and_another_has_zero(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """1.5 Tarea 1 tiene 2 llamadas válidas y Tarea 2 no tiene ninguna: debe rechazarse."""
    run_id = uuid.uuid4()
    base_time = datetime.now(UTC) - timedelta(hours=13)

    async with session_factory() as session, session.begin():
        srv = S4Service(session)
        run = await srv.create_load_run(run_id=run_id, target_tasks=2)
        await srv.start_load_run(run.id)
        run.completed_tasks = 2
        run.started_at = base_time

        t1 = await srv.create_task_execution(run_id=run_id, task_number=1, input_payload={})
        t1.status = S4TaskStatus.SUCCEEDED.value
        t1.validation_passed = True

        t2 = await srv.create_task_execution(run_id=run_id, task_number=2, input_payload={})
        t2.status = S4TaskStatus.SUCCEEDED.value
        t2.validation_passed = True

        # Dos llamadas válidas en Tarea 1
        r1 = LLMUsageRecord(
            id=uuid.uuid4(),
            s4_task_execution_id=t1.id,
            call_sequence=1,
            model="grok-4.6",
            tokens_input=100,
            tokens_output=50,
            tokens_total=150,
            created_at=base_time,
            measurement_status="measured",
        )
        r2 = LLMUsageRecord(
            id=uuid.uuid4(),
            s4_task_execution_id=t1.id,
            call_sequence=2,
            model="grok-4.6",
            tokens_input=100,
            tokens_output=50,
            tokens_total=150,
            created_at=base_time + timedelta(seconds=43200),
            measurement_status="measured",
        )
        session.add_all([r1, r2])

    async with session_factory() as session, session.begin():
        srv = S4Service(session)
        with pytest.raises(S4RunPrematureCompletionError) as exc_info:
            await srv.finish_load_run(run_id, status=S4RunStatus.COMPLETED, min_duration_seconds=43200.0)
        assert "lack confirmed LLM calls with positive usage" in str(exc_info.value) or "continuous uninterrupted" in str(exc_info.value)


@pytest.mark.asyncio
async def test_not_exists_rejects_succeeded_task_without_confirmed_calls(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """1.6 Correlación NOT EXISTS: Tarea exitosa sin llamadas confirmadas es rechazada."""
    run_id = uuid.uuid4()
    t0 = datetime.now(UTC) - timedelta(seconds=10)

    async with session_factory() as session, session.begin():
        srv = S4Service(session)
        run = await srv.create_load_run(run_id=run_id, target_tasks=1)
        await srv.start_load_run(run.id)
        run.completed_tasks = 1
        run.started_at = t0
        t = await srv.create_task_execution(run_id=run_id, task_number=1, input_payload={})
        t.status = S4TaskStatus.SUCCEEDED.value
        t.validation_passed = True

    async with session_factory() as session, session.begin():
        srv = S4Service(session)
        with pytest.raises(S4RunPrematureCompletionError) as exc_info:
            await srv.finish_load_run(run_id, status=S4RunStatus.COMPLETED, min_duration_seconds=1.0)
        assert "lack confirmed LLM calls with positive usage" in str(exc_info.value) or "no LLM activity records" in str(exc_info.value)


@pytest.mark.asyncio
async def test_not_exists_accepts_succeeded_task_with_confirmed_call(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """1.7 Correlación NOT EXISTS: Tarea exitosa con una llamada confirmada es aceptada."""
    run_id = uuid.uuid4()
    t0 = datetime.now(UTC) - timedelta(seconds=10)

    async with session_factory() as session, session.begin():
        srv = S4Service(session)
        run = await srv.create_load_run(run_id=run_id, target_tasks=1)
        await srv.start_load_run(run.id)
        run.completed_tasks = 1
        run.started_at = t0
        t = await srv.create_task_execution(run_id=run_id, task_number=1, input_payload={})
        t.status = S4TaskStatus.SUCCEEDED.value
        t.validation_passed = True

        # Dos llamadas válidas en la misma tarea separadas por 2 segundos
        r1 = LLMUsageRecord(
            id=uuid.uuid4(),
            s4_task_execution_id=t.id,
            call_sequence=1,
            model="grok-4.6",
            tokens_input=100,
            tokens_output=50,
            tokens_total=150,
            created_at=t0,
            measurement_status="measured",
        )
        r2 = LLMUsageRecord(
            id=uuid.uuid4(),
            s4_task_execution_id=t.id,
            call_sequence=2,
            model="grok-4.6",
            tokens_input=100,
            tokens_output=50,
            tokens_total=150,
            created_at=t0 + timedelta(seconds=2),
            measurement_status="measured",
        )
        session.add_all([r1, r2])

    async with session_factory() as session, session.begin():
        srv = S4Service(session)
        completed = await srv.finish_load_run(run_id, status=S4RunStatus.COMPLETED, min_duration_seconds=1.0)
        assert completed.status == S4RunStatus.COMPLETED.value


@pytest.mark.asyncio
async def test_not_exists_presence_of_null_fk_records_does_not_bypass_validation(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """1.8 Correlación NOT EXISTS: Registros en LLMUsageRecord con s4_task_execution_id=NULL no eluden la validación."""
    run_id = uuid.uuid4()
    t0 = datetime.now(UTC) - timedelta(seconds=10)

    async with session_factory() as session, session.begin():
        srv = S4Service(session)
        run = await srv.create_load_run(run_id=run_id, target_tasks=2)
        await srv.start_load_run(run.id)
        run.completed_tasks = 2
        run.started_at = t0

        t1 = await srv.create_task_execution(run_id=run_id, task_number=1, input_payload={})
        t1.status = S4TaskStatus.SUCCEEDED.value
        t1.validation_passed = True

        t2 = await srv.create_task_execution(run_id=run_id, task_number=2, input_payload={})
        t2.status = S4TaskStatus.SUCCEEDED.value
        t2.validation_passed = True

        # Tarea 1 tiene 2 llamadas válidas
        r1 = LLMUsageRecord(id=uuid.uuid4(), s4_task_execution_id=t1.id, call_sequence=1, model="grok-4.6", tokens_input=100, tokens_output=50, measurement_status="measured", created_at=t0)
        r2 = LLMUsageRecord(id=uuid.uuid4(), s4_task_execution_id=t1.id, call_sequence=2, model="grok-4.6", tokens_input=100, tokens_output=50, measurement_status="measured", created_at=t0 + timedelta(seconds=2))

        # Registro espurio con FK NULL en la base de datos (ej. registro huérfano o llamada desacoplada)
        null_fk_rec = LLMUsageRecord(
            id=uuid.uuid4(),
            s4_task_execution_id=None,  # FK NULL
            interview_id=None,
            call_sequence=1,
            model="grok-4.6",
            tokens_input=999,
            tokens_output=999,
            tokens_total=1998,
            measurement_status="measured",
            created_at=t0,
        )
        session.add_all([r1, r2, null_fk_rec])

    async with session_factory() as session, session.begin():
        srv = S4Service(session)
        # Tarea 2 NO tiene llamadas confirmadas. El registro NULL no debe engañar a la consulta.
        with pytest.raises(S4RunPrematureCompletionError) as exc_info:
            await srv.finish_load_run(run_id, status=S4RunStatus.COMPLETED, min_duration_seconds=1.0)
        assert "lack confirmed LLM calls with positive usage" in str(exc_info.value)
        assert "#2" in str(exc_info.value)


@pytest.mark.asyncio
async def test_not_exists_call_from_another_task_or_run_cannot_validate_task(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """1.9 Correlación NOT EXISTS: Una tarea no puede quedar validada por una llamada perteneciente a otra tarea o corrida."""
    run_id_a = uuid.uuid4()
    run_id_b = uuid.uuid4()
    t0 = datetime.now(UTC) - timedelta(seconds=10)

    async with session_factory() as session, session.begin():
        srv = S4Service(session)
        # Corrida B con tarea que sí tiene llamada
        run_b = await srv.create_load_run(run_id=run_id_b, target_tasks=1)
        await srv.start_load_run(run_b.id)
        t_b = await srv.create_task_execution(run_id=run_id_b, task_number=1, input_payload={})
        r_b = LLMUsageRecord(
            id=uuid.uuid4(),
            s4_task_execution_id=t_b.id,
            call_sequence=1,
            model="grok-4.6",
            tokens_input=500,
            tokens_output=200,
            measurement_status="measured",
            created_at=t0,
        )

        # Corrida A con tarea 1 sin llamada
        run_a = await srv.create_load_run(run_id=run_id_a, target_tasks=1)
        await srv.start_load_run(run_a.id)
        run_a.completed_tasks = 1
        run_a.started_at = t0
        t_a = await srv.create_task_execution(run_id=run_id_a, task_number=1, input_payload={})
        t_a.status = S4TaskStatus.SUCCEEDED.value
        t_a.validation_passed = True

        session.add(r_b)

    async with session_factory() as session, session.begin():
        srv = S4Service(session)
        # Finalizar Corrida A debe fallar porque la llamada de Corrida B no le pertenece a t_a
        with pytest.raises(S4RunPrematureCompletionError) as exc_info:
            await srv.finish_load_run(run_id_a, status=S4RunStatus.COMPLETED, min_duration_seconds=1.0)
        assert "no LLM activity records found in PostgreSQL" in str(exc_info.value) or "lack confirmed LLM calls" in str(exc_info.value)


# =============================================================================
# 2. POLÍTICA ESTRICTA DE INACTIVIDAD (VENTANA CONTINUA SIN BRECHAS > 120s)
# =============================================================================

@pytest.mark.asyncio
async def test_inactivity_gap_of_121s_breaks_continuous_window(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """2.1 Una brecha de 121s (> 120s) rompe la ventana continua; la ventana resultante no acumula el lapso anterior."""
    run_id = uuid.uuid4()
    t0 = datetime.now(UTC) - timedelta(minutes=10)

    async with session_factory() as session, session.begin():
        srv = S4Service(session)
        run = await srv.create_load_run(run_id=run_id, target_tasks=3)
        await srv.start_load_run(run.id)
        t = await srv.create_task_execution(run_id=run_id, task_number=1, input_payload={})

        c1 = LLMUsageRecord(
            id=uuid.uuid4(),
            s4_task_execution_id=t.id,
            call_sequence=1,
            model="grok-4.6",
            tokens_input=100,
            tokens_output=50,
            tokens_total=150,
            created_at=t0,
            measurement_status="measured",
        )
        # Brecha de 121s
        c2 = LLMUsageRecord(
            id=uuid.uuid4(),
            s4_task_execution_id=t.id,
            call_sequence=2,
            model="grok-4.6",
            tokens_input=100,
            tokens_output=50,
            tokens_total=150,
            created_at=t0 + timedelta(seconds=121),
            measurement_status="measured",
        )
        c3 = LLMUsageRecord(
            id=uuid.uuid4(),
            s4_task_execution_id=t.id,
            call_sequence=3,
            model="grok-4.6",
            tokens_input=100,
            tokens_output=50,
            tokens_total=150,
            created_at=t0 + timedelta(seconds=160),
            measurement_status="measured",
        )
        session.add_all([c1, c2, c3])

    async with session_factory() as session:
        srv = S4Service(session)
        stats = await srv.get_run_statistics(run_id)
        assert stats.inactivity_exceeded_count == 1
        assert stats.interruption_count == 1
        assert stats.max_gap_seconds_between_calls == 121.0
        # Ventana 1 duró 0s (1 sola llamada). Ventana 2 duró 39s (160 - 121).
        assert stats.longest_continuous_window_seconds == 39.0
        assert stats.effective_llm_activity_seconds == 39.0


@pytest.mark.asyncio
async def test_ten_minute_interruption_in_13h_run_is_rejected(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """2.2 Corrida de 13h con una pausa de 10 min a las 8 horas rechaza porque ninguna ventana alcanza 12 horas."""
    run_id = uuid.uuid4()
    t_start = datetime.now(UTC) - timedelta(hours=14)

    async with session_factory() as session, session.begin():
        srv = S4Service(session)
        run = await srv.create_load_run(run_id=run_id, target_tasks=4)
        await srv.start_load_run(run.id)
        run.completed_tasks = 4
        run.started_at = t_start

        # Ventana 1: 8 horas (0s a 28.800s)
        # Pausa de 600s (10 minutos)
        # Ventana 2: 5 horas (29.400s a 47.400s)
        t_w1_start = t_start
        t_w1_end = t_start + timedelta(hours=8)
        t_w2_start = t_w1_end + timedelta(minutes=10)
        t_w2_end = t_w2_start + timedelta(hours=5)

        for i in range(4):
            t = await srv.create_task_execution(run_id=run_id, task_number=i + 1, input_payload={})
            t.status = S4TaskStatus.SUCCEEDED.value
            t.validation_passed = True

        t1_id = (await session.execute(select(S4TaskExecution.id).where(S4TaskExecution.run_id == run_id, S4TaskExecution.task_number == 1))).scalar_one()
        t2_id = (await session.execute(select(S4TaskExecution.id).where(S4TaskExecution.run_id == run_id, S4TaskExecution.task_number == 2))).scalar_one()
        t3_id = (await session.execute(select(S4TaskExecution.id).where(S4TaskExecution.run_id == run_id, S4TaskExecution.task_number == 3))).scalar_one()
        t4_id = (await session.execute(select(S4TaskExecution.id).where(S4TaskExecution.run_id == run_id, S4TaskExecution.task_number == 4))).scalar_one()

        r1 = LLMUsageRecord(id=uuid.uuid4(), s4_task_execution_id=t1_id, model="grok-4.6", tokens_input=10, tokens_output=10, measurement_status="measured", created_at=t_w1_start)
        r2 = LLMUsageRecord(id=uuid.uuid4(), s4_task_execution_id=t2_id, model="grok-4.6", tokens_input=10, tokens_output=10, measurement_status="measured", created_at=t_w1_end)
        r3 = LLMUsageRecord(id=uuid.uuid4(), s4_task_execution_id=t3_id, model="grok-4.6", tokens_input=10, tokens_output=10, measurement_status="measured", created_at=t_w2_start)
        r4 = LLMUsageRecord(id=uuid.uuid4(), s4_task_execution_id=t4_id, model="grok-4.6", tokens_input=10, tokens_output=10, measurement_status="measured", created_at=t_w2_end)
        session.add_all([r1, r2, r3, r4])

    async with session_factory() as session, session.begin():
        srv = S4Service(session)
        with pytest.raises(S4RunPrematureCompletionError) as exc_info:
            await srv.finish_load_run(run_id, status=S4RunStatus.COMPLETED, min_duration_seconds=43200.0)
        assert "continuous uninterrupted LLM activity duration" in str(exc_info.value)


@pytest.mark.asyncio
async def test_reconstruction_of_interrupted_window_from_postgres_after_restart(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """2.3 Tras reiniciar la sesión/proceso, las estadísticas y partición de ventanas se reconstruyen de forma idéntica."""
    run_id = uuid.uuid4()
    t0 = datetime.now(UTC) - timedelta(hours=1)

    async with session_factory() as session, session.begin():
        srv = S4Service(session)
        run = await srv.create_load_run(run_id=run_id, target_tasks=3)
        await srv.start_load_run(run.id)
        t = await srv.create_task_execution(run_id=run_id, task_number=1, input_payload={})
        c1 = LLMUsageRecord(id=uuid.uuid4(), s4_task_execution_id=t.id, call_sequence=1, model="grok-4.6", tokens_input=50, tokens_output=50, measurement_status="measured", created_at=t0)
        c2 = LLMUsageRecord(id=uuid.uuid4(), s4_task_execution_id=t.id, call_sequence=2, model="grok-4.6", tokens_input=50, tokens_output=50, measurement_status="measured", created_at=t0 + timedelta(seconds=130))
        c3 = LLMUsageRecord(id=uuid.uuid4(), s4_task_execution_id=t.id, call_sequence=3, model="grok-4.6", tokens_input=50, tokens_output=50, measurement_status="measured", created_at=t0 + timedelta(seconds=200))
        session.add_all([c1, c2, c3])

    async with session_factory() as session2:
        srv2 = S4Service(session2)
        stats = await srv2.get_run_statistics(run_id)
        assert stats.interruption_count == 1
        assert stats.max_gap_seconds_between_calls == 130.0
        assert stats.longest_continuous_window_seconds == 70.0
        assert stats.effective_llm_activity_seconds == 70.0


# =============================================================================
# 3. DISTRIBUCIÓN HORARIA: BLOQUES CONSECUTIVOS OBLIGATORIOS
# =============================================================================

@pytest.mark.asyncio
async def test_twelve_non_consecutive_hourly_blocks_are_rejected(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """3.1 Si existen 12 bloques horarios distintos pero no son consecutivos (ej. faltan horas), se rechaza."""
    run_id = uuid.uuid4()
    t_start = datetime.now(UTC) - timedelta(hours=25)

    non_consecutive_hours = [0, 1, 2, 4, 5, 6, 8, 9, 10, 12, 14, 16]

    async with session_factory() as session, session.begin():
        srv = S4Service(session)
        run = await srv.create_load_run(run_id=run_id, target_tasks=len(non_consecutive_hours))
        await srv.start_load_run(run.id)
        run.completed_tasks = len(non_consecutive_hours)
        run.started_at = t_start

        for idx, hr in enumerate(non_consecutive_hours):
            t = await srv.create_task_execution(run_id=run_id, task_number=idx + 1, input_payload={})
            t.status = S4TaskStatus.SUCCEEDED.value
            t.validation_passed = True
            rec = LLMUsageRecord(
                id=uuid.uuid4(),
                s4_task_execution_id=t.id,
                model="grok-4.6",
                tokens_input=100,
                tokens_output=50,
                tokens_total=150,
                created_at=t_start + timedelta(hours=hr, minutes=5),
                measurement_status="measured",
            )
            session.add(rec)

    async with session_factory() as session, session.begin():
        srv = S4Service(session)
        with pytest.raises(S4RunPrematureCompletionError) as exc_info:
            await srv.finish_load_run(run_id, status=S4RunStatus.COMPLETED, min_duration_seconds=43200.0)
        assert "missing required continuous hourly blocks" in str(exc_info.value) or "continuous uninterrupted" in str(exc_info.value)


@pytest.mark.asyncio
async def test_twelve_valid_consecutive_hourly_blocks_succeeds(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """3.2 Doce bloques horarios consecutivos (0 a 11) con llamadas válidas y ventana continua aprueba."""
    run_id = uuid.uuid4()
    t_start = datetime.now(UTC) - timedelta(seconds=43210)

    async with session_factory() as session, session.begin():
        srv = S4Service(session)
        run = await srv.create_load_run(run_id=run_id, target_tasks=12)
        await srv.start_load_run(run.id)
        run.completed_tasks = 12
        run.started_at = t_start

        for i in range(12):
            t = await srv.create_task_execution(run_id=run_id, task_number=i + 1, input_payload={})
            t.status = S4TaskStatus.SUCCEEDED.value
            t.validation_passed = True

        # Crear 433 llamadas cada 100s cubriendo las 12 horas continuas sin brechas > 120s
        calls = []
        for step in range(433):
            task_num = (step % 12) + 1
            call_t = t_start + timedelta(seconds=step * 100)
            stmt_t = select(S4TaskExecution.id).where(S4TaskExecution.run_id == run_id, S4TaskExecution.task_number == task_num)
            tid = (await session.execute(stmt_t)).scalar_one()
            c = LLMUsageRecord(
                id=uuid.uuid4(),
                s4_task_execution_id=tid,
                call_sequence=(step // 12) + 1,
                model="grok-4.6",
                tokens_input=100,
                tokens_output=50,
                tokens_total=150,
                created_at=call_t,
                measurement_status="measured",
            )
            calls.append(c)
        session.add_all(calls)

    async with session_factory() as session, session.begin():
        srv = S4Service(session)
        completed_run = await srv.finish_load_run(run_id, status=S4RunStatus.COMPLETED, min_duration_seconds=43200.0)
        assert completed_run.status == S4RunStatus.COMPLETED.value


# =============================================================================
# 4. PACER Y CONCURRENCIA
# =============================================================================

@pytest.mark.asyncio
async def test_pacer_restores_last_dispatch_from_postgres_on_worker_restart(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """4.1 Worker reconcilia started_at de la última tarea en PostgreSQL y reanuda cadencia sin ráfaga."""
    run_id = uuid.uuid4()
    cat = S4TaskCatalogGenerator(seed=42)
    pacer = S4Pacer(total_tasks=1000, total_duration_seconds=43200.0, min_interval_seconds=5.0)

    dispatch_time = datetime.now(UTC) - timedelta(seconds=15)

    async with session_factory() as session, session.begin():
        srv = S4Service(session)
        run = await srv.create_load_run(run_id=run_id, target_tasks=10)
        await srv.start_load_run(run.id)
        run.started_at = dispatch_time
        t = await srv.create_task_execution(run_id=run_id, task_number=1, input_payload={})
        t.status = S4TaskStatus.RUNNING.value
        t.started_at = dispatch_time

    worker = S4TaskWorker(
        run_id=run_id,
        session_factory=session_factory,
        worker_id="test-restart-worker",
        catalog=cat,
        executor=default_synthetic_executor,
        pacer=pacer,
    )

    await worker.run_autonomous_loop(max_tasks=0)

    assert pacer._last_dispatch_monotonic is not None
    delay = pacer.compute_pacing_delay(completed_tasks=1)
    assert 25.0 <= delay <= 30.0


def test_pacer_slow_task_cadence_explanation() -> None:
    """4.2 Tarea de 60s espera 5s de suelo anti-ráfaga (espacio entre despachos = 65s)."""
    pacer = S4Pacer(total_tasks=1000, total_duration_seconds=43200.0, min_interval_seconds=5.0)
    t0 = 1000.0
    pacer.start(monotonic_now=t0)
    pacer.record_dispatch(monotonic_now=t0)

    t_fin = t0 + 60.0
    delay = pacer.compute_pacing_delay(completed_tasks=1, current_monotonic=t_fin)
    assert delay == 5.0


@pytest.mark.asyncio
async def test_replenishment_unique_constraint_enforced_at_database_level(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """4.3 La base de datos tiene restricción de unicidad estricta UNIQUE(run_id, task_number)."""
    run_id = uuid.uuid4()
    async with session_factory() as session, session.begin():
        srv = S4Service(session)
        run = await srv.create_load_run(run_id=run_id, target_tasks=5)
        await srv.start_load_run(run.id)
        await srv.create_task_execution(run_id=run_id, task_number=1, input_payload={})

    async with session_factory() as session, session.begin():
        srv = S4Service(session)
        with pytest.raises(S4DuplicateTaskNumberError):
            await srv.create_task_execution(run_id=run_id, task_number=1, input_payload={})


# =============================================================================
# 5. PROCEDENCIA DE IDENTIFICADORES DE GROK
# =============================================================================

@pytest.mark.asyncio
async def test_export_distinguishes_response_body_id_gateway_id_and_cf_ray(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """5.1 La exportación distingue response_body_id (origen no verificado), gateway_request_id y cf_ray."""
    run_id = uuid.uuid4()

    async with session_factory() as session, session.begin():
        srv = S4Service(session)
        run = await srv.create_load_run(run_id=run_id, target_tasks=1)
        await srv.start_load_run(run.id)
        t = await srv.create_task_execution(run_id=run_id, task_number=1, input_payload={})

        c1 = LLMUsageRecord(
            id=uuid.uuid4(),
            s4_task_execution_id=t.id,
            model="grok-4.6",
            tokens_input=1200,
            tokens_output=300,
            tokens_total=1500,
            cost_usd=0.0081,
            measurement_status="measured",
            gateway_request_id="req-gateway-12345",
            gateway_metadata={
                "provider_id": "chatcmpl-grok-abcde",
                "cf_ray": "ray-cloudflare-xyz",
            },
            call_sequence=1,
        )
        session.add(c1)

    async with session_factory() as session:
        csv_data = await S4Exporter.export_calls_csv(run_id, session)
        reader = list(csv.DictReader(io.StringIO(csv_data)))
        assert len(reader) == 1

        assert reader[0]["measurement_status"] == "measured"
        assert reader[0]["gateway_request_id"] == "req-gateway-12345"
        assert reader[0]["response_body_id"] == "chatcmpl-grok-abcde"
        assert reader[0]["provider_request_id"] == "chatcmpl-grok-abcde"
        assert reader[0]["cf_ray"] == "ray-cloudflare-xyz"
