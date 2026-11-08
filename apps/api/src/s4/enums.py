"""Enumeraciones oficiales del módulo S4 (Semana de Carga)."""

from enum import StrEnum


class S4RunStatus(StrEnum):
    """Estados del ciclo de vida de una corrida de carga S4."""

    PLANNED = "planned"
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class S4TaskStatus(StrEnum):
    """Estados explícitos del ciclo de vida de una unidad de trabajo S4."""

    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class S4TaskType(StrEnum):
    """Categorías de unidades de trabajo técnicas admitidas en S4."""

    BENCHMARK_EVALUATION = "benchmark_evaluation"
    AUTONOMOUS_CODING = "autonomous_coding"
    ADVERSARIAL_SECURITY = "adversarial_security"
    GENERAL_TECHNICAL = "general_technical"

