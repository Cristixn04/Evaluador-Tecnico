"""Coordinador de recuperación, reintentos y saneamiento de tareas huérfanas para S4."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models.s4 import S4TaskExecution
from src.s4.service import S4Service

logger = logging.getLogger("evaluador.s4.recovery")


class S4RecoveryCoordinator:
    """Coordinador centralizado de recuperación ante fallos y leases caídos."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        timeout_seconds: float = 120.0,
        max_attempts: int = 3,
    ) -> None:
        self._session = session
        self._service = S4Service(session)
        self.timeout_seconds = timeout_seconds
        self.max_attempts = max_attempts

    async def sweep_and_recover_orphans(
        self,
        run_id: uuid.UUID,
    ) -> list[S4TaskExecution]:
        """Detecta y procesa tareas en ejecución cuyo worker dejó de reportar latidos.
        
        Aplica política de reencolado con incremento de intento o marcación de fallo
        si superó max_attempts.
        """
        recovered = await self._service.recover_orphan_tasks(
            run_id=run_id,
            timeout_seconds=self.timeout_seconds,
            max_attempts=self.max_attempts,
        )
        if recovered:
            logger.warning(
                f"[S4-RECOVERY] Recovered {len(recovered)} orphan task(s) in run {run_id}."
            )
        return recovered

    async def record_transient_retry(
        self,
        task_id: uuid.UUID,
        *,
        attempt: int,
        error_details: str,
        event_type: str = "transient_retry",
    ) -> dict[str, Any]:
        """Registra explícitamente un evento de reintento transitorio en la tarea."""
        event = await self._service.record_task_recovery_event(
            task_id=task_id,
            event_type=event_type,
            attempt=attempt,
            details=error_details,
        )
        return event.model_dump(mode="json")

