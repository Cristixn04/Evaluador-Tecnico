"""Punto de entrada ejecutable CLI para el Autonomous Load Runner S4."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import signal
import sys
import uuid
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.core.config import settings
from src.s4.agent_executor import create_real_agent_executor
from src.s4.catalog import S4TaskCatalogGenerator
from src.s4.enums import S4RunStatus
from src.s4.exporter import S4Exporter
from src.s4.lock import S4RunAdvisoryLock, S4RunLockAcquisitionError
from src.s4.pacer import S4Pacer
from src.s4.preflight import run_s4_preflight
from src.s4.service import S4Service
from src.s4.watchdog import S4Watchdog
from src.s4.worker import S4TaskWorker, default_synthetic_executor

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("evaluador.s4.cli")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m src.s4.cli",
        description="S4 Autonomous Load Runner — Evaluador-Técnico (1.000 tareas / 12 horas)",
    )
    parser.add_argument("--run-id", type=str, default=None, help="UUID de la corrida S4 existente o nueva")
    parser.add_argument("--tasks", type=int, default=1000, help="Número de tareas objetivo (por defecto: 1000)")
    parser.add_argument("--seed", type=int, default=42, help="Semilla pseudoaleatoria determinista (por defecto: 42)")
    parser.add_argument("--interval", type=float, default=43.20, help="Cadencia objetivo en segundos por tarea (por defecto: 43.20)")
    parser.add_argument("--budget-usd", type=float, default=None, help="Límite máximo de presupuesto en dólares")
    parser.add_argument("--resume", action="store_true", help="Reanudar corrida existente indicada en --run-id")
    parser.add_argument("--mock", action="store_true", help="Utilizar ejecutor técnico sintético (costo $0.00)")
    parser.add_argument("--offline", action="store_true", help="Operar completamente offline sin dependencias externas")
    parser.add_argument("--dry-run", action="store_true", help="Generar y registrar tareas sin iniciar el despacho")
    parser.add_argument("--export", action="store_true", help="Exportar bitácoras de la corrida a JSON y CSV y salir")
    parser.add_argument("--export-json", type=str, default=None, help="Ruta de archivo para guardar exportación JSON")
    parser.add_argument("--export-csv", type=str, default=None, help="Ruta de archivo para guardar exportación CSV")
    parser.add_argument("--export-calls-csv", type=str, default=None, help="Ruta de archivo para guardar exportación CSV de llamadas LLM individuales")
    parser.add_argument("--preflight", action="store_true", help="Ejecutar diagnóstico preflight del sistema y salir")
    parser.add_argument("--worker-id", type=str, default=None, help="Identificador del worker (por defecto autogenerado)")
    parser.add_argument(
        "--min-duration-seconds",
        "--min-duration",
        dest="min_duration_seconds",
        type=float,
        default=43200.0,
        help="Duración mínima requerida en segundos para marcar COMPLETED (por defecto: 43200.0 / 12h)",
    )
    return parser


async def async_main(args: argparse.Namespace) -> int:
    # 1. Preflight
    if args.preflight:
        report = await run_s4_preflight()
        print(report.summary())
        return 0 if report.passed else 1

    engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    try:
        # Resolver o crear corrida
        run_uuid: uuid.UUID
        if args.run_id:
            try:
                run_uuid = uuid.UUID(args.run_id)
            except ValueError:
                logger.error(f"Formato de --run-id inválido: {args.run_id}")
                return 1
        else:
            run_uuid = uuid.uuid4()

        # Exportación bajo demanda
        if args.export:
            if not args.run_id:
                logger.error("Debe proporcionar --run-id para exportar evidencias.")
                return 1
            async with session_factory() as session:
                json_data = await S4Exporter.export_json(run_uuid, session)
                csv_data = await S4Exporter.export_csv(run_uuid, session)
                if args.export_json:
                    Path(args.export_json).write_text(json.dumps(json_data, indent=2, ensure_ascii=False))
                    logger.info(f"Evidencia JSON escrita en: {args.export_json}")
                if args.export_csv:
                    Path(args.export_csv).write_text(csv_data)
                    logger.info(f"Evidencia CSV escrita en: {args.export_csv}")
                if args.export_calls_csv:
                    calls_csv = await S4Exporter.export_calls_csv(run_uuid, session)
                    Path(args.export_calls_csv).write_text(calls_csv)
                    logger.info(f"Evidencia CSV de llamadas LLM escrita en: {args.export_calls_csv}")
                logger.info(f"Exportación JSON generada ({len(json_data['tasks'])} tareas).")
                logger.info(f"Exportación CSV generada ({len(csv_data)} bytes).")
            return 0

        # Validación estricta de presupuesto en modo real (Sección 12)
        is_synthetic = bool(args.mock or args.offline)
        if not is_synthetic and (args.budget_usd is None or args.budget_usd <= 0.0):
            logger.error("En modo real debe especificarse explícitamente un presupuesto positivo con --budget-usd.")
            return 1

        effective_budget = float(args.budget_usd or 35.0)
        if not is_synthetic and effective_budget > 35.0:
            logger.warning(
                f"Presupuesto solicitado (${effective_budget:.2f} USD) excede el máximo autorizado ($35.00 USD). "
                "Ajustando automáticamente a $35.00 USD."
            )
            effective_budget = 35.0

        # 2. Adquirir Advisory Lock exclusivo de PostgreSQL por corrida (AUD-S4-13)
        advisory_lock = S4RunAdvisoryLock(engine, run_uuid)
        try:
            await advisory_lock.acquire()
        except S4RunLockAcquisitionError as lock_err:
            logger.error(str(lock_err))
            return 1

        try:
            # 3. Inicializar corrida en PostgreSQL
            async with session_factory() as session, session.begin():
                srv = S4Service(session)
                if args.resume:
                    run = await srv.get_load_run(run_uuid, for_update=True)
                    logger.info(f"Reanudando corrida {run.id} en estado '{run.status}'.")
                    if run.budget_limit_usd != effective_budget:
                        logger.info(
                            f"Actualizando presupuesto de corrida de ${run.budget_limit_usd:.2f} a ${effective_budget:.2f} USD."
                        )
                        run.budget_limit_usd = effective_budget
                    if run.status != S4RunStatus.ACTIVE.value:
                        await srv.start_load_run(run.id)
                else:
                    run = await srv.create_load_run(
                        run_id=run_uuid,
                        target_tasks=args.tasks,
                        budget_limit_usd=effective_budget,
                        meta={
                            "seed": args.seed,
                            "mode": "synthetic" if is_synthetic else "real",
                            "cadence_seconds": args.interval,
                        },
                    )
                    # Encolar tareas deterministas del catálogo
                    catalog = S4TaskCatalogGenerator(seed=args.seed)
                    tdefs = catalog.generate_catalog(count=args.tasks)
                    logger.info(f"Encolando {len(tdefs)} tareas técnicas deterministas...")
                    for tdef in tdefs:
                        await srv.create_task_execution(
                            run_id=run.id,
                            task_number=tdef["task_number"],
                            task_type=tdef["task_type"],
                            input_payload=tdef,
                        )
                    await srv.start_load_run(run.id)
                    logger.info(f"Corrida {run.id} inicializada y activada con éxito.")

            if args.dry_run:
                logger.info("Modo --dry-run activado: tareas registradas. Finalizando sin despachar.")
                return 0

            # 4. Configurar componentes
            pacer = S4Pacer(
                total_tasks=args.tasks,
                total_duration_seconds=float(args.tasks) * float(args.interval),
                min_interval_seconds=5.0,
            )
            watchdog = S4Watchdog(budget_limit_usd=effective_budget)

            executor: Any
            if is_synthetic:
                executor = default_synthetic_executor
            else:
                executor = create_real_agent_executor()

            worker = S4TaskWorker(
                run_id=run_uuid,
                session_factory=session_factory,
                worker_id=args.worker_id or f"worker-{uuid.uuid4().hex[:8]}",
                watchdog=watchdog,
                pacer=pacer,
                catalog=S4TaskCatalogGenerator(seed=args.seed),
                executor=executor,
                min_duration_seconds=args.min_duration_seconds,
                is_manual_resume=bool(args.resume),
            )

            # 5. Manejo de señales de SO (SIGINT / SIGTERM) para detención ordenada (AUD-S4-10)
            loop = asyncio.get_running_loop()

            def handle_stop_signal(sig_num: int) -> None:
                logger.warning(f"Señal recibida ({signal.Signals(sig_num).name}). Solicitando parada ordenada...")
                worker.request_stop()

            for sig in (signal.SIGINT, signal.SIGTERM):
                try:
                    loop.add_signal_handler(sig, handle_stop_signal, sig)
                except NotImplementedError:
                    pass

            # 6. Ejecutar bucle autónomo
            logger.info("Iniciando bucle autónomo del worker...")
            summary = await worker.run_autonomous_loop()
            logger.info(
                f"Bucle finalizado. Tareas completadas: {summary.completed_tasks}/{summary.target_tasks}. "
                f"Costo: ${summary.total_cost_usd:.4f} USD."
            )

            # Verificar si se puede completar oficialmente con guardia de duración (AUD-S4-08)
            async with session_factory() as session, session.begin():
                srv = S4Service(session)
                try:
                    if summary.completed_tasks >= summary.target_tasks:
                        await srv.finish_load_run(
                            run_uuid,
                            status=S4RunStatus.COMPLETED,
                            min_duration_seconds=args.min_duration_seconds,
                        )
                        logger.info(f"Corrida {run_uuid} declarada COMPLETED exitosamente.")
                except Exception as comp_err:  # noqa: BLE001
                    logger.warning(f"La corrida no pudo marcarse como completada: {comp_err}")

            if args.export_json or args.export_csv or args.export_calls_csv:
                async with session_factory() as session:
                    json_data = await S4Exporter.export_json(run_uuid, session)
                    csv_data = await S4Exporter.export_csv(run_uuid, session)
                    if args.export_json:
                        Path(args.export_json).write_text(json.dumps(json_data, indent=2, ensure_ascii=False))
                        logger.info(f"Evidencia JSON escrita en: {args.export_json}")
                    if args.export_csv:
                        Path(args.export_csv).write_text(csv_data)
                        logger.info(f"Evidencia CSV escrita en: {args.export_csv}")
                    if args.export_calls_csv:
                        calls_csv = await S4Exporter.export_calls_csv(run_uuid, session)
                        Path(args.export_calls_csv).write_text(calls_csv)
                        logger.info(f"Evidencia CSV de llamadas LLM escrita en: {args.export_calls_csv}")

            return 0 if summary.completed_tasks >= summary.target_tasks else 2

        finally:
            await advisory_lock.release()

    finally:
        await engine.dispose()


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    try:
        code = asyncio.run(async_main(args))
        sys.exit(code)
    except KeyboardInterrupt:
        logger.warning("Interrupción forzada por el usuario.")
        sys.exit(130)


if __name__ == "__main__":
    main()
