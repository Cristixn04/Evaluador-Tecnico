"""Pruebas unitarias e integración para las capacidades de la Semana 3 (S3).

Verifica:
1. Consolidación de costos conversacionales y evaluación.
2. Ausencia de doble contabilización en `TaskCostBreakdown`.
3. Manejo determinista de modelos sin tarifa configurada (preserva None sin asumir 0.0).
4. Manejo de tokens desconocidos o incompletos (preserva None sin asumir 0).
5. Evaluación con evidencia insuficiente o sin turnos/snapshots (marca needs_human_review = True).
6. Validación de referencias de evidencia (mantiene IDs existentes y descarta inexistentes).
7. Idempotencia de la evaluación y generación estructurada de reportes.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.telemetry import (
    InterviewCostTracker,
    get_task_cost_breakdown,
)
from src.db.enums import InterviewPhase, InterviewStatus, Seniority, TurnSpeaker
from src.db.models import (
    Interview,
    Organization,
    Problem,
    Snapshot,
    Turn,
    Vacancy,
)
from src.evaluation.pricing import calculate_llm_cost
from src.evaluation.service import EvaluationService
from src.problems.loader import load_default_catalog

# -----------------------------------------------------------------------------
# 1. Pruebas de Costo por Tarea y Ausencia de Doble Contabilización
# -----------------------------------------------------------------------------

def test_task_cost_breakdown_separates_stages_without_double_counting():
    """Verifica que TaskCostBreakdown separa conversación y evaluación sin doble suma."""
    tracker = InterviewCostTracker()
    interview_id = str(uuid.uuid4())

    # Turno conversacional 1: grok-4.6 ($5.00 prompt / $15.00 completion)
    # 1,000 prompt -> $0.005, 200 completion -> $0.003 => $0.008
    r1 = tracker.record_call(
        interview_id=interview_id,
        model="grok-4.6",
        input_tokens=1_000,
        output_tokens=200,
        stage="conversational",
    )
    # Turno conversacional 2:
    # 2,000 prompt -> $0.010, 400 completion -> $0.006 => $0.016
    r2 = tracker.record_call(
        interview_id=interview_id,
        model="grok-4.6",
        input_tokens=2_000,
        output_tokens=400,
        stage="conversational",
    )
    # Turno de evaluación:
    # 5,000 prompt -> $0.025, 1,000 completion -> $0.015 => $0.040
    r3 = tracker.record_call(
        interview_id=interview_id,
        model="grok-4.6",
        input_tokens=5_000,
        output_tokens=1_000,
        stage="evaluation",
    )

    breakdown = tracker.get_task_breakdown(interview_id)

    # Conversación
    assert breakdown.conversational.call_count == 2
    assert breakdown.conversational.total_input_tokens == 3_000
    assert breakdown.conversational.total_output_tokens == 600
    assert breakdown.conversational.total_tokens == 3_600
    assert breakdown.conversational.total_estimated_cost == pytest.approx(0.024, rel=1e-5)

    # Evaluación
    assert breakdown.evaluation.call_count == 1
    assert breakdown.evaluation.total_input_tokens == 5_000
    assert breakdown.evaluation.total_output_tokens == 1_000
    assert breakdown.evaluation.total_tokens == 6_000
    assert breakdown.evaluation.total_estimated_cost == pytest.approx(0.040, rel=1e-5)

    # Total de la tarea (suma estricta de llamadas, cada una contada 1 vez)
    assert breakdown.total.call_count == 3
    assert breakdown.total.total_input_tokens == 8_000
    assert breakdown.total.total_output_tokens == 1_600
    assert breakdown.total.total_tokens == 9_600
    assert breakdown.total.total_estimated_cost == pytest.approx(0.064, rel=1e-5)

    # Verificación de identidad sin duplicados
    assert len(breakdown.records) == 3
    assert set(breakdown.records) == {r1, r2, r3}


def test_cost_calculation_unknown_model_preserves_none():
    """Un modelo no soportado debe retornar None deterministamente, nunca 0.0."""
    cost = calculate_llm_cost("unsupported-exotic-model-v99", 5_000, 1_000)
    assert cost is None


def test_cost_calculation_incomplete_tokens_preserves_none():
    """Si no se reportan tokens de prompt o completion, el costo debe ser None."""
    assert calculate_llm_cost("grok-4.6", None, 500) is None
    assert calculate_llm_cost("grok-4.6", 1000, None) is None
    assert calculate_llm_cost("grok-4.6", -10, 500) is None
    assert calculate_llm_cost("grok-4.6", "invalid", 500) is None


def test_task_breakdown_flags_unknown_costs_safely():
    """Si una llamada tiene costo desconocido, el total se marca con has_unknown_cost y None."""
    tracker = InterviewCostTracker()
    interview_id = str(uuid.uuid4())

    tracker.record_call(
        interview_id=interview_id,
        model="grok-4.6",
        input_tokens=1_000,
        output_tokens=200,
        stage="conversational",
    )
    # Llamada con modelo sin tarifa
    tracker.record_call(
        interview_id=interview_id,
        model="unknown-model-without-rate",
        input_tokens=2_000,
        output_tokens=400,
        stage="evaluation",
    )

    breakdown = tracker.get_task_breakdown(interview_id)
    assert breakdown.conversational.total_estimated_cost == pytest.approx(0.008, rel=1e-5)
    assert breakdown.evaluation.total_estimated_cost is None
    assert breakdown.evaluation.has_unknown_cost is True
    # El total tampoco oculta la llamada desconocida: se define como None
    assert breakdown.total.total_estimated_cost is None
    assert breakdown.total.has_unknown_cost is True


# -----------------------------------------------------------------------------
# 2. Pruebas de Datos Reales (Catálogo y Carga)
# -----------------------------------------------------------------------------

def test_pse_reconciliation_problem_spec_loads_valid():
    """Verifica que el problema pse-payment-reconciliation sea válido según el catálogo oficial."""
    catalog = load_default_catalog()
    pse = next((p for p in catalog if p.id == "pse-payment-reconciliation"), None)
    assert pse is not None
    assert "conciliación" in pse.title.lower() or "pse" in pse.title.lower()
    assert len(pse.tests) >= 3
    assert pse.limits.timeout_ms > 0
    assert pse.limits.memory_mb > 0
    assert any("python" in str(lang).lower() for lang in pse.languages)


# -----------------------------------------------------------------------------
# 3. Pruebas de Evaluación Propia con Base de Datos
# -----------------------------------------------------------------------------

@pytest.fixture
async def sample_real_interview(db_session: AsyncSession) -> Interview:
    """Fixture para crear una entrevista en base de datos aislada."""
    org = Organization(name=f"Org-{uuid.uuid4().hex[:6]}")
    db_session.add(org)
    await db_session.flush()

    vac = Vacancy(
        organization_id=org.id,
        title="Backend Engineer",
        raw_description="Backend testing",
        role_category="Backend",
        seniority=Seniority.MID,
    )
    db_session.add(vac)
    await db_session.flush()

    catalog = load_default_catalog()
    pse_spec = next(p for p in catalog if p.id == "pse-payment-reconciliation")
    prob = Problem(
        id=pse_spec.persistence_id(),
        title=pse_spec.title,
        difficulty=pse_spec.difficulty,
        language="python",
        scenario_preview=pse_spec.statement[:200],
        tags=list(pse_spec.tags),
    )
    db_session.add(prob)
    await db_session.flush()

    interview = Interview(
        vacancy_id=vac.id,
        problem_id=prob.id,
        candidate_name="Candidato Test S3",
        candidate_email="candidato-test-s3@evaluador.local",
        status=InterviewStatus.COMPLETED,
        phase=InterviewPhase.WRAPUP,
        expires_at=datetime.now(UTC),
    )
    db_session.add(interview)
    await db_session.flush()
    return interview


@pytest.mark.asyncio
async def test_evaluation_without_evidence_returns_needs_human_review(
    db_session: AsyncSession,
    sample_real_interview: Interview,
):
    """Una entrevista sin turnos ni snapshots no debe evaluarse automáticamente: needs_human_review=True."""
    eval_service = EvaluationService(db_session)
    report = await eval_service.evaluate(sample_real_interview.id)

    assert report.needs_human_review is True
    assert report.overall_score == 0.0
    assert report.recommendation == "borderline"
    assert "insuficiente" in (report.discrepancy_note or "").lower()


@pytest.mark.asyncio
async def test_evaluation_validates_and_scrubs_hallucinated_evidence_references(
    db_session: AsyncSession,
    sample_real_interview: Interview,
):
    """Verifica que referencias de turnos inexistentes sean descartadas por _validate_evidence."""
    real_turn = Turn(
        interview_id=sample_real_interview.id,
        speaker=TurnSpeaker.CANDIDATE,
        content="Optimizamos el procesamiento en O(N) usando un hash set.",
    )
    db_session.add(real_turn)
    await db_session.flush()

    eval_service = EvaluationService(db_session)

    fake_turn_uuid = uuid.uuid4()
    raw_evidence = [
        {
            "competency": "algorithmic_reasoning",
            "evidence_quote": "Optimizamos el procesamiento en O(N)",
            "turn_id": str(real_turn.id),
            "reasoning": "Cita válida de turno existente",
        },
        {
            "competency": "problem_solving",
            "evidence_quote": "Esta es una cita inventada",
            "turn_id": str(fake_turn_uuid),
            "reasoning": "Referencia alucinada por LLM",
        },
    ]

    validated = await eval_service._validate_evidence(sample_real_interview, raw_evidence)
    assert len(validated) == 1
    assert validated[0]["turn_id"] == real_turn.id
    assert validated[0]["competency"] == "algorithmic_reasoning"


@pytest.mark.asyncio
async def test_evaluation_service_records_evaluation_stage_telemetry(
    db_session: AsyncSession,
    sample_real_interview: Interview,
):
    """Verifica que EvaluationService registra su consumo de tokens con stage='evaluation'."""
    # Añadir un turno y un snapshot para tener evidencia suficiente
    turn = Turn(
        interview_id=sample_real_interview.id,
        speaker=TurnSpeaker.CANDIDATE,
        content="Diseño con tabla hash O(N).",
    )
    snap = Snapshot(
        interview_id=sample_real_interview.id,
        code="def reconcile(a, b): return []",
        language="python",
        phase="CODING",
        reason="run",
        tests_passed=1,
        total_tests=1,
        execution_status="success",
    )
    db_session.add(turn)
    db_session.add(snap)
    await db_session.flush()

    mock_llm_json = {
        "competencies": {
            "problem_solving": 4,
            "algorithmic_reasoning": 4,
            "code_quality": 4,
            "technical_communication": 4,
            "complexity_management": 4,
        },
        "evidence": [
            {
                "competency": "algorithmic_reasoning",
                "evidence_quote": "Diseño con tabla hash O(N)",
                "turn_id": str(turn.id),
                "reasoning": "Muestra comprensión de complejidad temporal.",
            }
        ],
        "strengths": ["Buena comprensión algorítmica"],
        "risks": [],
        "tokens_prompt": 1200,
        "tokens_completion": 300,
        "model_name": "grok-4.6",
    }

    eval_service = EvaluationService(db_session)

    with patch.object(eval_service, "_call_judge_llm", new=AsyncMock(return_value=mock_llm_json)):
        report = await eval_service.evaluate(sample_real_interview.id, force=True)

    assert report.overall_score == 4.0
    assert report.recommendation == "hire"
    assert report.needs_human_review is False

    breakdown = get_task_cost_breakdown(sample_real_interview.id)
    # Debe tener registro en etapa evaluation
    assert breakdown.evaluation.call_count >= 1
    assert breakdown.evaluation.total_input_tokens is not None
    assert breakdown.evaluation.total_input_tokens > 0


@pytest.mark.asyncio
async def test_persistent_telemetry_and_reconstruction_from_db(
    db_session: AsyncSession,
    sample_real_interview: Interview,
) -> None:
    """Verifica que la telemetría se persiste en PostgreSQL y se reconstruye post-mortem."""
    from src.core.telemetry import (
        interview_cost_tracker,
        reconstruct_task_cost_breakdown_from_db,
        record_persisted_interview_cost,
    )

    # 1. Registrar llamadas conversacionales y de evaluación
    await record_persisted_interview_cost(
        interview_id=sample_real_interview.id,
        model="grok-4.6",
        input_tokens=1500,
        output_tokens=250,
        stage="conversational",
        measurement_status="measured",
        session=db_session,
    )
    await record_persisted_interview_cost(
        interview_id=sample_real_interview.id,
        model="grok-4.6",
        input_tokens=3000,
        output_tokens=800,
        stage="evaluation",
        measurement_status="measured",
        session=db_session,
    )
    await db_session.commit()

    # 2. Simular reinicio del proceso limpiando el tracker en memoria
    interview_cost_tracker.clear()
    assert interview_cost_tracker.get_task_breakdown(sample_real_interview.id).total.call_count == 0

    # 3. Reconstruir el desglose directamente desde PostgreSQL
    reconstructed = await reconstruct_task_cost_breakdown_from_db(db_session, sample_real_interview.id)

    assert reconstructed.conversational.call_count == 1
    assert reconstructed.conversational.total_input_tokens == 1500
    assert reconstructed.conversational.total_output_tokens == 250
    assert reconstructed.conversational.measured_cost == pytest.approx(0.01125, rel=1e-4)

    assert reconstructed.evaluation.call_count == 1
    assert reconstructed.evaluation.total_input_tokens == 3000
    assert reconstructed.evaluation.total_output_tokens == 800
    assert reconstructed.evaluation.measured_cost == pytest.approx(0.02700, rel=1e-4)

    assert reconstructed.total.call_count == 2
    assert reconstructed.total.total_tokens == 5550
    assert reconstructed.total.total_estimated_cost == pytest.approx(0.03825, rel=1e-4)


@pytest.mark.asyncio
async def test_judge0_unavailable_handling_graceful(
    db_session: AsyncSession,
    sample_real_interview: Interview,
) -> None:
    """Verifica que si Judge0 no está disponible, el sistema marca unavailable sin simular tests."""
    from src.execution.service import CodeExecutionService
    from src.interview.service import InterviewService

    class MockUnavailableRunner:
        async def check_availability(self) -> bool:
            return False

        async def aclose(self) -> None:
            pass

    interview_service = InterviewService(db_session)
    exec_service = CodeExecutionService(db_session, interview_service)
    exec_service._runner = MockUnavailableRunner()

    result = await exec_service.execute_code(
        interview_id=sample_real_interview.id,
        code="def solution(): pass",
        language="python",
    )

    assert result["status"] == "unavailable"
    assert result["tests_passed"] is None
    assert "Judge0 CE sandbox is currently unavailable" in result["stderr"]


@pytest.mark.asyncio
async def test_judge0_multi_test_execution_mocked(
    db_session: AsyncSession,
    sample_real_interview: Interview,
) -> None:
    """Verifica que el servicio ejecute cada prueba real y contabilice passed/total con precisión."""
    from src.execution.service import CodeExecutionService
    from src.interview.service import InterviewService
    from src.sandbox.types import ExecutionStatus, RunRequest, RunResult

    class MockRunner:
        def __init__(self) -> None:
            self.call_count = 0

        async def check_availability(self) -> bool:
            return True

        async def run(self, request: RunRequest) -> RunResult:
            self.call_count += 1
            # Primera prueba pasa, segunda falla
            if self.call_count == 1:
                return RunResult(
                    status=ExecutionStatus.ACCEPTED,
                    stdout='{"mismatches":[]}',
                    stderr="",
                    compile_output="",
                    time_seconds=0.05,
                )
            else:
                return RunResult(
                    status=ExecutionStatus.WRONG_ANSWER,
                    stdout='{"mismatches":["ERR"]}',
                    stderr="AssertionError",
                    compile_output="",
                    time_seconds=0.06,
                )

        async def aclose(self) -> None:
            pass

    interview_service = InterviewService(db_session)
    exec_service = CodeExecutionService(db_session, interview_service)
    exec_service._runner = MockRunner()

    result = await exec_service.execute_code(
        interview_id=sample_real_interview.id,
        code="def solution(): pass",
        language="python",
    )

    assert result["status"] == "test_failure"
    assert result["tests_passed"] == 1
    assert result["total_tests"] == 3
    assert len(result["test_details"]) == 3

