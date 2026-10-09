import asyncio
from collections.abc import Mapping
from typing import Any

import httpx

from src.llm.exceptions import (
    LLMAuthenticationError,
    LLMConfigurationError,
    LLMInvalidResponseError,
    LLMProviderError,
    LLMRateLimitError,
    LLMTimeoutError,
)
from src.llm.types import ChatCompletion, ChatMessage, TokenUsage

_TRANSIENT_STATUS = {408, 500, 502, 503, 504}


class OpenAICompatibleClient:
    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        timeout_seconds: float = 30.0,
        max_retries: int = 2,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if not api_key:
            raise LLMConfigurationError("LLM API key is not configured")
        if not base_url:
            raise LLMConfigurationError("LLM base URL is not configured")
        if not model:
            raise LLMConfigurationError("LLM model is not configured")

        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout = timeout_seconds
        self._max_retries = max(0, max_retries)
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(timeout=timeout_seconds)

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def complete(
        self,
        messages: list[ChatMessage],
        *,
        model: str | None = None,
    ) -> ChatCompletion:
        payload = {
            "model": model or self._model,
            "messages": [
                {"role": message.role, "content": message.content} for message in messages
            ],
        }
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        url = f"{self._base_url}/chat/completions"
        last_error: Exception | None = None

        for attempt in range(self._max_retries + 1):
            try:
                response = await self._client.post(url, json=payload, headers=headers)
            except httpx.TimeoutException as exc:
                last_error = LLMTimeoutError("LLM request timed out")
                if attempt >= self._max_retries:
                    raise last_error from exc
                await asyncio.sleep(self._backoff(attempt))
                continue
            except httpx.HTTPError as exc:
                last_error = LLMProviderError("LLM provider request failed")
                if attempt >= self._max_retries:
                    raise last_error from exc
                await asyncio.sleep(self._backoff(attempt))
                continue

            if response.status_code in {401, 403}:
                raise LLMAuthenticationError("LLM authentication failed")
            if response.status_code == 429:
                last_error = LLMRateLimitError("LLM rate limit exceeded")
                if attempt >= self._max_retries:
                    raise last_error
                await asyncio.sleep(self._backoff(attempt))
                continue
            if response.status_code in _TRANSIENT_STATUS:
                last_error = LLMProviderError(f"LLM provider error ({response.status_code})")
                if attempt >= self._max_retries:
                    raise last_error
                await asyncio.sleep(self._backoff(attempt))
                continue
            if response.status_code >= 400:
                raise LLMProviderError(f"LLM provider error ({response.status_code})")

            return self._parse_completion(response.json())

        raise last_error or LLMProviderError("LLM provider request failed")

    def _backoff(self, attempt: int) -> float:
        return min(2**attempt, 4)

    def _parse_completion(self, body: Any) -> ChatCompletion:
        if not isinstance(body, Mapping):
            raise LLMInvalidResponseError("LLM response is not an object")
        choices = body.get("choices")
        if not isinstance(choices, list) or not choices:
            raise LLMInvalidResponseError("LLM response has no choices")
        first = choices[0]
        if not isinstance(first, Mapping):
            raise LLMInvalidResponseError("LLM choice is invalid")
        message = first.get("message")
        if not isinstance(message, Mapping):
            raise LLMInvalidResponseError("LLM message is invalid")
        content = message.get("content")
        if not isinstance(content, str):
            raise LLMInvalidResponseError("LLM content is invalid")

        usage_raw = body.get("usage")
        usage = TokenUsage()
        if isinstance(usage_raw, Mapping):
            usage = TokenUsage(
                prompt_tokens=_as_optional_int(usage_raw.get("prompt_tokens")),
                completion_tokens=_as_optional_int(usage_raw.get("completion_tokens")),
                total_tokens=_as_optional_int(usage_raw.get("total_tokens")),
            )

        model = body.get("model")
        return ChatCompletion(
            content=content,
            model=model if isinstance(model, str) else self._model,
            usage=usage,
        )


def _as_optional_int(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value
