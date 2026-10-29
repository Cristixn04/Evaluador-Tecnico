from datetime import UTC, datetime, timedelta

import pytest
from httpx import ASGITransport, AsyncClient

from src.core.security import create_access_token, hash_password
from src.db.enums import InterviewPhase, InterviewStatus, Seniority, TurnSpeaker, UserRole
from src.db.models import (
    Interview,
    Invitation,
    Membership,
    Organization,
    User,
    Vacancy,
)
from src.db.models.interview import Snapshot, Turn
from src.main import app


@pytest.mark.asyncio
async def test_privacy_policy():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/privacy/policy")
        assert response.status_code == 200
        data = response.json()
        assert "Ley 1581" in data["regulatory_framework"]
        assert len(data["rights"]) >= 3
        assert data["guarantees"]["blind_evaluation"] is True


@pytest.mark.asyncio
async def test_revoke_consent_nonexistent_token():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/privacy/consent/revoke",
            json={"invitation_token": "nonexistent_token_123456789"},
        )
        assert response.status_code == 404


@pytest.mark.asyncio
async def test_revoke_consent_valid_invitation(db_session):
    vacancy = Vacancy(
        title="Privacy Test Vacancy",
        role_category="Backend",
        seniority=Seniority.MID,
        raw_description="Pruebas de Habeas Data",
        profile={"required_skills": ["Python"]},
    )
    db_session.add(vacancy)
    await db_session.flush()

    raw_token = "A1B2C3D4E5F6G7H8" + "secret"
    invitation = Invitation(
        vacancy_id=vacancy.id,
        candidate_name="Candidato Privacidad",
        candidate_email="candidato_privacidad@test.com",
        token_hash="dummy_hash",
        token_selector=raw_token[:16],
        expires_at=datetime.now(UTC) + timedelta(days=7),
    )
    db_session.add(invitation)
    await db_session.flush()

    interview = Interview(
        vacancy_id=vacancy.id,
        candidate_email="candidato@test.com",
        candidate_name="Candidato Test",
        expires_at=datetime.now(UTC) + timedelta(hours=2),
        status=InterviewStatus.IN_PROGRESS,
        phase=InterviewPhase.CODING,
    )
    db_session.add(interview)
    await db_session.flush()

    invitation.interview_id = interview.id
    await db_session.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/privacy/consent/revoke",
            json={"invitation_token": raw_token, "reason": "Decisión voluntaria del candidato"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "revoked"

    # Verificar que el status de la entrevista pasó a CANCELLED
    await db_session.refresh(interview)
    assert interview.status == InterviewStatus.CANCELLED


@pytest.mark.asyncio
async def test_delete_candidate_data(db_session):
    org = Organization(name="Privacy Test Org")
    db_session.add(org)
    await db_session.flush()

    user = User(
        email="privacy_admin@test.com",
        hashed_password=hash_password("secret123"),
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()

    membership = Membership(
        user_id=user.id,
        organization_id=org.id,
        role=UserRole.ADMIN,
    )
    db_session.add(membership)
    await db_session.flush()

    token = create_access_token(
        user_id=user.id,
        organization_id=org.id,
        role=UserRole.ADMIN,
    )
    auth_headers = {"Authorization": f"Bearer {token}"}

    vacancy = Vacancy(
        title="Deletion Test Vacancy",
        role_category="Backend",
        seniority=Seniority.SENIOR,
        raw_description="Pruebas de supresión de datos",
        profile={"required_skills": ["Python"]},
    )
    db_session.add(vacancy)
    await db_session.flush()

    interview = Interview(
        vacancy_id=vacancy.id,
        candidate_email="candidato@test.com",
        candidate_name="Candidato Test",
        expires_at=datetime.now(UTC) + timedelta(hours=2),
        status=InterviewStatus.COMPLETED,
        phase=InterviewPhase.EVALUATE,
    )
    db_session.add(interview)
    await db_session.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.delete(
            f"/privacy/candidates/{interview.id}",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "deleted"

    await db_session.refresh(interview)
    assert interview.status == InterviewStatus.CANCELLED


@pytest.mark.asyncio
async def test_strict_anonymization_no_pii_in_evaluation_context(db_session):
    """S-19: Cero PII en el contexto enviado a los jueces LLM (nombre, correo, edad, género)."""
    from src.evaluation.service import EvaluationService, _generate_masked_candidate_id

    vacancy = Vacancy(
        title="Privacy Vacancy",
        role_category="Backend",
        seniority=Seniority.SENIOR,
        raw_description="Prueba de anonimización estricta",
    )
    db_session.add(vacancy)
    await db_session.flush()

    # Candidato con datos personales sensibles
    candidate_name = "María Fernanda Rodríguez"
    candidate_email = "maria.rodriguez@universidad.edu.co"
    interview = Interview(
        vacancy_id=vacancy.id,
        candidate_name=candidate_name,
        candidate_email=candidate_email,
        expires_at=datetime.now(UTC) + timedelta(hours=2),
        status=InterviewStatus.COMPLETED,
        phase=InterviewPhase.EVALUATE,
    )
    db_session.add(interview)
    await db_session.flush()

    turn1 = Turn(
        interview_id=interview.id,
        speaker=TurnSpeaker.CANDIDATE,
        content=f"Hola, mi correo personal es {candidate_email} y mi solución usa un hash map.",
    )
    db_session.add(turn1)
    await db_session.commit()

    service = EvaluationService(db_session)
    context = await service._build_context(interview)

    # 1. El contexto de datos brutos no debe contener los atributos personales del candidato
    assert "candidate_name" not in context
    assert "candidate_email" not in context

    # 2. El texto formateado para el LLM no debe contener datos personales
    formatted_prompt = service._format_evidence_for_llm(context)

    assert candidate_name not in formatted_prompt
    assert candidate_email not in formatted_prompt
    assert "[REDACTED_EMAIL]" in formatted_prompt
    assert "universidad.edu.co" not in formatted_prompt
    # Solo identificadores de formato opaco
    assert f"CAND-{interview.id.hex[:4].upper()}" in _generate_masked_candidate_id(interview)


@pytest.mark.asyncio
async def test_llm_client_complete_payload_has_zero_candidate_pii(db_session):
    """S-19: Inspecciona el payload exacto de llm_client.complete en evaluate_interview confirmando ausencia total de PII."""
    import json
    from typing import Any
    from unittest.mock import AsyncMock, MagicMock, patch

    from src.evaluation.service import EvaluationService, _generate_masked_candidate_id

    vacancy = Vacancy(
        title="Privacy Vacancy Payload",
        role_category="Backend",
        seniority=Seniority.SENIOR,
        raw_description="Prueba estricta de payload hacia LLM",
    )
    db_session.add(vacancy)
    await db_session.flush()

    candidate_name = "Carlos Alberto Mendoza"
    candidate_email = "carlos.mendoza@unal.edu.co"
    interview = Interview(
        vacancy_id=vacancy.id,
        candidate_name=candidate_name,
        candidate_email=candidate_email,
        expires_at=datetime.now(UTC) + timedelta(hours=2),
        status=InterviewStatus.COMPLETED,
        phase=InterviewPhase.EVALUATE,
    )
    db_session.add(interview)
    await db_session.flush()

    turn1 = Turn(
        interview_id=interview.id,
        speaker=TurnSpeaker.CANDIDATE,
        content=f"Hola, mi nombre es {candidate_name} y mi correo es {candidate_email}. Tengo 28 años y soy de Colombia.",
    )
    db_session.add(turn1)

    snap1 = Snapshot(
        interview_id=interview.id,
        phase="CODING",
        code=f"# Autor: {candidate_name} <{candidate_email}>\ndef solve(n):\n    return n * 2\n",
        reason="run",
        execution_status="success",
        tests_passed=3,
        total_tests=3,
    )
    db_session.add(snap1)
    await db_session.commit()

    captured_messages: list[Any] = []

    mock_response = {
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
                "evidence_quote": "solve",
                "turn_id": str(snap1.id),
                "reasoning": "Bien estructurado",
            }
        ],
        "overall_score": 4.0,
        "recommendation": "hire",
        "needs_human_review": False,
    }

    mock_client = AsyncMock()

    async def mock_complete(messages):
        captured_messages.extend(messages)
        return MagicMock(
            content=json.dumps(mock_response),
            usage=MagicMock(prompt_tokens=100, completion_tokens=50),
            model="test-judge",
        )

    mock_client.complete = mock_complete
    mock_client.aclose = AsyncMock()

    with patch("src.llm.factory.create_llm_client", return_value=mock_client):
        service = EvaluationService(db_session)
        report = await service.evaluate(interview.id)

    assert report is not None
    assert len(captured_messages) > 0

    all_payload_text = " ".join(msg.content for msg in captured_messages)

    # 1. PII del candidato NO debe aparecer en el payload del LLM
    assert candidate_name not in all_payload_text
    assert candidate_email not in all_payload_text
    assert "carlos.mendoza" not in all_payload_text
    assert "unal.edu.co" not in all_payload_text

    # 2. El email y el nombre en código y en turno deben haber sido redactados
    assert "[REDACTED_EMAIL]" in all_payload_text
    assert "[REDACTED_PII]" in all_payload_text

    # 3. Solo debe aparecer el identificador enmascarado
    masked_id = _generate_masked_candidate_id(interview)
    assert report.masked_candidate_id == masked_id
