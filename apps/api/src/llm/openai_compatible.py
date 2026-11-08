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
        timeout_seconds: float = 45.0,
        connect_timeout_seconds: float = 10.0,
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
        self._connect_timeout = connect_timeout_seconds
        self._max_retries = max(0, max_retries)
        self._owns_client = client is None
        if client is not None:
            self._client = client
        else:
            timeouts = httpx.Timeout(
                connect=connect_timeout_seconds,
                read=timeout_seconds,
                write=10.0,
                pool=5.0,
            )
            self._client = httpx.AsyncClient(timeout=timeouts)

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    @staticmethod
    def _extract_gateway_metadata(response_headers: Mapping[str, str] | None) -> dict[str, str]:
        if not response_headers:
            return {}
        gw_meta: dict[str, str] = {}
        for h in (
            "x-request-id",
            "request-id",
            "x-groq-request-id",
            "cf-ray",
            "retry-after",
            "x-ratelimit-remaining-requests",
            "x-ratelimit-remaining-tokens",
            "x-ratelimit-limit-requests",
            "x-ratelimit-limit-tokens",
            "x-ratelimit-reset-requests",
            "x-ratelimit-reset-tokens",
        ):
            val = response_headers.get(h)
            if val:
                gw_meta[h] = str(val).strip()
        return gw_meta

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
        max_tokens: int | None = None,
    ) -> ChatCompletion:
        payload: dict[str, Any] = {
            "model": model or self._model,
            "messages": [self._serialize_message(message) for message in messages],
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
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
            except (httpx.ConnectTimeout, httpx.PoolTimeout) as exc:
                # El handshake TCP no se estableció o el pool expiró: el payload no fue enviado.
                # Es seguro reintentar si quedan intentos configurados.
                last_error = LLMTimeoutError("LLM connection timed out", is_uncertain=False)
                if attempt >= self._max_retries:
                    raise last_error from exc
                await asyncio.sleep(self._backoff(attempt))
                continue
            except httpx.ReadTimeout as exc:
                # CRÍTICO: ReadTimeout ocurre DESPUÉS de haber transmitido el payload completo.
                # El servidor remoto puede haber recibido la petición y facturado la generación.
                # El reintento automático está ESTRICTAMENTE PROHIBIDO para evitar duplicar cargos y costos inciertos.
                raise LLMTimeoutError(
                    f"LLM read timed out after {self._timeout}s (payload already sent; billing uncertain)",
                    is_uncertain=True,
                ) from exc
            except httpx.WriteTimeout as exc:
                # Interrupción durante transmisión de payload: estado incierto. No reintentar automáticamente.
                raise LLMTimeoutError(
                    "LLM write timed out during payload transmission (billing uncertain)",
                    is_uncertain=True,
                ) from exc
            except httpx.TimeoutException as exc:
                raise LLMTimeoutError("LLM request timed out", is_uncertain=True) from exc
            except httpx.HTTPError as exc:
                last_error = LLMProviderError(f"LLM network error: {exc!s}")
                if attempt >= self._max_retries:
                    raise last_error from exc
                await asyncio.sleep(self._backoff(attempt))
                continue

            gw_meta = self._extract_gateway_metadata(response.headers)

            if response.status_code in {401, 403}:
                raise LLMAuthenticationError(f"LLM authentication failed ({response.status_code})")

            if response.status_code == 429:
                last_error = LLMProviderError(
                    "LLM rate limit exceeded",
                    status_code=429,
                    headers=response.headers,
                    gateway_metadata=gw_meta,
                    is_uncertain=False,
                )
                if attempt >= self._max_retries:
                    raise LLMRateLimitError("LLM rate limit exceeded") from last_error
                # Extraer posible retry-after de cabeceras o usar backoff exponencial
                retry_after_str = gw_meta.get("retry-after")
                delay = float(retry_after_str) if retry_after_str and retry_after_str.isdigit() else self._backoff(attempt)
                await asyncio.sleep(min(delay, 5.0))
                continue

            if response.status_code in {500, 502, 503, 504, 408}:
                # CRÍTICO: En pasarelas y proxies LLM (ej. Cloudflare -> Proxy -> xAI), un error 500/502/503/504
                # puede producirse DESPUÉS de que el modelo upstream consumiera tokens y comenzara a generar.
                # Reintentar automáticamente sin garantía estricta de idempotencia puede causar doble facturación.
                # Se prohíbe el reintento automático y se clasifica como pasivo incierto (is_uncertain=True).
                raise LLMProviderError(
                    f"LLM provider error ({response.status_code}): upstream processing uncertain",
                    status_code=response.status_code,
                    headers=response.headers,
                    gateway_metadata=gw_meta,
                    is_uncertain=True,
                )

            if response.status_code >= 400:
                raise LLMProviderError(
                    f"LLM client error ({response.status_code})",
                    status_code=response.status_code,
                    headers=response.headers,
                    gateway_metadata=gw_meta,
                    is_uncertain=False,
                )

            try:
                raw_json = response.json()
            except ValueError as exc:
                raise LLMInvalidResponseError(
                    "LLM response is not valid JSON",
                    gateway_metadata=gw_meta,
                    is_uncertain=True,
                ) from exc

            return self._parse_completion(raw_json, response_headers=response.headers)

        raise last_error or LLMProviderError("LLM provider request failed")

    def _backoff(self, attempt: int) -> float:
        return min(2**attempt, 4)

    def _parse_tool_calls(
        self,
        raw_tool_calls: Any,
        gateway_metadata: dict[str, str] | None = None,
    ) -> list[ToolCall] | None:
        if raw_tool_calls is None:
            return None
        if not isinstance(raw_tool_calls, list):
            raise LLMInvalidResponseError("LLM tool_calls is not a list", gateway_metadata=gateway_metadata, is_uncertain=True)
        if not raw_tool_calls:
            return None

        parsed: list[ToolCall] = []
        for item in raw_tool_calls:
            if not isinstance(item, Mapping):
                raise LLMInvalidResponseError("LLM tool_call entry is not an object", gateway_metadata=gateway_metadata, is_uncertain=True)
            call_id = item.get("id")
            if not isinstance(call_id, str) or not call_id.strip():
                raise LLMInvalidResponseError("LLM tool_call id is missing or invalid", gateway_metadata=gateway_metadata, is_uncertain=True)
            call_type = item.get("type", "function")
            if not isinstance(call_type, str) or not call_type.strip():
                call_type = "function"
            func = item.get("function")
            if not isinstance(func, Mapping):
                raise LLMInvalidResponseError("LLM tool_call function is missing or invalid", gateway_metadata=gateway_metadata, is_uncertain=True)
            func_name = func.get("name")
            if not isinstance(func_name, str) or not func_name.strip():
                raise LLMInvalidResponseError("LLM tool_call function name is missing or invalid", gateway_metadata=gateway_metadata, is_uncertain=True)
            raw_args = func.get("arguments", "{}")
            if isinstance(raw_args, Mapping):
                args_str = json.dumps(dict(raw_args), ensure_ascii=False)
            elif isinstance(raw_args, str):
                args_str = raw_args
            else:
                raise LLMInvalidResponseError("LLM tool_call arguments must be a JSON string or object", gateway_metadata=gateway_metadata, is_uncertain=True)
            parsed.append(
                ToolCall(
                    id=call_id.strip(),
                    name=func_name.strip(),
                    arguments=args_str,
                    type=call_type.strip(),
                )
            )
        return parsed

    def _parse_completion(
        self,
        body: Any,
        response_headers: Mapping[str, str] | None = None,
    ) -> ChatCompletion:
        gw_meta = self._extract_gateway_metadata(response_headers)

        if not isinstance(body, Mapping):
            raise LLMInvalidResponseError("LLM response is not an object", gateway_metadata=gw_meta, is_uncertain=True)
        choices = body.get("choices")
        if not isinstance(choices, list) or not choices:
            raise LLMInvalidResponseError("LLM response has no choices", gateway_metadata=gw_meta, is_uncertain=True)
        first = choices[0]
        if not isinstance(first, Mapping):
            raise LLMInvalidResponseError("LLM choice is invalid", gateway_metadata=gw_meta, is_uncertain=True)
        message = first.get("message")
        if not isinstance(message, Mapping):
            raise LLMInvalidResponseError("LLM message is invalid", gateway_metadata=gw_meta, is_uncertain=True)

        tool_calls = self._parse_tool_calls(message.get("tool_calls"), gateway_metadata=gw_meta)
        content = message.get("content")
        if content is None and tool_calls:
            content = ""
        if not isinstance(content, str):
            raise LLMInvalidResponseError("LLM content is invalid", gateway_metadata=gw_meta, is_uncertain=True)

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

        # Captura de identificadores de trazabilidad y rate limits de la pasarela
        gw_meta = self._extract_gateway_metadata(response_headers)
        body_id = body.get("id") if isinstance(body.get("id"), str) else None
        cf_ray = gw_meta.get("cf-ray")
        req_id_header = (
            gw_meta.get("x-request-id")
            or gw_meta.get("request-id")
            or gw_meta.get("x-groq-request-id")
        )
        request_id = req_id_header or cf_ray

        if gw_meta:
            if body_id:
                gw_meta["provider_id"] = body_id
            if cf_ray:
                gw_meta["cf_ray"] = cf_ray
            if req_id_header:
                gw_meta["gateway_header_request_id"] = req_id_header

        return ChatCompletion(
            content=content,
            model=model if isinstance(model, str) else self._model,
            usage=usage,
            tool_calls=tool_calls,
            finish_reason=finish_reason,
            request_id=request_id,
            gateway_metadata=gw_meta or None,
        )


def _as_optional_int(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value
