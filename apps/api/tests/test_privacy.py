from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from src.core.security import create_access_token, hash_password
from src.db.enums import InterviewPhase, InterviewStatus, Seniority, UserRole
from src.db.models import Interview, Invitation, Membership, Organization, User, Vacancy
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
