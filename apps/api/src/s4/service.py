"""Servicio de gestión, trazabilidad y agregación para corridas S4."""

from __future__ import annotations

import json
import math
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import exists, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from src.db.models.interview import LLMUsageRecord
from src.db.models.s4 import S4LoadRun, S4TaskExecution
from src.evaluation.pricing import calculate_llm_cost
from src.s4.enums import S4RunStatus, S4TaskStatus, S4TaskType
from src.s4.sanitizer import S4Sanitizer
from src.s4.schemas import S4LoadRunSummary, S4RecoveryEvent


class S4Error(Exception):
    """Excepción base del módulo S4."""


class S4RunNotFoundError(S4Error):
    """La corrida S4 solicitada no existe."""


class S4TaskNotFoundError(S4Error):
    """La tarea S4 solicitada no existe."""


class S4InvalidStateTransitionError(S4Error):
    """Transición de estado no autorizada en el ciclo de vida de S4."""


class S4TaskValidationError(S4Error):
    """La tarea no cumple con los criterios de validación para el estado objetivo."""


class S4RunIncompleteError(S4Error):
    """La corrida no puede declararse completada porque no alcanzó el objetivo de tareas."""


class S4RunPrematureCompletionError(S4Error):
    """La corrida no puede declararse completada porque no cumplió la duración mínima requerida."""


class S4WorkerLeaseExpiredError(S4Error):
    """El lease del worker sobre la tarea expiró o fue transferido a otra generación."""


class S4DuplicateTaskNumberError(S4Error):
    """El número de tarea ya está registrado dentro de esta corrida."""


