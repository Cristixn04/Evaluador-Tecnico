from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from src.db.enums import Seniority


class CreateVacancyRequest(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    raw_description: str = Field(min_length=1)


class VacancyProfile(BaseModel):
    required_skills: list[str]
    preferred_skills: list[str]
    primary_language: str
    focus_areas: list[str] = Field(default_factory=list)


class VacancyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    role_category: str
    seniority: Seniority
    profile: VacancyProfile
    created_at: datetime
