from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.db.enums import InterviewPhase, InterviewStatus
from src.db.models import Interview, Problem
from src.execution.service import CodeExecutionError, CodeExecutionService
from src.interview.service import InterviewService
from src.sandbox.types import ExecutionStatus, RunResult


class TestCodeExecutionService:
    @pytest.fixture
    def mock_runner(self):
        runner = AsyncMock()
        runner.aclose = AsyncMock()
        return runner

    @pytest.fixture
    def mock_session(self):
        session = AsyncMock()
        session.get = AsyncMock()
        session.add = MagicMock()
        session.flush = AsyncMock()
        session.commit = AsyncMock()
        session.rollback = AsyncMock()
        return session

    @pytest.fixture
    def mock_interview_service(self):
        return MagicMock(spec=InterviewService)

    @pytest.fixture
    def execution_service(self, mock_runner, mock_interview_service, mock_session):
        with patch("src.execution.service.create_code_runner", return_value=mock_runner):
            service = CodeExecutionService(
                session=mock_session,
                interview_service=mock_interview_service,
            )
            service._runner = mock_runner
            return service

    @pytest.fixture
    def problem_id(self):
        return uuid4()

    @pytest.fixture
    def sample_interview(self, problem_id):
        return Interview(
            id=uuid4(),
            vacancy_id=uuid4(),
            problem_id=problem_id,
            candidate_email="test@example.com",
            candidate_name="Test",
            access_token=None,
            status=InterviewStatus.IN_PROGRESS,
            phase=InterviewPhase.CODING,
            expires_at=None,
        )

    @pytest.fixture
    def sample_problem(self, problem_id):
        from unittest.mock import MagicMock

        from src.problems.schemas import ExecutionLimits, ProblemSpec, TestCase
        
        # Create a mock spec with the correct persistence_id
        spec = MagicMock(spec=ProblemSpec)
        spec.persistence_id.return_value = problem_id
        spec.tests = [
            TestCase(id="test1", input="1\n2\n", expected_output="3\n"),
            TestCase(id="test2", input="2\n3\n", expected_output="5\n"),
        ]
        spec.limits = ExecutionLimits(timeout_ms=2000, memory_mb=128)
        spec.title = "Test Problem"
        spec.statement = "Test"
        spec.role = "backend"
        spec.seniority = "mid"
        spec.difficulty = "mid"
        spec.tags = ["test"]
        spec.languages = ["python"]
        
        problem = Problem(
            id=problem_id,
            title="Test Problem",
            difficulty="mid",
            language="python",
            scenario_preview="Test",
            tags=["test"],
        )
        problem._spec = spec
        return problem

    # Status mapping tests
    @pytest.mark.asyncio
    async def test_accepted_maps_to_success(
        self, execution_service, sample_interview, sample_problem
    ) -> None:
        execution_service._session.get = AsyncMock(side_effect=[sample_interview, sample_problem])
        execution_service._runner.run.return_value = RunResult(
            status=ExecutionStatus.ACCEPTED,
            stdout="3\n",
            stderr="",
            compile_output="",
            time_seconds=0.1,
            memory_kb=1024,
        )

        with patch("src.problems.loader.load_default_catalog", return_value=[sample_problem._spec]):
            result = await execution_service.execute_code(
                interview_id=sample_interview.id,
                code="print(1+2)",
                language="python",
            )

        assert result["status"] == "success"
        assert result["tests_passed"] == 2
        assert result["total_tests"] == 2

    @pytest.mark.asyncio
    async def test_wrong_answer_maps_to_test_failure(
        self, execution_service, sample_interview, sample_problem
    ) -> None:
        execution_service._session.get = AsyncMock(side_effect=[sample_interview, sample_problem])
        execution_service._runner.run.return_value = RunResult(
            status=ExecutionStatus.WRONG_ANSWER,
            stdout="5\n",
            stderr="",
            compile_output="",
            time_seconds=0.1,
            memory_kb=1024,
            provider_status_id=4,
        )

        with patch("src.problems.loader.load_default_catalog", return_value=[sample_problem._spec]):
            result = await execution_service.execute_code(
                interview_id=sample_interview.id,
                code="print(1+2)",
                language="python",
            )

        assert result["status"] == "test_failure"
        assert result["tests_passed"] == 0

    @pytest.mark.asyncio
    async def test_compile_error_maps_to_compile_error(
        self, execution_service, sample_interview, sample_problem
    ) -> None:
        execution_service._session.get = AsyncMock(side_effect=[sample_interview, sample_problem])
        execution_service._runner.run.return_value = RunResult(
            status=ExecutionStatus.COMPILE_ERROR,
            stdout="",
            stderr="SyntaxError: invalid syntax",
            compile_output="SyntaxError: invalid syntax",
            time_seconds=0.0,
            memory_kb=0,
        )

        with patch("src.problems.loader.load_default_catalog", return_value=[sample_problem._spec]):
            result = await execution_service.execute_code(
                interview_id=sample_interview.id,
                code="invalid syntax",
                language="python",
            )

        assert result["status"] == "compile_error"

    @pytest.mark.asyncio
    async def test_timeout_maps_to_timeout(
        self, execution_service, sample_interview, sample_problem
    ) -> None:
        execution_service._session.get = AsyncMock(side_effect=[sample_interview, sample_problem])
        execution_service._runner.run.return_value = RunResult(
            status=ExecutionStatus.TIME_LIMIT_EXCEEDED,
            stdout="",
            stderr="",
            compile_output="",
            time_seconds=2.0,
            memory_kb=1024,
        )

        with patch("src.problems.loader.load_default_catalog", return_value=[sample_problem._spec]):
            result = await execution_service.execute_code(
                interview_id=sample_interview.id,
                code="while True: pass",
                language="python",
            )

        assert result["status"] == "timeout"

    @pytest.mark.asyncio
    async def test_memory_limit_maps_to_runtime_error(
        self, execution_service, sample_interview, sample_problem
    ) -> None:
        execution_service._session.get = AsyncMock(side_effect=[sample_interview, sample_problem])
        execution_service._runner.run.return_value = RunResult(
            status=ExecutionStatus.MEMORY_LIMIT_EXCEEDED,
            stdout="",
            stderr="",
            compile_output="",
            time_seconds=0.1,
            memory_kb=200000,
        )

        with patch("src.problems.loader.load_default_catalog", return_value=[sample_problem._spec]):
            result = await execution_service.execute_code(
                interview_id=sample_interview.id,
                code="x = [1] * 10**9",
                language="python",
            )

        assert result["status"] == "runtime_error"

    @pytest.mark.asyncio
    async def test_runtime_error_maps_to_runtime_error(
        self, execution_service, sample_interview, sample_problem
    ) -> None:
        execution_service._session.get = AsyncMock(side_effect=[sample_interview, sample_problem])
        execution_service._runner.run.return_value = RunResult(
            status=ExecutionStatus.RUNTIME_ERROR,
            stdout="",
            stderr="ZeroDivisionError: division by zero",
            compile_output="",
            time_seconds=0.1,
            memory_kb=1024,
        )

        with patch("src.problems.loader.load_default_catalog", return_value=[sample_problem._spec]):
            result = await execution_service.execute_code(
                interview_id=sample_interview.id,
                code="1/0",
                language="python",
            )

        assert result["status"] == "runtime_error"

    @pytest.mark.asyncio
    async def test_internal_error_maps_to_runtime_error(
        self, execution_service, sample_interview, sample_problem
    ) -> None:
        execution_service._session.get = AsyncMock(side_effect=[sample_interview, sample_problem])
        execution_service._runner.run.return_value = RunResult(
            status=ExecutionStatus.INTERNAL_ERROR,
            stdout="",
            stderr="Internal error",
            compile_output="",
            time_seconds=0.0,
            memory_kb=0,
        )

        with patch("src.problems.loader.load_default_catalog", return_value=[sample_problem._spec]):
            result = await execution_service.execute_code(
                interview_id=sample_interview.id,
                code="print(1)",
                language="python",
            )

        assert result["status"] == "runtime_error"

    @pytest.mark.asyncio
    async def test_missing_problem_raises_error(
        self, execution_service, sample_interview
    ) -> None:
        sample_interview.problem_id = None
        execution_service._session.get = AsyncMock(return_value=sample_interview)

        with pytest.raises(CodeExecutionError, match="No problem assigned"):
            await execution_service.execute_code(
                interview_id=sample_interview.id,
                code="print(1)",
                language="python",
            )

    @pytest.mark.asyncio
    async def test_nonexistent_interview_raises_error(
        self, execution_service
    ) -> None:
        execution_service._session.get = AsyncMock(return_value=None)

        with pytest.raises(CodeExecutionError, match="Interview not found"):
            await execution_service.execute_code(
                interview_id=uuid4(),
                code="print(1)",
                language="python",
            )

    @pytest.mark.asyncio
    async def test_persists_snapshot_and_turn(
        self, execution_service, sample_interview, sample_problem
    ) -> None:
        execution_service._session.get = AsyncMock(side_effect=[sample_interview, sample_problem])
        execution_service._runner.run.return_value = RunResult(
            status=ExecutionStatus.ACCEPTED,
            stdout="3\n",
            stderr="",
            compile_output="",
            time_seconds=0.1,
            memory_kb=1024,
        )

        with patch("src.problems.loader.load_default_catalog", return_value=[sample_problem._spec]):
            await execution_service.execute_code(
                interview_id=sample_interview.id,
                code="print(1+2)",
                language="python",
            )

        # Verify snapshot and turn were added
        assert execution_service._session.add.call_count >= 2
        # Check that a Snapshot and Turn were added
        added_objects = [call.args[0] for call in execution_service._session.add.call_args_list]
        from src.db.models import Snapshot, Turn
        assert any(isinstance(obj, Snapshot) for obj in added_objects)
        assert any(isinstance(obj, Turn) for obj in added_objects)