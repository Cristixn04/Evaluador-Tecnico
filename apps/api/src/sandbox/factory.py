from collections.abc import AsyncGenerator

from src.core.config import Settings, settings
from src.sandbox.exceptions import SandboxUnavailableError
from src.sandbox.judge0 import Judge0Adapter
from src.sandbox.types import RunRequest, RunResult


class LocalRunnerUnavailable:
    async def run(self, request: RunRequest) -> RunResult:
        raise SandboxUnavailableError(
            "Local runner is unavailable without isolated infrastructure"
        )


def create_code_runner(config: Settings | None = None) -> Judge0Adapter:
    current = config or settings
    return Judge0Adapter(
        base_url=current.JUDGE0_BASE_URL,
        api_key=current.JUDGE0_API_KEY,
        timeout_seconds=current.JUDGE0_TIMEOUT_SECONDS,
        poll_interval_seconds=current.JUDGE0_POLL_INTERVAL_SECONDS,
        max_polls=current.JUDGE0_MAX_POLLS,
    )


async def get_code_runner() -> AsyncGenerator[Judge0Adapter, None]:
    runner = create_code_runner()
    try:
        yield runner
    finally:
        await runner.aclose()
