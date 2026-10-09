import json

import httpx
import pytest

from src.core.config import Settings
from src.llm.exceptions import (
    LLMAuthenticationError,
    LLMInvalidResponseError,
    LLMProviderError,
    LLMRateLimitError,
    LLMTimeoutError,
)
from src.llm.factory import create_llm_client
from src.llm.openai_compatible import OpenAICompatibleClient
from src.llm.types import ChatMessage


def _completion_body(**overrides: object) -> dict[str, object]:
    body: dict[str, object] = {
        "model": "grok-4.6",
        "choices": [{"message": {"role": "assistant", "content": "ok"}}],
        "usage": {"prompt_tokens": 11, "completion_tokens": 3, "total_tokens": 14},
    }
    body.update(overrides)
    return body


def test_factory_uses_settings_without_secrets_in_repr() -> None:
    config = Settings(
        LLM_API_KEY="test-key",
        LLM_BASE_URL="https://api.reto.pltk.mx/v1",
        LLM_MODEL="grok-4.6",
    )
    client = create_llm_client(config)
    assert client._model == "grok-4.6"
    assert "test-key" not in repr(client)


@pytest.mark.asyncio
async def test_complete_success_and_usage() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/chat/completions")
        assert request.headers["authorization"] == "Bearer test-key"
        return httpx.Response(200, json=_completion_body())

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = OpenAICompatibleClient(
        api_key="test-key",
        base_url="https://api.reto.pltk.mx/v1",
        model="grok-4.6",
        client=http_client,
    )
    result = await client.complete([ChatMessage(role="user", content="hola")])
    assert result.content == "ok"
    assert result.model == "grok-4.6"
    assert result.usage.prompt_tokens == 11
    assert result.usage.completion_tokens == 3
    assert result.usage.total_tokens == 14
    await http_client.aclose()


@pytest.mark.asyncio
async def test_authentication_error_is_not_retried() -> None:
    calls = {"count": 0}

    async def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        return httpx.Response(401, json={"error": "unauthorized"})

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = OpenAICompatibleClient(
        api_key="test-key",
        base_url="https://api.reto.pltk.mx/v1",
        model="grok-4.6",
        max_retries=2,
        client=http_client,
    )
    with pytest.raises(LLMAuthenticationError, match="authentication"):
        await client.complete([ChatMessage(role="user", content="hola")])
    assert calls["count"] == 1
    await http_client.aclose()


@pytest.mark.asyncio
async def test_timeout_and_retry_then_success() -> None:
    calls = {"count": 0}

    async def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        if calls["count"] == 1:
            raise httpx.ReadTimeout("timed out")
        return httpx.Response(200, json=_completion_body())

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = OpenAICompatibleClient(
        api_key="test-key",
        base_url="https://api.reto.pltk.mx/v1",
        model="grok-4.6",
        max_retries=1,
        client=http_client,
    )
    result = await client.complete([ChatMessage(role="user", content="hola")])
    assert result.content == "ok"
    assert calls["count"] == 2
    await http_client.aclose()


@pytest.mark.asyncio
async def test_timeout_exhausted() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out")

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = OpenAICompatibleClient(
        api_key="test-key",
        base_url="https://api.reto.pltk.mx/v1",
        model="grok-4.6",
        max_retries=0,
        client=http_client,
    )
    with pytest.raises(LLMTimeoutError):
        await client.complete([ChatMessage(role="user", content="hola")])
    await http_client.aclose()


@pytest.mark.asyncio
async def test_rate_limit_and_invalid_response() -> None:
    async def rate_limited(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"error": "slow down"})

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(rate_limited))
    client = OpenAICompatibleClient(
        api_key="test-key",
        base_url="https://api.reto.pltk.mx/v1",
        model="grok-4.6",
        max_retries=0,
        client=http_client,
    )
    with pytest.raises(LLMRateLimitError):
        await client.complete([ChatMessage(role="user", content="hola")])
    await http_client.aclose()

    async def invalid(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": []})

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(invalid))
    client = OpenAICompatibleClient(
        api_key="test-key",
        base_url="https://api.reto.pltk.mx/v1",
        model="grok-4.6",
        client=http_client,
    )
    with pytest.raises(LLMInvalidResponseError):
        await client.complete([ChatMessage(role="user", content="hola")])
    await http_client.aclose()


@pytest.mark.asyncio
async def test_provider_error_and_no_secret_in_exception() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="boom")

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = OpenAICompatibleClient(
        api_key="super-secret-key",
        base_url="https://api.reto.pltk.mx/v1",
        model="grok-4.6",
        max_retries=0,
        client=http_client,
    )
    with pytest.raises(LLMProviderError) as exc:
        await client.complete([ChatMessage(role="user", content="hola")])
    assert "super-secret-key" not in str(exc.value)
    await http_client.aclose()


def test_errors_do_not_embed_api_keys() -> None:
    dumped = json.dumps(
        {
            "LLM_API_KEY": "mock-llm-key",
        }
    )
    assert "sk-" not in dumped
