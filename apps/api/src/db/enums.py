from enum import StrEnum


class Seniority(StrEnum):
    JUNIOR = "junior"
    MID = "mid"
    SENIOR = "senior"
    LEAD = "lead"


class Difficulty(StrEnum):
    JUNIOR = "junior"
    MID = "mid"
    SENIOR = "senior"


class InterviewStatus(StrEnum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    EVALUATED = "evaluated"


class InterviewPhase(StrEnum):
    INTRO = "INTRO"
    PROBLEM = "PROBLEM"
    CLARIFY = "CLARIFY"
    DESIGN = "DESIGN"
    CODING = "CODING"
    PROBE = "PROBE"
    WRAPUP = "WRAPUP"
    EVALUATE = "EVALUATE"


class TurnSpeaker(StrEnum):
    CANDIDATE = "candidate"
    AGENT = "agent"


class UserRole(StrEnum):
    ADMIN = "admin"
    RECRUITER = "recruiter"
