import inspect
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from typing import get_args, get_origin

import pytest
from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from src.core.config import settings
from src.db.base import Base
from src.db.enums import Difficulty, InterviewStatus, Seniority, TurnSpeaker
from src.db.models import Interview, Problem, Snapshot, Turn, Vacancy
from src.db.session import get_db


def test_database_url_uses_asyncpg() -> None:
    assert settings.DATABASE_URL.startswith("postgresql+asyncpg://")


def test_models_are_registered_in_metadata() -> None:
    tables = set(Base.metadata.tables)
    assert tables == {"vacancies", "problems", "interviews", "turns", "snapshots"}


def test_get_db_is_async_generator() -> None:
    assert inspect.isasyncgenfunction(get_db)
    annotation = get_db.__annotations__["return"]
    assert get_origin(annotation) is AsyncGenerator
    assert get_args(annotation)[0] is AsyncSession


@pytest.mark.asyncio
async def test_postgres_connectivity() -> None:
    engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)
    try:
        async with engine.connect() as connection:
            await connection.execute(select(1))
    except (OSError, OperationalError) as exc:
        pytest.skip(f"NO EJECUTADO — PostgreSQL no disponible: {exc}")
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_persist_vacancy_and_interview_graph(db_session: AsyncSession) -> None:
    vacancy = Vacancy(
        title="Backend Python",
        raw_description="Buscamos backend con FastAPI y PostgreSQL.",
        role_category="backend",
        seniority=Seniority.MID,
        profile={
            "required_skills": ["python", "fastapi"],
            "preferred_skills": ["postgresql"],
            "primary_language": "python",
            "focus_areas": ["apis"],
        },
    )
    problem = Problem(
        title="Conciliación PSE",
        difficulty=Difficulty.MID,
        language="python",
        scenario_preview="Conciliar pagos PSE contra un extracto bancario.",
        tags=["fintech", "python"],
    )
    db_session.add_all([vacancy, problem])
    await db_session.flush()

    interview = Interview(
        vacancy_id=vacancy.id,
        problem_id=problem.id,
        candidate_email="candidato@example.com",
        candidate_name="Candidato Prueba",
        access_token="test-access-token",
        status=InterviewStatus.IN_PROGRESS,
        expires_at=datetime.now(UTC) + timedelta(hours=2),
    )
    db_session.add(interview)
    await db_session.flush()

    db_session.add_all(
        [
            Turn(
                interview_id=interview.id,
                speaker=TurnSpeaker.AGENT,
                content="Describe tu enfoque.",
            ),
            Snapshot(
                interview_id=interview.id,
                code="def solve():\n    return 1\n",
            ),
        ]
    )
    await db_session.flush()

    stored_vacancy = await db_session.get(Vacancy, vacancy.id)
    stored_interview = await db_session.get(Interview, interview.id)
    turns = (await db_session.scalars(select(Turn).where(Turn.interview_id == interview.id))).all()
    snapshots = (
        await db_session.scalars(select(Snapshot).where(Snapshot.interview_id == interview.id))
    ).all()

    assert stored_vacancy is not None
    assert stored_vacancy.title == "Backend Python"
    assert stored_vacancy.profile is not None
    assert stored_vacancy.profile["primary_language"] == "python"
    assert stored_interview is not None
    assert stored_interview.vacancy_id == vacancy.id
    assert stored_interview.problem_id == problem.id
    assert stored_interview.status is InterviewStatus.IN_PROGRESS
    assert len(turns) == 1
    assert turns[0].speaker is TurnSpeaker.AGENT
    assert len(snapshots) == 1
    assert "def solve" in snapshots[0].code
