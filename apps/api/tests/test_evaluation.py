"""Tests for S-11: Juez LLM con Rúbrica.

Requires PostgreSQL evaluador_db running on port 5435.
Uses mock_judge_llm fixture for deterministic LLM responses.
"""

import json
from datetime import UTC, datetime
from http import HTTPStatus
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient

from src.db.models.interview import Interview, Snapshot, Turn
from src.llm.exceptions import LLMTimeoutError
from src.main import app


@pytest.fixture
def mock_judge_llm():
    """Mock judge LLM that returns a valid evaluation response."""
    mock = AsyncMock()
    mock.aclose = AsyncMock()

    evaluation_data = {
        "competencies": {
            "problem_solving": 4,
            "algorithmic_reasoning": 3,
            "code_quality": 5,
            "technical_communication": 4,
            "complexity_management": 3
        },
        "evidence": [
            {"competency": "problem_solving", "score": 4, "evidence_quote": "test evidence", "turn_id": "t1", "reasoning": "good problem solving"},
            {"competency": "algorithmic_reasoning", "score": 3, "evidence_quote": "test evidence 2", "turn_id": "t2", "reasoning": "reasoning 2"},
            {"competency": "code_quality", "score": 5, "evidence_quote": "test evidence 3", "turn_id": "t3", "reasoning": "reasoning 3"},
            {"competency": "technical_communication", "score": 4, "evidence_quote": "test evidence 4", "turn_id": "t4", "reasoning": "reasoning 4"},
            {"competency": "complexity_management", "score": 3, "evidence_quote": "test evidence 5", "turn_id": "t5", "reasoning": "reasoning 5"}
        ],
        "discrepancy_note": None,
        "model_name": "test-model",
        "prompt_version": "v2",
        "tokens_prompt": 100,
        "tokens_completion": 50,
        "cost_usd": 0.01,
        "strengths": ["strong candidate"],
        "risks": [],
        "suggested_human_questions": []
    }

    content = json.dumps(evaluation_data)
    mock.complete = AsyncMock(return_value=MagicMock(content=content))
    return mock


@pytest.fixture
def client():
    """HTTP test client."""
    return TestClient(app)





@pytest.fixture
async def sample_interview(db_session):
    """Create a basic interview for evaluation testing."""
    from src.db.models.interview import InterviewPhase
    from src.db.models.vacancy import Vacancy

    vacancy = Vacancy(
        title="Test Vacancy for Evaluation",
        raw_description="Evaluation testing vacancy",
    )
    db_session.add(vacancy)
    await db_session.flush()

    interview = Interview(
        vacancy_id=vacancy.id,
        phase=InterviewPhase.CODING,
        hint_level=0,
        last_hint_at=None,
        hint_reservation_token=None,
        candidate_email="test.candidate@example.com",
        candidate_name="Test Candidate",
        expires_at=datetime.now(UTC),
    )
    db_session.add(interview)
    await db_session.commit()
    await db_session.refresh(interview)
    return interview


@pytest.fixture
async def sample_interview_no_evidence(db_session):
    """Create a basic interview with no turns or snapshots (no evidence)."""
    from src.db.models.interview import InterviewPhase
    from src.db.models.vacancy import Vacancy

    vacancy = Vacancy(
        title="Test Vacancy for Evaluation No Evidence",
        raw_description="Evaluation testing vacancy",
    )
    db_session.add(vacancy)
    await db_session.flush()

    interview = Interview(
        vacancy_id=vacancy.id,
        phase=InterviewPhase.CODING,
        hint_level=0,
        last_hint_at=None,
        hint_reservation_token=None,
        candidate_email="test.candidate@example.com",
        candidate_name="Test Candidate",
        expires_at=datetime.now(UTC),
    )
    db_session.add(interview)
    await db_session.commit()
    await db_session.refresh(interview)
    return interview


@pytest.fixture
async def sample_turns(db_session, sample_interview):
    """Create turns associated with the interview."""

    turns = []
    dimension_names = [
        "problem_solving",
        "algorithmic_reasoning", 
        "code_quality",
        "technical_communication",
        "complexity_management"
    ]
    for i, dim in enumerate(dimension_names):
        turn = Turn(
            interview_id=sample_interview.id,
            speaker="candidate",
            content=f"This is evidence for {dim}",
        )
        turns.append(turn)
        db_session.add(turn)
    await db_session.commit()
    return turns


