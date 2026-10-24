from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, ClassVar

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.security import verify_password
from src.db.enums import InterviewPhase, InterviewStatus
from src.db.models import Interview, Invitation, Vacancy
from src.interview.exceptions import InterviewPhaseTransitionError
from src.invitations.exceptions import (
    InvitationAlreadyUsedError,
    InvitationError,
    InvitationExpiredError,
    InvitationNotFoundError,
)

if TYPE_CHECKING:
    from src.problems.selector import ProblemSelector


class InterviewService:
    # Valid transitions based on the contract
    VALID_TRANSITIONS: ClassVar[dict[InterviewPhase, list[InterviewPhase]]] = {
        InterviewPhase.INTRO: [InterviewPhase.PROBLEM],
        InterviewPhase.PROBLEM: [InterviewPhase.CLARIFY],
        InterviewPhase.CLARIFY: [InterviewPhase.DESIGN],
        InterviewPhase.DESIGN: [InterviewPhase.CODING],
        InterviewPhase.CODING: [InterviewPhase.PROBE],
        InterviewPhase.PROBE: [InterviewPhase.WRAPUP],
        InterviewPhase.WRAPUP: [InterviewPhase.EVALUATE],
        InterviewPhase.EVALUATE: [],
    }

    MAX_CREATE_RETRIES = 3

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_or_create_from_invitation(
        self,
        token: str,
        *,
        problem_selector: ProblemSelector | None = None,
    ) -> Interview:
        """Get existing interview or create a new one from an invitation (idempotent).

        This method is safe for concurrent access - it uses row-level locking
        to ensure only one interview is created per invitation even under
        high concurrency.
        """
        selector = token[:16]

        for attempt in range(self.MAX_CREATE_RETRIES):
            # Lock invitation row FIRST by selector, then verify token and create interview atomically
            result = await self._session.execute(
                select(Invitation)
                .where(Invitation.token_selector == selector)
                .with_for_update()
            )
            locked_invitation = result.scalar_one_or_none()

            if locked_invitation is None:
                # No invitation with this selector - try legacy fallback (without lock)
                # Legacy invitations don't have token_selector, so we can't lock them
                # This is a rare case for old invitations
                from src.invitations.service import InvitationService
                invitation_service = InvitationService(self._session)
                invitation = await invitation_service.verify_token(token)
                # For legacy, we can't use SELECT FOR UPDATE, so fall back to old logic
                return await self._get_or_create_from_legacy_invitation(invitation, token)

            # Verify token hash within the locked transaction
            if not verify_password(token, locked_invitation.token_hash):
                raise InvitationNotFoundError("Invalid invitation token")

            # Re-validate invitation state after lock
            if locked_invitation.used_at is not None:
                raise InvitationAlreadyUsedError("Invitation has already been used")
            if locked_invitation.expires_at < datetime.now(UTC):
                raise InvitationExpiredError("Invitation has expired")

            # Fast path: interview already exists (check after lock)
            if locked_invitation.interview_id is not None:
                interview = await self._session.get(Interview, locked_invitation.interview_id)
                if interview is not None:
                    return interview

            # Create new interview
            interview = await self._create_interview(locked_invitation, problem_selector)

            try:
                # Link invitation to interview in same transaction
                # DO NOT set used_at here - invitation remains reusable for reconnection (per DR-4)
                locked_invitation.interview_id = interview.id
                await self._session.commit()  # Commit -> UNIQUE constraint check
                return interview
            except IntegrityError as e:
                await self._session.rollback()
                if "uq_invitations_interview_id" in str(e.orig):
                    # Race lost: another request created the interview -> retry
                    continue
                raise

        raise RuntimeError("Max retries exceeded creating interview")

    async def _get_or_create_from_legacy_invitation(
        self,
        invitation: Invitation,
        token: str,
    ) -> Interview:
        """Handle legacy invitations without token_selector (no row locking possible)."""
        # This is a fallback for old invitations - race condition is possible but rare
        if invitation.interview_id is not None:
            interview = await self._session.get(Interview, invitation.interview_id)
            if interview is not None:
                return interview

        interview = await self._create_interview(invitation, None)
        invitation.interview_id = interview.id
        await self._session.commit()
        return interview

    async def _create_interview(
        self,
        invitation: Invitation,
        problem_selector: ProblemSelector | None = None,
    ) -> Interview:
        vacancy = await self._session.get(Vacancy, invitation.vacancy_id)
        if vacancy is None:
            raise InvitationError("Vacancy not found")

        # Select a problem for the interview
        if problem_selector is None:
            from src.problems.selector import ProblemSelector
            problem_selector = ProblemSelector(self._session)
        problem = None
        if vacancy.profile is not None:
            required_skills = vacancy.profile.get("required_skills", [])
            preferred_skills = vacancy.profile.get("preferred_skills", [])
            primary_language = vacancy.profile.get("primary_language", "python")
            seniority = vacancy.seniority

            problem = await problem_selector.select_one(
                skills=required_skills,
                seniority=seniority,
                language=primary_language,
                preferred_skills=preferred_skills,
                seed=str(vacancy.id),
            )

        interview = Interview(
            vacancy_id=invitation.vacancy_id,
            problem_id=problem.id if problem else None,
            candidate_email=invitation.candidate_email,
            candidate_name=invitation.candidate_name,
            access_token=None,  # Legacy: NULL for new interviews
            status=InterviewStatus.PENDING,
            phase=InterviewPhase.INTRO,
            expires_at=invitation.expires_at,
        )
        self._session.add(interview)
        await self._session.flush()  # Generate ID without commit
        return interview

    def validate_transition(self, current_phase: InterviewPhase, target_phase: InterviewPhase) -> bool:
        """Validate if a phase transition is allowed."""
        allowed = self.VALID_TRANSITIONS.get(current_phase, [])
        return target_phase in allowed

    async def transition_phase(
        self,
        interview: Interview,
        target_phase: InterviewPhase,
        *,
        reason: str | None = None,
    ) -> Interview:
        """Transition interview to a new phase."""
        if not self.validate_transition(interview.phase, target_phase):
            raise InterviewPhaseTransitionError(
                f"Invalid phase transition from {interview.phase} to {target_phase}"
            )

        interview.phase = target_phase

        # Update status based on phase
        if target_phase == InterviewPhase.INTRO:
            interview.status = InterviewStatus.PENDING
        elif target_phase in (
            InterviewPhase.PROBLEM,
            InterviewPhase.CLARIFY,
            InterviewPhase.DESIGN,
            InterviewPhase.CODING,
            InterviewPhase.PROBE,
            InterviewPhase.WRAPUP,
        ):
            interview.status = InterviewStatus.IN_PROGRESS
        elif target_phase == InterviewPhase.EVALUATE:
            interview.status = InterviewStatus.EVALUATED

        await self._session.flush()

        # Persist a turn for the phase transition
        from src.db.enums import TurnSpeaker
        from src.db.models import Turn

        turn = Turn(
            interview_id=interview.id,
            speaker=TurnSpeaker.AGENT,
            content=f"Phase transitioned to {target_phase.value}" + (f": {reason}" if reason else ""),
        )
        self._session.add(turn)
        await self._session.flush()

        return interview

    def get_available_transitions(self, current_phase: InterviewPhase) -> list[InterviewPhase]:
        """Get available transitions from the current phase."""
        return self.VALID_TRANSITIONS.get(current_phase, []).copy()