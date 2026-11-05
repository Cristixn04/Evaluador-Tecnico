from __future__ import annotations

from typing import ClassVar
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.telemetry import tool_telemetry
from src.db.enums import TurnSpeaker
from src.db.models import Interview, Problem, Snapshot, Turn
from src.interview.service import InterviewService
from src.sandbox.exceptions import (
    SandboxInvalidResponseError,
    SandboxProviderError,
    SandboxTimeoutError,
    SandboxUnavailableError,
)
from src.sandbox.factory import create_code_runner
from src.sandbox.types import CodeRunner, ExecutionStatus, RunRequest


class CodeExecutionError(Exception):
    pass


class CodeExecutionService:
    # Mapping from sandbox ExecutionStatus to WS ExecutionStatus
    STATUS_MAP: ClassVar[dict[ExecutionStatus, str]] = {
        ExecutionStatus.ACCEPTED: "success",
        ExecutionStatus.WRONG_ANSWER: "test_failure",
        ExecutionStatus.COMPILE_ERROR: "compile_error",
        ExecutionStatus.TIME_LIMIT_EXCEEDED: "timeout",
        ExecutionStatus.MEMORY_LIMIT_EXCEEDED: "runtime_error",
        ExecutionStatus.RUNTIME_ERROR: "runtime_error",
        ExecutionStatus.INTERNAL_ERROR: "runtime_error",
    }

    def __init__(
        self,
        session: AsyncSession,
        interview_service: InterviewService,
        sandbox_runner: CodeRunner | None = None,
    ) -> None:
        self._session = session
        self._interview_service = interview_service
        self._runner = sandbox_runner if sandbox_runner is not None else create_code_runner()

    async def execute_code(
        self,
        interview_id: UUID,
        code: str,
        language: str,
    ) -> dict:
        """Execute code and return result in WS contract format."""
        telemetry = tool_telemetry("code_execution_sandbox", "execute_code")
        telemetry.start(
            language=language,
            code_bytes=len(code.encode("utf-8")),
        )
        try:
            # Load interview and problem
            interview = await self._session.get(Interview, interview_id)
            if not interview:
                raise CodeExecutionError("Interview not found")

            if not interview.problem_id:
                raise CodeExecutionError("No problem assigned to interview")

            problem = await self._session.get(Problem, interview.problem_id)
            if not problem:
                raise CodeExecutionError("Problem not found")

            # Get problem spec for test cases and limits
            from src.problems.loader import load_default_catalog

            catalog = load_default_catalog()
            problem_spec = None
            for spec in catalog:
                if spec.persistence_id() == interview.problem_id:
                    problem_spec = spec
                    break

            if not problem_spec:
                raise CodeExecutionError("Problem specification not found")

            # Verificar disponibilidad real del sandbox Judge0
            runner_available = True
            if hasattr(self._runner, "check_availability"):
                try:
                    runner_available = await self._runner.check_availability()
                except Exception:  # noqa: BLE001
                    runner_available = False

            if not runner_available:
                return await self._record_unavailable(
                    interview_id=interview_id,
                    phase=interview.phase.value,
                    code=code,
                    language=language,
                    total_tests=len(problem_spec.tests),
                    telemetry=telemetry,
                    reason_detail="Judge0 CE sandbox is currently unavailable. Code execution could not be verified in real time.",
                )

            # Ejecutar pruebas reales vinculadas al problema en Judge0
            tests_passed = 0
            total_tests = len(problem_spec.tests)
            test_details = []
            final_stdout: list[str] = []
            final_stderr: list[str] = []
            total_time_seconds = 0.0
            worst_status = "success"
            stdout_str: str | None = None
            stderr_str: str | None = None

            try:
                if total_tests == 0:
                    # Si no hay tests especificados, ejecutar código una vez
                    run_request = RunRequest(
                        language=language,
                        source=code,
                        timeout_ms=problem_spec.limits.timeout_ms,
                        memory_mb=problem_spec.limits.memory_mb,
                    )
                    result = await self._runner.run(run_request)
                    ws_status = self.STATUS_MAP.get(result.status, "runtime_error")
                    execution_time_ms = int(result.time_seconds * 1000) if result.time_seconds else 0
                    stdout_str = result.stdout
                    stderr_str = result.stderr or result.compile_output or None
                else:
                    for tc in problem_spec.tests:
                        run_req = RunRequest(
                            language=language,
                            source=code,
                            stdin=tc.input,
                            expected_output=tc.expected_output,
                            timeout_ms=problem_spec.limits.timeout_ms,
                            memory_mb=problem_spec.limits.memory_mb,
                        )
                        res = await self._runner.run(run_req)
                        if res.time_seconds:
                            total_time_seconds += res.time_seconds
                        if res.stdout:
                            final_stdout.append(res.stdout)
                        err_out = res.stderr or res.compile_output
                        if err_out:
                            final_stderr.append(err_out)

                        status_mapped = self.STATUS_MAP.get(res.status, "runtime_error")
                        passed = status_mapped == "success"
                        if passed:
                            tests_passed += 1
                        elif worst_status == "success":
                            worst_status = status_mapped

                        test_details.append({
                            "test_name": tc.id,
                            "passed": passed,
                            "message": "Passed" if passed else (err_out or status_mapped),
                        })

                    ws_status = "success" if (tests_passed == total_tests) else worst_status
                    execution_time_ms = int(total_time_seconds * 1000)
                    stdout_str = "\n".join(final_stdout) if final_stdout else None
                    stderr_str = "\n".join(final_stderr) if final_stderr else None
            except (SandboxUnavailableError, SandboxProviderError) as exc:
                return await self._record_unavailable(
                    interview_id=interview_id,
                    phase=interview.phase.value,
                    code=code,
                    language=language,
                    total_tests=total_tests,
                    telemetry=telemetry,
                    reason_detail=f"Judge0 sandbox provider unavailable: {exc}",
                )
            except SandboxTimeoutError as exc:
                ws_status = "timeout"
                execution_time_ms = problem_spec.limits.timeout_ms
                stdout_str = "\n".join(final_stdout) if final_stdout else None
                stderr_str = str(exc) or "Execution timed out in sandbox"
            except SandboxInvalidResponseError as exc:
                ws_status = "runtime_error"
                execution_time_ms = int(total_time_seconds * 1000)
                stdout_str = "\n".join(final_stdout) if final_stdout else None
                stderr_str = f"Malformed response from execution provider: {exc}"

            # Persistir snapshot con resultados reales de ejecución
            snapshot = Snapshot(
                interview_id=interview_id,
                code=code,
                phase=interview.phase.value,
                language=language,
                reason="run",
                tests_passed=tests_passed,
                total_tests=total_tests,
                execution_status=ws_status,
            )
            self._session.add(snapshot)

            # Persistir turno del candidato
            turn = Turn(
                interview_id=interview_id,
                speaker=TurnSpeaker.CANDIDATE,
                content=f"[Code execution]\n```{language}\n{code}\n```",
            )
            self._session.add(turn)

            await self._session.flush()

            if ws_status in ("compile_error", "timeout", "runtime_error"):
                telemetry.error(
                    stderr_str or ws_status,
                    status=ws_status,
                    duration_ms=execution_time_ms,
                )
            else:
                telemetry.success(
                    status=ws_status,
                    passed=f"{tests_passed}/{total_tests}",
                    duration_ms=execution_time_ms,
                )

            return {
                "status": ws_status,
                "stdout": stdout_str,
                "stderr": stderr_str,
                "execution_time_ms": execution_time_ms,
                "tests_passed": tests_passed,
                "total_tests": total_tests,
                "test_details": test_details,
            }
        except Exception as exc:
            telemetry.error(exc, status="runtime_error")
            raise

    async def _record_unavailable(
        self,
        *,
        interview_id: UUID,
        phase: str,
        code: str,
        language: str,
        total_tests: int,
        telemetry: object,
        reason_detail: str,
    ) -> dict:
        snapshot = Snapshot(
            interview_id=interview_id,
            code=code,
            phase=phase,
            language=language,
            reason="run",
            tests_passed=None,
            total_tests=total_tests,
            execution_status="unavailable",
        )
        self._session.add(snapshot)
        turn = Turn(
            interview_id=interview_id,
            speaker=TurnSpeaker.CANDIDATE,
            content=f"[Code execution attempt - sandbox unavailable]\n```{language}\n{code}\n```",
        )
        self._session.add(turn)
        await self._session.flush()

        if hasattr(telemetry, "error"):
            telemetry.error("Judge0 sandbox unavailable", status="unavailable")
        return {
            "status": "unavailable",
            "stdout": None,
            "stderr": reason_detail,
            "execution_time_ms": 0,
            "tests_passed": None,
            "total_tests": total_tests,
            "test_details": [],
        }

    async def close(self) -> None:
        aclose_fn = getattr(self._runner, "aclose", None)
        if callable(aclose_fn):
            await aclose_fn()