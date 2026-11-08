"""Vigilante de presupuesto, circuito de seguridad y detección de fallas continuas para S4."""

from __future__ import annotations

import collections
from datetime import UTC, datetime
from typing import Any


class S4BudgetExceededError(Exception):
    """El presupuesto límite de la corrida fue alcanzado o excedido."""


class S4CircuitBreakerTrippedError(Exception):
    """El disyuntor de seguridad (circuit breaker) se disparó por fallas repetidas."""


class S4CircuitState:
    HEALTHY = "healthy"
    COOLING_DOWN = "cooling_down"
    PROBING = "probing"
    PERMANENT_TRIP = "permanent_trip"


class S4Watchdog:
    """Monitor de salud, presupuesto y disyuntor automático para ejecuciones de carga S4."""

    def __init__(
        self,
        *,
        budget_limit_usd: float = 40.0,
        max_consecutive_failures: int = 5,
        window_size: int = 20,
        max_window_failure_rate: float = 0.50,
        initial_uncertain_liabilities_usd: float = 0.0,
        cooldown_seconds: float = 30.0,
        max_cooldown_cycles: int = 3,
    ) -> None:
        val = float(budget_limit_usd)
        if val <= 0.0:
            raise ValueError(f"budget_limit_usd must be positive and explicitly authorized (received {budget_limit_usd})")
        self.budget_limit_usd = val
        self.max_consecutive_failures = max_consecutive_failures
        self.window_size = window_size
        self.max_window_failure_rate = max_window_failure_rate
        self.cooldown_seconds = max(0.01, float(cooldown_seconds))
        self.max_cooldown_cycles = max(1, int(max_cooldown_cycles))

        self._consecutive_failures: int = 0
        self._history: collections.deque[bool] = collections.deque(maxlen=window_size)
        self._circuit_state: str = S4CircuitState.HEALTHY
        self._cooldown_cycles: int = 0
        self._last_cooldown_started_at: datetime | None = None
        self._trip_reason: str | None = None
        self._tripped_at: datetime | None = None
        self._tripped_cost_usd: float | None = None
        self._active_reservations: float = 0.0
        self._uncertain_liabilities_usd: float = max(0.0, float(initial_uncertain_liabilities_usd))

    @property
    def circuit_state(self) -> str:
        """Estado actual del disyuntor: healthy, cooling_down, probing o permanent_trip."""
        return self._circuit_state

    @property
    def is_tripped(self) -> bool:
        """Indica si el disyuntor está actualmente abierto (bloqueando ejecución inmediata)."""
        return self._circuit_state in (S4CircuitState.COOLING_DOWN, S4CircuitState.PERMANENT_TRIP)

    @property
    def is_permanent_trip(self) -> bool:
        """Indica si el disyuntor sufrió una falla permanente que requiere intervención."""
        return self._circuit_state == S4CircuitState.PERMANENT_TRIP

    @property
    def is_cooling_down(self) -> bool:
        """Indica si el circuito está en periodo de enfriamiento antes de intentar una sonda."""
        return self._circuit_state == S4CircuitState.COOLING_DOWN

    @property
    def is_probing(self) -> bool:
        """Indica si el circuito está probando una tarea tras cumplirse el enfriamiento."""
        return self._circuit_state == S4CircuitState.PROBING

    @property
    def trip_reason(self) -> str | None:
        """Causa que provocó el disparo del disyuntor."""
        return self._trip_reason

    @property
    def tripped_at(self) -> datetime | None:
        """Timestamp en que se disparó el disyuntor."""
        return self._tripped_at

    @property
    def active_reservations_usd(self) -> float:
        """Total de reservas activas en dólares para tareas en vuelo."""
        return round(self._active_reservations, 6)

    @property
    def uncertain_liabilities_usd(self) -> float:
        """Total acumulado de pasivos de costo incierto retenidos por timeouts o fallos no reconciliados."""
        return round(self._uncertain_liabilities_usd, 6)

    @property
    def cooldown_cycles(self) -> int:
        """Número de ciclos de enfriamiento completados o en curso."""
        return self._cooldown_cycles

    def total_exposure_usd(self, current_cost_usd: float = 0.0) -> float:
        """Calcula la exposición financiera total (coste confirmado + reservas activas + pasivos inciertos)."""
        return round(current_cost_usd + self._active_reservations + self._uncertain_liabilities_usd, 6)

    def trip(
        self,
        reason: str,
        current_cost_usd: float | None = None,
        *,
        is_permanent: bool = False,
    ) -> None:
        """Dispara el disyuntor de seguridad persistiendo razón y timestamp."""
        now = datetime.now(UTC)
        self._trip_reason = reason
        self._tripped_at = now
        if current_cost_usd is not None:
            self._tripped_cost_usd = current_cost_usd

        is_budget_trip = (
            is_permanent
            or (current_cost_usd is not None and current_cost_usd >= self.budget_limit_usd)
            or "budget" in reason.lower()
            or "presupuesto" in reason.lower()
            or self._cooldown_cycles >= self.max_cooldown_cycles
        )

        if is_budget_trip:
            self._circuit_state = S4CircuitState.PERMANENT_TRIP
        else:
            self._circuit_state = S4CircuitState.COOLING_DOWN
            self._cooldown_cycles += 1
            self._last_cooldown_started_at = now

    def check_and_advance_cooldown(self) -> tuple[bool, str]:
        """Comprueba si el periodo de enfriamiento ha transcurrido para habilitar una sonda."""
        if self._circuit_state == S4CircuitState.HEALTHY:
            return True, "Circuit is healthy"
        if self._circuit_state == S4CircuitState.PROBING:
            return True, "Circuit is currently probing"
        if self._circuit_state == S4CircuitState.PERMANENT_TRIP:
            return False, f"Permanent circuit failure: {self._trip_reason}"

        if self._circuit_state == S4CircuitState.COOLING_DOWN:
            if not self._last_cooldown_started_at:
                self._circuit_state = S4CircuitState.PROBING
                return True, "Cooldown initiated probing"
            elapsed = (datetime.now(UTC) - self._last_cooldown_started_at).total_seconds()
            if elapsed >= self.cooldown_seconds:
                self._circuit_state = S4CircuitState.PROBING
                return True, (
                    f"Cooldown of {self.cooldown_seconds:.1f}s completed. "
                    f"Entering probing state (cycle {self._cooldown_cycles}/{self.max_cooldown_cycles})."
                )
            remaining = max(0.0, self.cooldown_seconds - elapsed)
            return False, f"Cooling down: {remaining:.1f}s remaining in cycle {self._cooldown_cycles}/{self.max_cooldown_cycles}"

        return False, "Unknown circuit state"

    def rehydrate_circuit_state(
        self,
        meta: dict[str, Any] | None,
        *,
        is_manual_resume: bool = False,
    ) -> None:
        """Restaura el estado del disyuntor a partir de metadatos persistidos en PostgreSQL."""
        if not meta:
            return

        unc_val = meta.get("uncertain_liabilities_usd")
        if unc_val is not None:
            self._uncertain_liabilities_usd = round(max(0.0, float(unc_val)), 6)

        if is_manual_resume:
            # En reanudación explícita por el operador:
            # 1. Si el disyuntor se disparó por presupuesto, evaluar si sigue excedido
            if meta.get("watchdog_tripped"):
                reason = str(meta.get("watchdog_trip_reason") or "")
                if "budget" in reason.lower() or "presupuesto" in reason.lower():
                    self._circuit_state = S4CircuitState.PERMANENT_TRIP
                    self._trip_reason = reason
                    return
            # 2. Si fue por fallos transitorios de infraestructura o ciclos agotados,
            # transicionar de forma segura a PROBING para verificar conectividad con 1 sonda
            self._circuit_state = S4CircuitState.PROBING
            self._consecutive_failures = 0
            self._cooldown_cycles = 0
            self._trip_reason = None
            self._tripped_at = None
            return

        saved_state = meta.get("circuit_state")
        if saved_state in (
            S4CircuitState.HEALTHY,
            S4CircuitState.COOLING_DOWN,
            S4CircuitState.PROBING,
            S4CircuitState.PERMANENT_TRIP,
        ):
            self._circuit_state = saved_state

        if meta.get("watchdog_tripped"):
            self._trip_reason = meta.get("watchdog_trip_reason")
            tripped_at_str = meta.get("watchdog_tripped_at")
            if tripped_at_str:
                try:
                    self._tripped_at = datetime.fromisoformat(tripped_at_str)
                except (ValueError, TypeError):
                    self._tripped_at = datetime.now(UTC)

        self._cooldown_cycles = int(meta.get("circuit_cooldown_cycles", self._cooldown_cycles))

    def reset(self) -> None:
        """Restablece el estado de los disyuntores a saludable."""
        self._circuit_state = S4CircuitState.HEALTHY
        self._trip_reason = None
        self._tripped_at = None
        self._tripped_cost_usd = None
        self._consecutive_failures = 0
        self._cooldown_cycles = 0
        self._last_cooldown_started_at = None
        self._active_reservations = 0.0
        self._uncertain_liabilities_usd = 0.0
        self._history.clear()

    def reserve_cost(self, amount_usd: float, current_cost_usd: float) -> tuple[bool, str]:
        """Reserva presupuesto anticipado antes de despachar una llamada/tarea."""
        if self._circuit_state in (S4CircuitState.COOLING_DOWN, S4CircuitState.PERMANENT_TRIP):
            return False, f"Circuit breaker active ({self._circuit_state}): {self._trip_reason}"

        projected = current_cost_usd + self._active_reservations + self._uncertain_liabilities_usd + amount_usd
        if projected > self.budget_limit_usd:
            msg = (
                f"Budget limit reservation rejected: projected cost ${projected:.4f} USD "
                f"(current: ${current_cost_usd:.4f}, reserved: ${self._active_reservations:.4f}, "
                f"uncertain: ${self._uncertain_liabilities_usd:.4f}, req: ${amount_usd:.4f}) "
                f"exceeds limit ${self.budget_limit_usd:.4f} USD"
            )
            self.trip(msg, current_cost_usd, is_permanent=True)
            return False, msg

        self._active_reservations = round(self._active_reservations + amount_usd, 6)
        return True, "Cost reserved successfully"

    def release_cost_reservation(self, amount_usd: float) -> None:
        """Libera una reserva de costo al confirmarse un resultado que no generó costo incierto."""
        self._active_reservations = max(0.0, round(self._active_reservations - amount_usd, 6))

    def retain_uncertain_liability(self, amount_usd: float) -> None:
        """Transfiere una reserva activa a pasivo incierto al detectarse un timeout o falla de facturación indeterminada."""
        self._active_reservations = max(0.0, round(self._active_reservations - amount_usd, 6))
        self._uncertain_liabilities_usd = round(self._uncertain_liabilities_usd + amount_usd, 6)

    def reconcile_uncertain_liability(self, reconciled_cost_usd: float, estimated_liability_usd: float) -> None:
        """Reconcilia un pasivo incierto tras conocerse la auditoría o factura real del proveedor."""
        self._uncertain_liabilities_usd = max(0.0, round(self._uncertain_liabilities_usd - estimated_liability_usd, 6))

    def check_budget(self, current_cost_usd: float) -> tuple[bool, str]:
        """Evalúa si la exposición total (confirmado + reservas + inciertos) respeta el presupuesto asignado."""
        total_eval = current_cost_usd + self._active_reservations + self._uncertain_liabilities_usd
        if total_eval >= self.budget_limit_usd:
            msg = (
                f"Budget limit reached: current evaluated cost ${total_eval:.4f} USD "
                f"(confirmed: ${current_cost_usd:.4f}, reserved: ${self._active_reservations:.4f}, "
                f"uncertain: ${self._uncertain_liabilities_usd:.4f}) "
                f"exceeds limit ${self.budget_limit_usd:.4f} USD"
            )
            self.trip(msg, current_cost_usd, is_permanent=True)
            return False, msg
        return True, "Budget within limits"

    def record_task_outcome(
        self,
        *,
        validation_passed: bool,
        current_cost_usd: float,
        error_details: str | None = None,
    ) -> tuple[bool, str]:
        """Registra el resultado de una tarea evaluando presupuesto, disyuntor y recuperación de sondas."""
        # 1. Chequeo prioritario de presupuesto
        budget_ok, budget_msg = self.check_budget(current_cost_usd)
        if not budget_ok:
            return False, budget_msg

        # 2. Manejo de estado PROBING (recuperación desatendida)
        if self._circuit_state == S4CircuitState.PROBING:
            if validation_passed:
                self._circuit_state = S4CircuitState.HEALTHY
                self._consecutive_failures = 0
                self._cooldown_cycles = 0
                self._trip_reason = None
                self._tripped_at = None
                self._history.append(True)
                return True, "Probe task succeeded; circuit recovered to healthy."

            # Sonda fallida
            self._consecutive_failures += 1
            self._history.append(False)
            err_msg = error_details or "Probe task failed"

            if self._cooldown_cycles >= self.max_cooldown_cycles:
                self._circuit_state = S4CircuitState.PERMANENT_TRIP
                self._trip_reason = (
                    f"Circuit breaker permanent failure: probe failed after {self._cooldown_cycles} "
                    f"cooldown cycles. Last error: {err_msg}"
                )
                self._tripped_at = datetime.now(UTC)
                return False, self._trip_reason

            self._circuit_state = S4CircuitState.COOLING_DOWN
            self._cooldown_cycles += 1
            self._last_cooldown_started_at = datetime.now(UTC)
            self._tripped_at = datetime.now(UTC)
            self._trip_reason = (
                f"Probe failed (cycle {self._cooldown_cycles}/{self.max_cooldown_cycles}). "
                f"Re-entering cooldown for {self.cooldown_seconds}s. Error: {err_msg}"
            )
            return False, self._trip_reason

        # 3. Registrar en ventana deslizante en estado normal
        self._history.append(validation_passed)

        if validation_passed:
            self._consecutive_failures = 0
            return True, "Task successful; circuit healthy"

        # 4. Fallo detectado en operación normal
        self._consecutive_failures += 1
        err_msg = error_details or "Unspecified task failure"

        if self._consecutive_failures >= self.max_consecutive_failures:
            reason = (
                f"Circuit breaker tripped: {self._consecutive_failures} consecutive task failures. "
                f"Last error: {err_msg}"
            )
            self.trip(reason, current_cost_usd, is_permanent=False)
            return False, reason

        # 5. Chequeo de tasa de fallo en ventana deslizante (si la ventana está completa)
        if len(self._history) >= self.window_size:
            failed_in_window = sum(1 for passed in self._history if not passed)
            fail_rate = failed_in_window / float(len(self._history))
            if fail_rate >= self.max_window_failure_rate:
                reason = (
                    f"Circuit breaker tripped: failure rate {fail_rate:.1%} in last "
                    f"{len(self._history)} tasks exceeds threshold {self.max_window_failure_rate:.1%}"
                )
                self.trip(reason, current_cost_usd, is_permanent=False)
                return False, reason

        return True, f"Failure recorded ({self._consecutive_failures}/{self.max_consecutive_failures})"

    def get_status(self) -> dict[str, Any]:
        """Reporte de estado de salud del watchdog."""
        window_fails = sum(1 for p in self._history if not p)
        window_rate = (
            round(window_fails / float(len(self._history)), 3)
            if self._history
            else 0.0
        )
        return {
            "is_tripped": self.is_tripped,
            "circuit_state": self._circuit_state,
            "is_permanent_trip": self.is_permanent_trip,
            "is_cooling_down": self.is_cooling_down,
            "is_probing": self.is_probing,
            "cooldown_cycles": self._cooldown_cycles,
            "max_cooldown_cycles": self.max_cooldown_cycles,
            "cooldown_seconds": self.cooldown_seconds,
            "trip_reason": self._trip_reason,
            "tripped_at": self._tripped_at.isoformat() if self._tripped_at else None,
            "consecutive_failures": self._consecutive_failures,
            "max_consecutive_failures": self.max_consecutive_failures,
            "budget_limit_usd": self.budget_limit_usd,
            "active_reservations_usd": self.active_reservations_usd,
            "uncertain_liabilities_usd": self.uncertain_liabilities_usd,
            "total_exposure_without_confirmed_usd": round(self._active_reservations + self._uncertain_liabilities_usd, 6),
            "window_size": len(self._history),
            "window_failure_rate": window_rate,
        }

