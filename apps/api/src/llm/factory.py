from collections.abc import AsyncGenerator

from src.core.config import Settings, settings
from src.llm.openai_compatible import OpenAICompatibleClient


def create_llm_client(config: Settings | None = None) -> OpenAICompatibleClient:
    current = config or settings
    return OpenAICompatibleClient(
        api_key=current.LLM_API_KEY,
        base_url=current.LLM_BASE_URL,
        model=current.LLM_MODEL,
        timeout_seconds=current.LLM_TIMEOUT_SECONDS,
        max_retries=current.LLM_MAX_RETRIES,
    )


async def get_llm_client() -> AsyncGenerator[OpenAICompatibleClient, None]:
    client = create_llm_client()
    try:
        yield client
    finally:
        await client.aclose()
