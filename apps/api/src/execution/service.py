from __future__ import annotations

from typing import ClassVar
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.telemetry import tool_telemetry
from src.db.enums import TurnSpeaker
from src.db.models import Interview, Problem, Snapshot, Turn
from src.interview.service import InterviewService
from src.sandbox.factory import create_code_runner
from src.sandbox.types import ExecutionStatus, RunRequest


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
    ) -> None:
        self._session = session
        self._interview_service = interview_service
        self._runner = create_code_runner()

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

            # Build run request with problem's test cases and limits
            run_request = RunRequest(
                language=language,
                source=code,
                timeout_ms=problem_spec.limits.timeout_ms,
                memory_mb=problem_spec.limits.memory_mb,
            )

            # Execute code
            result = await self._runner.run(run_request)

            # Map status
            ws_status = self.STATUS_MAP.get(result.status, "runtime_error")

            # Calculate tests passed/failed
            tests_passed = 0
            total_tests = len(problem_spec.tests)
            test_details = []

            if ws_status == "success":
                tests_passed = total_tests
                test_details = [
                    {"test_name": tc.id, "passed": True, "message": "Passed"}
                    for tc in problem_spec.tests
                ]
            elif ws_status == "test_failure" and result.provider_status_id == 4:
                # Judge0 WRONG_ANSWER - we don't know which specific tests failed
                # In a real implementation, we'd parse the output
                test_details = [
                    {"test_name": tc.id, "passed": False, "message": "Failed"}
                    for tc in problem_spec.tests
                ]

            execution_time_ms = int(result.time_seconds * 1000) if result.time_seconds else 0

            # Persist snapshot with execution results
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

            # Persist candidate turn
            turn = Turn(
                interview_id=interview_id,
                speaker=TurnSpeaker.CANDIDATE,
                content=f"[Code execution]\n```{language}\n{code}\n```",
            )
            self._session.add(turn)

            await self._session.flush()

            if ws_status in ("compile_error", "timeout", "runtime_error"):
                clean_err = (result.stderr or result.compile_output or ws_status).strip()
                telemetry.error(
                    clean_err,
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
                "stdout": result.stdout,
                "stderr": result.stderr,
                "execution_time_ms": execution_time_ms,
                "tests_passed": tests_passed,
                "total_tests": total_tests,
                "test_details": test_details,
            }
        except Exception as exc:
            telemetry.error(exc, status="runtime_error")
            raise

    async def close(self) -> None:
        await self._runner.aclose()