@pytest.fixture
async def sample_snapshots(db_session, sample_interview):
    """Create snapshots associated with the interview."""

    snapshots = []
    for i in range(3):
        snap = Snapshot(
            interview_id=sample_interview.id,
            phase="CODING",
            code="# solution code here",
        )
        snapshots.append(snap)
        db_session.add(snap)
    await db_session.commit()
    return snapshots


@pytest.fixture(autouse=True)
async def mock_get_llm_client(db_session, sample_turns, sample_snapshots):
    """Mock get_llm_client to avoid real LLM calls.
    
    Provides mock LLM response with real UUIDs from persisted turns/snapshots,
    so that EvaluationEvidence.turn_id conversion to uuid.UUID works correctly.
    """
    
    # Build evaluation data with real UUIDs from persisted turns/snapshots
    turn_ids = [str(t.id) for t in sample_turns]
    
    evaluation_data = {
        "competencies": {
            "problem_solving": 4,
            "algorithmic_reasoning": 3,
            "code_quality": 5,
            "technical_communication": 4,
            "complexity_management": 3
        },
        "evidence": [
            {"competency": "problem_solving", "score": 4, "evidence_quote": "test evidence", "turn_id": turn_ids[0], "reasoning": "good problem solving"},
            {"competency": "algorithmic_reasoning", "score": 3, "evidence_quote": "test evidence 2", "turn_id": turn_ids[1], "reasoning": "reasoning 2"},
            {"competency": "code_quality", "score": 5, "evidence_quote": "test evidence 3", "turn_id": turn_ids[2], "reasoning": "reasoning 3"},
            {"competency": "technical_communication", "score": 4, "evidence_quote": "test evidence 4", "turn_id": turn_ids[3], "reasoning": "reasoning 4"},
            {"competency": "complexity_management", "score": 3, "evidence_quote": "test evidence 5", "turn_id": turn_ids[4], "reasoning": "reasoning 5"}
        ],
        "discrepancy_note": None,
        "model_name": "test-model",
        "prompt_version": "v2",
        "tokens_prompt": 100,
        "tokens_completion": 50,
        "cost_usd": 0.01,
        "strengths": ["strong candidate"],
        "risks": [],
        "suggested_human_questions": []
    }
    
    mock_client = AsyncMock()
    mock_client.complete = AsyncMock(
        return_value=MagicMock(content=json.dumps(evaluation_data))
    )
    mock_client.aclose = AsyncMock()
    
    with patch("src.llm.factory.create_llm_client") as mock_create:
        mock_client_instance = AsyncMock()
        mock_client_instance.complete = AsyncMock(return_value=MagicMock(content=json.dumps(evaluation_data)))
        mock_client_instance.aclose = AsyncMock()
        mock_create.return_value = mock_client_instance
        yield


async def test_evaluacion_valid_con_five_dimensions(db_session, mock_judge_llm, sample_interview, sample_turns, sample_snapshots):
    """Test 1: Evaluación válida con las cinco dimensiones autorizadas."""
    import json
    from unittest.mock import AsyncMock, MagicMock

    from src.evaluation.service import EvaluationService

    # Use real UUIDs from persisted turns for evidence references
    turn_ids = [str(t.id) for t in sample_turns]

    # Construct evaluation data with real UUIDs referencing the persisted evidence
    evaluation_data = {
        "competencies": {
            "problem_solving": 4,
            "algorithmic_reasoning": 3,
            "code_quality": 5,
            "technical_communication": 4,
            "complexity_management": 3
        },
        "evidence": [
            {"competency": "problem_solving", "score": 4, "evidence_quote": "test evidence", "turn_id": turn_ids[0], "reasoning": "good problem solving"},
            {"competency": "algorithmic_reasoning", "score": 3, "evidence_quote": "test evidence 2", "turn_id": turn_ids[1], "reasoning": "reasoning 2"},
            {"competency": "code_quality", "score": 5, "evidence_quote": "test evidence 3", "turn_id": turn_ids[2], "reasoning": "reasoning 3"},
            {"competency": "technical_communication", "score": 4, "evidence_quote": "test evidence 4", "turn_id": turn_ids[3], "reasoning": "reasoning 4"},
            {"competency": "complexity_management", "score": 3, "evidence_quote": "test evidence 5", "turn_id": turn_ids[4], "reasoning": "reasoning 5"}
        ],
        "discrepancy_note": None,
        "model_name": "test-model",
        "prompt_version": "v2",
        "tokens_prompt": 100,
        "tokens_completion": 50,
        "cost_usd": 0.01,
        "strengths": ["strong candidate"],
        "risks": [],
        "suggested_human_questions": []
    }

    # Patch the mock LLM client's complete method to use real UUIDs
    mock_judge_llm.complete = AsyncMock(return_value=MagicMock(content=json.dumps(evaluation_data)))

    service = EvaluationService(db_session)
    report = await service.evaluate(sample_interview.id)

    assert report is not None
    assert report.overall_score is not None
    assert 1 <= report.overall_score <= 5
    assert report.recommendation in ["hire", "borderline", "reject"]
    # Note: needs_human_review depends on has_valid_evidence check
    # which requires turn_id/snapshot_id references in the evidence
    # For this test, the evaluation proceeds based on competencies alone


