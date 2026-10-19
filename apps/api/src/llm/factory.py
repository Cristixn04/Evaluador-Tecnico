from collections.abc import AsyncGenerator

from src.core.config import Settings, settings
from src.llm.exceptions import LLMConfigurationError
from src.llm.mock import MockLLMClient
from src.llm.openai_compatible import OpenAICompatibleClient
from src.llm.types import LLMClient


def create_llm_client(config: Settings | None = None) -> LLMClient:
    current = config or settings
    env = current.ENVIRONMENT.strip().lower()

    if env in {"production", "prod"}:
        if current.USE_MOCK_LLM:
            raise LLMConfigurationError(
                "Mock LLM client cannot be enabled in production environment"
            )
        if not current.LLM_API_KEY or current.LLM_API_KEY == "mock-llm-key":
            raise LLMConfigurationError(
                "Real LLM API key must be configured in production environment"
            )

    if current.USE_MOCK_LLM:
        return MockLLMClient()

    return OpenAICompatibleClient(
        api_key=current.LLM_API_KEY,
        base_url=current.LLM_BASE_URL,
        model=current.LLM_MODEL,
        timeout_seconds=current.LLM_TIMEOUT_SECONDS,
        max_retries=current.LLM_MAX_RETRIES,
    )


async def get_llm_client() -> AsyncGenerator[LLMClient, None]:
    client = create_llm_client()
    try:
        yield client
    finally:
        await client.aclose()
