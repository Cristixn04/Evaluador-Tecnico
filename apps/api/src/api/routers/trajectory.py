from datetime import UTC

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.schemas.interview import InterviewTrajectory, TrajectorySnapshot
from src.db.models import Interview, Snapshot
from src.db.session import get_db

router = APIRouter(prefix="/interviews", tags=["Interview Trajectory"])


@router.get(
    "/{interview_id}/trajectory",
    response_model=InterviewTrajectory,
    summary="Obtener la trayectoria cronológica de código y depuración de la entrevista",
)
async def get_interview_trajectory(
    interview_id: str,
    session: AsyncSession = Depends(get_db),
) -> InterviewTrajectory:
    """Obtener la trayectoria cronológica de una entrevista.

    Devuelve los snapshots de código con marcas de tiempo, fases y resultados de tests
    a lo largo de la entrevista, compatibles con el contrato del frontend.
    """

    # Buscar la entrevista
    try:
        interview_id_uuid = interview_id
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid interview ID format",
        )

    interview = await session.get(Interview, interview_id_uuid)
    if not interview:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Interview not found",
        )

    # Cargar snapshots ordenados por fecha de creación (cronológico)
    result = await session.execute(
        select(Snapshot).where(Snapshot.interview_id == interview_id_uuid).order_by(Snapshot.created_at)
    )
    snapshots = result.scalars().all()

    # Construir la respuesta de trayectoria
    interview_created_at = interview.created_at
    if interview_created_at.tzinfo is None:
        interview_created_at = interview_created_at.replace(tzinfo=UTC)

    snapshot_dtos = []
    for snapshot in snapshots:
        timestamp_offset = (snapshot.created_at - interview_created_at).total_seconds()
        snapshot_dto = TrajectorySnapshot(
            timestamp_offset_seconds=timestamp_offset,
            phase=snapshot.phase,
            reason=snapshot.reason,
            code=snapshot.code,
            language=snapshot.language,
            tests_passed=snapshot.tests_passed,
            total_tests=snapshot.total_tests,
            execution_status=snapshot.execution_status,
        )
        snapshot_dtos.append(snapshot_dto)

    # Calcular duración total
    if snapshots:
        first_created = snapshots[0].created_at
        last_created = snapshots[-1].created_at
        if first_created.tzinfo is None:
            first_created = first_created.replace(tzinfo=UTC)
        if last_created.tzinfo is None:
            last_created = last_created.replace(tzinfo=UTC)
        total_duration = (last_created - first_created).total_seconds()
    else:
        total_duration = 0.0

    return InterviewTrajectory(
        interview_id=str(interview.id),
        total_duration_seconds=total_duration,
        snapshots=snapshot_dtos,
    )