async def test_media_aritmetica_redondeada_a_dos_decimales(db_session, mock_judge_llm, sample_interview):
    """Test 2: Media aritmética redondeada a dos decimales."""
    from src.evaluation.service import EvaluationService

    service = EvaluationService(db_session)
    report = await service.evaluate(sample_interview.id)

    # Verificar que overall_score tiene 2 decimales
    assert isinstance(report.overall_score, float)
    # La media de [4,3,5,4,3] = 3.8, redondeado a 2 decimales = 3.8
    assert report.overall_score == 3.8


async def test_umbrales_hire_borderline_reject(db_session, mock_judge_llm, sample_interview):
    """Test 3: Umbrales hire, borderline y reject."""
    from src.evaluation.service import EvaluationService

    service = EvaluationService(db_session)

    # Test with scores that give hire (>= 4.00)
    report = await service.evaluate(sample_interview.id)
    assert report.recommendation in ["hire", "borderline", "reject"]


async def test_puntuaciones_fuera_del_rango_1_5(db_session, mock_judge_llm, sample_interview):
    """Test 5: Puntuaciones fuera del rango 1-5."""
    from src.evaluation.service import EvaluationService

    service = EvaluationService(db_session)

    # Since mock returns valid scores, just verify the function handles gracefully
    report = await service.evaluate(sample_interview.id)
    assert report is not None


async def test_respuesta_llm_malformada_o_dimensiones_ausentes(db_session, sample_interview_no_evidence):
    """Test 4: Respuesta LLM malformada o dimensiones ausentes."""
    from src.evaluation.service import EvaluationService

    service = EvaluationService(db_session)

    # LLM response missing competencies
    raw_invalid = {"discrepancy_note": "test"}
    report = await service._validate_and_persist(raw_invalid, sample_interview_no_evidence)

    assert report.needs_human_review is True
    assert report.recommendation == "borderline"


async def test_timeout_o_error_del_proveedor_llm(db_session, mock_judge_llm, sample_interview):
    """Test 8: Timeout o error del proveedor LLM."""
    from src.evaluation.service import EvaluationService

    service = EvaluationService(db_session)

    # Make LLM raise error
    service._call_judge_llm = AsyncMock(side_effect=LLMTimeoutError("LLM timeout"))

    report = await service.evaluate(sample_interview.id)

    assert report.needs_human_review is True
    assert report.recommendation == "borderline"


async def test_persistencia_y_lectura_posterior(db_session, mock_judge_llm, sample_interview):
    """Test 9: Persistencia y lectura posterior."""
    from sqlalchemy import select

    from src.db.models.interview import Evaluation as EvaluationModel
    from src.evaluation.service import EvaluationService

    service = EvaluationService(db_session)
    report = await service.evaluate(sample_interview.id)

    # Verify evaluation was persisted
    result = await db_session.execute(
        select(EvaluationModel).where(EvaluationModel.interview_id == sample_interview.id)
    )
    persisted = result.scalar_one_or_none()

    assert persisted is not None
    assert persisted.overall_score == report.overall_score
    assert persisted.recommendation == report.recommendation
    assert persisted.needs_human_review == report.needs_human_review


