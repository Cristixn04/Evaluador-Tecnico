"""Controlador de cadencia y ritmo (Pacer) para corridas S4 de 12 horas."""

from __future__ import annotations

import asyncio
import time
from typing import Any


class S4Pacer:
    """Regulador de cadencia basado en reloj monotónico para distribución uniforme de tareas.
    
    Por defecto:
    - 1.000 tareas en 12 horas (43.200 segundos).
    - Cadencia objetivo: 43.20 segundos por tarea (83.33 tareas/hora).
    """

    def __init__(
        self,
        *,
        total_tasks: int = 1000,
        total_duration_seconds: float = 43200.0,
        max_delay_seconds: float = 120.0,
        min_interval_seconds: float = 0.0,
        initial_elapsed_seconds: float = 0.0,
    ) -> None:
        self.total_tasks = max(1, total_tasks)
        self.total_duration_seconds = max(1.0, total_duration_seconds)
        self.target_seconds_per_task = self.total_duration_seconds / float(self.total_tasks)
        self.max_delay_seconds = max_delay_seconds
        self.min_interval_seconds = max(0.0, min_interval_seconds)
        self._initial_elapsed_seconds = max(0.0, float(initial_elapsed_seconds))

        self._start_monotonic: float | None = None
        self._start_wall: float | None = None
        self._last_dispatch_monotonic: float | None = None

    def start(
        self,
        monotonic_now: float | None = None,
        *,
        initial_elapsed_seconds: float | None = None,
    ) -> None:
        """Inicia el cronómetro del pacer usando reloj monotónico y tiempo base reconciliado."""
        if initial_elapsed_seconds is not None:
            self._initial_elapsed_seconds = max(0.0, float(initial_elapsed_seconds))
        now = monotonic_now if monotonic_now is not None else time.monotonic()
        self._start_monotonic = now
        self._start_wall = time.time()

    def record_dispatch(self, monotonic_now: float | None = None) -> None:
        """Registra la marca de tiempo de despacho real para calcular la cadencia entre tareas sucesivas."""
        now = monotonic_now if monotonic_now is not None else time.monotonic()
        if self._start_monotonic is None:
            self.start(now)
        self._last_dispatch_monotonic = now

    @property
    def is_started(self) -> bool:
        """Indica si el cronómetro ya fue iniciado."""
        return self._start_monotonic is not None

    def elapsed_seconds(self, current_monotonic: float | None = None) -> float:
        """Retorna el tiempo transcurrido total reconciliado (base persistente + monotónico local)."""
        if self._start_monotonic is None:
            return self._initial_elapsed_seconds
        now = current_monotonic if current_monotonic is not None else time.monotonic()
        return self._initial_elapsed_seconds + max(0.0, now - self._start_monotonic)

    def compute_pacing_delay(
        self,
        completed_tasks: int,
        current_monotonic: float | None = None,
        *,
        last_dispatch_monotonic: float | None = None,
        had_failure_or_timeout: bool = False,
    ) -> float:
        """Calcula el retardo necesario antes de despachar la siguiente tarea.
        
        Garantías:
        1. Se basa en el tiempo real de despacho previo para evitar ráfagas tras tareas lentas o fallidas.
        2. Respeta el intervalo mínimo `min_interval_seconds` como suelo anti-ráfaga.
        3. En reanudación tras pausas largas, no ejecuta ráfagas de 'desquite' para compensar atrasos.
        4. Al superar 1.000 tareas por reposición dinámica, mantiene la cadencia regular.
        5. Si la tarea inmediata anterior falló o sufrió timeout (`had_failure_or_timeout=True`),
           omite la espera post-tarea (0.0s) para proteger el umbral estricto de 120s entre llamadas confirmadas.
        """
        if self._start_monotonic is None:
            self.start(current_monotonic)

        now = current_monotonic if current_monotonic is not None else time.monotonic()
        if had_failure_or_timeout:
            self._last_dispatch_monotonic = now
            return 0.0
        last_dispatch = (
            last_dispatch_monotonic
            if last_dispatch_monotonic is not None
            else self._last_dispatch_monotonic
        )

        # 1. Componente basada en el tiempo de despacho real previo (anti-ráfagas)
        dispatch_delay = 0.0
        if last_dispatch is not None:
            time_since_dispatch = max(0.0, now - last_dispatch)
            # Si hubo una pausa larga o reanudación tras inactividad prolongada,
            # no acumular ráfagas de compensación
            if time_since_dispatch > self.max_delay_seconds:
                self._last_dispatch_monotonic = now
                return self.min_interval_seconds if self.min_interval_seconds > 0 else 0.0

            target_spacing = self.target_seconds_per_task
            if time_since_dispatch < target_spacing:
                dispatch_delay = target_spacing - time_since_dispatch

        # 2. Componente basada en el itinerario global acumulado (solo para el plan base)
        schedule_delay = 0.0
        if completed_tasks < self.total_tasks:
            elapsed = self.elapsed_seconds(now)
            target_elapsed = float(completed_tasks) * self.target_seconds_per_task
            schedule_delay = target_elapsed - elapsed

        # Tomar el retardo efectivo
        effective_delay = max(dispatch_delay, schedule_delay)
        if effective_delay <= 0.0:
            return self.min_interval_seconds if self.min_interval_seconds > 0 else 0.0

        return min(max(effective_delay, self.min_interval_seconds), self.max_delay_seconds)

    def get_pacing_metrics(
        self,
        completed_tasks: int,
        current_monotonic: float | None = None,
    ) -> dict[str, Any]:
        """Calcula métricas diagnósticas de cadencia, deriva temporal y proyección."""
        elapsed = self.elapsed_seconds(current_monotonic)
        target_elapsed = float(completed_tasks) * self.target_seconds_per_task
        drift = round(target_elapsed - elapsed, 3)

        actual_cadence = (
            round(elapsed / float(completed_tasks), 3) if completed_tasks > 0 else 0.0
        )
        actual_tph = (
            round((float(completed_tasks) / elapsed) * 3600.0, 2)
            if elapsed > 0.0
            else 0.0
        )
        target_tph = round((float(self.total_tasks) / self.total_duration_seconds) * 3600.0, 2)

        projected_total = (
            round(actual_cadence * float(self.total_tasks), 2)
            if actual_cadence > 0.0
            else self.total_duration_seconds
        )

        return {
            "elapsed_seconds": round(elapsed, 2),
            "target_elapsed_seconds": round(target_elapsed, 2),
            "target_cadence_seconds_per_task": round(self.target_seconds_per_task, 3),
            "actual_cadence_seconds_per_task": actual_cadence,
            "tasks_per_hour_actual": actual_tph,
            "tasks_per_hour_target": target_tph,
            "drift_seconds": drift,
            "is_ahead": drift > 0.0,
            "is_behind": drift < 0.0,
            "projected_total_duration_seconds": projected_total,
        }

    async def sleep_delay(self, delay: float) -> None:
        """Pausa asíncrona no bloqueante."""
        if delay > 0.0:
            await asyncio.sleep(delay)

