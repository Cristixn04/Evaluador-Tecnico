"""Módulo S4 (Semana de Carga): contrato, persistencia, trazabilidad y exportación."""

from typing import TYPE_CHECKING, Any

from src.s4.catalog import S4TaskCatalogGenerator
from src.s4.enums import S4RunStatus, S4TaskStatus, S4TaskType
from src.s4.pacer import S4Pacer
from src.s4.sanitizer import S4Sanitizer
from src.s4.schemas import (
    S4LoadRunSummary,
    S4RecoveryEvent,
    S4RunExportJSON,
    S4TaskExecutionRecord,
    S4TaskExportRow,
    S4TaskInput,
    S4TaskResult,
)
from src.s4.watchdog import S4BudgetExceededError, S4CircuitBreakerTrippedError, S4Watchdog

if TYPE_CHECKING:
    from src.s4.agent_executor import create_real_agent_executor
    from src.s4.exporter import S4Exporter
    from src.s4.lock import S4RunAdvisoryLock, S4RunLockAcquisitionError
    from src.s4.preflight import run_s4_preflight
    from src.s4.recovery import S4RecoveryCoordinator
    from src.s4.service import (
        S4DuplicateTaskNumberError,
        S4Error,
        S4InvalidStateTransitionError,
        S4RunIncompleteError,
        S4RunNotFoundError,
        S4RunPrematureCompletionError,
        S4Service,
        S4TaskNotFoundError,
        S4TaskValidationError,
        S4WorkerLeaseExpiredError,
    )
    from src.s4.worker import S4TaskWorker


def __getattr__(name: str) -> Any:
    if name == "S4Exporter":
        from src.s4.exporter import S4Exporter

        return S4Exporter
    if name == "S4RecoveryCoordinator":
        from src.s4.recovery import S4RecoveryCoordinator

        return S4RecoveryCoordinator
    if name == "S4TaskWorker":
        from src.s4.worker import S4TaskWorker

        return S4TaskWorker
    if name in {"S4RunAdvisoryLock", "S4RunLockAcquisitionError"}:
        import src.s4.lock as lock_mod

        return getattr(lock_mod, name)
    if name == "create_real_agent_executor":
        from src.s4.agent_executor import create_real_agent_executor

        return create_real_agent_executor
    if name == "run_s4_preflight":
        from src.s4.preflight import run_s4_preflight

        return run_s4_preflight
    if name in {
        "S4Service",
        "S4Error",
        "S4RunNotFoundError",
        "S4TaskNotFoundError",
        "S4InvalidStateTransitionError",
        "S4TaskValidationError",
        "S4RunIncompleteError",
        "S4RunPrematureCompletionError",
        "S4WorkerLeaseExpiredError",
        "S4DuplicateTaskNumberError",
    }:
        import src.s4.service as service_mod

        return getattr(service_mod, name)
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")


__all__ = [
    "S4BudgetExceededError",
    "S4CircuitBreakerTrippedError",
    "S4DuplicateTaskNumberError",
    "S4Error",
    "S4Exporter",
    "S4InvalidStateTransitionError",
    "S4LoadRunSummary",
    "S4Pacer",
    "S4RecoveryCoordinator",
    "S4RecoveryEvent",
    "S4RunAdvisoryLock",
    "S4RunExportJSON",
    "S4RunIncompleteError",
    "S4RunLockAcquisitionError",
    "S4RunNotFoundError",
    "S4RunPrematureCompletionError",
    "S4RunStatus",
    "S4Sanitizer",
    "S4Service",
    "S4TaskCatalogGenerator",
    "S4TaskExecutionRecord",
    "S4TaskExportRow",
    "S4TaskInput",
    "S4TaskNotFoundError",
    "S4TaskResult",
    "S4TaskStatus",
    "S4TaskType",
    "S4TaskValidationError",
    "S4TaskWorker",
    "S4Watchdog",
    "S4WorkerLeaseExpiredError",
    "create_real_agent_executor",
    "run_s4_preflight",
]