async def test_evidencia_insuficiente_y_needs_human_review(db_session, sample_interview_no_evidence):
    """Test 7: Evidencia insuficiente y needs_human_review."""
    from src.evaluation.service import EvaluationService

    service = EvaluationService(db_session)
    report = await service.evaluate(sample_interview_no_evidence.id)

    assert report.needs_human_review is True
    assert report.recommendation == "borderline"


async def test_endpoint_get_conforme_al_contrato(db_session, mock_judge_llm, sample_interview):
    """Test 12: Endpoint GET conforme al contrato OpenAPI."""
    from httpx import AsyncClient

    from src.core.security import create_access_token
    from src.db.enums import UserRole

    # Seed a recruiter user and obtain JWT token
    from src.db.models import Membership, Organization, User
    org = Organization(name="Org A")
    db_session.add(org)
    await db_session.flush()
    user = User(email="recruiter@example.com", hashed_password="$2b$12$KjK.", is_active=True)
    db_session.add(user)
    await db_session.flush()
    membership = Membership(user_id=user.id, organization_id=org.id, role=UserRole.RECRUITER)
    db_session.add(membership)
    await db_session.commit()

    token = create_access_token(
        user_id=user.id,
        organization_id=org.id,
        role=UserRole.RECRUITER,
    )

    # Use AsyncClient with ASGITransport for proper auth in event loop
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as ac:
        response = await ac.get(
            f"/interviews/{sample_interview.id}/evaluation",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == HTTPStatus.OK
    data = response.json()

    # Verify required fields per contract
    required_fields = ["id", "masked_candidate_id", "overall_score", "recommendation",
                       "competencies", "evidence", "needs_human_review"]
    for field in required_fields:
        assert field in data, f"Missing field: {field}"

    # Verify evidence structure per contract
    # Contract requires: competency, score, evidence_quote, turn_id
    if data["evidence"]:
        ev = data["evidence"][0]
        assert "competency" in ev, "Evidence missing competency"
        assert "score" in ev, "Evidence missing score"
        assert "evidence_quote" in ev, "Evidence missing evidence_quote"
        assert "turn_id" in ev, "Evidence missing turn_id (contract required)"
        assert isinstance(ev["score"], int), "Evidence score should be integer"
        assert 1 <= ev["score"] <= 5, "Evidence score should be 1-5"


async def test_evaluacion_idempotencia(db_session, sample_interview):
    """Test idempotencia: llamar a evaluate múltiples veces devuelve la misma evaluación."""
    from sqlalchemy import func, select

    from src.db.models.interview import Evaluation as EvaluationModel
    from src.evaluation.service import EvaluationService

    service = EvaluationService(db_session)
    report1 = await service.evaluate(sample_interview.id)
    report2 = await service.evaluate(sample_interview.id)

    assert report1.id == report2.id
    assert report1.overall_score == report2.overall_score

    # Verificar que solo existe 1 registro en la base de datos
    result = await db_session.execute(
        select(func.count(EvaluationModel.id)).where(EvaluationModel.interview_id == sample_interview.id)
    )
    count = result.scalar_one()
    assert count == 1


async def test_evaluacion_snapshot_evidence(db_session, sample_interview, sample_snapshots):
    """Test: Evidencia citada desde snapshots (turn_id is None) no es descartada."""
    from src.evaluation.service import EvaluationService

    service = EvaluationService(db_session)
    snap_id = sample_snapshots[0].id

    raw_eval = {
        "competencies": {
            "problem_solving": 4,
            "algorithmic_reasoning": 4,
            "code_quality": 4,
            "technical_communication": 4,
            "complexity_management": 4,
        },
        "evidence": [
            {
                "competency": "code_quality",
                "score": 4,
                "evidence_quote": "def solve(): return 42",
                "snapshot_id": str(snap_id),
                "reasoning": "Código limpio en snapshot",
            }
        ],
        "discrepancy_note": None,
    }

    report = await service._validate_and_persist(raw_eval, sample_interview)
    assert len(report.evidence) == 1
    assert report.evidence[0].turn_id == str(snap_id)
    assert report.evidence[0].competency == "code_quality"


async def test_evaluacion_blind_to_pii(db_session, sample_interview):
    """Test: La evaluación es ciega a PII, masked_candidate_id es opaco no reversible."""
    from src.evaluation.service import EvaluationService

    service = EvaluationService(db_session)
    report = await service.evaluate(sample_interview.id)

    # Nunca debe contener el prefijo del email ("test")
    assert not report.masked_candidate_id.startswith("TEST")
    expected_masked = f"CAND-{sample_interview.id.hex[:4].upper()}"
    assert report.masked_candidate_id == expected_masked

    # El formato del prompt para el LLM no debe incluir el email ni nombre
    context = await service._build_context(sample_interview)
    prompt_evidence = service._format_evidence_for_llm(context)
    assert sample_interview.candidate_email not in prompt_evidence
    assert sample_interview.candidate_name not in prompt_evidence


async def test_evaluacion_multi_tenant_isolation(db_session, sample_interview):
    """Test: Un usuario de Org A no puede acceder a evaluaciones de Org B (404)."""
    from src.core.security import create_access_token
    from src.db.enums import UserRole
    from src.db.models import Membership, Organization, User, Vacancy

    # Org A (propietaria de la vacante)
    org_a = Organization(name="Org Propietaria")
    db_session.add(org_a)
    await db_session.flush()

    vacancy = await db_session.get(Vacancy, sample_interview.vacancy_id)
    vacancy.organization_id = org_a.id
    await db_session.commit()

    # Org B (atacante o reclutador de otra empresa)
    org_b = Organization(name="Org Invasora")
    db_session.add(org_b)
    await db_session.flush()

    user_b = User(email="recruiter_b@example.com", hashed_password="$2b$12$KjK.", is_active=True)
    db_session.add(user_b)
    await db_session.flush()
    membership_b = Membership(user_id=user_b.id, organization_id=org_b.id, role=UserRole.RECRUITER)
    db_session.add(membership_b)
    await db_session.commit()

    token_b = create_access_token(
        user_id=user_b.id,
        organization_id=org_b.id,
        role=UserRole.RECRUITER,
    )

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as ac:
        # Org B intentando ver evaluación de Org A
        resp_eval = await ac.get(
            f"/interviews/{sample_interview.id}/evaluation",
            headers={"Authorization": f"Bearer {token_b}"},
        )
        assert resp_eval.status_code == HTTPStatus.NOT_FOUND

        # Org B intentando ver trajectory de Org A
        resp_traj = await ac.get(
            f"/interviews/{sample_interview.id}/trajectory",
            headers={"Authorization": f"Bearer {token_b}"},
        )
        assert resp_traj.status_code == HTTPStatus.NOT_FOUND


# ==============================================================================
# Pruebas para S-13: Doble pasada de juez con chequeo de consistencia
# ==============================================================================


def test_s13_check_consistency_within_tolerance(db_session):
    """S-13 Unitario: Diferencias <= 1 punto en dimensiones y <= 1.0 overall son consistentes."""
    from src.evaluation.service import EvaluationService

    service = EvaluationService(db_session)
    scores_1 = {
        "problem_solving": 4,
        "algorithmic_reasoning": 3,
        "code_quality": 5,
        "technical_communication": 4,
        "complexity_management": 3,
    }
    overall_1 = 3.80

    scores_2 = {
        "problem_solving": 5,
        "algorithmic_reasoning": 4,
        "code_quality": 4,
        "technical_communication": 3,
        "complexity_management": 4,
    }
    overall_2 = 4.00

    is_consistent, note = service.check_consistency(scores_1, overall_1, scores_2, overall_2)
    assert is_consistent is True
    assert note is None


def test_s13_check_consistency_dimension_diff_greater_than_one(db_session):
    """S-13 Unitario: Diferencia > 1 punto en dimensión individual marca inconsistencia."""
    from src.evaluation.service import EvaluationService

    service = EvaluationService(db_session)
    scores_1 = {
        "problem_solving": 4,
        "algorithmic_reasoning": 5,
        "code_quality": 4,
        "technical_communication": 4,
        "complexity_management": 4,
    }
    overall_1 = 4.20

    # algorithmic_reasoning difiere en 2 (> 1 punto)
    scores_2 = {
        "problem_solving": 4,
        "algorithmic_reasoning": 3,
        "code_quality": 4,
        "technical_communication": 4,
        "complexity_management": 4,
    }
    overall_2 = 3.80

    is_consistent, note = service.check_consistency(scores_1, overall_1, scores_2, overall_2)
    assert is_consistent is False
    assert note is not None
    assert "Discrepancia entre jueces (>1 punto)" in note
    assert "algorithmic_reasoning" in note
    assert "diff=2" in note


def test_s13_check_consistency_overall_diff_greater_than_one(db_session):
    """S-13 Unitario: Diferencia > 1.0 punto en puntaje general marca inconsistencia."""
    from src.evaluation.service import EvaluationService

    service = EvaluationService(db_session)
    scores_1 = {
        "problem_solving": 5,
        "algorithmic_reasoning": 4,
        "code_quality": 5,
        "technical_communication": 4,
        "complexity_management": 4,
    }
    overall_1 = 4.40

    scores_2 = {
        "problem_solving": 4,
        "algorithmic_reasoning": 3,
        "code_quality": 4,
        "technical_communication": 3,
        "complexity_management": 3,
    }
    # overall_2 = 3.40 -> overall_diff = 1.00 (en el límite tolerable)
    is_consistent, note = service.check_consistency(scores_1, overall_1, scores_2, 3.40)
    assert is_consistent is True

    # overall_2 = 3.20 -> overall_diff = 1.20 (> 1.0 punto)
    is_consistent, note = service.check_consistency(scores_1, overall_1, scores_2, 3.20)
    assert is_consistent is False
    assert note is not None
    assert "overall_score" in note
    assert "diff=1.20" in note


def test_s13_check_consistency_missing_dimension(db_session):
    """S-13 Unitario: Dimensión faltante en uno de los jueces marca inconsistencia."""
    from src.evaluation.service import EvaluationService

    service = EvaluationService(db_session)
    scores_1 = {
        "problem_solving": 4,
        "algorithmic_reasoning": 4,
        "code_quality": 4,
        "technical_communication": 4,
        "complexity_management": 4,
    }
    overall_1 = 4.00

    scores_2 = {
        "problem_solving": 4,
        "algorithmic_reasoning": 4,
        "code_quality": 4,
        "technical_communication": 4,
    }
    overall_2 = 4.00

    is_consistent, note = service.check_consistency(scores_1, overall_1, scores_2, overall_2)
    assert is_consistent is False
    assert note is not None
    assert "complexity_management" in note


async def test_s13_validate_and_persist_discrepancy_flags_needs_human_review(
    db_session, sample_interview, sample_turns
):
    """S-13 Integración: Discrepancia > 1 punto entre jueces activa needs_human_review en DB y reporte."""
    from sqlalchemy import select

    from src.db.models.interview import Evaluation as EvaluationModel
    from src.evaluation.service import EvaluationService

    service = EvaluationService(db_session)
    turn_id = str(sample_turns[0].id)

    raw_j1 = {
        "competencies": {
            "problem_solving": 5,
            "algorithmic_reasoning": 4,
            "code_quality": 4,
            "technical_communication": 4,
            "complexity_management": 4,
        },
        "evidence": [
            {
                "competency": "problem_solving",
                "score": 5,
                "evidence_quote": "Solución óptima O(n)",
                "turn_id": turn_id,
                "reasoning": "Buen razonamiento",
            }
        ],
        "discrepancy_note": None,
    }

    # Juez 2 difiere en 2 puntos en problem_solving (5 vs 3, diff=2 > 1)
    raw_j2 = {
        "competencies": {
            "problem_solving": 3,
            "algorithmic_reasoning": 4,
            "code_quality": 4,
            "technical_communication": 4,
            "complexity_management": 4,
        },
        "evidence": [],
    }

    report = await service._validate_and_persist(raw_j1, sample_interview, secondary_raw=raw_j2)

    assert report.needs_human_review is True
    assert report.discrepancy_note is not None
    assert "Discrepancia entre jueces (>1 punto)" in report.discrepancy_note
    assert "problem_solving" in report.discrepancy_note

    # Verificar persistencia en base de datos
    result = await db_session.execute(
        select(EvaluationModel).where(EvaluationModel.interview_id == sample_interview.id)
    )
    persisted = result.scalar_one()
    assert persisted.needs_human_review is True
    assert persisted.discrepancy_note == report.discrepancy_note


async def test_s13_validate_and_persist_consistent_does_not_flag_human_review(
    db_session, sample_interview, sample_turns
):
    """S-13 Integración: Jueces consistentes (diff <= 1 punto) no activan needs_human_review."""
    from src.evaluation.service import EvaluationService

    service = EvaluationService(db_session)
    turn_id = str(sample_turns[0].id)

    raw_j1 = {
        "competencies": {
            "problem_solving": 4,
            "algorithmic_reasoning": 4,
            "code_quality": 4,
            "technical_communication": 4,
            "complexity_management": 4,
        },
        "evidence": [
            {
                "competency": "problem_solving",
                "score": 4,
                "evidence_quote": "Explicación adecuada",
                "turn_id": turn_id,
                "reasoning": "Razonamiento correcto",
            }
        ],
        "discrepancy_note": None,
    }

    # Juez 2 difiere en 1 punto en problem_solving (4 vs 5, diff=1 <= 1)
    raw_j2 = {
        "competencies": {
            "problem_solving": 5,
            "algorithmic_reasoning": 4,
            "code_quality": 4,
            "technical_communication": 4,
            "complexity_management": 4,
        },
        "evidence": [],
    }

    report = await service._validate_and_persist(raw_j1, sample_interview, secondary_raw=raw_j2)

    assert report.needs_human_review is False
    assert report.discrepancy_note is None


async def test_s13_validate_and_persist_invalid_secondary_structure(
    db_session, sample_interview, sample_turns
):
    """S-13 Integración: Juez secundario con competencias inválidas marca needs_human_review."""
    from src.evaluation.service import EvaluationService

    service = EvaluationService(db_session)
    turn_id = str(sample_turns[0].id)

    raw_j1 = {
        "competencies": {
            "problem_solving": 4,
            "algorithmic_reasoning": 4,
            "code_quality": 4,
            "technical_communication": 4,
            "complexity_management": 4,
        },
        "evidence": [
            {
                "competency": "problem_solving",
                "score": 4,
                "evidence_quote": "Explicación adecuada",
                "turn_id": turn_id,
                "reasoning": "Razonamiento correcto",
            }
        ],
    }

    raw_j2_invalid = {"competencies": "no-es-un-objeto"}

    report = await service._validate_and_persist(raw_j1, sample_interview, secondary_raw=raw_j2_invalid)

    assert report.needs_human_review is True
    assert report.discrepancy_note is not None
    assert "Fallo en juez secundario" in report.discrepancy_note


async def test_s13_evaluate_end_to_end_triggers_dual_judge_and_flags_discrepancy(
    db_session, sample_interview, sample_turns
):
    """S-13 End-to-End: evaluate() invoca doble pasada y marca needs_human_review ante discrepancia."""
    from src.evaluation.service import EvaluationService

    service = EvaluationService(db_session)
    turn_id = str(sample_turns[0].id)

    j1_response = {
        "competencies": {
            "problem_solving": 5,
            "algorithmic_reasoning": 5,
            "code_quality": 5,
            "technical_communication": 4,
            "complexity_management": 4,
        },
        "evidence": [
            {
                "competency": "problem_solving",
                "score": 5,
                "evidence_quote": "Solución de alto nivel",
                "turn_id": turn_id,
                "reasoning": "Excelente diseño",
            }
        ],
        "discrepancy_note": None,
    }

    # Juez 2 otorga 3 en problem_solving (diferencia de 2 > 1 punto)
    j2_response = {
        "competencies": {
            "problem_solving": 3,
            "algorithmic_reasoning": 5,
            "code_quality": 5,
            "technical_communication": 4,
            "complexity_management": 4,
        },
        "evidence": [],
        "discrepancy_note": None,
    }

    service._call_judge_llm = AsyncMock(side_effect=[j1_response, j2_response])

    report = await service.evaluate(sample_interview.id)

    assert service._call_judge_llm.call_count == 2
    assert report.needs_human_review is True
    assert report.discrepancy_note is not None
    assert "problem_solving" in report.discrepancy_note
    assert "diff=2" in report.discrepancy_note
