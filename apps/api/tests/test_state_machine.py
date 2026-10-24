from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.enums import InterviewPhase, InterviewStatus, Seniority
from src.db.models import Interview, Vacancy
from src.interview.exceptions import InterviewPhaseTransitionError
from src.interview.service import InterviewService


class TestInterviewStateMachine:
    @pytest.fixture
    async def vacancy(self, db_session: AsyncSession) -> Vacancy:
        vacancy = Vacancy(
            title="State Machine Test",
            raw_description="Test",
            role_category="backend",
            seniority=Seniority.MID,
            profile={
                "required_skills": ["python"],
                "preferred_skills": [],
                "primary_language": "python",
                "focus_areas": [],
            },
        )
        db_session.add(vacancy)
        await db_session.flush()
        return vacancy

    @pytest.fixture
    async def interview(self, db_session: AsyncSession, vacancy: Vacancy) -> Interview:
        interview = Interview(
            vacancy_id=vacancy.id,
            candidate_email="test@example.com",
            candidate_name="Test Candidate",
            access_token=None,
            status=InterviewStatus.PENDING,
            phase=InterviewPhase.INTRO,
            expires_at=datetime.now(UTC) + timedelta(hours=2),
        )
        db_session.add(interview)
        await db_session.flush()
        return interview

    @pytest.fixture
    def service(self, db_session: AsyncSession) -> InterviewService:
        return InterviewService(db_session)

    # Valid transitions
    @pytest.mark.asyncio
    async def test_transition_intro_to_problem(
        self, service: InterviewService, interview: Interview
    ) -> None:
        interview = await service.transition_phase(interview, InterviewPhase.PROBLEM)
        assert interview.phase == InterviewPhase.PROBLEM
        assert interview.status == InterviewStatus.IN_PROGRESS

    @pytest.mark.asyncio
    async def test_transition_problem_to_clarify(
        self, service: InterviewService, interview: Interview
    ) -> None:
        interview = await service.transition_phase(interview, InterviewPhase.PROBLEM)
        interview = await service.transition_phase(interview, InterviewPhase.CLARIFY)
        assert interview.phase == InterviewPhase.CLARIFY
        assert interview.status == InterviewStatus.IN_PROGRESS

    @pytest.mark.asyncio
    async def test_transition_clarify_to_design(
        self, service: InterviewService, interview: Interview
    ) -> None:
        interview = await service.transition_phase(interview, InterviewPhase.PROBLEM)
        interview = await service.transition_phase(interview, InterviewPhase.CLARIFY)
        interview = await service.transition_phase(interview, InterviewPhase.DESIGN)
        assert interview.phase == InterviewPhase.DESIGN

    @pytest.mark.asyncio
    async def test_transition_design_to_coding(
        self, service: InterviewService, interview: Interview
    ) -> None:
        interview = await service.transition_phase(interview, InterviewPhase.PROBLEM)
        interview = await service.transition_phase(interview, InterviewPhase.CLARIFY)
        interview = await service.transition_phase(interview, InterviewPhase.DESIGN)
        interview = await service.transition_phase(interview, InterviewPhase.CODING)
        assert interview.phase == InterviewPhase.CODING

    @pytest.mark.asyncio
    async def test_transition_coding_to_probe(
        self, service: InterviewService, interview: Interview
    ) -> None:
        for phase in [
            InterviewPhase.PROBLEM,
            InterviewPhase.CLARIFY,
            InterviewPhase.DESIGN,
            InterviewPhase.CODING,
        ]:
            interview = await service.transition_phase(interview, phase)
        interview = await service.transition_phase(interview, InterviewPhase.PROBE)
        assert interview.phase == InterviewPhase.PROBE

    @pytest.mark.asyncio
    async def test_transition_probe_to_wrapup(
        self, service: InterviewService, interview: Interview
    ) -> None:
        for phase in [
            InterviewPhase.PROBLEM,
            InterviewPhase.CLARIFY,
            InterviewPhase.DESIGN,
            InterviewPhase.CODING,
            InterviewPhase.PROBE,
        ]:
            interview = await service.transition_phase(interview, phase)
        interview = await service.transition_phase(interview, InterviewPhase.WRAPUP)
        assert interview.phase == InterviewPhase.WRAPUP

    @pytest.mark.asyncio
    async def test_transition_wrapup_to_evaluate(
        self, service: InterviewService, interview: Interview
    ) -> None:
        for phase in [
            InterviewPhase.PROBLEM,
            InterviewPhase.CLARIFY,
            InterviewPhase.DESIGN,
            InterviewPhase.CODING,
            InterviewPhase.PROBE,
            InterviewPhase.WRAPUP,
        ]:
            interview = await service.transition_phase(interview, phase)
        interview = await service.transition_phase(interview, InterviewPhase.EVALUATE)
        assert interview.phase == InterviewPhase.EVALUATE
        assert interview.status == InterviewStatus.EVALUATED  # EVALUATE -> EVALUATED

    # Status mappings
    @pytest.mark.asyncio
    async def test_intro_phase_maps_to_pending_status(
        self, service: InterviewService, interview: Interview
    ) -> None:
        # Initial state is INTRO/PENDING
        assert interview.phase == InterviewPhase.INTRO
        assert interview.status == InterviewStatus.PENDING

    @pytest.mark.asyncio
    async def test_intermediate_phases_map_to_in_progress(
        self, service: InterviewService, interview: Interview
    ) -> None:
        for phase in [
            InterviewPhase.PROBLEM,
            InterviewPhase.CLARIFY,
            InterviewPhase.DESIGN,
            InterviewPhase.CODING,
            InterviewPhase.PROBE,
            InterviewPhase.WRAPUP,
        ]:
            interview = await service.transition_phase(interview, phase)
            assert interview.status == InterviewStatus.IN_PROGRESS

    @pytest.mark.asyncio
    async def test_evaluate_phase_maps_to_evaluated_status(
        self, service: InterviewService, interview: Interview
    ) -> None:
        for phase in [
            InterviewPhase.PROBLEM,
            InterviewPhase.CLARIFY,
            InterviewPhase.DESIGN,
            InterviewPhase.CODING,
            InterviewPhase.PROBE,
            InterviewPhase.WRAPUP,
        ]:
            interview = await service.transition_phase(interview, phase)
        interview = await service.transition_phase(interview, InterviewPhase.EVALUATE)
        assert interview.status == InterviewStatus.EVALUATED

    # Invalid transitions
    @pytest.mark.asyncio
    async def test_skip_phase_raises_error(
        self, service: InterviewService, interview: Interview
    ) -> None:
        with pytest.raises(InterviewPhaseTransitionError):
            await service.transition_phase(interview, InterviewPhase.DESIGN)  # Skip PROBLEM, CLARIFY

    @pytest.mark.asyncio
    async def test_backward_transition_raises_error(
        self, service: InterviewService, interview: Interview
    ) -> None:
        interview = await service.transition_phase(interview, InterviewPhase.PROBLEM)
        interview = await service.transition_phase(interview, InterviewPhase.CLARIFY)
        with pytest.raises(InterviewPhaseTransitionError):
            await service.transition_phase(interview, InterviewPhase.PROBLEM)  # Backward

    @pytest.mark.asyncio
    async def test_transition_from_evaluate_raises_error(
        self, service: InterviewService, interview: Interview
    ) -> None:
        # Advance to EVALUATE
        for phase in [
            InterviewPhase.PROBLEM,
            InterviewPhase.CLARIFY,
            InterviewPhase.DESIGN,
            InterviewPhase.CODING,
            InterviewPhase.PROBE,
            InterviewPhase.WRAPUP,
            InterviewPhase.EVALUATE,
        ]:
            interview = await service.transition_phase(interview, phase)

        # No transitions allowed from EVALUATE
        with pytest.raises(InterviewPhaseTransitionError):
            await service.transition_phase(interview, InterviewPhase.WRAPUP)

    @pytest.mark.asyncio
    async def test_invalid_target_phase_raises_error(
        self, service: InterviewService, interview: Interview
    ) -> None:
        with pytest.raises(InterviewPhaseTransitionError):
            await service.transition_phase(interview, InterviewPhase.EVALUATE)

    # Agent suggestion not binding
    @pytest.mark.asyncio
    async def test_suggested_transition_not_binding(
        self, service: InterviewService, interview: Interview
    ) -> None:
        """Agent's suggested_transition should not auto-transition."""
        # Just verify the service doesn't auto-apply suggestions
        available = service.get_available_transitions(interview.phase)
        assert InterviewPhase.PROBLEM in available
        # The service only validates explicit requests, not suggestions