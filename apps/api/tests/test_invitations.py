import secrets
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.enums import Seniority
from src.db.models import Invitation, Vacancy
from src.invitations.exceptions import (
    InvitationAlreadyUsedError,
    InvitationExpiredError,
    InvitationNotFoundError,
)
from src.invitations.service import InvitationService


class TestInvitationService:
    @pytest.fixture
    async def vacancy(self, db_session: AsyncSession) -> Vacancy:
        vacancy = Vacancy(
            title="Test Vacancy",
            raw_description="Test description",
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
    async def invitation(self, db_session: AsyncSession, vacancy: Vacancy) -> tuple[Invitation, str]:
        service = InvitationService(db_session)
        invitation, token = await service.create(
            vacancy=vacancy,
            candidate_name="Test Candidate",
            candidate_email="test@example.com",
            candidate_phone=None,
        )
        await db_session.commit()
        return invitation, token

    @pytest.mark.asyncio
    async def test_create_invitation_returns_token_and_hash(
        self, db_session: AsyncSession, vacancy: Vacancy
    ) -> None:
        service = InvitationService(db_session)
        invitation, token = await service.create(
            vacancy=vacancy,
            candidate_name="Test Candidate",
            candidate_email="test@example.com",
            candidate_phone=None,
        )

        assert invitation.token_hash != token
        assert invitation.token_selector == token[:16]
        assert len(invitation.token_selector) == 16

    @pytest.mark.asyncio
    async def test_verify_valid_token_returns_invitation(
        self, db_session: AsyncSession, invitation: tuple[Invitation, str]
    ) -> None:
        invitation_obj, token = invitation
        service = InvitationService(db_session)

        result = await service.verify_token(token)

        assert result.id == invitation_obj.id
        assert result.token_selector == token[:16]

    @pytest.mark.asyncio
    async def test_verify_invalid_token_raises_not_found(
        self, db_session: AsyncSession
    ) -> None:
        service = InvitationService(db_session)

        with pytest.raises(InvitationNotFoundError):
            await service.verify_token("invalid-token")

    @pytest.mark.asyncio
    async def test_verify_token_with_wrong_hash_raises_not_found(
        self, db_session: AsyncSession, invitation: tuple[Invitation, str]
    ) -> None:
        invitation_obj, _ = invitation
        service = InvitationService(db_session)

        # Use selector but wrong token
        wrong_token = "x" * 32
        wrong_token = (invitation_obj.token_selector or "") + wrong_token[16:]

        with pytest.raises(InvitationNotFoundError):
            await service.verify_token(wrong_token)

    @pytest.mark.asyncio
    async def test_verify_expired_token_raises_expired(
        self, db_session: AsyncSession, vacancy: Vacancy
    ) -> None:
        service = InvitationService(db_session)
        _invitation, token = await service.create(
            vacancy=vacancy,
            candidate_name="Test",
            candidate_email="test@example.com",
            candidate_phone=None,
            expires_in_hours=-1,  # Already expired
        )
        await db_session.commit()

        with pytest.raises(InvitationExpiredError):
            await service.verify_token(token)

    @pytest.mark.asyncio
    async def test_verify_used_token_raises_already_used(
        self, db_session: AsyncSession, invitation: tuple[Invitation, str]
    ) -> None:
        invitation_obj, token = invitation
        service = InvitationService(db_session)

        # First verification succeeds
        await service.verify_token(token)

        # Mark as used
        await service.mark_used(invitation_obj)
        await db_session.commit()

        # Second verification should fail
        with pytest.raises(InvitationAlreadyUsedError):
            await service.verify_token(token)

    @pytest.mark.asyncio
    async def test_verify_legacy_invitation_without_selector(
        self, db_session: AsyncSession, vacancy: Vacancy
    ) -> None:
        """Test fallback verification for legacy invitations without selector."""
        # Create invitation directly without token_selector
        token = secrets.token_urlsafe(24)
        token_hash = hash_password(token)
        invitation = Invitation(
            vacancy_id=vacancy.id,
            candidate_name="Legacy Candidate",
            candidate_email="legacy@example.com",
            token_hash=token_hash,
            token_selector=None,  # Legacy: no selector
            expires_at=datetime.now(UTC) + timedelta(hours=48),
        )
        db_session.add(invitation)
        await db_session.commit()

        service = InvitationService(db_session)

        # Should still verify via legacy fallback
        result = await service.verify_token(token)
        assert result.id == invitation.id
        assert result.token_selector is None

    @pytest.mark.asyncio
    async def test_verify_selector_mismatch_raises_not_found(
        self, db_session: AsyncSession, invitation: tuple[Invitation, str]
    ) -> None:
        _invitation_obj, token = invitation
        service = InvitationService(db_session)

        # Different selector but same length
        other_token = "y" * 16 + token[16:]

        with pytest.raises(InvitationNotFoundError):
            await service.verify_token(other_token)


# Need to import these for the legacy test
from src.core.security import hash_password