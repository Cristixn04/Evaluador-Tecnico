import asyncio
import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from src.db.enums import Difficulty, Seniority
from src.db.models import Interview, Problem, Vacancy
from src.invitations.service import InvitationService


def _problem(
    *,
    title: str,
    difficulty: Difficulty,
    language: str,
    tags: list[str],
    slug: str,
) -> Problem:
    return Problem(
        id=uuid.uuid5(uuid.UUID("a3f1c8e2-7b54-4d91-9e06-2c5b8f4a1d73"), slug),
        title=title,
        difficulty=difficulty,
        language=language,
        scenario_preview=title,
        tags=tags,
    )


async def _seed_problems(session) -> None:
    # Check if problems already exist to avoid duplicate key errors
    from sqlalchemy import select
    cache_id = uuid.uuid5(uuid.UUID("a3f1c8e2-7b54-4d91-9e06-2c5b8f4a1d73"), "cache")
    breaker_id = uuid.uuid5(uuid.UUID("a3f1c8e2-7b54-4d91-9e06-2c5b8f4a1d73"), "breaker")
    existing = (await session.scalars(select(Problem).where(Problem.id.in_([cache_id, breaker_id])))).all()
    
    if not existing:
        session.add_all(
            [
                Problem(
                    id=cache_id,
                    title="Cache Invalidation",
                    difficulty=Difficulty.MID,
                    language="python",
                    scenario_preview="Cache Invalidation",
                    tags=["python", "cache", "redis"],
                ),
                Problem(
                    id=uuid.uuid5(uuid.UUID("a3f1c8e2-7b54-4d91-9e06-2c5b8f4a1d73"), "breaker"),
                    title="Circuit Breaker",
                    difficulty=Difficulty.SENIOR,
                    language="python",
                    scenario_preview="Circuit Breaker",
                    tags=["python", "resilience", "circuit-breaker"],
                ),
            ]
        )
        await session.flush()


@pytest.mark.asyncio
async def test_concurrent_verify_same_token_creates_single_interview(db_session):
    """Test that concurrent verify requests for the same token create only one interview."""
    from src.main import app

    # Seed problems first
    await _seed_problems(db_session)

    # Setup: create vacancy and invitation
    vacancy = Vacancy(
        title="Concurrency Test",
        raw_description="Test",
        role_category="backend",
        seniority=Seniority.MID,
        profile={
            "required_skills": ["python", "cache", "redis"],
            "preferred_skills": [],
            "primary_language": "python",
            "focus_areas": [],
        },
    )
    db_session.add(vacancy)
    await db_session.flush()

    inv_service = InvitationService(db_session)
    _invitation, token = await inv_service.create(
        vacancy=vacancy,
        candidate_name="Concurrent Candidate",
        candidate_email="concurrent@example.com",
        candidate_phone=None,
    )
    await db_session.commit()

    async def verify_request():
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            return await client.get(
                "/sessions/verify",
                headers={"Authorization": f"Bearer {token}"},
            )

    # Launch 10 concurrent requests
    responses = await asyncio.gather(*[verify_request() for _ in range(10)])

    # All should succeed
    assert all(r.status_code == 200 for r in responses), [
        r.text for r in responses if r.status_code != 200
    ]

    # All should return the SAME interview_id
    interview_ids = {r.json()["session_id"] for r in responses}
    assert len(interview_ids) == 1, f"Expected 1 interview, got {len(interview_ids)}: {interview_ids}"

    # Database should have exactly 1 Interview
    count = len((await db_session.scalars(select(Interview))).all())
    assert count == 1, f"Expected 1 interview in DB, got {count}"

    # The interview should have the correct status and phase
    interview = (await db_session.scalars(select(Interview))).first()
    assert interview is not None
    assert interview.status.value == "pending"
    assert interview.phase.value == "INTRO"
    assert interview.access_token is None  # New interviews have NULL access_token


@pytest.mark.asyncio
async def test_sequential_verify_reuses_interview(db_session):
    """Test that sequential verify requests reuse the same interview."""
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from src.db.models import Invitation
    from src.main import app

    # Seed problems first
    await _seed_problems(db_session)

    vacancy = Vacancy(
        title="Sequential Test",
        raw_description="Test",
        role_category="backend",
        seniority=Seniority.MID,
        profile={
            "required_skills": ["python", "cache", "redis"],
            "preferred_skills": [],
            "primary_language": "python",
            "focus_areas": [],
        },
    )
    db_session.add(vacancy)
    await db_session.flush()

    inv_service = InvitationService(db_session)
    invitation, token = await inv_service.create(
        vacancy=vacancy,
        candidate_name="Sequential Candidate",
        candidate_email="sequential@example.com",
        candidate_phone=None,
    )
    await db_session.commit()
    
    # Debug: verify invitation exists in DB using a NEW session from fixture's engine
    engine = db_session.bind
    session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_maker() as new_session:
        result = await new_session.execute(select(Invitation).where(Invitation.id == invitation.id))
        inv = result.scalar_one()
        print(f"DEBUG TEST: Invitation in NEW session: id={inv.id}, selector={inv.token_selector}, used_at={inv.used_at}")
    
    # Debug: also check with test's session
    result = await db_session.execute(select(Invitation).where(Invitation.id == invitation.id))
    inv = result.scalar_one()
    print(f"DEBUG TEST: Invitation in test session: id={inv.id}, selector={inv.token_selector}, used_at={inv.used_at}")
    
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # First request
        r1 = await client.get("/sessions/verify", headers={"Authorization": f"Bearer {token}"})
        print(f"First request status: {r1.status_code}, body: {r1.text}")
        assert r1.status_code == 200, f"Expected 200, got {r1.status_code}: {r1.text}"
        id1 = r1.json()["session_id"]

        # Second request
        r2 = await client.get("/sessions/verify", headers={"Authorization": f"Bearer {token}"})
        print(f"Second request status: {r2.status_code}, body: {r2.text}")
        assert r2.status_code == 200
        id2 = r2.json()["session_id"]

        # Should be the same interview
        assert id1 == id2

    # DB should have exactly 1 interview
    count = len((await db_session.scalars(select(Interview))).all())
    assert count == 1