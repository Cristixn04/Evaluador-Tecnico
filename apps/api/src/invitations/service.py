from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.security import hash_password, verify_password
from src.db.enums import InterviewStatus
from src.db.models import Interview, Invitation, Vacancy
from src.invitations.exceptions import (
    InvitationAlreadyUsedError,
    InvitationExpiredError,
    InvitationNotFoundError,
)
from src.problems.selector import ProblemSelector


class InvitationService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # Maximum number of legacy invitations to check in fallback (safety limit)
    _MAX_LEGACY_CHECK = 100

    async def create(
        self,
        *,
        vacancy: Vacancy,
        candidate_name: str,
        candidate_email: str,
        candidate_phone: str | None,
        expires_in_hours: int = 48,
    ) -> tuple[Invitation, str]:
        """Create a new invitation and return the invitation and the plain access token."""
        access_token = self._generate_access_token()
        token_hash = hash_password(access_token)
        token_selector = access_token[:16]  # First 16 chars as selector for O(1) lookup

        expires_at = datetime.now(UTC) + timedelta(hours=expires_in_hours)

        invitation = Invitation(
            vacancy_id=vacancy.id,
            candidate_name=candidate_name,
            candidate_email=candidate_email,
            candidate_phone=candidate_phone,
            token_hash=token_hash,
            token_selector=token_selector,
            expires_at=expires_at,
        )
        self._session.add(invitation)
        await self._session.flush()
        return invitation, access_token

    async def verify_token(self, token: str) -> Invitation:
        """Verify an invitation token and return the invitation if valid."""
        # First, try O(1) lookup by selector (for new invitations)
        selector = token[:16]
        result = await self._session.execute(
            select(Invitation).where(Invitation.token_selector == selector)
        )
        invitation = result.scalar_one_or_none()

        if invitation is not None:
            if verify_password(token, invitation.token_hash):
                return self._validate_invitation(invitation)
            # Selector matched but hash didn't - invalid token
            raise InvitationNotFoundError("Invalid invitation token")

        # Fallback: legacy invitations without token_selector (safety limited)
        result = await self._session.execute(
            select(Invitation)
            .where(Invitation.token_selector.is_(None))
            .limit(self._MAX_LEGACY_CHECK)
        )
        for invitation in result.scalars():
            if verify_password(token, invitation.token_hash):
                return self._validate_invitation(invitation)

        raise InvitationNotFoundError("Invalid invitation token")

    def _validate_invitation(self, invitation: Invitation) -> Invitation:
        """Validate invitation state and return if valid."""
        if invitation.used_at is not None:
            raise InvitationAlreadyUsedError("Invitation has already been used")
        if invitation.expires_at < datetime.now(UTC):
            raise InvitationExpiredError("Invitation has expired")
        return invitation

    async def mark_used(self, invitation: Invitation) -> None:
        """Mark an invitation as used."""
        invitation.used_at = datetime.now(UTC)
        await self._session.flush()

    def _generate_access_token(self) -> str:
        """Generate a high-entropy access token."""
        return secrets.token_urlsafe(32)


class InterviewService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_or_create_from_invitation(
        self,
        invitation: Invitation,
        *,
        problem_selector: ProblemSelector | None = None,
    ) -> Interview:
        """Get existing interview or create a new one from an invitation (idempotent)."""
        # If invitation already has an interview, return it
        if invitation.interview_id is not None:
            interview = await self._session.get(Interview, invitation.interview_id)
            if interview is not None:
                return interview

        # Otherwise, create a new interview
        vacancy = await self._session.get(Vacancy, invitation.vacancy_id)
        if vacancy is None:
            raise ValueError("Vacancy not found")

        # Select a problem for the interview
        problem = None
        if problem_selector is not None and vacancy.profile is not None:
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
            access_token=invitation.token_hash,  # Store hash for reference, not used for auth
            status=InterviewStatus.PENDING,
            expires_at=invitation.expires_at,
        )
        self._session.add(interview)
        await self._session.flush()

        # Link the invitation to the interview
        invitation.interview_id = interview.id
        await self._session.flush()

        return interview