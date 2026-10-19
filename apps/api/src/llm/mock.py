import json
from typing import Any

from src.llm.types import ChatCompletion, ChatMessage, TokenUsage

DEFAULT_MOCK_VACANCY_PROFILE: dict[str, Any] = {
    "role_category": "backend",
    "seniority": "mid",
    "required_skills": ["python", "fastapi"],
    "preferred_skills": ["postgresql"],
    "primary_language": "python",
    "focus_areas": ["apis", "clean code"],
}


class MockLLMClient:
    """Cliente LLM simulado para desarrollo local y pruebas E2E sin coste ni dependencias externas."""

    def __init__(
        self,
        default_response: str | dict[str, Any] | None = None,
        *,
        model: str = "mock-model",
        error: Exception | None = None,
    ) -> None:
        if isinstance(default_response, dict):
            self._content = json.dumps(default_response)
        elif isinstance(default_response, str):
            self._content = default_response
        else:
            self._content = json.dumps(DEFAULT_MOCK_VACANCY_PROFILE)

        self._model = model
        self._error = error
        self.history: list[list[ChatMessage]] = []

    async def complete(
        self,
        messages: list[ChatMessage],
        *,
        model: str | None = None,
    ) -> ChatCompletion:
        self.history.append(list(messages))
        if self._error is not None:
            raise self._error

        return ChatCompletion(
            content=self._content,
            model=model or self._model,
            usage=TokenUsage(
                prompt_tokens=10,
                completion_tokens=20,
                total_tokens=30,
            ),
        )

    async def aclose(self) -> None:
        pass
