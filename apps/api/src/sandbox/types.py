from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol


class ExecutionStatus(StrEnum):
    ACCEPTED = "accepted"
    WRONG_ANSWER = "wrong_answer"
    COMPILE_ERROR = "compile_error"
    RUNTIME_ERROR = "runtime_error"
    TIME_LIMIT_EXCEEDED = "time_limit_exceeded"
    MEMORY_LIMIT_EXCEEDED = "memory_limit_exceeded"
    INTERNAL_ERROR = "internal_error"


MAX_TIMEOUT_MS: int = 2000
MAX_MEMORY_MB: int = 128
MIN_TIMEOUT_MS: int = 100
MIN_MEMORY_MB: int = 1


@dataclass(frozen=True, slots=True)
class RunRequest:
    language: str
    source: str
    stdin: str = ""
    expected_output: str | None = None
    timeout_ms: int = MAX_TIMEOUT_MS
    memory_mb: int = MAX_MEMORY_MB
    strict_limits: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.timeout_ms, int) or isinstance(self.timeout_ms, bool):
            raise TypeError("timeout_ms must be an integer")
        if not isinstance(self.memory_mb, int) or isinstance(self.memory_mb, bool):
            raise TypeError("memory_mb must be an integer")
        if self.timeout_ms <= 0:
            raise ValueError(f"timeout_ms must be greater than 0, got {self.timeout_ms}")
        if self.memory_mb <= 0:
            raise ValueError(f"memory_mb must be greater than 0, got {self.memory_mb}")

        if self.strict_limits:
            if self.timeout_ms > MAX_TIMEOUT_MS:
                raise ValueError(
                    f"timeout_ms exceeds maximum allowed limit of {MAX_TIMEOUT_MS}ms, got {self.timeout_ms}"
                )
            if self.memory_mb > MAX_MEMORY_MB:
                raise ValueError(
                    f"memory_mb exceeds maximum allowed limit of {MAX_MEMORY_MB}MB, got {self.memory_mb}"
                )
        else:
            if self.timeout_ms > MAX_TIMEOUT_MS:
                object.__setattr__(self, "timeout_ms", MAX_TIMEOUT_MS)
            if self.memory_mb > MAX_MEMORY_MB:
                object.__setattr__(self, "memory_mb", MAX_MEMORY_MB)


@dataclass(frozen=True, slots=True)
class RunResult:
    status: ExecutionStatus
    stdout: str
    stderr: str
    compile_output: str
    exit_code: int | None = None
    time_seconds: float | None = None
    memory_kb: int | None = None
    provider_status_id: int | None = None


class CodeRunner(Protocol):
    async def run(self, request: RunRequest) -> RunResult: ...
