import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.enums import Difficulty, Seniority
from src.db.models import Problem
from src.problems.loader import DEFAULT_CATALOG_DIR, ProblemLoader
from src.problems.selector import ProblemSelector, difficulty_for_seniority, spec_to_problem


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


async def _seed(session: AsyncSession) -> None:
    session.add_all(
        [
            _problem(
                title="Cache Invalidation",
                difficulty=Difficulty.MID,
                language="python",
                tags=["python", "cache", "redis"],
                slug="cache",
            ),
            _problem(
                title="Circuit Breaker",
                difficulty=Difficulty.SENIOR,
                language="python",
                tags=["python", "resilience", "circuit-breaker"],
                slug="breaker",
            ),
            _problem(
                title="Feature Flags",
                difficulty=Difficulty.JUNIOR,
                language="javascript",
                tags=["javascript", "feature-flags", "hashing"],
                slug="flags",
            ),
            _problem(
                title="SQL Schema Migration",
                difficulty=Difficulty.MID,
                language="sql",
                tags=["sql", "migrations", "postgresql"],
                slug="sql",
            ),
        ]
    )
    await session.flush()


@pytest.mark.asyncio
async def test_filter_by_language(db_session: AsyncSession) -> None:
    await _seed(db_session)
    selector = ProblemSelector(db_session)
    matches = await selector.search(language="Python")
    assert [item.title for item in matches] == ["Cache Invalidation", "Circuit Breaker"]


@pytest.mark.asyncio
async def test_filter_by_seniority_maps_to_difficulty(db_session: AsyncSession) -> None:
    await _seed(db_session)
    selector = ProblemSelector(db_session)
    matches = await selector.search(seniority=Seniority.JUNIOR)
    assert [item.title for item in matches] == ["Feature Flags"]
    lead = await selector.search(seniority=Seniority.LEAD)
    assert [item.title for item in lead] == ["Circuit Breaker"]
    assert difficulty_for_seniority(Seniority.LEAD) is Difficulty.SENIOR


@pytest.mark.asyncio
async def test_filter_by_required_skills_overlap(db_session: AsyncSession) -> None:
    await _seed(db_session)
    selector = ProblemSelector(db_session)
    matches = await selector.search(skills=["Redis", "cache"])
    assert [item.title for item in matches] == ["Cache Invalidation"]


@pytest.mark.asyncio
async def test_combined_filters(db_session: AsyncSession) -> None:
    await _seed(db_session)
    selector = ProblemSelector(db_session)
    matches = await selector.search(
        skills=["python"],
        seniority=Seniority.MID,
        language="python",
    )
    assert [item.title for item in matches] == ["Cache Invalidation"]


@pytest.mark.asyncio
async def test_no_matches_returns_empty(db_session: AsyncSession) -> None:
    await _seed(db_session)
    selector = ProblemSelector(db_session)
    matches = await selector.search(language="go")
    assert matches == []
    assert await selector.select_one(language="go") is None


@pytest.mark.asyncio
async def test_preferred_skills_rank_without_excluding(db_session: AsyncSession) -> None:
    await _seed(db_session)
    selector = ProblemSelector(db_session)
    matches = await selector.search(language="python", preferred_skills=["resilience"])
    assert [item.title for item in matches] == ["Circuit Breaker", "Cache Invalidation"]


@pytest.mark.asyncio
async def test_select_one_is_deterministic_without_seed(db_session: AsyncSession) -> None:
    await _seed(db_session)
    selector = ProblemSelector(db_session)
    first = await selector.select_one(language="python")
    second = await selector.select_one(language="python")
    assert first is not None and second is not None
    assert first.id == second.id
    assert first.title == "Cache Invalidation"


@pytest.mark.asyncio
async def test_select_one_seed_is_reproducible(db_session: AsyncSession) -> None:
    await _seed(db_session)
    selector = ProblemSelector(db_session)
    first = await selector.select_one(language="python", seed="vacancy-1")
    second = await selector.select_one(language="python", seed="vacancy-1")
    assert first is not None and second is not None
    assert first.id == second.id


@pytest.mark.asyncio
async def test_problems_are_global_without_tenant_column(db_session: AsyncSession) -> None:
    await _seed(db_session)
    assert not hasattr(Problem, "organization_id")
    matches = await ProblemSelector(db_session).search()
    assert len(matches) == 4


@pytest.mark.asyncio
async def test_spec_to_problem_uses_stable_uuid() -> None:
    spec = ProblemLoader(DEFAULT_CATALOG_DIR).get("feature-flags")
    problem = spec_to_problem(spec)
    assert problem.id == spec.persistence_id()
    assert problem.language == "javascript"
    assert problem.difficulty is Difficulty.JUNIOR
    assert "feature-flags" in problem.tags
