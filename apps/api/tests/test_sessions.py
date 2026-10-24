"""HTTP integration tests for Candidate Sessions and Invitations."""

import uuid
from datetime import timedelta

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.security import create_access_token, hash_password
from src.db.enums import Seniority
from src.db.models import Organization, Problem, User, Vacancy
from src.db.models.auth import Membership
from src.main import app


async def _seed_test_problem(db_session: AsyncSession) -> Problem:
    problem = Problem(
        id=uuid.uuid4(),
        title="Cache Invalidation Problem",
        difficulty="mid",
        language="python",
        scenario_preview="Implement an LRU cache with TTL.",
        tags=["python", "cache"],
    )
    db_session.add(problem)
    await db_session.commit()
    await db_session.refresh(problem)
    return problem


@pytest.fixture
async def recruiter_auth(db_session: AsyncSession):
    org = Organization(id=uuid.uuid4(), name="Acme Corp")
    db_session.add(org)
    await db_session.flush()

    user = User(
        id=uuid.uuid4(),
        email="recruiter@acme.com",
        hashed_password=hash_password("RecruiterPass123!"),
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()

    membership = Membership(
        id=uuid.uuid4(),
        user_id=user.id,
        organization_id=org.id,
        role="admin",
    )
    db_session.add(membership)

    vacancy = Vacancy(
        id=uuid.uuid4(),
        organization_id=org.id,
        title="Senior Backend Engineer",
        raw_description="Looking for Python and caching experts.",
        role_category="backend",
        seniority=Seniority.MID,
        profile={
            "required_skills": ["python", "cache"],
            "preferred_skills": [],
            "primary_language": "python",
            "focus_areas": [],
        },
    )
    db_session.add(vacancy)
    await db_session.commit()

    from src.db.enums import UserRole

    token = create_access_token(
        user_id=user.id,
        organization_id=org.id,
        role=UserRole.ADMIN,
        expires_delta=timedelta(hours=1),
    )
    return {"token": token, "org": org, "user": user, "vacancy": vacancy}


@pytest.mark.asyncio
async def test_invitation_creation_and_session_verify_contract(db_session: AsyncSession, recruiter_auth):
    """Test full flow: POST invitation -> GET /sessions/verify returns session_id, ws_token, ws_url."""
    await _seed_test_problem(db_session)
    vacancy = recruiter_auth["vacancy"]
    recruiter_token = recruiter_auth["token"]

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. POST /vacancies/{vacancy_id}/invitations
        inv_resp = await client.post(
            f"/vacancies/{vacancy.id}/invitations",
            headers={"Authorization": f"Bearer {recruiter_token}"},
            json={
                "candidate_name": "Alice Candidate",
                "candidate_email": "alice@candidate.com",
            },
        )
        assert inv_resp.status_code == 201, inv_resp.text
        inv_data = inv_resp.json()
        assert "access_token" in inv_data
        candidate_token = inv_data["access_token"]
        assert inv_data["masked_candidate_id"].startswith("CAND-")

        # 2. GET /sessions/verify with candidate token
        verify_resp = await client.get(
            "/sessions/verify",
            headers={"Authorization": f"Bearer {candidate_token}"},
        )
        assert verify_resp.status_code == 200, verify_resp.text
        session_data = verify_resp.json()

        # Contract assertion: session_id, ws_token, ws_url
        assert "session_id" in session_data
        assert "ws_token" in session_data
        assert "ws_url" in session_data
        assert session_data["masked_candidate_id"].startswith("CAND-")
        assert session_data["current_phase"] == "INTRO"
        assert session_data["status"] == "pending"
        assert session_data["problem"]["title"] == "Cache Invalidation Problem"

        # Verify ws_url format
        session_id = session_data["session_id"]
        assert session_data["ws_url"] == f"ws://test/ws/interview/{session_id}"
