"""Worker autónomo para ejecución, verificación y despacho de unidades de trabajo S4."""

from __future__ import annotations

import asyncio
import inspect
import logging
import time
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.db.models.interview import LLMUsageRecord
from src.db.models.s4 import S4TaskExecution
from src.s4.catalog import S4TaskCatalogGenerator
from src.s4.enums import S4RunStatus, S4TaskStatus
from src.s4.pacer import S4Pacer
from src.s4.recovery import S4RecoveryCoordinator
from src.s4.schemas import S4LoadRunSummary
from src.s4.service import S4Service, S4WorkerLeaseExpiredError
from src.s4.watchdog import S4Watchdog

logger = logging.getLogger("evaluador.s4.worker")


async def default_synthetic_executor(
    task: S4TaskExecution,
    task_def: dict[str, Any],
) -> dict[str, Any]:
    """Ejecutor técnico sintético determinista para pruebas de carga y simulación controlada."""
    seniority = task_def.get("seniority", "mid")
    category = task_def.get("category", "general")
    task_num = task.task_number

    # Simular una o dos llamadas LLM según la dificultad
    calls = [
        {
            "model": "grok-beta",
            "input_tokens": 120 + (task_num % 50),
            "output_tokens": 80 + (task_num % 30),
            "gateway_request_id": f"gw_mock_req_{task_num:05d}_01",
            "gateway_metadata": {
                "cf-ray": f"8a9b{task_num:04d}cdef-BOG",
                "x-ratelimit-remaining-tokens": 985000,
                "provider": "xai-gateway",
                "category": category,
            },
        }
    ]

    # Para seniorities altos, añadir turno adicional de evaluación
    if seniority in ("senior", "lead"):
        calls.append(
            {
                "model": "grok-beta",
                "input_tokens": 180 + (task_num % 40),
                "output_tokens": 110 + (task_num % 20),
                "gateway_request_id": f"gw_mock_req_{task_num:05d}_02",
                "gateway_metadata": {
                    "cf-ray": f"8a9b{task_num:04d}cdef-BOG-2",
                    "x-ratelimit-remaining-tokens": 983000,
                    "provider": "xai-gateway",
                },
            }
        )

    # Construir un resultado verificado acorde a los criterios de aceptación
    req_kws = task_def.get("acceptance_criteria", {}).get("required_keywords", [])
    kw_str = " and ".join(req_kws) if req_kws else "standard architectural pattern"

    summary = (
        f"Definitive technical evaluation for task #{task_num} [{seniority.upper()}]. "
        f"Analysis verified domain concepts: {kw_str}. Solution adheres to optimal constraints and temporal complexity bounds."
    )

    return {
        "validation_passed": True,
        "summary": summary,
        "metrics": {"score": 92.5, "latency_ms": 145},
        "sandbox_result": {"status": "accepted"},
        "model_calls": calls,
    }


