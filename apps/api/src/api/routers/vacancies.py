from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.schemas.vacancies import CreateVacancyRequest, VacancyProfile, VacancyResponse
from src.core.auth import AuthenticatedPrincipal, get_current_user
from src.db.models import Vacancy
from src.db.session import get_db
from src.llm.exceptions import (
    LLMAuthenticationError,
    LLMConfigurationError,
    LLMError,
    LLMProviderError,
    LLMRateLimitError,
    LLMTimeoutError,
)
from src.llm.factory import get_llm_client
from src.llm.types import LLMClient
from src.vacancies.exceptions import (
    VacancyParserInvalidInputError,
    VacancyParserInvalidResponseError,
)
from src.vacancies.parser import VacancyParser

router = APIRouter(prefix="/vacancies", tags=["Vacancies"])


def _to_response(vacancy: Vacancy) -> VacancyResponse:
    if vacancy.role_category is None or vacancy.seniority is None or vacancy.profile is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Vacancy is missing parsed profile fields",
        )
    return VacancyResponse(
        id=str(vacancy.id),
        title=vacancy.title,
        role_category=vacancy.role_category,
        seniority=vacancy.seniority,
        profile=VacancyProfile.model_validate(vacancy.profile),
        created_at=vacancy.created_at,
    )


@router.post("", response_model=VacancyResponse, status_code=status.HTTP_201_CREATED)
async def create_vacancy(
    payload: CreateVacancyRequest,
    principal: AuthenticatedPrincipal = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
    llm_client: LLMClient = Depends(get_llm_client),
) -> VacancyResponse:
    parser = VacancyParser(llm_client)
    try:
        parsed = await parser.parse(payload.raw_description)
    except VacancyParserInvalidInputError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    except VacancyParserInvalidResponseError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except LLMTimeoutError as exc:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail="LLM request timed out"
        ) from exc
    except LLMRateLimitError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="LLM rate limit exceeded"
        ) from exc
    except (LLMAuthenticationError, LLMConfigurationError, LLMProviderError, LLMError) as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail="LLM provider error"
        ) from exc

    vacancy = Vacancy(
        organization_id=principal.organization_id,
        title=payload.title.strip(),
        raw_description=payload.raw_description.strip(),
        role_category=parsed.role_category,
        seniority=parsed.seniority,
        profile=parsed.model_dump(mode="json", exclude={"role_category", "seniority"}),
    )
    session.add(vacancy)
    await session.flush()
    await session.refresh(vacancy)
    return _to_response(vacancy)


@router.get("/{vacancy_id}/profile", response_model=VacancyProfile)
async def get_vacancy_profile(
    vacancy_id: UUID,
    principal: AuthenticatedPrincipal = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> VacancyProfile:
    result = await session.execute(select(Vacancy).where(Vacancy.id == vacancy_id))
    vacancy = result.scalar_one_or_none()
    if vacancy is None or vacancy.organization_id != principal.organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vacancy not found")
    if vacancy.profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Vacancy profile not found"
        )
    return VacancyProfile.model_validate(vacancy.profile)
