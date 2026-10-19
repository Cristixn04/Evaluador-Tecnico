import json

import httpx
import pytest

from src.core.config import Settings
from src.db.enums import Seniority
from src.llm.exceptions import (
    LLMAuthenticationError,
    LLMConfigurationError,
    LLMInvalidResponseError,
    LLMProviderError,
    LLMRateLimitError,
    LLMTimeoutError,
)
from src.llm.factory import create_llm_client
from src.llm.mock import MockLLMClient
from src.llm.openai_compatible import OpenAICompatibleClient
from src.llm.types import ChatMessage
from src.vacancies.parser import VacancyParser


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
    assert isinstance(client, OpenAICompatibleClient)
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


def test_factory_returns_openai_client_by_default() -> None:
    config = Settings(
        USE_MOCK_LLM=False,
        LLM_API_KEY="test-key",
        ENVIRONMENT="development",
    )
    client = create_llm_client(config)
    assert isinstance(client, OpenAICompatibleClient)


def test_factory_returns_mock_client_when_enabled() -> None:
    config = Settings(
        USE_MOCK_LLM=True,
        ENVIRONMENT="development",
    )
    client = create_llm_client(config)
    assert isinstance(client, MockLLMClient)


@pytest.mark.parametrize("env_name", ["production", "prod", "PRODUCTION"])
def test_factory_raises_in_production_when_mock_enabled(env_name: str) -> None:
    config = Settings(
        USE_MOCK_LLM=True,
        ENVIRONMENT=env_name,
        LLM_API_KEY="real-prod-key",
    )
    with pytest.raises(
        LLMConfigurationError, match="Mock LLM client cannot be enabled in production"
    ):
        create_llm_client(config)


@pytest.mark.parametrize("env_name", ["production", "prod"])
def test_factory_raises_in_production_with_dummy_api_key(env_name: str) -> None:
    config = Settings(
        USE_MOCK_LLM=False,
        ENVIRONMENT=env_name,
        LLM_API_KEY="mock-llm-key",
    )
    with pytest.raises(
        LLMConfigurationError, match="Real LLM API key must be configured in production"
    ):
        create_llm_client(config)


def test_factory_allows_openai_client_in_production_with_real_key() -> None:
    config = Settings(
        USE_MOCK_LLM=False,
        ENVIRONMENT="production",
        LLM_API_KEY="sk-real-production-api-key-here",
    )
    client = create_llm_client(config)
    assert isinstance(client, OpenAICompatibleClient)


@pytest.mark.asyncio
async def test_mock_llm_client_complete_returns_valid_completion() -> None:
    client = MockLLMClient()
    messages = [ChatMessage(role="user", content="hello")]
    completion = await client.complete(messages)

    assert completion.model == "mock-model"
    assert completion.usage.total_tokens == 30
    assert len(client.history) == 1
    assert client.history[0] == messages

    parsed = json.loads(completion.content)
    assert parsed["role_category"] == "backend"
    assert parsed["seniority"] == "mid"
    assert parsed["primary_language"] == "python"


@pytest.mark.asyncio
async def test_mock_llm_client_can_be_parsed_by_vacancy_parser() -> None:
    client = MockLLMClient()
    parser = VacancyParser(client)
    profile = await parser.parse("Buscamos desarrollador Backend Python con FastAPI y PostgreSQL.")

    assert profile.role_category == "backend"
    assert profile.seniority == Seniority.MID
    assert profile.primary_language == "python"
    assert "python" in profile.required_skills
    assert "fastapi" in profile.required_skills
