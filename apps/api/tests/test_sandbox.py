import httpx
import pytest

from src.core.config import Settings
from src.sandbox.exceptions import (
    SandboxConfigurationError,
    SandboxInvalidResponseError,
    SandboxProviderError,
    SandboxTimeoutError,
    SandboxUnavailableError,
)
from src.sandbox.factory import LocalRunnerUnavailable, create_code_runner
from src.sandbox.judge0 import Judge0Adapter
from src.sandbox.types import ExecutionStatus, RunRequest


def _make_submission_response(token: str = "test-token") -> dict:
    return {"token": token}


def _make_poll_response(
    status_id: int = 3,
    stdout: str = "output",
    stderr: str = "",
    compile_output: str = "",
    time: float | None = 0.5,
    memory: int | None = 1024,
    exit_code: int | None = 0,
) -> dict:
    return {
        "status": {"id": status_id, "description": "Accepted"},
        "stdout": stdout,
        "stderr": stderr,
        "compile_output": compile_output,
        "time": time,
        "memory": memory,
        "exit_code": exit_code,
    }


class MockTransport:
    def __init__(self, responses: list[httpx.Response]):
        self.responses = responses
        self.call_count = 0

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        if self.call_count >= len(self.responses):
            return httpx.Response(500, json={"error": "no more mock responses"})
        response = self.responses[self.call_count]
        self.call_count += 1
        return response

    async def aclose(self) -> None:
        pass


def test_factory_uses_settings_without_secrets_in_repr() -> None:
    config = Settings(
        JUDGE0_BASE_URL="http://localhost:2358",
        JUDGE0_API_KEY="test-secret-key",
    )
    runner = create_code_runner(config)
    assert runner._base_url == "http://localhost:2358"
    assert "test-secret-key" not in repr(runner)


def test_factory_requires_base_url() -> None:
    config = Settings(JUDGE0_BASE_URL="", JUDGE0_API_KEY="")
    with pytest.raises(SandboxConfigurationError, match="base URL is not configured"):
        create_code_runner(config)


def test_factory_invalid_max_polls() -> None:
    config = Settings(JUDGE0_BASE_URL="http://localhost:2358", JUDGE0_MAX_POLLS=0)
    with pytest.raises(SandboxConfigurationError, match="max polls must be at least 1"):
        create_code_runner(config)


@pytest.mark.asyncio
async def test_judge0_adapter_submit_success() -> None:
    responses = [
        httpx.Response(200, json=_make_submission_response("token-123")),
        httpx.Response(200, json=_make_poll_response()),
    ]
    transport = MockTransport(responses)
    client = httpx.AsyncClient(transport=transport)  # type: ignore[arg-type]

    adapter = Judge0Adapter(
        base_url="http://localhost:2358",
        client=client,
        max_polls=2,
    )

    request = RunRequest(
        language="python",
        source="print('hello')",
        timeout_ms=2000,
        memory_mb=128,
    )
    result = await adapter.run(request)

    assert result.status is ExecutionStatus.ACCEPTED
    assert result.stdout == "output"
    assert result.time_seconds == 0.5
    assert result.memory_kb == 1024
    await client.aclose()


@pytest.mark.asyncio
async def test_judge0_adapter_wrong_answer() -> None:
    responses = [
        httpx.Response(200, json=_make_submission_response("token-123")),
        httpx.Response(200, json=_make_poll_response(status_id=4)),
    ]
    transport = MockTransport(responses)
    client = httpx.AsyncClient(transport=transport)  # type: ignore[arg-type]

    adapter = Judge0Adapter(base_url="http://localhost:2358", client=client, max_polls=2)
    request = RunRequest(language="python", source="print(1)")
    result = await adapter.run(request)

    assert result.status is ExecutionStatus.WRONG_ANSWER
    await client.aclose()


