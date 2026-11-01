"""Tests para S2-01A: Telemetría estructurada de herramientas del agente."""

import logging
import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.agent.service import InterviewAgent
from src.core.telemetry import tool_telemetry
from src.db.enums import Difficulty, InterviewPhase, Seniority, TurnSpeaker
from src.db.models import Interview, Organization, Problem, Turn, Vacancy
from src.execution.service import CodeExecutionService
from src.interview.service import InterviewService
from src.problems.loader import load_default_catalog
from src.problems.selector import ProblemSelector
from src.sandbox.types import ExecutionStatus, RunResult


@pytest.fixture
def clean_telemetry_logs(caplog: pytest.LogCaptureFixture):
    caplog.set_level(logging.INFO, logger="agent.telemetry")
    return caplog


def _get_telemetry_events(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [
        record.message
        for record in caplog.records
        if "[AGENT_TOOL_CALL:" in record.message
    ]


# -----------------------------------------------------------------------------
# 1. Tests Unitarios del Helper de Telemetría (Invariantes y Seguridad)
# -----------------------------------------------------------------------------

def test_telemetry_correct_tool_names_and_lifecycle(clean_telemetry_logs):
    """Verifica nombres correctos de herramientas y ciclo START -> SUCCESS."""
    tel = tool_telemetry("problem_selector", "select_one")
    tel.start(seniority="junior", language="python")
    tel.success(problem_id="p1234567", title="Test Problem")

    events = _get_telemetry_events(clean_telemetry_logs)
    assert len(events) == 2
    assert "[AGENT_TOOL_CALL:START] tool=problem_selector operation=select_one seniority=junior language=python" in events[0]
    assert "[AGENT_TOOL_CALL:SUCCESS] tool=problem_selector operation=select_one" in events[1]
    assert "problem_id=p1234567" in events[1]
    assert "duration_ms=" in events[1]


def test_telemetry_error_suppresses_subsequent_success(clean_telemetry_logs):
    """Un error no genera simultáneamente SUCCESS y viceversa."""
    tel = tool_telemetry("code_execution_sandbox", "execute_code")
    tel.start(language="python", code_bytes=100)
    tel.error("SyntaxError: invalid syntax", status="compile_error")
    # Intento inválido de registrar éxito posterior
    tel.success(status="success", passed="3/3")

    events = _get_telemetry_events(clean_telemetry_logs)
    assert len(events) == 2
    assert "[AGENT_TOOL_CALL:START]" in events[0]
    assert "[AGENT_TOOL_CALL:ERROR] tool=code_execution_sandbox" in events[1]
    assert "status=compile_error" in events[1]
    # No debe existir evento SUCCESS
    assert not any("[AGENT_TOOL_CALL:SUCCESS]" in e for e in events)


def test_telemetry_success_suppresses_subsequent_error(clean_telemetry_logs):
    """Un éxito no genera simultáneamente ERROR posterior."""
    tel = tool_telemetry("code_execution_sandbox", "execute_code")
    tel.start(language="python")
    tel.success(status="success")
    tel.error("Late error")

    events = _get_telemetry_events(clean_telemetry_logs)
    assert len(events) == 2
    assert "[AGENT_TOOL_CALL:START]" in events[0]
    assert "[AGENT_TOOL_CALL:SUCCESS]" in events[1]
    assert not any("[AGENT_TOOL_CALL:ERROR]" in e for e in events)


def test_telemetry_contains_no_pii_or_tokens(clean_telemetry_logs):
    """Garantiza sanitización estricta: nunca filtra JWT, Bearer tokens, emails ni API keys."""
    tel = tool_telemetry("problem_selector", "select_one")
    tel.start(
        auth_header="Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.abc",
        candidate_email="candidato.privado@empresa.com",
        api_key="sk-123456789012345678901234567890",
    )
    tel.error("Error connecting with token eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.test for juan@mail.com")

    events = _get_telemetry_events(clean_telemetry_logs)
    combined = " ".join(events)

    assert "eyJhbGciOi" not in combined
    assert "candidato.privado@empresa.com" not in combined
    assert "juan@mail.com" not in combined
    assert "sk-1234567890" not in combined
    assert "[REDACTED]" in combined


# -----------------------------------------------------------------------------
# 2. Tool 1: ProblemSelector Integration Telemetry
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_problem_selector_emits_start_and_success(db_session: AsyncSession, clean_telemetry_logs):
    """ProblemSelector emite START y SUCCESS al encontrar problema."""
    prob = Problem(
        id=uuid.uuid4(),
        title="Conciliación PSE",
        difficulty=Difficulty.JUNIOR,
        language="python",
        scenario_preview="Conciliar transacciones",
        tags=["python", "pse", "fintech"],
    )
    db_session.add(prob)
    await db_session.flush()

    selector = ProblemSelector(db_session)
    selected = await selector.select_one(skills=["pse"], seniority=Seniority.JUNIOR, language="python")

    assert selected is not None
    assert selected.title == "Conciliación PSE"

    events = _get_telemetry_events(clean_telemetry_logs)
    assert any("[AGENT_TOOL_CALL:START] tool=problem_selector operation=select_one" in e for e in events)
    assert any("[AGENT_TOOL_CALL:SUCCESS] tool=problem_selector operation=select_one" in e and "title=\"Conciliación PSE\"" in e for e in events)


@pytest.mark.asyncio
async def test_problem_selector_emits_start_and_error_when_no_match(db_session: AsyncSession, clean_telemetry_logs):
    """ProblemSelector emite START y ERROR cuando no hay coincidencias."""
    selector = ProblemSelector(db_session)
    # Buscar con criterio imposible sin seed de catálogo para forzar None
    selected = await selector.select_one(skills=["non_existent_skill_xyz_123"], language="cobol")

    assert selected is None
    events = _get_telemetry_events(clean_telemetry_logs)
    assert any("[AGENT_TOOL_CALL:START] tool=problem_selector" in e for e in events)
    assert any("[AGENT_TOOL_CALL:ERROR] tool=problem_selector" in e and "No problem matches criteria" in e for e in events)


# -----------------------------------------------------------------------------
# 3. Tool 2: CodeExecutionSandbox Integration Telemetry
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_sandbox_emits_start_and_success(db_session: AsyncSession, clean_telemetry_logs):
    """Sandbox emite START y SUCCESS ante ejecución exitosa de pruebas."""
    # Crear problema y entrevista mínima
    org = Organization(name="Org Telemetry Test")
    db_session.add(org)
    await db_session.flush()

    vac = Vacancy(title="Backend Dev", raw_description="Backend Dev Desc", organization_id=org.id)
    db_session.add(vac)
    await db_session.flush()

    catalog = load_default_catalog()
    spec = catalog[0]
    prob_id = spec.persistence_id()

    prob = Problem(
        id=prob_id,
        title=spec.title,
        difficulty=spec.difficulty,
        language="python",
        scenario_preview="Test problem",
        tags=list(spec.tags),
    )
    db_session.add(prob)
    await db_session.flush()

    interview = Interview(
        vacancy_id=vac.id,
        problem_id=prob.id,
        candidate_email="test@example.com",
        candidate_name="Test Candidate",
        expires_at=datetime.now(UTC) + timedelta(hours=2),
        phase=InterviewPhase.CODING,
    )
    db_session.add(interview)
    await db_session.flush()

    interview_service = InterviewService(db_session)
    exec_service = CodeExecutionService(db_session, interview_service)

    # Mock runner con resultado exitoso
    mock_res = RunResult(
        status=ExecutionStatus.ACCEPTED,
        stdout="All tests passed",
        stderr="",
        compile_output="",
        time_seconds=0.085,
    )
    mock_runner = AsyncMock()
    mock_runner.run = AsyncMock(return_value=mock_res)
    mock_runner.aclose = AsyncMock()
    exec_service._runner = mock_runner  # type: ignore[assignment]

    result = await exec_service.execute_code(
        interview_id=interview.id,
        code="def solution(): return True",
        language="python",
    )

    assert result["status"] == "success"
    events = _get_telemetry_events(clean_telemetry_logs)
    assert any("[AGENT_TOOL_CALL:START] tool=code_execution_sandbox operation=execute_code language=python" in e for e in events)
    assert any("[AGENT_TOOL_CALL:SUCCESS] tool=code_execution_sandbox operation=execute_code status=success" in e for e in events)


@pytest.mark.asyncio
async def test_sandbox_emits_start_and_error_on_compile_error(db_session: AsyncSession, clean_telemetry_logs):
    """Sandbox emite START y ERROR ante fallo controlado (error de sintaxis/compilación)."""
    org = Organization(name="Org Telemetry Test 2")
    db_session.add(org)
    await db_session.flush()

    vac = Vacancy(title="Backend Dev", raw_description="Backend Dev Desc", organization_id=org.id)
    db_session.add(vac)
    await db_session.flush()

    catalog = load_default_catalog()
    spec = catalog[0]
    prob_id = spec.persistence_id()

    prob = Problem(
        id=prob_id,
        title=spec.title,
        difficulty=spec.difficulty,
        language="python",
        scenario_preview="Test problem",
        tags=list(spec.tags),
    )
    db_session.add(prob)
    await db_session.flush()

    interview = Interview(
        vacancy_id=vac.id,
        problem_id=prob.id,
        candidate_email="test@example.com",
        candidate_name="Test Candidate",
        expires_at=datetime.now(UTC) + timedelta(hours=2),
        phase=InterviewPhase.CODING,
    )
    db_session.add(interview)
    await db_session.flush()

    interview_service = InterviewService(db_session)
    exec_service = CodeExecutionService(db_session, interview_service)

    # Mock runner con fallo controlado de compilación
    mock_res = RunResult(
        status=ExecutionStatus.COMPILE_ERROR,
        stdout="",
        stderr="SyntaxError: invalid syntax line 1",
        compile_output="SyntaxError: invalid syntax line 1",
        time_seconds=0.03,
    )
    mock_runner_err = AsyncMock()
    mock_runner_err.run = AsyncMock(return_value=mock_res)
    mock_runner_err.aclose = AsyncMock()
    exec_service._runner = mock_runner_err  # type: ignore[assignment]

    result = await exec_service.execute_code(
        interview_id=interview.id,
        code="def invalid syntax:",
        language="python",
    )

    assert result["status"] == "compile_error"
    events = _get_telemetry_events(clean_telemetry_logs)
    assert any("[AGENT_TOOL_CALL:START] tool=code_execution_sandbox operation=execute_code" in e for e in events)
    assert any("[AGENT_TOOL_CALL:ERROR] tool=code_execution_sandbox" in e and "status=compile_error" in e for e in events)


# -----------------------------------------------------------------------------
# 4. Tool 3: AdaptiveHintGenerator Integration Telemetry
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_hint_generator_emits_start_and_success_when_delivered(db_session: AsyncSession, clean_telemetry_logs):
    """AdaptiveHintGenerator emite START y SUCCESS cuando efectivamente se entrega una pista."""
    org = Organization(name="Org Telemetry Test 3")
    db_session.add(org)
    await db_session.flush()

    vac = Vacancy(title="Backend Dev", raw_description="Backend Dev Desc", organization_id=org.id)
    db_session.add(vac)
    await db_session.flush()

    interview = Interview(
        id=uuid.uuid4(),
        vacancy_id=vac.id,
        candidate_email="test@example.com",
        candidate_name="Test Candidate",
        expires_at=datetime.now(UTC) + timedelta(hours=2),
        phase=InterviewPhase.CODING,
        hint_level=0,
    )
    # Turno del candidato con timestamp de hace 200 segundos (supera umbral de nivel 0: 180s)
    old_turn = Turn(
        interview_id=interview.id,
        speaker=TurnSpeaker.CANDIDATE,
        content="No se como empezar",
        created_at=datetime.now(UTC) - timedelta(seconds=200),
    )
    interview.turns.append(old_turn)
    db_session.add(interview)
    db_session.add(old_turn)
    await db_session.flush()

    interview_service = InterviewService(db_session)
    selector = ProblemSelector(db_session)
    agent = InterviewAgent(db_session, interview_service, selector)

    delivered = await agent._maybe_deliver_hint(interview, InterviewPhase.CODING)

    assert delivered is True
    assert interview.hint_level == 1

    events = _get_telemetry_events(clean_telemetry_logs)
    assert any("[AGENT_TOOL_CALL:START] tool=adaptive_hint_generator operation=deliver_hint" in e for e in events)
    assert any("[AGENT_TOOL_CALL:SUCCESS] tool=adaptive_hint_generator operation=deliver_hint" in e and "new_level=1" in e for e in events)


@pytest.mark.asyncio
async def test_hint_generator_does_not_emit_telemetry_when_inactivity_not_met(db_session: AsyncSession, clean_telemetry_logs):
    """AdaptiveHintGenerator NO emite telemetría si no se cumplen las condiciones de estancamiento."""
    org = Organization(name="Org Telemetry Test 4")
    db_session.add(org)
    await db_session.flush()

    vac = Vacancy(title="Backend Dev", raw_description="Backend Dev Desc", organization_id=org.id)
    db_session.add(vac)
    await db_session.flush()

    interview = Interview(
        id=uuid.uuid4(),
        vacancy_id=vac.id,
        candidate_email="test@example.com",
        candidate_name="Test Candidate",
        expires_at=datetime.now(UTC) + timedelta(hours=2),
        phase=InterviewPhase.CODING,
        hint_level=0,
    )
    # Turno reciente (hace solo 10 segundos, no cumple umbral de 180s)
    recent_turn = Turn(
        interview_id=interview.id,
        speaker=TurnSpeaker.CANDIDATE,
        content="Estoy pensando...",
        created_at=datetime.now(UTC) - timedelta(seconds=10),
    )
    interview.turns.append(recent_turn)
    db_session.add(interview)
    db_session.add(recent_turn)
    await db_session.flush()

    interview_service = InterviewService(db_session)
    selector = ProblemSelector(db_session)
    agent = InterviewAgent(db_session, interview_service, selector)

    delivered = await agent._maybe_deliver_hint(interview, InterviewPhase.CODING)

    assert delivered is False
    assert interview.hint_level == 0

    # NO debe existir telemetría falsa de inicio ni éxito
    events = _get_telemetry_events(clean_telemetry_logs)
    assert not any("[AGENT_TOOL_CALL:" in e for e in events)
