from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.schemas.evaluation import EvaluationReport
from src.core.auth import AuthenticatedPrincipal, get_current_user
from src.db.models import Interview, Vacancy
from src.db.session import get_db
from src.evaluation.service import EvaluationService

router = APIRouter(prefix="/interviews", tags=["Evaluation"])


@router.get(
    "/{id}/evaluation",
    response_model=EvaluationReport,
    summary="Obtener la evaluación y rúbrica defendible de una entrevista (Ciega a PII)",
)
async def get_evaluation(
    id: str,
    principal: AuthenticatedPrincipal = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> EvaluationReport:
    """Obtener la evaluación defendible de una entrevista.

    Retorna la rúbrica de 5 dimensiones (1-5), la puntuación general,
    la recomendación y la evidencia citada (turnos, snapshots, ejecuciones).
    La evaluación está ciega a datos personales del candidato (PII aislada).

    Requiere autenticación de reclutador/admin y pertenencia a la misma organización.
    """
    try:
        interview_id = UUID(id)
    except (ValueError, TypeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Interview not found"
        ) from exc

    # Verificación multi-tenant: interview -> vacancy -> organization_id
    result = await session.execute(
        select(Interview, Vacancy)
        .outerjoin(Vacancy, Interview.vacancy_id == Vacancy.id)
        .where(Interview.id == interview_id)
    )
    row = result.first()
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Interview not found"
        )
    _interview, vacancy = row
    if (
        vacancy
        and vacancy.organization_id is not None
        and vacancy.organization_id != principal.organization_id
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Interview not found"
        )

    service = EvaluationService(session)
    try:
        evaluation = await service.evaluate(interview_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    return evaluation
