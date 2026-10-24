from datetime import datetime

from pydantic import BaseModel, ConfigDict


class PhaseTransitionRequest(BaseModel):
    target_phase: str
    reason: str | None = None


class PhaseTransitionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    current_phase: str
    available_transitions: list[str]
    phase_instructions: str | None = None


class InterviewSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    masked_candidate_id: str
    vacancy_title: str
    status: str
    overall_score: float | None = None
    recommendation: str | None = None
    created_at: datetime


class TrajectorySnapshot(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    timestamp_offset_seconds: float
    phase: str
    reason: str
    code: str
    language: str
    tests_passed: int | None = None
    total_tests: int | None = None
    execution_status: str | None = None


class InterviewTrajectory(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    interview_id: str
    total_duration_seconds: float
    snapshots: list[TrajectorySnapshot]