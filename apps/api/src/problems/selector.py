from collections.abc import Sequence
from hashlib import sha256

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.telemetry import tool_telemetry
from src.db.enums import Difficulty, Seniority
from src.db.models import Problem
from src.problems.schemas import ProblemSpec


def difficulty_for_seniority(seniority: Seniority) -> Difficulty:
    if seniority is Seniority.LEAD:
        return Difficulty.SENIOR
    return Difficulty(seniority.value)


def _normalize_skills(values: Sequence[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for item in values:
        skill = item.strip().casefold()
        if not skill or skill in seen:
            continue
        seen.add(skill)
        normalized.append(skill)
    return normalized


def _preferred_overlap(tags: Sequence[str], preferred: Sequence[str]) -> int:
    tag_set = {tag.casefold() for tag in tags}
    return sum(1 for skill in preferred if skill in tag_set)


class ProblemSelector:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def search(
        self,
        *,
        skills: Sequence[str] | None = None,
        seniority: Seniority | None = None,
        language: str | None = None,
        preferred_skills: Sequence[str] | None = None,
    ) -> list[Problem]:
        stmt = self._filtered_statement(skills=skills, seniority=seniority, language=language)
        result = await self._session.scalars(stmt)
        matches = list(result.all())
        if not matches:
            count = await self._session.scalar(select(func.count(Problem.id)))
            if count == 0:
                from src.problems.loader import DEFAULT_CATALOG_DIR, ProblemLoader
                specs = ProblemLoader(DEFAULT_CATALOG_DIR).load()
                for spec in specs:
                    self._session.add(spec_to_problem(spec))
                await self._session.flush()
                result = await self._session.scalars(stmt)
                matches = list(result.all())

        preferred = _normalize_skills(preferred_skills or ())
        if not preferred:
            return matches
        return sorted(
            matches,
            key=lambda problem: (
                -_preferred_overlap(problem.tags, preferred),
                problem.title,
                str(problem.id),
            ),
        )

    async def select_one(
        self,
        *,
        skills: Sequence[str] | None = None,
        seniority: Seniority | None = None,
        language: str | None = None,
        preferred_skills: Sequence[str] | None = None,
        seed: str | None = None,
    ) -> Problem | None:
        telemetry = tool_telemetry("problem_selector", "select_one")
        telemetry.start(
            seniority=seniority.value if seniority else "any",
            language=language or "any",
            skills_count=len(skills) if skills else 0,
        )
        try:
            matches = await self.search(
                skills=skills,
                seniority=seniority,
                language=language,
                preferred_skills=preferred_skills,
            )
            if not matches:
                telemetry.error("No problem matches criteria")
                return None
            if seed is None:
                selected = matches[0]
            else:
                digest = sha256(seed.encode("utf-8")).digest()
                index = int.from_bytes(digest[:8], "big") % len(matches)
                selected = matches[index]

            telemetry.success(
                problem_id=str(selected.id)[:8],
                difficulty=selected.difficulty.value if hasattr(selected.difficulty, "value") else str(selected.difficulty),
                title=selected.title,
            )
            return selected
        except Exception as exc:
            telemetry.error(exc)
            raise

    def _filtered_statement(
        self,
        *,
        skills: Sequence[str] | None,
        seniority: Seniority | None,
        language: str | None,
    ) -> Select[Problem]:
        stmt = select(Problem)
        required = _normalize_skills(skills or ())
        if language is not None:
            cleaned = language.strip().casefold()
            if cleaned:
                stmt = stmt.where(func.lower(Problem.language) == cleaned)
        if seniority is not None:
            stmt = stmt.where(Problem.difficulty == difficulty_for_seniority(seniority))
        if required:
            stmt = stmt.where(Problem.tags.overlap(required))
        return stmt.order_by(Problem.title.asc(), Problem.id.asc())


def spec_to_problem(spec: ProblemSpec) -> Problem:
    return Problem(
        id=spec.persistence_id(),
        title=spec.title,
        difficulty=spec.difficulty,
        language=spec.primary_language,
        scenario_preview=spec.statement,
        tags=list(spec.tags),
    )
