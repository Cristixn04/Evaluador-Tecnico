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


@dataclass(frozen=True, slots=True)
class RunRequest:
    language: str
    source: str
    stdin: str = ""
    expected_output: str | None = None
    timeout_ms: int = 2000
    memory_mb: int = 128


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
