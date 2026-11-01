from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.schemas.interview import InterviewSummary
from src.core.auth import AuthenticatedPrincipal, get_current_user, require_organization
from src.db.models import Organization, Vacancy
from src.db.models.interview import Evaluation, Interview
from src.db.session import get_db

router = APIRouter(prefix="/organizations", tags=["Organizations"])


@router.get(
    "/{id}/interviews",
    response_model=list[InterviewSummary],
    operation_id="listOrganizationInterviews",
    summary="Listar entrevistas de una organización para el panel de reclutamiento",
)
async def list_organization_interviews(
    id: str,
    principal: AuthenticatedPrincipal = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> list[InterviewSummary]:
    """Listar entrevistas de una organización para el panel de reclutamiento.

    Retorna las entrevistas asociadas a las vacantes de la organización especificada,
    incluyendo su estado y puntuaciones si ya fueron evaluadas.
    La información es ciega a datos personales del candidato (PII aislada).
    """
    try:
        org_id = UUID(id)
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found",
        )

    org = await session.get(Organization, org_id)
    if org is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found",
        )

    require_organization(org_id, principal)

    query = (
        select(
            Interview.id,
            Interview.status,
            Interview.created_at,
            Vacancy.title.label("vacancy_title"),
            Evaluation.overall_score,
            Evaluation.recommendation,
        )
        .join(Vacancy, Interview.vacancy_id == Vacancy.id)
        .outerjoin(Evaluation, Evaluation.interview_id == Interview.id)
        .where(Vacancy.organization_id == org_id)
        .order_by(Interview.created_at.desc())
    )

    result = await session.execute(query)
    rows = result.all()

    return [
        InterviewSummary(
            id=str(row.id),
            masked_candidate_id=f"CAND-{row.id.hex[:4].upper()}",
            vacancy_title=row.vacancy_title,
            status=row.status.value if hasattr(row.status, "value") else str(row.status),
            overall_score=row.overall_score,
            recommendation=row.recommendation,
            created_at=row.created_at,
        )
        for row in rows
    ]
