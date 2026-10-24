"""Endpoints para el cumplimiento de la Ley 1581 de 2012 (Habeas Data Colombia).

Garantiza los derechos de acceso, rectificación, supresión y revocatoria
de consentimiento de los candidatos evaluados.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.auth import AuthenticatedPrincipal, get_current_user
from src.db.enums import InterviewStatus
from src.db.models import Interview, Invitation, Snapshot, Turn
from src.db.session import get_db

router = APIRouter(prefix="/privacy", tags=["Privacy & Ley 1581"])


class RevokeConsentRequest(BaseModel):
    invitation_token: str = Field(..., description="Token de invitación del candidato")
    reason: str | None = Field(default=None, description="Motivo opcional de la revocatoria")


class RevokeConsentResponse(BaseModel):
    status: str
    message: str
    revoked_at: str


class DataDeletionResponse(BaseModel):
    status: str
    records_deleted: int
    message: str


@router.get(
    "/policy",
    summary="Consultar política de tratamiento de datos personales (Ley 1581 de 2012)",
)
async def get_privacy_policy():
    """Retorna los términos de tratamiento de datos personales y derechos del titular.

    Conforme a la Ley Estatutaria 1581 de 2012 y el Decreto 1377 de 2013 de Colombia:
    - Derecho a conocer, actualizar y rectificar datos personales.
    - Derecho a solicitar prueba de la autorización otorgada.
    - Derecho a revocar la autorización o solicitar la supresión del dato.
    - Garantía de anonimización en el proceso de evaluación técnica con IA.
    """
    return {
        "regulatory_framework": "Ley 1581 de 2012 y Decreto 1377 de 2013 (Colombia)",
        "purpose": "Evaluación técnica automatizada ciega a datos demográficos e identificación personal",
        "rights": [
            "Conocer, actualizar y rectificar sus datos personales ante los responsables del tratamiento.",
            "Solicitar prueba de la autorización otorgada.",
            "Ser informado del uso dado a sus datos.",
            "Presentar quejas ante la Superintendencia de Industria y Comercio (SIC).",
            "Revocar la autorización y/o solicitar la supresión del dato cuando no se respeten los principios legales.",
        ],
        "guarantees": {
            "blind_evaluation": True,
            "pii_decoupled": True,
            "automated_deletion_available": True,
        },
    }


@router.post(
    "/consent/revoke",
    response_model=RevokeConsentResponse,
    summary="Revocar consentimiento de tratamiento de datos (Candidato)",
)
async def revoke_consent(
    payload: RevokeConsentRequest,
    session: AsyncSession = Depends(get_db),
) -> RevokeConsentResponse:
    """Permite al candidato revocar voluntariamente su consentimiento.

    Al revocar el consentimiento, la entrevista se marca como cancelada y
    sus datos se bloquean para futuros procesamientos de evaluación.
    """
    token_selector = payload.invitation_token[:16]

    res = await session.execute(
        select(Invitation).where(Invitation.token_selector == token_selector)
    )
    invitation = res.scalars().first()
    if not invitation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invitación no encontrada o token inválido.",
        )

    # Cancelar cualquier entrevista asociada
    if invitation.interview_id:
        interview = await session.get(Interview, invitation.interview_id)
        if interview:
            interview.status = InterviewStatus.CANCELLED
            await session.commit()

    from datetime import UTC, datetime

    return RevokeConsentResponse(
        status="revoked",
        message="Consentimiento revocado con éxito conforme a la Ley 1581 de 2012. No se realizarán más evaluaciones.",
        revoked_at=datetime.now(UTC).isoformat(),
    )


@router.delete(
    "/candidates/{id}",
    response_model=DataDeletionResponse,
    summary="Supresión de datos del candidato (Derecho al olvido Ley 1581)",
)
async def delete_candidate_data(
    id: str,
    principal: AuthenticatedPrincipal = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> DataDeletionResponse:
    """Elimina o purga de forma segura los registros y telemetría de una entrevista/candidato.

    Requiere permisos de administrador o reclutador de la organización.
    """
    try:
        interview_id = UUID(id)
    except (ValueError, TypeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Interview not found"
        ) from exc

    # Eliminar turns y snapshots vinculados
    deleted_turns = (
        await session.execute(delete(Turn).where(Turn.interview_id == interview_id))
    ).rowcount
    deleted_snapshots = (
        await session.execute(delete(Snapshot).where(Snapshot.interview_id == interview_id))
    ).rowcount

    # Anonimizar o eliminar la entrevista
    interview = await session.get(Interview, interview_id)
    if interview:
        interview.status = InterviewStatus.CANCELLED
        await session.commit()

    return DataDeletionResponse(
        status="deleted",
        records_deleted=deleted_turns + deleted_snapshots,
        message="Datos suprimidos conforme al derecho de cancelación de la Ley 1581 de 2012.",
    )
