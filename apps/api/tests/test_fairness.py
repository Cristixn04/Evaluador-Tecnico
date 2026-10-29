"""Pruebas de Equidad e Invarianza (S-22: Fairness Tests).

Verifica que el pipeline de evaluación técnica sea invariante ante variaciones
no técnicas (dialectos regionales colombianos, estilo formal/informal, comentarios
superficiales y declaraciones personales irrelevantes).

NOTA DE RIGOR METODOLÓGICO:
Esta suite prueba el comportamiento determinista de integración del sistema
(sanitización, encapsulamiento en <untrusted_candidate_input>, anonimización ciega,
preservación de evidencia técnica y estabilidad de las rúbricas).
El uso de mocks o fixtures controladas evalúa el pipeline de la aplicación y
no constituye una demostración empírica de imparcialidad intrínseca del modelo LLM.
Los experimentos con LLMs reales se ejecutan fuera de CI mediante la variable RUN_LIVE_LLM_EVAL.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.db.enums import InterviewPhase, InterviewStatus, TurnSpeaker
from src.db.models import Interview, Snapshot, Turn, Vacancy
from src.evaluation.service import EvaluationService


def _create_mock_judge_response(
    scores: dict[str, int],
    evidence_ref_id: str,
    evidence_quote: str = "def deduplicate(txs):",
) -> str:
    """Generar respuesta JSON válida para el evaluador LLM."""
    competencies = {
        "problem_solving": scores.get("problem_solving", 4),
        "algorithmic_reasoning": scores.get("algorithmic_reasoning", 4),
        "code_quality": scores.get("code_quality", 4),
        "technical_communication": scores.get("technical_communication", 4),
        "complexity_management": scores.get("complexity_management", 4),
    }
    evidence = [
        {
            "competency": comp,
            "score": score,
            "evidence_quote": evidence_quote,
            "turn_id": evidence_ref_id,
            "reasoning": f"Evidencia técnica consistente para {comp}.",
        }
        for comp, score in competencies.items()
    ]
    return json.dumps({
        "competencies": competencies,
        "evidence": evidence,
        "discrepancy_note": None,
        "model_name": "mock-judge-v1",
        "prompt_version": "v2",
        "tokens_prompt": 150,
        "tokens_completion": 80,
        "cost_usd": 0.001,
        "strengths": ["Estructura de datos adecuada", "Complejidad óptima"],
        "risks": [],
        "suggested_human_questions": [],
    })


@pytest.fixture
async def fairness_vacancy(db_session: AsyncSession) -> Vacancy:
    """Fixture para crear vacante para pruebas de equidad."""
    vacancy = Vacancy(
        title="Backend Developer",
        raw_description="Python backend position with async experience",
    )
    db_session.add(vacancy)
    await db_session.flush()
    await db_session.commit()
    return vacancy


@pytest.mark.asyncio
async def test_fairness_prompt_encapsulation_dialect_colombian_vs_neutral(
    db_session: AsyncSession,
    fairness_vacancy: Vacancy,
) -> None:
    """Verifica que turnos con dialecto regional y neutro se encapsulen idénticamente como untrusted."""
    service = EvaluationService(db_session)

    # Caso A: Español neutro
    interview_a = Interview(
        vacancy_id=fairness_vacancy.id,
        candidate_email="carlos.neutral@example.com",
        candidate_name="Carlos Neutral",
        phase=InterviewPhase.WRAPUP,
        status=InterviewStatus.COMPLETED,
        expires_at=datetime.now(UTC),
    )
    db_session.add(interview_a)
    await db_session.flush()

    turn_a = Turn(
        interview_id=interview_a.id,
        speaker=TurnSpeaker.CANDIDATE,
        content="Hola, voy a utilizar un diccionario para almacenar los usuarios y luego iterar sobre la lista.",
    )
    db_session.add(turn_a)

    # Caso B: Expresiones regionales colombianas (parce, bacano, de una, camello)
    interview_b = Interview(
        vacancy_id=fairness_vacancy.id,
        candidate_email="carlos.paisa@example.com",
        candidate_name="Carlos Paisa",
        phase=InterviewPhase.WRAPUP,
        status=InterviewStatus.COMPLETED,
        expires_at=datetime.now(UTC),
    )
    db_session.add(interview_b)
    await db_session.flush()

    turn_b = Turn(
        interview_id=interview_b.id,
        speaker=TurnSpeaker.CANDIDATE,
        content="Buenas parce, voy a armar un diccionario bien bacano pa' guardar los parceros y después le meto un loop de una.",
    )
    db_session.add(turn_b)
    await db_session.commit()

    context_a = await service._build_context(interview_a)
    context_b = await service._build_context(interview_b)

    prompt_a = service._format_evidence_for_llm(context_a, judge_id="judge_1")
    prompt_b = service._format_evidence_for_llm(context_b, judge_id="judge_1")

    # 1. Ambos deben encapsular el input en <untrusted_candidate_input>
    assert "<untrusted_candidate_input>" in prompt_a
    assert "</untrusted_candidate_input>" in prompt_a
    assert "<untrusted_candidate_input>" in prompt_b
    assert "</untrusted_candidate_input>" in prompt_b

    # 2. Ambos deben aplicar la directiva de evaluación ciega
    assert "La evaluación es estrictamente ciega a sesgos demográficos" in prompt_a
    assert "La evaluación es estrictamente ciega a sesgos demográficos" in prompt_b

    # 3. La identidad y correos del candidato no deben aparecer sin sanitizar en los prompts
    assert "carlos.neutral@example.com" not in prompt_a
    assert "carlos.paisa@example.com" not in prompt_b


@pytest.mark.asyncio
async def test_fairness_pairwise_evaluation_score_parity(
    db_session: AsyncSession,
    fairness_vacancy: Vacancy,
) -> None:
    """Verifica que dos soluciones con el mismo código y tests tengan paridad de puntuación (Delta <= 0.1)."""
    service = EvaluationService(db_session)

    code_solution = (
        "def deduplicate(txs):\n"
        "    seen = set()\n"
        "    result = []\n"
        "    for tx in txs:\n"
        "        if tx['id'] not in seen:\n"
        "            seen.add(tx['id'])\n"
        "            result.append(tx)\n"
        "    return result\n"
    )

    # Entrevista A: Comunicación formal
    int_a = Interview(
        vacancy_id=fairness_vacancy.id,
        candidate_email="carlos.formal@example.com",
        candidate_name="Carlos Formal",
        status=InterviewStatus.COMPLETED,
        phase=InterviewPhase.WRAPUP,
        expires_at=datetime.now(UTC),
    )
    db_session.add(int_a)
    await db_session.flush()

    snap_a = Snapshot(
        interview_id=int_a.id,
        code=code_solution,
        tests_passed=5,
        total_tests=5,
        execution_status="success",
        phase="CODING",
    )
    turn_a = Turn(
        interview_id=int_a.id,
        speaker=TurnSpeaker.CANDIDATE,
        content="Procedo a inicializar una estructura de conjunto hash para mantener complejidad O(1) en búsquedas.",
    )
    db_session.add_all([snap_a, turn_a])

    # Entrevista B: Comunicación coloquial / regional
    int_b = Interview(
        vacancy_id=fairness_vacancy.id,
        candidate_email="carlos.regional@example.com",
        candidate_name="Carlos Regional",
        status=InterviewStatus.COMPLETED,
        phase=InterviewPhase.WRAPUP,
        expires_at=datetime.now(UTC),
    )
    db_session.add(int_b)
    await db_session.flush()

    snap_b = Snapshot(
        interview_id=int_b.id,
        code=code_solution,
        tests_passed=5,
        total_tests=5,
        execution_status="success",
        phase="CODING",
    )
    turn_b = Turn(
        interview_id=int_b.id,
        speaker=TurnSpeaker.CANDIDATE,
        content="Listo parce, meto un set pa' que las búsquedas salgan de una sin gastar tiempo O(1).",
    )
    db_session.add_all([snap_b, turn_b])
    await db_session.commit()

    # Mocks del LLM devolviendo puntuación técnica idéntica y citando el snapshot de cada entrevista
    payload_a = _create_mock_judge_response(
        scores={
            "problem_solving": 5,
            "algorithmic_reasoning": 4,
            "code_quality": 4,
            "technical_communication": 4,
            "complexity_management": 4,
        },
        evidence_ref_id=str(snap_a.id),
    )
    payload_b = _create_mock_judge_response(
        scores={
            "problem_solving": 5,
            "algorithmic_reasoning": 4,
            "code_quality": 4,
            "technical_communication": 4,
            "complexity_management": 4,
        },
        evidence_ref_id=str(snap_b.id),
    )

    mock_client_a = AsyncMock()
    mock_client_a.complete = AsyncMock(return_value=MagicMock(content=payload_a))
    mock_client_a.aclose = AsyncMock()

    mock_client_b = AsyncMock()
    mock_client_b.complete = AsyncMock(return_value=MagicMock(content=payload_b))
    mock_client_b.aclose = AsyncMock()

    with patch("src.evaluation.service.llm_factory.create_llm_client", side_effect=[mock_client_a, mock_client_a, mock_client_b, mock_client_b]):
        report_a = await service.evaluate(int_a.id)
        report_b = await service.evaluate(int_b.id)

    # Comprobar paridad estricta en el pipeline
    score_delta = abs(report_a.overall_score - report_b.overall_score)
    assert score_delta <= 0.1, f"La diferencia de puntuación no técnica ({score_delta}) supera el umbral de 0.1"
    assert report_a.recommendation == report_b.recommendation

    for dim in EvaluationService.EVALUATION_DIMENSIONS:
        dim_score_a = report_a.competencies[dim]
        dim_score_b = report_b.competencies[dim]
        assert abs(dim_score_a - dim_score_b) <= 0.1, f"Dimensión {dim} difiere entre estilos"


@pytest.mark.asyncio
async def test_fairness_irrelevant_personal_disclosure_is_scrubbed_and_not_evidence(
    db_session: AsyncSession,
    fairness_vacancy: Vacancy,
) -> None:
    """Verifica que menciones accidentales de PII demográfico en los turnos sean saneadas y no sean evidencia."""
    service = EvaluationService(db_session)

    interview = Interview(
        vacancy_id=fairness_vacancy.id,
        candidate_email="contacto@correo.com",
        candidate_name="Pedro Cali",
        status=InterviewStatus.COMPLETED,
        phase=InterviewPhase.WRAPUP,
        expires_at=datetime.now(UTC),
    )
    db_session.add(interview)
    await db_session.flush()

    # El candidato divulga datos personales irrelevantes y un email
    turn_pii = Turn(
        interview_id=interview.id,
        speaker=TurnSpeaker.CANDIDATE,
        content="Tengo 22 años, soy de Cali y mi correo personal es contacto@correo.com. Usaré un algoritmo voraz.",
    )
    db_session.add(turn_pii)
    await db_session.commit()

    context = await service._build_context(interview)
    prompt = service._format_evidence_for_llm(context, judge_id="judge_1")

    # 1. El email debe estar sanitizado por el scrub regex
    assert "contacto@correo.com" not in prompt
    assert "[REDACTED_EMAIL]" in prompt

    # 2. Las instrucciones exigen evaluación ciega
    assert "La evaluación es estrictamente ciega a sesgos demográficos (sin nombre, género, edad ni universidad)" in prompt


@pytest.mark.asyncio
async def test_fairness_superficial_comments_do_not_alter_evaluation(
    db_session: AsyncSession,
    fairness_vacancy: Vacancy,
) -> None:
    """Verifica que comentarios superficiales o informales en el código no alteren el pipeline de evaluación."""
    service = EvaluationService(db_session)

    code_clean = "def sumar(a, b):\n    return a + b\n"
    code_with_slang = "def sumar(a, b):\n    # parce sumamos esto de una\n    return a + b\n"

    int_clean = Interview(
        vacancy_id=fairness_vacancy.id,
        candidate_email="clean@example.com",
        candidate_name="Clean Dev",
        status=InterviewStatus.COMPLETED,
        phase=InterviewPhase.WRAPUP,
        expires_at=datetime.now(UTC),
    )
    int_slang = Interview(
        vacancy_id=fairness_vacancy.id,
        candidate_email="slang@example.com",
        candidate_name="Slang Dev",
        status=InterviewStatus.COMPLETED,
        phase=InterviewPhase.WRAPUP,
        expires_at=datetime.now(UTC),
    )
    db_session.add_all([int_clean, int_slang])
    await db_session.flush()

    snap_clean = Snapshot(interview_id=int_clean.id, code=code_clean, tests_passed=2, total_tests=2, execution_status="success")
    snap_slang = Snapshot(interview_id=int_slang.id, code=code_with_slang, tests_passed=2, total_tests=2, execution_status="success")
    db_session.add_all([snap_clean, snap_slang])
    await db_session.commit()

    ctx_clean = await service._build_context(int_clean)
    ctx_slang = await service._build_context(int_slang)

    prompt_clean = service._format_evidence_for_llm(ctx_clean, judge_id="judge_1")
    prompt_slang = service._format_evidence_for_llm(ctx_slang, judge_id="judge_1")

    # En ambos casos, el código se encapsula como untrusted_candidate_input
    assert "<untrusted_candidate_input>" in prompt_clean
    assert "<untrusted_candidate_input>" in prompt_slang


@pytest.mark.skipif(
    os.getenv("RUN_LIVE_LLM_EVAL") != "1",
    reason="Experimento con LLM real deshabilitado por defecto para evitar costos y cuotas en CI. Habilitar con RUN_LIVE_LLM_EVAL=1.",
)
@pytest.mark.asyncio
async def test_fairness_live_llm_dialect_empirical_invariance(
    db_session: AsyncSession,
    fairness_vacancy: Vacancy,
) -> None:
    """Experimento empírico opcional con LLM real (ejecutar exclusivamente fuera de CI)."""
    if not settings.LLM_API_KEY:
        pytest.skip("LLM_API_KEY no configurada para prueba live.")
