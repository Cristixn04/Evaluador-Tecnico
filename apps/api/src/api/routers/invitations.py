from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.schemas.invitations import CreateInvitationRequest, InvitationResponse
from src.core.auth import AuthenticatedPrincipal, get_current_user
from src.core.config import settings
from src.db.models import Vacancy
from src.db.session import get_db
from src.invitations.service import InvitationService

router = APIRouter(prefix="/vacancies", tags=["Vacancies"])


def _masked_candidate_id(invitation_id: UUID) -> str:
    return f"CAND-{invitation_id.hex[:4].upper()}"


def _access_url(invitation_id: UUID) -> str:
    base = settings.API_V1_STR.replace("/api/v1", "")
    return f"{base}/interview/{invitation_id}"


@router.post("/{vacancy_id}/invitations", response_model=InvitationResponse, status_code=status.HTTP_201_CREATED)
async def create_invitation(
    vacancy_id: UUID,
    payload: CreateInvitationRequest,
    principal: AuthenticatedPrincipal = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> InvitationResponse:
    result = await session.execute(select(Vacancy).where(Vacancy.id == vacancy_id))
    vacancy = result.scalar_one_or_none()
    if vacancy is None or vacancy.organization_id != principal.organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vacancy not found")

    invitation_service = InvitationService(session)
    invitation, access_token = await invitation_service.create(
        vacancy=vacancy,
        candidate_name=payload.candidate_name,
        candidate_email=payload.candidate_email,
        candidate_phone=payload.candidate_phone,
    )

    return InvitationResponse(
        invitation_id=str(invitation.id),
        masked_candidate_id=_masked_candidate_id(invitation.id),
        access_url=_access_url(invitation.id),
        access_token=access_token,
        expires_at=invitation.expires_at,
    )