@pytest.mark.asyncio
async def test_judge0_adapter_compile_error() -> None:
    responses = [
        httpx.Response(200, json=_make_submission_response("token-123")),
        httpx.Response(
            200,
            json=_make_poll_response(
                status_id=6,
                compile_output="SyntaxError: invalid syntax",
            ),
        ),
    ]
    transport = MockTransport(responses)
    client = httpx.AsyncClient(transport=transport)  # type: ignore[arg-type]

    adapter = Judge0Adapter(base_url="http://localhost:2358", client=client, max_polls=2)
    request = RunRequest(language="python", source="invalid syntax")
    result = await adapter.run(request)

    assert result.status is ExecutionStatus.COMPILE_ERROR
    assert "SyntaxError" in result.compile_output
    await client.aclose()


@pytest.mark.asyncio
async def test_judge0_adapter_time_limit_exceeded() -> None:
    responses = [
        httpx.Response(200, json=_make_submission_response("token-123")),
        httpx.Response(200, json=_make_poll_response(status_id=5)),
    ]
    transport = MockTransport(responses)
    client = httpx.AsyncClient(transport=transport)  # type: ignore[arg-type]

    adapter = Judge0Adapter(base_url="http://localhost:2358", client=client, max_polls=2)
    request = RunRequest(language="python", source="while True: pass")
    result = await adapter.run(request)

    assert result.status is ExecutionStatus.TIME_LIMIT_EXCEEDED
    await client.aclose()


@pytest.mark.asyncio
async def test_judge0_adapter_memory_limit_exceeded() -> None:
    responses = [
        httpx.Response(200, json=_make_submission_response("token-123")),
        httpx.Response(200, json=_make_poll_response(status_id=137)),
    ]
    transport = MockTransport(responses)
    client = httpx.AsyncClient(transport=transport)  # type: ignore[arg-type]

    adapter = Judge0Adapter(base_url="http://localhost:2358", client=client, max_polls=2)
    request = RunRequest(language="python", source="x = [1] * 10**9")
    result = await adapter.run(request)

    assert result.status is ExecutionStatus.MEMORY_LIMIT_EXCEEDED
    await client.aclose()


@pytest.mark.asyncio
async def test_judge0_adapter_runtime_error() -> None:
    responses = [
        httpx.Response(200, json=_make_submission_response("token-123")),
        httpx.Response(200, json=_make_poll_response(status_id=7)),
    ]
    transport = MockTransport(responses)
    client = httpx.AsyncClient(transport=transport)  # type: ignore[arg-type]

    adapter = Judge0Adapter(base_url="http://localhost:2358", client=client, max_polls=2)
    request = RunRequest(language="python", source="1/0")
    result = await adapter.run(request)

    assert result.status is ExecutionStatus.RUNTIME_ERROR
    await client.aclose()


@pytest.mark.asyncio
async def test_judge0_adapter_http_error_on_submit() -> None:
    responses = [httpx.Response(500, json={"error": "internal server error"})]
    transport = MockTransport(responses)
    client = httpx.AsyncClient(transport=transport)  # type: ignore[arg-type]

    adapter = Judge0Adapter(base_url="http://localhost:2358", client=client, max_polls=2)
    request = RunRequest(language="python", source="print(1)")

    with pytest.raises(SandboxProviderError, match="Judge0 submit error"):
        await adapter.run(request)

    await client.aclose()


@pytest.mark.asyncio
async def test_judge0_adapter_http_error_on_poll() -> None:
    responses = [
        httpx.Response(200, json=_make_submission_response("token-123")),
        httpx.Response(503, json={"error": "service unavailable"}),
    ]
    transport = MockTransport(responses)
    client = httpx.AsyncClient(transport=transport)  # type: ignore[arg-type]

    adapter = Judge0Adapter(base_url="http://localhost:2358", client=client, max_polls=2)
    request = RunRequest(language="python", source="print(1)")

    with pytest.raises(SandboxProviderError, match="Judge0 poll error"):
        await adapter.run(request)

    await client.aclose()


@pytest.mark.asyncio
async def test_judge0_adapter_submit_timeout() -> None:
    async def timeout_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("timeout")

    client = httpx.AsyncClient(transport=httpx.MockTransport(timeout_handler))

    adapter = Judge0Adapter(base_url="http://localhost:2358", client=client, max_polls=2)
    request = RunRequest(language="python", source="print(1)")

    with pytest.raises(SandboxTimeoutError, match="Judge0 submit timed out"):
        await adapter.run(request)

    await client.aclose()


