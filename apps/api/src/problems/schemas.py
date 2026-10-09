import uuid
from enum import StrEnum

from pydantic import BaseModel, Field, field_validator, model_validator

from src.db.enums import Difficulty, Seniority

PROBLEM_ID_NAMESPACE = uuid.UUID("a3f1c8e2-7b54-4d91-9e06-2c5b8f4a1d73")


class RoleFamily(StrEnum):
    BACKEND = "backend"
    FRONTEND = "frontend"
    FULLSTACK = "fullstack"
    DATA = "data"
    DEVOPS = "devops"


class CatalogLanguage(StrEnum):
    PYTHON = "python"
    JAVASCRIPT = "javascript"
    SQL = "sql"


class TestCase(BaseModel):
    id: str = Field(min_length=1, max_length=80, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    input: str
    expected_output: str
    timeout_ms: int = Field(default=2000, gt=0, le=30000)
    memory_mb: int = Field(default=128, gt=0, le=512)


class ExecutionLimits(BaseModel):
    timeout_ms: int = Field(default=2000, gt=0, le=30000)
    memory_mb: int = Field(default=128, gt=0, le=512)


class ProblemSpec(BaseModel):
    id: str = Field(min_length=1, max_length=80, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    title: str = Field(min_length=1, max_length=255)
    statement: str = Field(min_length=1)
    role: RoleFamily
    seniority: Seniority
    difficulty: Difficulty
    tags: list[str] = Field(min_length=1)
    languages: list[CatalogLanguage] = Field(min_length=1)
    tests: list[TestCase] = Field(min_length=1)
    limits: ExecutionLimits = Field(default_factory=ExecutionLimits)
    boilerplate: dict[str, str] = Field(default_factory=dict)

    @field_validator("title")
    @classmethod
    def _strip_title(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("title cannot be empty")
        return cleaned

    @field_validator("statement")
    @classmethod
    def _strip_statement(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("statement cannot be empty")
        return cleaned

    @field_validator("tags")
    @classmethod
    def _normalize_tags(cls, values: list[str]) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for item in values:
            tag = item.strip().casefold()
            if not tag:
                raise ValueError("tags cannot contain empty values")
            if tag in seen:
                continue
            seen.add(tag)
            normalized.append(tag)
        if not normalized:
            raise ValueError("tags cannot be empty")
        return normalized

    @field_validator("languages")
    @classmethod
    def _unique_languages(cls, values: list[CatalogLanguage]) -> list[CatalogLanguage]:
        unique: list[CatalogLanguage] = []
        seen: set[CatalogLanguage] = set()
        for language in values:
            if language in seen:
                continue
            seen.add(language)
            unique.append(language)
        return unique

    @field_validator("tests")
    @classmethod
    def _unique_test_ids(cls, values: list[TestCase]) -> list[TestCase]:
        seen: set[str] = set()
        for case in values:
            if case.id in seen:
                raise ValueError(f"duplicate test id: {case.id}")
            seen.add(case.id)
        return values

    @model_validator(mode="after")
    def _boilerplate_matches_languages(self) -> "ProblemSpec":
        allowed = {language.value for language in self.languages}
        for key, source in self.boilerplate.items():
            if key not in allowed:
                raise ValueError(f"boilerplate language {key!r} is not in languages")
            if not source.strip():
                raise ValueError(f"boilerplate for {key!r} cannot be empty")
        return self

    def persistence_id(self) -> uuid.UUID:
        return uuid.uuid5(PROBLEM_ID_NAMESPACE, self.id)

    @property
    def primary_language(self) -> str:
        return self.languages[0].value