class S4Service:
    """Servicio de persistencia, control de estados y agregaciones para S4."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # -------------------------------------------------------------------------
    # 1. Ciclo de Vida de la Corrida (S4LoadRun)
    # -------------------------------------------------------------------------

    async def create_load_run(
        self,
        *,
        target_tasks: int = 1000,
        budget_limit_usd: float = 50.0,
        meta: dict[str, Any] | None = None,
        run_id: uuid.UUID | None = None,
    ) -> S4LoadRun:
        """Crea una nueva corrida de carga en estado 'planned'."""
        run = S4LoadRun(
            id=run_id or uuid.uuid4(),
            status=S4RunStatus.PLANNED.value,
            target_tasks=target_tasks,
            budget_limit_usd=budget_limit_usd,
            meta=meta or {},
        )
        self._session.add(run)
        await self._session.flush()
        return run

    async def get_load_run(
        self,
        run_id: uuid.UUID,
        *,
        for_update: bool = False,
    ) -> S4LoadRun:
        """Obtiene una corrida por su ID o eleva S4RunNotFoundError."""
        if for_update:
            stmt = select(S4LoadRun).where(S4LoadRun.id == run_id).with_for_update()
            run = (await self._session.execute(stmt)).scalar_one_or_none()
        else:
            run = await self._session.get(S4LoadRun, run_id)
        if not run:
            raise S4RunNotFoundError(f"S4LoadRun '{run_id}' not found")
        return run

    async def start_load_run(self, run_id: uuid.UUID) -> S4LoadRun:
        """Inicia la corrida pasando de 'planned' o 'paused' a 'active'."""
        run = await self.get_load_run(run_id)
        if run.status not in (S4RunStatus.PLANNED.value, S4RunStatus.PAUSED.value):
            raise S4InvalidStateTransitionError(
                f"Cannot start run from status '{run.status}'"
            )
        run.status = S4RunStatus.ACTIVE.value
        if run.started_at is None:
            run.started_at = datetime.now(UTC)
        await self._session.flush()
        return run

    async def pause_load_run(self, run_id: uuid.UUID) -> S4LoadRun:
        """Pausa una corrida activa."""
        run = await self.get_load_run(run_id)
        if run.status != S4RunStatus.ACTIVE.value:
            raise S4InvalidStateTransitionError(
                f"Cannot pause run from status '{run.status}'"
            )
        run.status = S4RunStatus.PAUSED.value
        await self._session.flush()
        return run

    async def finish_load_run(
        self,
        run_id: uuid.UUID,
        status: S4RunStatus = S4RunStatus.COMPLETED,
        *,
        min_duration_seconds: float = 43200.0,
    ) -> S4LoadRun:
        """Finaliza una corrida. Valida que completed_tasks >= target_tasks y duración mínima si es COMPLETED."""
        run = await self.get_load_run(run_id, for_update=True)
        if status == S4RunStatus.COMPLETED:
            if run.completed_tasks < run.target_tasks:
                raise S4RunIncompleteError(
                    f"Cannot complete run: completed {run.completed_tasks} of {run.target_tasks} target tasks"
                )
            if run.started_at:
                elapsed = (datetime.now(UTC) - run.started_at).total_seconds()
                if elapsed < min_duration_seconds:
                    raise S4RunPrematureCompletionError(
                        f"Cannot complete run: elapsed duration {elapsed:.1f}s is less than "
                        f"required minimum duration {min_duration_seconds:.1f}s (12 hours)"
                    )
            # Validación de la ventana de actividad real LLM si min_duration_seconds > 0
            if min_duration_seconds > 0.0:
                stats = await self.get_run_statistics(run_id)
                if stats.first_llm_call_at is None or stats.effective_llm_activity_seconds is None:
                    raise S4RunPrematureCompletionError(
                        "Cannot complete run: no LLM activity records found in PostgreSQL"
                    )
                if stats.effective_llm_activity_seconds < min_duration_seconds:
                    raise S4RunPrematureCompletionError(
                        f"Cannot complete run: continuous uninterrupted LLM activity duration {stats.effective_llm_activity_seconds:.1f}s is less than "
                        f"required minimum duration {min_duration_seconds:.1f}s (12 hours)"
                    )
                # Validar distribución horaria continua (todos los bloques horarios consecutivos 0..expected_hours-1)
                expected_hours = int(min_duration_seconds // 3600)
                if expected_hours > 0:
                    missing_consecutive_hours = [
                        h for h in range(expected_hours) if f"hour_{h:02d}" not in stats.hourly_distribution
                    ]
                    if missing_consecutive_hours:
                        raise S4RunPrematureCompletionError(
                            f"Cannot complete run: missing required continuous hourly blocks {missing_consecutive_hours} "
                            f"(found {len(stats.hourly_distribution)} blocks: {sorted(stats.hourly_distribution.keys())})"
                        )
                # Validar que existan llamadas reales con tokens medidos positivos
                if stats.calls_with_usage < run.completed_tasks:
                    raise S4RunPrematureCompletionError(
                        f"Cannot complete run: only {stats.calls_with_usage} calls have valid measured token usage "
                        f"(minimum required: {run.completed_tasks})"
                    )
                # Verificar mediante NOT EXISTS que CADA tarea SUCCEEDED con validation_passed=True
                # tenga al menos una llamada LLM con usage confirmado (inmune a NULLs en s4_task_execution_id)
                stmt_unconfirmed = (
                    select(S4TaskExecution.task_number)
                    .where(
                        S4TaskExecution.run_id == run_id,
                        S4TaskExecution.status == S4TaskStatus.SUCCEEDED.value,
                        S4TaskExecution.validation_passed.is_(True),
                        ~exists(
                            select(1)
                            .where(
                                LLMUsageRecord.s4_task_execution_id == S4TaskExecution.id,
                                LLMUsageRecord.tokens_input > 0,
                                LLMUsageRecord.tokens_output > 0,
                                LLMUsageRecord.measurement_status.in_(["measured", "exact", "reconciled"]),
                            )
                        ),
                    )
                    .order_by(S4TaskExecution.task_number.asc())
                )
                unconfirmed_task_numbers = (await self._session.execute(stmt_unconfirmed)).scalars().all()
                if unconfirmed_task_numbers:
                    raise S4RunPrematureCompletionError(
                        f"Cannot complete run: {len(unconfirmed_task_numbers)} SUCCEEDED task(s) with validation_passed=True "
                        f"lack confirmed LLM calls with positive usage (e.g. task #{unconfirmed_task_numbers[0]})"
                    )
            # Verificar que no existan tareas activas o encoladas
            pending_stmt = select(func.count(S4TaskExecution.id)).where(
                S4TaskExecution.run_id == run_id,
                S4TaskExecution.status.in_([S4TaskStatus.QUEUED.value, S4TaskStatus.RUNNING.value]),
            )
            pending_count = int((await self._session.execute(pending_stmt)).scalar_one() or 0)
            if pending_count > 0:
                raise S4InvalidStateTransitionError(
                    f"Cannot complete run: {pending_count} task(s) are still queued or running"
                )

        run.status = status.value
        run.finished_at = datetime.now(UTC)
        await self._session.flush()
        return run

    # -------------------------------------------------------------------------
    # 2. Ciclo de Vida de Tareas (S4TaskExecution)
    # -------------------------------------------------------------------------

    async def create_task_execution(
        self,
        *,
        run_id: uuid.UUID,
        task_number: int,
        task_type: S4TaskType | str = S4TaskType.GENERAL_TECHNICAL,
        input_payload: Any,
        task_id: uuid.UUID | None = None,
    ) -> S4TaskExecution:
        """Registra una nueva unidad de trabajo en estado 'queued' con input sanitizado."""
        # Verificar que la corrida existe
        run = await self.get_load_run(run_id)
        if run.status in (S4RunStatus.COMPLETED.value, S4RunStatus.CANCELLED.value):
            raise S4InvalidStateTransitionError(
                f"Cannot add tasks to a {run.status} run"
            )

        # Verificar unicidad de task_number
        existing_stmt = select(S4TaskExecution.id).where(
            S4TaskExecution.run_id == run_id,
            S4TaskExecution.task_number == task_number,
        )
        existing = (await self._session.execute(existing_stmt)).scalar_one_or_none()
        if existing:
            raise S4DuplicateTaskNumberError(
                f"Task number {task_number} already exists in run {run_id}"
            )

        sanitized_input = S4Sanitizer.sanitize_payload(input_payload)
        task_type_str = task_type.value if isinstance(task_type, S4TaskType) else str(task_type)

        task = S4TaskExecution(
            id=task_id or uuid.uuid4(),
            run_id=run_id,
            task_number=task_number,
            task_type=task_type_str,
            status=S4TaskStatus.QUEUED.value,
            input_sanitized=sanitized_input,
            validation_passed=False,
            recovery_events=[],
        )
        self._session.add(task)
        try:
            await self._session.flush()
        except IntegrityError as exc:
            await self._session.rollback()
            raise S4DuplicateTaskNumberError(f"Duplicate task number in run: {exc}") from exc

        return task

    async def get_next_task_number(
        self,
        run_id: uuid.UUID,
        *,
        for_update: bool = False,
    ) -> int:
        """Determina de forma atómica el siguiente número secuencial de tarea en la corrida.
        
        Si for_update=True, adquiere bloqueo exclusivo sobre la fila del run (SELECT ... FOR UPDATE)
        para serializar la asignación entre transacciones concurrentes.
        """
        if for_update:
            await self.get_load_run(run_id, for_update=True)
        stmt = select(func.coalesce(func.max(S4TaskExecution.task_number), 0) + 1).where(
            S4TaskExecution.run_id == run_id
        )
        return int((await self._session.execute(stmt)).scalar_one())

    async def allocate_replenishment_task(
        self,
        run_id: uuid.UUID,
        catalog: Any,
        *,
        min_duration_seconds: float = 43200.0,
    ) -> S4TaskExecution | None:
        """Genera y encola atómicamente la siguiente tarea de reposición bajo bloqueo transaccional.
        
        Garantías de concurrencia e idempotencia:
        1. Bloquea la fila del run en PostgreSQL (SELECT ... FOR UPDATE) impidiendo que dos workers generen números concurrentemente.
        2. Verifica si ya existen tareas QUEUED o RUNNING suficientes; si existen, no crea tareas innecesarias.
        3. Verifica si ya se cumplieron simultáneamente las metas de tareas exitosas y duración; si ambas se alcanzaron, no crea tareas.
        4. Calcula atómicamente MAX(task_number) + 1 e inserta la tarea sin riesgo de colisión de unicidad.
        """
        run = await self.get_load_run(run_id, for_update=True)
        if run.status in (S4RunStatus.COMPLETED.value, S4RunStatus.CANCELLED.value):
            return None

        # Comprobar si hay tareas pendientes encoladas o en ejecución
        stmt_pending = select(func.count(S4TaskExecution.id)).where(
            S4TaskExecution.run_id == run_id,
            S4TaskExecution.status.in_([S4TaskStatus.QUEUED.value, S4TaskStatus.RUNNING.value]),
        )
        pending_count = int((await self._session.execute(stmt_pending)).scalar_one() or 0)
        if pending_count > 0:
            return None

        elapsed = (datetime.now(UTC) - run.started_at).total_seconds() if run.started_at else 0.0
        is_completed_target = run.completed_tasks >= run.target_tasks
        if min_duration_seconds > 0.0:
            stats = await self.get_run_statistics(run_id)
            effective_activity = float(stats.effective_llm_activity_seconds or 0.0)
            is_duration_target = (elapsed >= min_duration_seconds) and (effective_activity >= min_duration_seconds)
        else:
            is_duration_target = True

        if is_completed_target and is_duration_target:
            return None

        stmt_max = select(func.coalesce(func.max(S4TaskExecution.task_number), 0) + 1).where(
            S4TaskExecution.run_id == run_id
        )
        next_num = int((await self._session.execute(stmt_max)).scalar_one())
        tdef = catalog.generate_task_definition(next_num)

        return await self.create_task_execution(
            run_id=run_id,
            task_number=next_num,
            task_type=tdef.get("task_type", S4TaskType.GENERAL_TECHNICAL),
            input_payload=tdef,
        )

    async def get_task_execution(
        self,
        task_id: uuid.UUID,
        *,
        for_update: bool = False,
    ) -> S4TaskExecution:
        """Obtiene una ejecución de tarea por su ID o eleva S4TaskNotFoundError."""
        if for_update:
            stmt = select(S4TaskExecution).where(S4TaskExecution.id == task_id).with_for_update()
            task = (await self._session.execute(stmt)).scalar_one_or_none()
        else:
            task = await self._session.get(S4TaskExecution, task_id)
        if not task:
            raise S4TaskNotFoundError(f"S4TaskExecution '{task_id}' not found")
        return task

    async def start_task_execution(
        self,
        task_id: uuid.UUID,
        worker_id: str | None = None,
        lease_token: str | None = None,
    ) -> S4TaskExecution:
        """Inicia la ejecución de una tarea pasando a 'running' bajo bloqueo exclusivo y lease token."""
        task = await self.get_task_execution(task_id, for_update=True)
        if task.status != S4TaskStatus.QUEUED.value:
            raise S4InvalidStateTransitionError(
                f"Cannot start task from status '{task.status}' (expected 'queued')"
            )
        now = datetime.now(UTC)
        task.status = S4TaskStatus.RUNNING.value
        task.started_at = now
        task.heartbeat_at = now
        if worker_id:
            task.worker_id = worker_id
        task.lease_token = lease_token or uuid.uuid4().hex
        task.lease_generation = (task.lease_generation or 0) + 1
        await self._session.flush()
        return task

    async def claim_next_task(
        self,
        run_id: uuid.UUID,
        worker_id: str,
    ) -> S4TaskExecution | None:
        """Reclama atómicamente la siguiente tarea en cola con SELECT ... FOR UPDATE SKIP LOCKED y token de lease.
        
        Permite dispatch concurrente de múltiples workers sin colisiones ni bloqueos de contención.
        """
        stmt = (
            select(S4TaskExecution)
            .where(
                S4TaskExecution.run_id == run_id,
                S4TaskExecution.status == S4TaskStatus.QUEUED.value,
            )
            .order_by(S4TaskExecution.task_number.asc())
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        task = (await self._session.execute(stmt)).scalar_one_or_none()
        if not task:
            return None

        now = datetime.now(UTC)
        task.status = S4TaskStatus.RUNNING.value
        task.worker_id = worker_id
        task.lease_token = uuid.uuid4().hex
        task.lease_generation = (task.lease_generation or 0) + 1
        task.started_at = now
        task.heartbeat_at = now
        await self._session.flush()
        return task

    async def update_task_heartbeat(
        self,
        task_id: uuid.UUID,
        worker_id: str | None = None,
        lease_token: str | None = None,
    ) -> datetime:
        """Actualiza la marca de vida (lease) de una tarea activa con verificación estricta de propietario."""
        task = await self.get_task_execution(task_id, for_update=True)
        if task.status != S4TaskStatus.RUNNING.value:
            raise S4WorkerLeaseExpiredError(
                f"Cannot heartbeat task '{task_id}': task status is '{task.status}' (expected 'running')"
            )
        if worker_id is not None and task.worker_id != worker_id:
            raise S4WorkerLeaseExpiredError(
                f"Worker '{worker_id}' lease expired for task '{task_id}'. Active worker is '{task.worker_id}'."
            )
        if lease_token is not None and task.lease_token != lease_token:
            raise S4WorkerLeaseExpiredError(
                f"Lease token mismatch for task '{task_id}': active token '{task.lease_token}', presented '{lease_token}'."
            )
        now = datetime.now(UTC)
        task.heartbeat_at = now
        if worker_id:
            task.worker_id = worker_id
        await self._session.flush()
        return now

    async def recover_orphan_tasks(
        self,
        run_id: uuid.UUID,
        timeout_seconds: float = 120.0,
        max_attempts: int = 3,
    ) -> list[S4TaskExecution]:
        """Detecta y recupera tareas huérfanas cuya última señal de vida excedió el umbral.
        
        Si la tarea tiene reintentos disponibles (< max_attempts), se reencola a 'queued'
        con worker_id y lease_token reseteados (invalidando al worker anterior) y se registra el evento.
        Si excedió max_attempts, se marca como 'failed' y se contabiliza en la corrida.
        """
        cutoff = datetime.now(UTC) - timedelta(seconds=timeout_seconds)
        stmt = (
            select(S4TaskExecution)
            .where(
                S4TaskExecution.run_id == run_id,
                S4TaskExecution.status == S4TaskStatus.RUNNING.value,
                func.coalesce(S4TaskExecution.heartbeat_at, S4TaskExecution.started_at) < cutoff,
            )
            .order_by(S4TaskExecution.task_number.asc())
            .with_for_update(skip_locked=True)
        )
        orphans = (await self._session.execute(stmt)).scalars().all()
        recovered: list[S4TaskExecution] = []

        for task in orphans:
            # Inspeccionar si la tarea huérfana tiene llamadas LLM inciertas (timeout_uncertain)
            unc_stmt = select(func.count(LLMUsageRecord.id)).where(
                LLMUsageRecord.s4_task_execution_id == task.id,
                LLMUsageRecord.measurement_status == "timeout_uncertain",
            )
            uncertain_calls = int((await self._session.execute(unc_stmt)).scalar_one())
            has_uncertain_call = (
                uncertain_calls > 0
                or (task.error_sanitized is not None and "uncertain" in task.error_sanitized.lower())
            )

            if has_uncertain_call:
                # Regla de seguridad financiera: NO reencolar automáticamente si hay llamadas de costo incierto
                task.status = S4TaskStatus.FAILED.value
                task.validation_passed = False
                task.finished_at = datetime.now(UTC)
                task.lease_token = None
                clean_details = (
                    f"Heartbeat timed out after {timeout_seconds}s. Task has {uncertain_calls} uncertain LLM call(s); "
                    "automatic requeue prohibited pending manual reconciliation."
                )
                task.error_sanitized = clean_details
                event = S4RecoveryEvent(
                    timestamp=datetime.now(UTC),
                    event_type="uncertain_recovery_blocked",
                    attempt=task.attempt_count,
                    details=clean_details,
                )
                events = list(task.recovery_events or [])
                events.append(event.model_dump(mode="json"))
                task.recovery_events = events
                run = await self.get_load_run(task.run_id, for_update=True)
                run.failed_tasks += 1
            elif task.attempt_count < max_attempts:
                task.attempt_count += 1
                task.status = S4TaskStatus.QUEUED.value
                task.worker_id = None
                task.lease_token = None
                task.lease_generation = (task.lease_generation or 0) + 1
                task.heartbeat_at = None
                clean_details = (
                    f"Heartbeat timed out after {timeout_seconds}s. "
                    f"Requeued for attempt {task.attempt_count}."
                )
                event = S4RecoveryEvent(
                    timestamp=datetime.now(UTC),
                    event_type="heartbeat_timeout",
                    attempt=task.attempt_count,
                    details=clean_details,
                )
                events = list(task.recovery_events or [])
                events.append(event.model_dump(mode="json"))
                task.recovery_events = events
            else:
                task.status = S4TaskStatus.FAILED.value
                task.validation_passed = False
                task.finished_at = datetime.now(UTC)
                task.lease_token = None
                task.error_sanitized = (
                    f"Heartbeat timed out after {timeout_seconds}s and reached max attempts ({max_attempts})."
                )
                run = await self.get_load_run(task.run_id, for_update=True)
                run.failed_tasks += 1
            recovered.append(task)

        if recovered:
            await self._session.flush()
        return recovered

    async def record_uncertain_liability(
        self,
        run_id: uuid.UUID,
        task_id: uuid.UUID,
        amount_usd: float,
    ) -> float:
        """Registra y persiste un pasivo incierto de costo en la corrida para trazabilidad durable."""
        run = await self.get_load_run(run_id, for_update=True)
        meta = dict(run.meta or {})
        current_liabilities = float(meta.get("uncertain_liabilities_usd", 0.0))
        new_liabilities = round(current_liabilities + amount_usd, 6)
        meta["uncertain_liabilities_usd"] = new_liabilities
        unreconciled = list(meta.get("unreconciled_task_ids", []))
        str_task_id = str(task_id)
        if str_task_id not in unreconciled:
            unreconciled.append(str_task_id)
        meta["unreconciled_task_ids"] = unreconciled
        run.meta = meta
        flag_modified(run, "meta")
        await self._session.flush()
        return new_liabilities

    async def reserve_run_budget(
        self,
        run_id: uuid.UUID,
        amount_usd: float,
    ) -> tuple[bool, str]:
        """Reserva presupuesto atómicamente en PostgreSQL bajo bloqueo de fila (SELECT ... FOR UPDATE)."""
        if amount_usd <= 0.0 or math.isnan(amount_usd) or math.isinf(amount_usd):
            raise ValueError(f"Reservation amount must be positive finite number: {amount_usd}")
        run = await self.get_load_run(run_id, for_update=True)
        meta = dict(run.meta or {})
        active_res = float(meta.get("active_reservations_usd", 0.0))
        uncertain_liab = float(meta.get("uncertain_liabilities_usd", 0.0))
        projected = run.total_cost_usd + active_res + uncertain_liab + amount_usd

        if projected > run.budget_limit_usd:
            msg = (
                f"DB budget reservation rejected: projected cost ${projected:.4f} USD "
                f"(confirmed: ${run.total_cost_usd:.4f}, active: ${active_res:.4f}, "
                f"uncertain: ${uncertain_liab:.4f}, req: ${amount_usd:.4f}) exceeds limit ${run.budget_limit_usd:.4f} USD"
            )
            return False, msg

        meta["active_reservations_usd"] = round(active_res + amount_usd, 6)
        run.meta = meta
        flag_modified(run, "meta")
        await self._session.flush()
        return True, "DB budget reserved successfully"

    async def release_run_budget_reservation(
        self,
        run_id: uuid.UUID,
        amount_usd: float,
    ) -> float:
        """Libera una reserva presupuestaria en PostgreSQL bajo bloqueo de fila."""
        run = await self.get_load_run(run_id, for_update=True)
        meta = dict(run.meta or {})
        active_res = float(meta.get("active_reservations_usd", 0.0))
        new_active = max(0.0, round(active_res - amount_usd, 6))
        meta["active_reservations_usd"] = new_active
        run.meta = meta
        flag_modified(run, "meta")
        await self._session.flush()
        return new_active

    async def reconcile_task_cost(
        self,
        task_id: uuid.UUID,
        confirmed_cost_usd: float,
        estimated_liability_usd: float = 0.05,
        operator: str = "operator",
    ) -> S4TaskExecution:
        """Reconcilia el costo real de una tarea que tuvo fallo incierto de forma idempotente y auditable."""
        if confirmed_cost_usd < 0.0 or math.isnan(confirmed_cost_usd) or math.isinf(confirmed_cost_usd):
            raise ValueError(f"Invalid confirmed_cost_usd: {confirmed_cost_usd} (must be finite non-negative number)")
        if estimated_liability_usd < 0.0 or math.isnan(estimated_liability_usd) or math.isinf(estimated_liability_usd):
            raise ValueError(f"Invalid estimated_liability_usd: {estimated_liability_usd} (must be finite non-negative number)")

        task = await self.get_task_execution(task_id, for_update=True)
        run = await self.get_load_run(task.run_id, for_update=True)
        meta = dict(run.meta or {})
        unreconciled_ids = list(meta.get("unreconciled_task_ids", []))
        is_first_reconciliation = str(task.id) in unreconciled_ids

        # Actualizar llamadas inciertas asociadas
        stmt = (
            select(LLMUsageRecord)
            .where(
                LLMUsageRecord.s4_task_execution_id == task.id,
                LLMUsageRecord.measurement_status.in_(["timeout_uncertain", "reconciled"]),
            )
            .order_by(LLMUsageRecord.call_sequence)
        )
        records = (await self._session.execute(stmt)).scalars().all()
        if records:
            if len(records) == 1:
                records[0].cost_usd = confirmed_cost_usd
                records[0].measurement_status = "reconciled"
            else:
                # Si hay múltiples llamadas, asignar a la primera y 0 a subsecuentes (o según se concilie)
                records[0].cost_usd = confirmed_cost_usd
                records[0].measurement_status = "reconciled"
                for r in records[1:]:
                    r.cost_usd = 0.0
                    r.measurement_status = "reconciled"

        # Re-calcular costo agregado de la tarea
        agg_stmt = (
            select(func.coalesce(func.sum(LLMUsageRecord.cost_usd), 0.0))
            .where(LLMUsageRecord.s4_task_execution_id == task.id)
        )
        raw_val = (await self._session.execute(agg_stmt)).scalar_one()
        new_task_cost = float(raw_val or 0.0)
        old_task_cost = task.cost_usd
        task.cost_usd = round(new_task_cost, 6)

        # Ajustar total_cost_usd de la corrida de forma consistente
        run.total_cost_usd = round(run.total_cost_usd - old_task_cost + task.cost_usd, 6)

        # Disminuir pasivo incierto en run.meta SOLO si es la primera reconciliación (idempotencia)
        actual_deduction = 0.0
        if is_first_reconciliation:
            curr_liabilities = float(meta.get("uncertain_liabilities_usd", 0.0))
            actual_deduction = min(curr_liabilities, estimated_liability_usd)
            new_liab = max(0.0, round(curr_liabilities - actual_deduction, 6))
            meta["uncertain_liabilities_usd"] = new_liab
            meta["unreconciled_task_ids"] = [t for t in unreconciled_ids if t != str(task.id)]
            run.meta = meta
            flag_modified(run, "meta")

        # Registrar evento de reconciliación auditable
        rec_event = S4RecoveryEvent(
            timestamp=datetime.now(UTC),
            event_type="cost_reconciled",
            attempt=task.attempt_count,
            details=(
                f"Reconciliation by {operator}: confirmed cost ${confirmed_cost_usd:.5f} USD "
                f"(previous: ${old_task_cost:.5f} USD, liability deducted: ${actual_deduction:.5f} USD)."
            ),
        )
        events = list(task.recovery_events or [])
        events.append(rec_event.model_dump(mode="json"))
        task.recovery_events = events
        flag_modified(task, "recovery_events")

        await self._session.flush()
        return task

    async def record_task_recovery_event(
        self,
        task_id: uuid.UUID,
        *,
        event_type: str,
        attempt: int,
        details: str,
    ) -> S4RecoveryEvent:
        """Registra un evento de recuperación sanitizado en la tarea."""
        task = await self.get_task_execution(task_id)
        clean_details = S4Sanitizer.sanitize_text(details)
        event = S4RecoveryEvent(
            timestamp=datetime.now(UTC),
            event_type=event_type,
            attempt=attempt,
            details=clean_details,
        )
        events = list(task.recovery_events or [])
        events.append(event.model_dump(mode="json"))
        task.recovery_events = events
        task.attempt_count = max(task.attempt_count, attempt)
        await self._session.flush()
        return event

    async def record_task_llm_call(
        self,
        task_id: uuid.UUID,
        *,
        model: str,
        input_tokens: int | None,
        output_tokens: int | None,
        total_tokens: int | None = None,
        stage: str = "s4_task_execution",
        provider: str = "openai-compatible",
        gateway_request_id: str | None = None,
        call_sequence: int | None = None,
        gateway_metadata: dict[str, Any] | None = None,
        measurement_status: str | None = None,
        cost_usd: float | None = None,
    ) -> LLMUsageRecord:
        """Registra una llamada LLM vinculada durablemente a la tarea S4 con secuencia y metadatos."""
        task = await self.get_task_execution(task_id)
        cost: float | None = cost_usd if cost_usd is not None else calculate_llm_cost(model, input_tokens, output_tokens)

        calc_total = total_tokens
        if calc_total is None and input_tokens is not None and output_tokens is not None:
            calc_total = input_tokens + output_tokens

        if measurement_status is not None:
            meas_status = measurement_status
        elif input_tokens is not None and output_tokens is not None:
            meas_status = "measured"
        else:
            meas_status = "unavailable"

        clean_request_id = str(gateway_request_id).strip() if gateway_request_id else None

        # Determinar secuencia de llamada si no fue provista explícitamente
        if call_sequence is None:
            seq_stmt = select(func.coalesce(func.max(LLMUsageRecord.call_sequence), 0) + 1).where(
                LLMUsageRecord.s4_task_execution_id == task.id
            )
            call_sequence = int((await self._session.execute(seq_stmt)).scalar_one())

        clean_gw_meta = None
        if gateway_metadata:
            try:
                sanitized_str = S4Sanitizer.sanitize_payload(gateway_metadata)
                clean_gw_meta = json.loads(sanitized_str)
            except (json.JSONDecodeError, TypeError, ValueError):
                clean_gw_meta = {"raw": S4Sanitizer.sanitize_text(str(gateway_metadata))}

        record = LLMUsageRecord(
            id=uuid.uuid4(),
            interview_id=None,
            turn_id=None,
            s4_task_execution_id=task.id,
            gateway_request_id=clean_request_id,
            call_sequence=call_sequence,
            gateway_metadata=clean_gw_meta,
            stage=stage,
            provider=provider,
            model=model,
            tokens_input=input_tokens,
            tokens_output=output_tokens,
            tokens_total=calc_total,
            cost_usd=cost,
            measurement_status=meas_status,
        )
        self._session.add(record)
        await self._session.flush()
        return record

    async def complete_task_execution(
        self,
        task_id: uuid.UUID,
        *,
        validation_passed: bool,
        result_summary: Any = None,
        error: Any | None = None,
        final_status: S4TaskStatus | None = None,
        worker_id: str | None = None,
        lease_token: str | None = None,
    ) -> S4TaskExecution:
        """Finaliza la tarea con agregación determinista bajo bloqueo de fila y validación de fencing (AUD-S4-05).
        
        Garantías del contrato S4:
        - Bloqueo exclusivo de fila (SELECT ... FOR UPDATE) en la tarea y en la corrida padre.
        - Fencing de lease: valida que el worker_id y lease_token coincidan con el propietario activo.
        - Una tarea NO puede marcarse como 'succeeded' a menos que validation_passed=True y
          cuente con un resultado válido no vacío.
        - Los costes y tokens se agregan de forma exacta desde las llamadas asociadas en BD.
        """
        task = await self.get_task_execution(task_id, for_update=True)
        if task.status != S4TaskStatus.RUNNING.value:
            raise S4InvalidStateTransitionError(
                f"Cannot complete task from status '{task.status}' (expected 'running')"
            )

        # Validación estricta de fencing (AUD-S4-05)
        if worker_id is not None and task.worker_id != worker_id:
            raise S4WorkerLeaseExpiredError(
                f"Worker '{worker_id}' lease expired for task '{task_id}'. Active worker is '{task.worker_id}'."
            )
        if lease_token is not None and task.lease_token != lease_token:
            raise S4WorkerLeaseExpiredError(
                f"Lease token mismatch for task '{task_id}': active token '{task.lease_token}', presented '{lease_token}'."
            )

        # Adquirir bloqueo en la corrida padre de forma consistente
        run = await self.get_load_run(task.run_id, for_update=True)

        # Determinar estado objetivo
        if final_status is not None:
            target_status = final_status
        elif validation_passed:
            target_status = S4TaskStatus.SUCCEEDED
        else:
            target_status = S4TaskStatus.FAILED

        # Regla innegociable: No success sin validación explícita y resultado
        if target_status == S4TaskStatus.SUCCEEDED:
            if not validation_passed:
                raise S4TaskValidationError(
                    "Task cannot be marked succeeded without explicit validation_passed=True"
                )
            if not result_summary or not str(result_summary).strip():
                raise S4TaskValidationError(
                    "Task cannot be marked succeeded with empty result_summary"
                )

        sanitized_result = S4Sanitizer.sanitize_payload(result_summary) if result_summary else None
        sanitized_error = S4Sanitizer.sanitize_payload(error) if error else None

        # Agregación determinista desde llm_usage_records vinculados a esta tarea
        stmt = (
            select(
                func.count(LLMUsageRecord.id),
                func.coalesce(func.sum(LLMUsageRecord.tokens_input), 0),
                func.coalesce(func.sum(LLMUsageRecord.tokens_output), 0),
                func.coalesce(func.sum(LLMUsageRecord.cost_usd), 0.0),
            )
            .where(LLMUsageRecord.s4_task_execution_id == task_id)
        )
        agg_result = (await self._session.execute(stmt)).one()
        calls_count, sum_in, sum_out, sum_cost = agg_result

        task.status = target_status.value
        task.validation_passed = validation_passed
        task.result_summary = sanitized_result
        task.error_sanitized = sanitized_error
        task.finished_at = datetime.now(UTC)
        task.model_calls = int(calls_count or 0)
        task.input_tokens = int(sum_in or 0)
        task.output_tokens = int(sum_out or 0)
        task.cost_usd = round(float(sum_cost or 0.0), 6)

        # Actualizar contadores de la corrida bloqueada
        if target_status == S4TaskStatus.SUCCEEDED:
            run.completed_tasks += 1
        elif target_status == S4TaskStatus.FAILED:
            run.failed_tasks += 1
            # Si la tarea falló con llamadas inciertas, persistir el pasivo atómicamente si no fue registrado previamente
            unc_stmt = select(func.count(LLMUsageRecord.id)).where(
                LLMUsageRecord.s4_task_execution_id == task_id,
                LLMUsageRecord.measurement_status == "timeout_uncertain",
            )
            has_uncertain = int((await self._session.execute(unc_stmt)).scalar_one()) > 0
            if has_uncertain or (sanitized_error and ("uncertain" in sanitized_error.lower() or "read timed out" in sanitized_error.lower())):
                meta = dict(run.meta or {})
                unrec = list(meta.get("unreconciled_task_ids", []))
                str_tid = str(task.id)
                if str_tid not in unrec:
                    curr_liab = float(meta.get("uncertain_liabilities_usd", 0.0))
                    meta["uncertain_liabilities_usd"] = round(curr_liab + 0.05, 6)
                    unrec.append(str_tid)
                    meta["unreconciled_task_ids"] = unrec
                    run.meta = meta
                    flag_modified(run, "meta")
        elif target_status == S4TaskStatus.CANCELLED:
            run.cancelled_tasks += 1

        run.total_cost_usd = round(run.total_cost_usd + task.cost_usd, 6)

        await self._session.flush()
        return task

    # -------------------------------------------------------------------------
    # 3. Métricas y Estadísticas de Corrida
    # -------------------------------------------------------------------------

    async def get_run_statistics(self, run_id: uuid.UUID) -> S4LoadRunSummary:
        """Calcula el resumen agregado y métricas de desempeño de la corrida."""
        run = await self.get_load_run(run_id)

        # Consulta agregada sobre tareas
        stmt = (
            select(
                func.count(S4TaskExecution.id),
                func.coalesce(func.sum(S4TaskExecution.model_calls), 0),
                func.coalesce(func.sum(S4TaskExecution.input_tokens), 0),
                func.coalesce(func.sum(S4TaskExecution.output_tokens), 0),
                func.coalesce(func.sum(S4TaskExecution.cost_usd), 0.0),
            )
            .where(S4TaskExecution.run_id == run_id)
        )
        agg_row = (await self._session.execute(stmt)).one()
        raw_tasks, raw_calls, raw_in, raw_out, raw_cost = agg_row

        total_tasks_recorded = int(raw_tasks or 0)
        total_calls = int(raw_calls or 0)
        total_in = int(raw_in or 0)
        total_out = int(raw_out or 0)
        total_cost = float(raw_cost or 0.0)
        success_rate = (
            round((run.completed_tasks / total_tasks_recorded) * 100.0, 2)
            if total_tasks_recorded > 0
            else 0.0
        )
        avg_cost = (
            round(float(total_cost) / total_tasks_recorded, 6)
            if total_tasks_recorded > 0
            else 0.0
        )

        duration_sec: float | None = None
        throughput_hr: float | None = None
        if run.started_at:
            end_time = run.finished_at or datetime.now(UTC)
            duration_sec = max(0.001, (end_time - run.started_at).total_seconds())
            if duration_sec > 0:
                throughput_hr = round((run.completed_tasks / duration_sec) * 3600.0, 2)

        # Consulta de telemetría y distribución de llamadas LLM (DEF-DURATION-01)
        llm_stmt = (
            select(LLMUsageRecord)
            .join(S4TaskExecution, S4TaskExecution.id == LLMUsageRecord.s4_task_execution_id)
            .where(S4TaskExecution.run_id == run_id)
            .order_by(LLMUsageRecord.created_at.asc())
        )
        llm_records = (await self._session.execute(llm_stmt)).scalars().all()

        CONFIRMED_MEASUREMENT_STATUSES = {"measured", "exact", "reconciled"}
        valid_records = [
            r for r in llm_records
            if r.tokens_input is not None
            and r.tokens_input > 0
            and r.tokens_output is not None
            and r.tokens_output > 0
            and r.measurement_status in CONFIRMED_MEASUREMENT_STATUSES
        ]
        calls_with_usage = len(valid_records)

        first_llm_call_at = valid_records[0].created_at if valid_records else None
        last_llm_call_at = valid_records[-1].created_at if valid_records else None

        llm_span_sec: float | None = None
        if first_llm_call_at and last_llm_call_at:
            llm_span_sec = round(max(0.0, (last_llm_call_at - first_llm_call_at).total_seconds()), 2)

        max_gap_sec: float | None = None
        inactivity_exceeded_count = 0
        max_inactivity_threshold = 120.0
        hourly_dist: dict[str, int] = {}

        # Partición en ventanas continuas sin brechas > 120s
        longest_continuous_window_sec = 0.0
        windows: list[list[LLMUsageRecord]] = []
        current_window: list[LLMUsageRecord] = []

        if valid_records:
            max_gap = 0.0
            current_window = [valid_records[0]]
            for i in range(1, len(valid_records)):
                gap = (valid_records[i].created_at - valid_records[i - 1].created_at).total_seconds()
                max_gap = max(max_gap, gap)
                if gap > max_inactivity_threshold:
                    inactivity_exceeded_count += 1
                    windows.append(current_window)
                    current_window = [valid_records[i]]
                else:
                    current_window.append(valid_records[i])
            if current_window:
                windows.append(current_window)
            max_gap_sec = round(max_gap, 2)

            for w in windows:
                if len(w) >= 2:
                    w_sec = (w[-1].created_at - w[0].created_at).total_seconds()
                else:
                    w_sec = 0.0
                longest_continuous_window_sec = max(longest_continuous_window_sec, w_sec)

            base_time = first_llm_call_at or run.started_at
            if base_time:
                for r in valid_records:
                    hour_idx = int(max(0.0, (r.created_at - base_time).total_seconds()) // 3600)
                    key = f"hour_{hour_idx:02d}"
                    hourly_dist[key] = hourly_dist.get(key, 0) + 1

        effective_activity_sec = (
            round(longest_continuous_window_sec, 2)
            if longest_continuous_window_sec > 0.0
            else (0.0 if valid_records else None)
        )
        continuous_window_valid = bool(longest_continuous_window_sec >= 43200.0)

        meta = dict(run.meta or {})
        uncertain_liab = float(meta.get("uncertain_liabilities_usd", 0.0))
        active_res = float(meta.get("active_reservations_usd", 0.0))
        total_exp = round(total_cost + active_res + uncertain_liab, 6)

        return S4LoadRunSummary(
            run_id=run.id,
            status=S4RunStatus(run.status),
            target_tasks=run.target_tasks,
            completed_tasks=run.completed_tasks,
            failed_tasks=run.failed_tasks,
            cancelled_tasks=run.cancelled_tasks,
            total_tasks_recorded=total_tasks_recorded,
            success_rate_percent=success_rate,
            budget_limit_usd=run.budget_limit_usd,
            total_cost_usd=round(float(total_cost), 6),
            average_cost_per_task_usd=avg_cost,
            total_input_tokens=int(total_in),
            total_output_tokens=int(total_out),
            total_model_calls=int(total_calls),
            started_at=run.started_at,
            finished_at=run.finished_at,
            duration_seconds=round(duration_sec, 2) if duration_sec is not None else None,
            throughput_tasks_per_hour=throughput_hr,
            first_llm_call_at=first_llm_call_at,
            last_llm_call_at=last_llm_call_at,
            llm_activity_duration_seconds=llm_span_sec,
            effective_llm_activity_seconds=effective_activity_sec,
            longest_continuous_window_seconds=round(longest_continuous_window_sec, 2) if longest_continuous_window_sec > 0.0 else None,
            continuous_window_valid=continuous_window_valid,
            interruption_count=inactivity_exceeded_count,
            calls_with_usage=calls_with_usage,
            max_gap_seconds_between_calls=max_gap_sec,
            inactivity_exceeded_count=inactivity_exceeded_count,
            max_inactivity_threshold_seconds=max_inactivity_threshold,
            uncertain_liabilities_usd=uncertain_liab,
            active_reservations_usd=active_res,
            total_exposure_usd=total_exp,
            hourly_distribution=hourly_dist,
        )
