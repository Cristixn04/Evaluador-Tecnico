"""Worker durable de ARQ para procesamiento asíncrono de evaluaciones (S-14)."""

from __future__ import annotations

import logging
import uuid
from typing import Any, ClassVar

from arq import Retry
from arq.connections import RedisSettings
from sqlalchemy import select

from src.core.config import settings
from src.db.models.interview import Evaluation
from src.db.session import get_session_maker
from src.evaluation.queue import evaluation_queue
from src.evaluation.service import EvaluationService
from src.llm.exceptions import LLMTimeoutError

logger = logging.getLogger(__name__)


def is_transient_error(exc: Exception) -> bool:
    """Identifica si un error es transitorio (reintentable) o permanente."""
    if isinstance(exc, (LLMTimeoutError, ConnectionError, TimeoutError, OSError)):
        return True
    exc_name = type(exc).__name__.lower()
    msg = str(exc).lower()
    if "timeout" in exc_name or "timeout" in msg:
        return True
    if "connection" in exc_name or "connection" in msg:
        return True
    return bool("502" in msg or "503" in msg or "504" in msg or "rate limit" in msg)



async def evaluate_interview_job(ctx: dict[str, Any], interview_id_str: str) -> dict[str, Any]:
    """Trabajo de evaluación ejecutado de forma asíncrona y durable por el worker de ARQ."""
    interview_uuid = uuid.UUID(interview_id_str)
    worker_id = str(ctx.get("worker_id") or f"worker-{uuid.uuid4().hex[:8]}")
    job_try = int(ctx.get("job_try", 1))
    max_tries = 3

    # 1. Lock distribuido en Redis para evitar ejecuciones concurrentes de la misma entrevista
    acquired = await evaluation_queue.acquire_lock(interview_uuid, worker_id, ttl_seconds=300)
    if not acquired:
        logger.warning(
            "Worker %s omitió evaluación de interview_id=%s: lock ya retenido por otro worker",
            worker_id,
            interview_uuid,
        )
        return {"status": "skipped", "reason": "lock_active"}

    try:
        session_maker = get_session_maker()
        async with session_maker() as session:
            # 2. Idempotencia en Base de Datos: verificar si ya existe evaluación persistida
            existing_eval = (
                await session.execute(select(Evaluation).where(Evaluation.interview_id == interview_uuid))
            ).scalar_one_or_none()

            if existing_eval is not None:
                logger.info(
                    "Interview %s ya cuenta con evaluación previa (id=%s). Retornando resultado existente sin reevaluar.",
                    interview_uuid,
                    existing_eval.id,
                )
                await evaluation_queue.set_evaluation_status(
                    interview_uuid,
                    status="completed",
                    metadata={
                        "report_id": str(existing_eval.id),
                        "overall_score": existing_eval.overall_score,
                        "recommendation": existing_eval.recommendation,
                        "needs_human_review": existing_eval.needs_human_review,
                        "is_idempotent_replay": True,
                    },
                )
                return {"status": "completed", "report_id": str(existing_eval.id), "cached": True}

            # 3. Notificar inicio de evaluación (in_progress)
            await evaluation_queue.set_evaluation_status(
                interview_uuid,
                status="in_progress",
                metadata={"worker_id": worker_id, "attempt": job_try},
            )

            # 4. Ejecución del pipeline de evaluación
            service = EvaluationService(session)
            report = await service.evaluate(interview_uuid)

            # 5. Notificar finalización exitosa (completed)
            await evaluation_queue.set_evaluation_status(
                interview_uuid,
                status="completed",
                metadata={
                    "report_id": report.id,
                    "overall_score": report.overall_score,
                    "recommendation": report.recommendation,
                    "needs_human_review": report.needs_human_review,
                    "attempt": job_try,
                },
            )

            logger.info(
                "Evaluación durable completada con éxito: interview_id=%s score=%.2f rec=%s",
                interview_uuid,
                report.overall_score,
                report.recommendation,
            )
            return {"status": "completed", "report_id": report.id}

    except Exception as exc:
        is_transient = is_transient_error(exc)
        logger.exception(
            "Fallo en evaluación de interview_id=%s (intento %d/%d, transitorio=%s)",
            interview_uuid,
            job_try,
            max_tries,
            is_transient,
        )

        if is_transient and job_try < max_tries:
            # Reintento acotado con backoff
            backoff_secs = 5 * job_try
            logger.info("Reintentando job para interview_id=%s en %d segundos...", interview_uuid, backoff_secs)
            raise Retry(defer=backoff_secs) from exc

        # Error permanente o reintentos agotados: marcar como failed
        error_type = "transient_exhausted" if is_transient else "permanent"
        await evaluation_queue.set_evaluation_status(
            interview_uuid,
            status="failed",
            metadata={
                "error": str(exc),
                "error_type": error_type,
                "failed_at_attempt": job_try,
            },
        )
        return {"status": "failed", "error": str(exc), "error_type": error_type}

    finally:
        # Siempre liberar el lock distribuido al terminar el intento
        await evaluation_queue.release_lock(interview_uuid, worker_id)


async def startup(ctx: dict[str, Any]) -> None:
    """Inicialización del worker de ARQ."""
    ctx["worker_id"] = f"arq-worker-{uuid.uuid4().hex[:8]}"
    logger.info("Iniciando ARQ Evaluation Worker (%s)...", ctx["worker_id"])


async def shutdown(ctx: dict[str, Any]) -> None:
    """Cierre ordenado del worker de ARQ."""
    logger.info("Deteniendo ARQ Evaluation Worker (%s)...", ctx.get("worker_id"))
    await evaluation_queue.close()


class WorkerSettings:
    """Configuración estándar de ejecución para el worker CLI de ARQ (`arq src.evaluation.worker.WorkerSettings`)."""

    functions: ClassVar[list[Any]] = [evaluate_interview_job]
    redis_settings: ClassVar[RedisSettings] = RedisSettings.from_dsn(settings.REDIS_URL)
    max_tries: ClassVar[int] = 3
    job_timeout: ClassVar[int] = 300
    on_startup = startup
    on_shutdown = shutdown

