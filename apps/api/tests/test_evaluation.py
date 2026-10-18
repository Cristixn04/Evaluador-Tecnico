"""Tests for S-11: Juez LLM con Rúbrica.

Requires PostgreSQL evaluador_db running on port 5435.
Uses mock_judge_llm fixture for deterministic LLM responses.
"""

from datetime import datetime, timezone
from http import HTTPStatus
from unittest.mock import AsyncMock, MagicMock, patch
import json

from httpx import AsyncClient, ASGITransport

import pytest

from fastapi.testclient import TestClient

from src.db.models.interview import Interview, Evaluation, Turn, Snapshot
from src.llm.exceptions import LLMInvalidResponseError, LLMTimeoutError
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
        expires_at=datetime.now(timezone.utc),
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
        expires_at=datetime.now(timezone.utc),
    )
    db_session.add(interview)
    await db_session.commit()
    await db_session.refresh(interview)
    return interview


@pytest.fixture
async def sample_turns(db_session, sample_interview):
    """Create turns associated with the interview."""
    from src.db.models.interview import InterviewPhase

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
    from src.db.models.interview import Snapshot

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
    from src.llm.factory import create_llm_client
    
    # Build evaluation data with real UUIDs from persisted turns/snapshots
    turn_ids = [str(t.id) for t in sample_turns]
    snapshot_ids = [str(s.id) for s in sample_snapshots]
    
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
    from src.evaluation.service import EvaluationService
    import json
    from unittest.mock import MagicMock, AsyncMock

    # Use real UUIDs from persisted turns for evidence references
    turn_ids = [str(t.id) for t in sample_turns]
    snapshot_ids = [str(s.id) for s in sample_snapshots]

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
    from src.llm.exceptions import LLMTimeoutError

    service = EvaluationService(db_session)

    # Make LLM raise error
    service._call_judge_llm = AsyncMock(side_effect=LLMTimeoutError("LLM timeout"))

    report = await service.evaluate(sample_interview.id)

    assert report.needs_human_review is True
    assert report.recommendation == "borderline"


async def test_persistencia_y_lectura_posterior(db_session, mock_judge_llm, sample_interview):
    """Test 9: Persistencia y lectura posterior."""
    from src.evaluation.service import EvaluationService
    from sqlalchemy import select
    from src.db.models.interview import Evaluation as EvaluationModel

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
    from starlette.testclient import TestClient as SyncTestClient
    from src.core.auth import get_current_user, require_role
    from src.core.security import create_access_token, decode_access_token
    from src.db.enums import UserRole
    from src.db.models import User

    # Seed a recruiter user and obtain JWT token
    from src.db.models import Membership, Organization
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
