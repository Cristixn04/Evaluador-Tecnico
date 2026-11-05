import asyncio
import json
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
from src.llm.types import ChatCompletion, ChatMessage, TokenUsage, ToolCall

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

    def _serialize_message(self, message: ChatMessage) -> dict[str, Any]:
        serialized: dict[str, Any] = {
            "role": message.role,
            "content": message.content if message.content is not None else "",
        }
        if message.role == "assistant" and message.tool_calls:
            serialized["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": tc.type or "function",
                    "function": {
                        "name": tc.name,
                        "arguments": tc.arguments,
                    },
                }
                for tc in message.tool_calls
            ]
        elif message.role == "tool":
            if not message.tool_call_id or not isinstance(message.tool_call_id, str):
                raise LLMConfigurationError("Tool message requires a valid tool_call_id")
            serialized["tool_call_id"] = message.tool_call_id
            if message.name:
                serialized["name"] = message.name
        return serialized

    async def complete(
        self,
        messages: list[ChatMessage],
        *,
        model: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | dict[str, Any] | None = None,
    ) -> ChatCompletion:
        payload: dict[str, Any] = {
            "model": model or self._model,
            "messages": [self._serialize_message(message) for message in messages],
        }
        if tools is not None:
            payload["tools"] = tools
            if tool_choice is not None:
                payload["tool_choice"] = tool_choice

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

            try:
                raw_json = response.json()
            except ValueError as exc:
                raise LLMInvalidResponseError("LLM response is not valid JSON") from exc

            return self._parse_completion(raw_json)

        raise last_error or LLMProviderError("LLM provider request failed")

    def _backoff(self, attempt: int) -> float:
        return min(2**attempt, 4)

    def _parse_tool_calls(self, raw_tool_calls: Any) -> list[ToolCall] | None:
        if raw_tool_calls is None:
            return None
        if not isinstance(raw_tool_calls, list):
            raise LLMInvalidResponseError("LLM tool_calls is not a list")
        if not raw_tool_calls:
            return None

        parsed: list[ToolCall] = []
        for item in raw_tool_calls:
            if not isinstance(item, Mapping):
                raise LLMInvalidResponseError("LLM tool_call entry is not an object")
            call_id = item.get("id")
            if not isinstance(call_id, str) or not call_id.strip():
                raise LLMInvalidResponseError("LLM tool_call id is missing or invalid")
            call_type = item.get("type", "function")
            if not isinstance(call_type, str) or not call_type.strip():
                call_type = "function"
            func = item.get("function")
            if not isinstance(func, Mapping):
                raise LLMInvalidResponseError("LLM tool_call function is missing or invalid")
            func_name = func.get("name")
            if not isinstance(func_name, str) or not func_name.strip():
                raise LLMInvalidResponseError("LLM tool_call function name is missing or invalid")
            raw_args = func.get("arguments", "{}")
            if isinstance(raw_args, Mapping):
                args_str = json.dumps(dict(raw_args), ensure_ascii=False)
            elif isinstance(raw_args, str):
                args_str = raw_args
            else:
                raise LLMInvalidResponseError("LLM tool_call arguments must be a JSON string or object")
            parsed.append(
                ToolCall(
                    id=call_id.strip(),
                    name=func_name.strip(),
                    arguments=args_str,
                    type=call_type.strip(),
                )
            )
        return parsed

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

        tool_calls = self._parse_tool_calls(message.get("tool_calls"))
        content = message.get("content")
        if content is None and tool_calls:
            content = ""
        if not isinstance(content, str):
            raise LLMInvalidResponseError("LLM content is invalid")

        finish_reason_raw = first.get("finish_reason")
        finish_reason = finish_reason_raw if isinstance(finish_reason_raw, str) else None

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
            tool_calls=tool_calls,
            finish_reason=finish_reason,
        )


def _as_optional_int(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value