class S4TaskWorker:
    """Worker autónomo para despacho, control de lease y ejecución concurrente de tareas S4."""

    def __init__(
        self,
        *,
        run_id: uuid.UUID,
        session_factory: async_sessionmaker[AsyncSession],
        worker_id: str | None = None,
        watchdog: S4Watchdog | None = None,
        pacer: S4Pacer | None = None,
        catalog: S4TaskCatalogGenerator | None = None,
        executor: Callable[..., Any] | None = None,
        heartbeat_interval_seconds: float = 10.0,
        orphan_sweep_interval_seconds: float = 60.0,
        min_duration_seconds: float = 43200.0,
        is_manual_resume: bool = False,
    ) -> None:
        self.run_id = run_id
        self.session_factory = session_factory
        self.worker_id = worker_id or f"worker-{uuid.uuid4().hex[:8]}"
        self.watchdog = watchdog or S4Watchdog()
        self.pacer = pacer
        self.catalog = catalog or S4TaskCatalogGenerator()
        self.executor: Any = executor or default_synthetic_executor
        self.heartbeat_interval_seconds = heartbeat_interval_seconds
        self.orphan_sweep_interval_seconds = orphan_sweep_interval_seconds
        self.min_duration_seconds = max(0.0, float(min_duration_seconds))
        self.is_manual_resume = is_manual_resume

        self._stop_requested = False
        self._last_orphan_sweep = 0.0

    def request_stop(self) -> None:
        """Solicita la detención ordenada del worker."""
        self._stop_requested = True

    async def _emit_heartbeat(self, task_id: uuid.UUID, lease_token: str | None = None) -> bool:
        """Emite una señal de latido atómica hacia PostgreSQL con validación de lease."""
        try:
            async with self.session_factory() as session, session.begin():
                service = S4Service(session)
                await service.update_task_heartbeat(task_id, self.worker_id, lease_token=lease_token)
                return True
        except S4WorkerLeaseExpiredError as lease_exc:
            logger.warning(f"Worker lease expired during heartbeat for task {task_id}: {lease_exc}")
            return False
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"Failed to emit heartbeat for task {task_id}: {exc}")
            return True

    async def _heartbeat_loop(
        self,
        task_id: uuid.UUID,
        lease_token: str | None,
        stop_event: asyncio.Event,
    ) -> None:
        """Bucle en segundo plano que mantiene vivo el lease de la tarea activa."""
        while not stop_event.is_set():
            try:
                await asyncio.wait_for(
                    stop_event.wait(),
                    timeout=self.heartbeat_interval_seconds,
                )
                break
            except TimeoutError:
                ok = await self._emit_heartbeat(task_id, lease_token)
                if not ok:
                    stop_event.set()
                    break

    async def execute_task(
        self,
        task: S4TaskExecution,
        session: AsyncSession,
    ) -> S4TaskExecution:
        """Ejecuta una tarea individual bajo control de lease, validación y trazabilidad."""
        service = S4Service(session)
        task_def = self.catalog.generate_task_definition(task.task_number)

        # Iniciar latidos concurrentes con token de lease (AUD-S4-05)
        stop_heartbeat = asyncio.Event()
        heartbeat_task = asyncio.create_task(
            self._heartbeat_loop(task.id, task.lease_token, stop_heartbeat)
        )

        reserved_cost = 0.05
        total_reserved_for_task = reserved_cost
        is_uncertain_outcome = False
        if self.pacer:
            self.pacer.record_dispatch()
        run = await service.get_load_run(self.run_id)
        # Reservar costo anticipadamente (Seguridad Presupuestaria AUD-S4-09 / Sección 12)
        reserved_ok, reserve_msg = self.watchdog.reserve_cost(reserved_cost, run.total_cost_usd)
        if not reserved_ok:
            stop_heartbeat.set()
            heartbeat_task.cancel()
            return await service.complete_task_execution(
                task.id,
                validation_passed=False,
                result_summary=None,
                error=f"BudgetReservationFailed: {reserve_msg}",
                final_status=S4TaskStatus.CANCELLED,
                worker_id=self.worker_id,
                lease_token=task.lease_token,
            )

        def reserve_turn_cost_cb(amount: float) -> tuple[bool, str]:
            nonlocal total_reserved_for_task
            ok, msg = self.watchdog.reserve_cost(amount, run.total_cost_usd)
            if ok:
                total_reserved_for_task = round(total_reserved_for_task + amount, 6)
            return ok, msg

        # Función de callback para persistencia INCREMENTAL inmediata de llamadas LLM (AUD-S4-06)
        async def record_call_callback(
            *,
            model: str,
            input_tokens: int | None,
            output_tokens: int | None,
            total_tokens: int | None = None,
            stage: str = "s4_task_execution",
            provider: str = "openai-compatible",
            gateway_request_id: str | None = None,
            gateway_metadata: dict[str, Any] | None = None,
            measurement_status: str | None = None,
            cost_usd: float | None = None,
        ) -> LLMUsageRecord:
            async with self.session_factory() as call_session, call_session.begin():
                call_srv = S4Service(call_session)
                return await call_srv.record_task_llm_call(
                    task.id,
                    model=model,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    total_tokens=total_tokens,
                    stage=stage,
                    provider=provider,
                    gateway_request_id=gateway_request_id,
                    gateway_metadata=gateway_metadata,
                    measurement_status=measurement_status,
                    cost_usd=cost_usd,
                )

        try:
            # Ejecución del agente técnico (soporta callback incremental y reserva de turnos)
            sig = inspect.signature(self.executor)
            if len(sig.parameters) >= 4:
                exec_output = await self.executor(task, task_def, record_call_callback, reserve_turn_cost_cb)
            elif len(sig.parameters) == 3:
                exec_output = await self.executor(task, task_def, record_call_callback)
            else:
                exec_output = await self.executor(task, task_def)
                # Si el ejecutor retornó model_calls en bloque, persistirlos inmediatamente
                model_calls = exec_output.get("model_calls", []) if isinstance(exec_output, dict) else []
                for call in model_calls:
                    await record_call_callback(
                        model=call.get("model", "grok-beta"),
                        input_tokens=call.get("input_tokens"),
                        output_tokens=call.get("output_tokens"),
                        total_tokens=call.get("total_tokens"),
                        stage=call.get("stage", "s4_task_execution"),
                        provider=call.get("provider", "openai-compatible"),
                        gateway_request_id=call.get("gateway_request_id"),
                        gateway_metadata=call.get("gateway_metadata"),
                        measurement_status=call.get("measurement_status"),
                        cost_usd=call.get("cost_usd"),
                    )

            if not isinstance(exec_output, dict):
                exec_output = {"summary": str(exec_output), "validation_passed": True}

            if exec_output.get("has_unavailable_usage"):
                is_uncertain_outcome = True

            # Validación de resultado según criterios de aceptación del catálogo (AUD-S4-11 / DEF-S4-04)
            valid, val_reason = self.catalog.validate_task_result(
                task_def,
                exec_output,
            )
            validation_passed = valid and bool(exec_output.get("validation_passed", False))

            # Finalizar tarea con agregación determinista en base de datos y validación de lease (AUD-S4-05)
            final_task = await service.complete_task_execution(
                task.id,
                validation_passed=validation_passed,
                result_summary=exec_output.get("summary"),
                error=None if validation_passed else val_reason,
                worker_id=self.worker_id,
                lease_token=task.lease_token,
            )

            # Notificar al watchdog sobre el costo acumulado y resultado
            run = await service.get_load_run(self.run_id)
            self.watchdog.record_task_outcome(
                validation_passed=validation_passed,
                current_cost_usd=run.total_cost_usd,
                error_details=val_reason if not validation_passed else None,
            )

            return final_task

        except S4WorkerLeaseExpiredError as lease_err:
            logger.warning(f"Task {task.task_number} rejected due to expired lease: {lease_err}")
            raise

        except Exception as exc:
            logger.exception("Error executing task %s", task.task_number)
            is_uncertain_outcome = (
                getattr(exc, "is_uncertain", False)
                or "uncertain" in str(exc).lower()
                or "read timed out" in str(exc).lower()
                or "write timed out" in str(exc).lower()
            )
            # Registrar fallo formal en BD
            final_task = await service.complete_task_execution(
                task.id,
                validation_passed=False,
                result_summary=None,
                error=f"WorkerExecutionError: {exc!s}",
                final_status=S4TaskStatus.FAILED,
                worker_id=self.worker_id,
                lease_token=task.lease_token,
            )
            run = await service.get_load_run(self.run_id)
            self.watchdog.record_task_outcome(
                validation_passed=False,
                current_cost_usd=run.total_cost_usd,
                error_details=str(exc),
            )
            return final_task

        finally:
            if is_uncertain_outcome:
                self.watchdog.retain_uncertain_liability(total_reserved_for_task)
            else:
                self.watchdog.release_cost_reservation(total_reserved_for_task)

            stop_heartbeat.set()
            heartbeat_task.cancel()
            try:
                await heartbeat_task
            except asyncio.CancelledError:
                pass

    async def run_single_step(self) -> S4TaskExecution | None:
        """Reclama y ejecuta una sola tarea de forma atómica y completa.
        
        Retorna la tarea ejecutada o None si la cola está vacía o el circuito está bloqueado.
        """
        if self._stop_requested or self.watchdog.is_permanent_trip:
            return None
        if self.watchdog.is_cooling_down:
            return None

        # 1. Reclamar tarea atómicamente con SKIP LOCKED y generación de lease
        claimed_task_id: uuid.UUID | None = None
        async with self.session_factory() as session, session.begin():
            service = S4Service(session)
            claimed = await service.claim_next_task(self.run_id, self.worker_id)
            if claimed:
                claimed_task_id = claimed.id

        if not claimed_task_id:
            return None

        # 2. Ejecutar la tarea reclamada en su propia transacción
        async with self.session_factory() as session, session.begin():
            service = S4Service(session)
            task = await service.get_task_execution(claimed_task_id)
            executed_task = await self.execute_task(task, session)
            return executed_task

    async def run_autonomous_loop(
        self,
        *,
        max_tasks: int | None = None,
        sweep_orphans: bool = True,
    ) -> S4LoadRunSummary:
        """Bucle principal de trabajo autónomo con soporte de enfriamiento y auto-recuperación desatendida.
        
        Despacha tareas, respeta el pacer durable, supervisa el watchdog y realiza barrido de huérfanos.
        """
        # Reconciliar cronómetro durable del pacer, pasivos inciertos y estado del circuito con PostgreSQL (AUD-S4-07)
        async with self.session_factory() as session:
            service = S4Service(session)
            run = await service.get_load_run(self.run_id)
            self.watchdog.rehydrate_circuit_state(run.meta, is_manual_resume=self.is_manual_resume)
            initial_liabilities = float((run.meta or {}).get("uncertain_liabilities_usd", 0.0))
            if initial_liabilities > 0:
                self.watchdog._uncertain_liabilities_usd = round(initial_liabilities, 6)
                logger.info(
                    f"Watchdog synchronized with ${initial_liabilities:.4f} USD of persistent uncertain liabilities."
                )

            initial_elapsed = 0.0
            if run.started_at:
                initial_elapsed = max(0.0, (datetime.now(UTC) - run.started_at).total_seconds())

            if self.pacer and not self.pacer.is_started:
                self.pacer.start(initial_elapsed_seconds=initial_elapsed)
                # Reconciliar última marca de despacho desde PostgreSQL para evitar ráfagas tras reinicio
                stmt_last = (
                    select(S4TaskExecution.started_at)
                    .where(S4TaskExecution.run_id == run.id, S4TaskExecution.started_at.is_not(None))
                    .order_by(S4TaskExecution.started_at.desc())
                    .limit(1)
                )
                last_started = (await session.execute(stmt_last)).scalar_one_or_none()
                if last_started:
                    sec_since_last = max(0.0, (datetime.now(UTC) - last_started).total_seconds())
                    self.pacer.record_dispatch(time.monotonic() - sec_since_last)

        processed_count = 0

        while not self._stop_requested and not self.watchdog.is_permanent_trip:
            if max_tasks is not None and processed_count >= max_tasks:
                break

            # Si el watchdog está en periodo de enfriamiento, esperar antes de habilitar la sonda (DEF-S4-03)
            if self.watchdog.is_cooling_down:
                can_probe, probe_msg = self.watchdog.check_and_advance_cooldown()
                if not can_probe:
                    logger.info(f"[WATCHDOG-COOLDOWN] {probe_msg}")
                    sleep_time = min(2.0, self.watchdog.cooldown_seconds)
                    await asyncio.sleep(sleep_time)
                    continue
                else:
                    logger.info(f"[WATCHDOG-PROBING] {probe_msg}")

            # Barrido periódico opcional de huérfanos
            if sweep_orphans:
                now_mono = asyncio.get_event_loop().time()
                if now_mono - self._last_orphan_sweep >= self.orphan_sweep_interval_seconds:
                    self._last_orphan_sweep = now_mono
                    async with self.session_factory() as session, session.begin():
                        recovery = S4RecoveryCoordinator(session)
                        await recovery.sweep_and_recover_orphans(self.run_id)

            if self.pacer:
                self.pacer.record_dispatch()

            task = await self.run_single_step()
            if not task:
                # Comprobar si la cola se vació pero aún no se han cumplido ambos objetivos:
                # 1. Al menos target_tasks completadas exitosamente (ej. 1.000 éxitos)
                # Y
                # 2. Al menos min_duration_seconds transcurridos de actividad (ej. 43.200s / 12 horas)
                # Si falta cualquiera de los dos, generar deterministamente la siguiente tarea (DEF-CAP-01)
                async with self.session_factory() as session, session.begin():
                    service = S4Service(session)
                    replenished_task = await service.allocate_replenishment_task(
                        self.run_id,
                        catalog=self.catalog,
                        min_duration_seconds=self.min_duration_seconds,
                    )
                    if replenished_task:
                        logger.info(
                            f"[DYNAMIC-REPLENISHMENT] Task #{replenished_task.task_number} enqueued atomically."
                        )
                        continue

                # Ambas condiciones fueron cumplidas exitosamente
                break

            processed_count += 1

            # Pacing dinámico si aplica (omite espera tras fallo/timeout para proteger ventana continua de 120s)
            if self.pacer:
                had_failure = task.status != S4TaskStatus.SUCCEEDED.value
                delay = self.pacer.compute_pacing_delay(
                    task.task_number,
                    had_failure_or_timeout=had_failure,
                )
                if delay > 0.0:
                    await self.pacer.sleep_delay(delay)

        # Si el watchdog disparó un disyuntor permanente o quedó en pausa, persistir inmediatamente en PostgreSQL (AUD-S4-09)
        if self.watchdog.is_permanent_trip or self.watchdog.is_tripped:
            async with self.session_factory() as session, session.begin():
                service = S4Service(session)
                run = await service.get_load_run(self.run_id, for_update=True)
                run.status = S4RunStatus.PAUSED.value
                meta = dict(run.meta or {})
                meta["watchdog_tripped"] = True
                meta["circuit_state"] = self.watchdog.circuit_state
                meta["circuit_cooldown_cycles"] = self.watchdog.cooldown_cycles
                meta["watchdog_trip_reason"] = self.watchdog.trip_reason
                meta["watchdog_tripped_at"] = (self.watchdog.tripped_at or datetime.now(UTC)).isoformat()
                meta["reserved_cost_usd"] = self.watchdog.active_reservations_usd
                meta["uncertain_liabilities_usd"] = self.watchdog.uncertain_liabilities_usd
                run.meta = meta

        # Retornar resumen final de la corrida
        async with self.session_factory() as session:
            service = S4Service(session)
            return await service.get_run_statistics(self.run_id)