@pytest.mark.asyncio
async def test_judge0_adapter_poll_timeout() -> None:
    async def timeout_handler(request: httpx.Request) -> httpx.Response:
        if "submissions" in str(request.url) and "submissions/" not in str(request.url):
            return httpx.Response(200, json=_make_submission_response("token-123"))
        raise httpx.TimeoutException("timeout")

    client = httpx.AsyncClient(transport=httpx.MockTransport(timeout_handler))

    adapter = Judge0Adapter(base_url="http://localhost:2358", client=client, max_polls=2)
    request = RunRequest(language="python", source="print(1)")

    with pytest.raises(SandboxTimeoutError, match="Judge0 poll timed out"):
        await adapter.run(request)

    await client.aclose()


@pytest.mark.asyncio
async def test_judge0_adapter_malformed_submit_response() -> None:
    responses = [httpx.Response(200, json={"no_token": True})]
    transport = MockTransport(responses)
    client = httpx.AsyncClient(transport=transport)  # type: ignore[arg-type]

    adapter = Judge0Adapter(base_url="http://localhost:2358", client=client, max_polls=2)
    request = RunRequest(language="python", source="print(1)")

    with pytest.raises(SandboxInvalidResponseError, match="has no token"):
        await adapter.run(request)

    await client.aclose()


@pytest.mark.asyncio
async def test_judge0_adapter_malformed_poll_response() -> None:
    responses = [
        httpx.Response(200, json=_make_submission_response("token-123")),
        httpx.Response(200, json={"status": "not-an-object"}),
    ]
    transport = MockTransport(responses)
    client = httpx.AsyncClient(transport=transport)  # type: ignore[arg-type]

    adapter = Judge0Adapter(base_url="http://localhost:2358", client=client, max_polls=2)
    request = RunRequest(language="python", source="print(1)")

    with pytest.raises(SandboxInvalidResponseError, match="status is invalid"):
        await adapter.run(request)

    await client.aclose()


@pytest.mark.asyncio
async def test_judge0_adapter_polling_exhausted() -> None:
    responses = [
        httpx.Response(200, json=_make_submission_response("token-123")),
    ] + [httpx.Response(200, json=_make_poll_response(status_id=1)) for _ in range(10)]
    transport = MockTransport(responses)
    client = httpx.AsyncClient(transport=transport)  # type: ignore[arg-type]

    adapter = Judge0Adapter(
        base_url="http://localhost:2358",
        client=client,
        max_polls=5,
        poll_interval_seconds=0.01,
    )
    request = RunRequest(language="python", source="print(1)")

    with pytest.raises(SandboxTimeoutError, match="polling exhausted"):
        await adapter.run(request)

    await client.aclose()


@pytest.mark.asyncio
async def test_judge0_adapter_unsupported_language() -> None:
    client = httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(200, json={})))
    adapter = Judge0Adapter(base_url="http://localhost:2358", client=client, max_polls=2)
    request = RunRequest(language="brainfuck", source="+[>+]")

    with pytest.raises(SandboxConfigurationError, match="Unsupported language"):
        await adapter.run(request)

    await client.aclose()


@pytest.mark.asyncio
async def test_judge0_adapter_expected_output_provided() -> None:
    responses = [
        httpx.Response(200, json=_make_submission_response("token-123")),
        httpx.Response(200, json=_make_poll_response(status_id=3)),
    ]
    transport = MockTransport(responses)
    client = httpx.AsyncClient(transport=transport)  # type: ignore[arg-type]

    adapter = Judge0Adapter(base_url="http://localhost:2358", client=client, max_polls=2)
    request = RunRequest(
        language="python",
        source="print('hello')",
        expected_output="hello\n",
    )
    result = await adapter.run(request)

    assert result.status is ExecutionStatus.ACCEPTED
    await client.aclose()


@pytest.mark.asyncio
async def test_local_runner_unavailable() -> None:
    runner = LocalRunnerUnavailable()
    request = RunRequest(language="python", source="print(1)")

    with pytest.raises(SandboxUnavailableError, match="unavailable without isolated infrastructure"):
        await runner.run(request)


