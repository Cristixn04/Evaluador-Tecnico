from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class CreateInvitationRequest(BaseModel):
    candidate_name: str = Field(min_length=1, max_length=255)
    candidate_email: EmailStr
    candidate_phone: str | None = Field(default=None, max_length=50)


class InvitationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    invitation_id: str
    masked_candidate_id: str
    access_url: str
    access_token: str
    expires_at: datetime


class AnonymousCandidateSession(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    session_id: str
    masked_candidate_id: str
    vacancy_title: str
    current_phase: str
    status: str
    problem: "ProblemSummary"
    ws_token: str


class ProblemSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    difficulty: str
    language: str
    scenario_preview: str
    tags: list[str]


# Import at the end to avoid circular imports
AnonymousCandidateSession.model_rebuild()