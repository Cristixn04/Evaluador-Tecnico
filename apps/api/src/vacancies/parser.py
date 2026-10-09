import json
import re
from typing import Any

from pydantic import BaseModel, Field, ValidationError, field_validator

from src.db.enums import Seniority
from src.llm.exceptions import LLMError, LLMInvalidResponseError
from src.llm.prompts import load_prompt
from src.llm.types import ChatMessage, LLMClient
from src.vacancies.exceptions import (
    VacancyParserInvalidInputError,
    VacancyParserInvalidResponseError,
)

_JSON_BLOCK = re.compile(r"\{.*\}", re.DOTALL)
PROMPT_NAME = "vacancy_parser"
PROMPT_VERSION = "v1"


class ParsedVacancyProfile(BaseModel):
    role_category: str = Field(min_length=1, max_length=100)
    seniority: Seniority
    required_skills: list[str]
    preferred_skills: list[str]
    primary_language: str = Field(min_length=1, max_length=50)
    focus_areas: list[str] = Field(default_factory=list)

    @field_validator("required_skills", "preferred_skills", "focus_areas")
    @classmethod
    def _normalize_skills(cls, values: list[str]) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for item in values:
            skill = item.strip()
            key = skill.casefold()
            if not skill or key in seen:
                continue
            seen.add(key)
            normalized.append(skill)
        return normalized

    @field_validator("role_category", "primary_language")
    @classmethod
    def _strip_required_text(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("value cannot be empty")
        return cleaned


def _extract_json_object(content: str) -> dict[str, Any]:
    raw = content.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
    try:
        loaded = json.loads(raw)
    except json.JSONDecodeError:
        match = _JSON_BLOCK.search(raw)
        if match is None:
            raise VacancyParserInvalidResponseError("LLM response is not valid JSON") from None
        try:
            loaded = json.loads(match.group(0))
        except json.JSONDecodeError as exc:
            raise VacancyParserInvalidResponseError("LLM response is not valid JSON") from exc
    if not isinstance(loaded, dict):
        raise VacancyParserInvalidResponseError("LLM response is not a JSON object")
    return loaded


class VacancyParser:
    def __init__(self, client: LLMClient, *, prompt_version: str = PROMPT_VERSION) -> None:
        self._client = client
        self._prompt_version = prompt_version

    async def parse(self, raw_description: str) -> ParsedVacancyProfile:
        description = raw_description.strip()
        if not description:
            raise VacancyParserInvalidInputError("Vacancy description cannot be empty")

        system_prompt = load_prompt(PROMPT_NAME, self._prompt_version)
        messages = [
            ChatMessage(role="system", content=system_prompt),
            ChatMessage(
                role="user",
                content=(
                    "Extract the vacancy profile from this description.\n"
                    "<untrusted_candidate_input>\n"
                    f"{description}\n"
                    "</untrusted_candidate_input>"
                ),
            ),
        ]
        try:
            completion = await self._client.complete(messages)
        except LLMInvalidResponseError as exc:
            raise VacancyParserInvalidResponseError(str(exc)) from exc
        except LLMError:
            raise

        try:
            payload = _extract_json_object(completion.content)
            return ParsedVacancyProfile.model_validate(payload)
        except (VacancyParserInvalidResponseError, ValidationError) as exc:
            raise VacancyParserInvalidResponseError(
                "LLM response does not match VacancyProfile"
            ) from exc
