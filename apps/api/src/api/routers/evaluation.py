from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.schemas.evaluation import EvaluationReport
from src.core.auth import AuthenticatedPrincipal, get_current_user
from src.db.models import Interview, Snapshot, Vacancy
from src.db.session import get_db
from src.evaluation.service import EvaluationService
from src.reports.generator import ReportPdfGenerator

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


@router.get(
    "/{id}/report.pdf",
    summary="Descargar el informe defendible en formato PDF (WeasyPrint con hash SHA-256)",
    responses={
        200: {
            "content": {"application/pdf": {}},
            "description": "Reporte en PDF de la evaluación técnica.",
        }
    },
)
async def get_report_pdf(
    id: str,
    principal: AuthenticatedPrincipal = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> Response:
    """Genera y descarga el informe de evaluación en formato PDF con WeasyPrint.

    Incluye el radar de competencias, las justificaciones por dimensión,
    las evidencias textuales citadas con turnos y un hash SHA-256 inmutable de auditoría.
    """
    try:
        interview_id = UUID(id)
    except (ValueError, TypeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Interview not found"
        ) from exc

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

    # Obtener el último snapshot de código si existe
    snapshot_res = await session.execute(
        select(Snapshot)
        .where(Snapshot.interview_id == interview_id)
        .order_by(Snapshot.created_at.desc())
    )
    latest_snapshot = snapshot_res.scalars().first()

    vacancy_title = vacancy.title if vacancy else "Desarrollador de Software"
    generator = ReportPdfGenerator()
    pdf_bytes, audit_hash = generator.generate_pdf(
        report=evaluation,
        vacancy_title=vacancy_title,
        final_code=latest_snapshot.code if latest_snapshot else "",
        code_language=latest_snapshot.language if latest_snapshot else "python",
    )

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename=reporte-evaluacion-{evaluation.masked_candidate_id}.pdf",
            "X-Audit-Hash-SHA256": audit_hash,
        },
    )