@pytest.mark.asyncio
async def test_judge0_adapter_with_api_key_header() -> None:
    captured_headers = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        if "submissions" in str(request.url) and "submissions/" not in str(request.url):
            captured_headers.update(dict(request.headers))
            return httpx.Response(200, json=_make_submission_response("token-123"))
        return httpx.Response(200, json=_make_poll_response())

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = Judge0Adapter(
        base_url="http://localhost:2358",
        api_key="secret-token",
        client=client,
        max_polls=2,
    )
    request = RunRequest(language="python", source="print(1)")
    await adapter.run(request)
    await client.aclose()

    assert captured_headers.get("X-Auth-Token") == "secret-token" or captured_headers.get("x-auth-token") == "secret-token"


@pytest.mark.asyncio
async def test_judge0_adapter_without_api_key() -> None:
    captured_headers = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured_headers.update(dict(request.headers))
        if "submissions" in str(request.url) and "submissions/" not in str(request.url):
            return httpx.Response(200, json=_make_submission_response("token-123"))
        return httpx.Response(200, json=_make_poll_response())

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = Judge0Adapter(base_url="http://localhost:2358", api_key="", client=client, max_polls=2)
    request = RunRequest(language="python", source="print(1)")
    await adapter.run(request)
    await client.aclose()

    assert "X-Auth-Token" not in captured_headers


@pytest.mark.asyncio
async def test_judge0_adapter_polling_respects_max_polls() -> None:
    responses = [
        httpx.Response(200, json=_make_submission_response("token-123")),
    ] + [httpx.Response(200, json=_make_poll_response(status_id=1)) for _ in range(20)]
    transport = MockTransport(responses)
    client = httpx.AsyncClient(transport=transport)  # type: ignore[arg-type]

    adapter = Judge0Adapter(
        base_url="http://localhost:2358",
        client=client,
        max_polls=3,
        poll_interval_seconds=0.01,
    )
    request = RunRequest(language="python", source="print(1)")

    with pytest.raises(SandboxTimeoutError):
        await adapter.run(request)

    assert transport.call_count == 4
    await client.aclose()


@pytest.mark.asyncio
async def test_judge0_adapter_provided_client_not_closed_by_adapter() -> None:
    responses = [httpx.Response(200, json=_make_submission_response("token-123"))]
    transport = MockTransport(responses)
    client = httpx.AsyncClient(transport=transport)  # type: ignore[arg-type]

    adapter = Judge0Adapter(base_url="http://localhost:2358", client=client, max_polls=1)
    await adapter.aclose()

    assert not client.is_closed


@pytest.mark.asyncio
async def test_judge0_adapter_owns_client_and_closes_it() -> None:
    adapter = Judge0Adapter(base_url="http://localhost:2358", max_polls=1)
    assert adapter._owns_client is True
    await adapter.aclose()


@pytest.mark.asyncio
async def test_judge0_adapter_with_limits_conversion() -> None:
    responses = [
        httpx.Response(200, json=_make_submission_response("token-123")),
        httpx.Response(200, json=_make_poll_response()),
    ]
    transport = MockTransport(responses)
    client = httpx.AsyncClient(transport=transport)  # type: ignore[arg-type]

    adapter = Judge0Adapter(base_url="http://localhost:2358", client=client, max_polls=2)
    request = RunRequest(
        language="python",
        source="print(1)",
        timeout_ms=5000,
        memory_mb=256,
    )
    await adapter.run(request)

    assert transport.call_count == 2
    await client.aclose()


def test_execution_status_values() -> None:
    assert ExecutionStatus.ACCEPTED.value == "accepted"
    assert ExecutionStatus.WRONG_ANSWER.value == "wrong_answer"
    assert ExecutionStatus.COMPILE_ERROR.value == "compile_error"
    assert ExecutionStatus.RUNTIME_ERROR.value == "runtime_error"
    assert ExecutionStatus.TIME_LIMIT_EXCEEDED.value == "time_limit_exceeded"
    assert ExecutionStatus.MEMORY_LIMIT_EXCEEDED.value == "memory_limit_exceeded"
    assert ExecutionStatus.INTERNAL_ERROR.value == "internal_error"