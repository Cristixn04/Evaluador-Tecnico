import asyncio
from collections.abc import Mapping
from typing import Any

import httpx

from src.sandbox.exceptions import (
    SandboxConfigurationError,
    SandboxInvalidResponseError,
    SandboxProviderError,
    SandboxTimeoutError,
)
from src.sandbox.types import ExecutionStatus, RunRequest, RunResult

# Judge0 CE language ids. Limits sent as cpu_time_limit / memory_limit are
# requests only: the provider may cap or ignore them.
LANGUAGE_IDS = {
    "python": 71,
    "javascript": 63,
    "sql": 82,
}

_PENDING_STATUS_IDS = {1, 2}
_STATUS_MAP = {
    3: ExecutionStatus.ACCEPTED,
    4: ExecutionStatus.WRONG_ANSWER,
    5: ExecutionStatus.TIME_LIMIT_EXCEEDED,
    6: ExecutionStatus.COMPILE_ERROR,
    7: ExecutionStatus.RUNTIME_ERROR,
    8: ExecutionStatus.RUNTIME_ERROR,
    9: ExecutionStatus.RUNTIME_ERROR,
    10: ExecutionStatus.RUNTIME_ERROR,
    11: ExecutionStatus.RUNTIME_ERROR,
    12: ExecutionStatus.RUNTIME_ERROR,
    13: ExecutionStatus.INTERNAL_ERROR,
    14: ExecutionStatus.INTERNAL_ERROR,
    137: ExecutionStatus.MEMORY_LIMIT_EXCEEDED,
}


class Judge0Adapter:
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str = "",
        timeout_seconds: float = 15.0,
        poll_interval_seconds: float = 0.2,
        max_polls: int = 50,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if not base_url:
            raise SandboxConfigurationError("Judge0 base URL is not configured")
        if max_polls < 1:
            raise SandboxConfigurationError("Judge0 max polls must be at least 1")

        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._timeout = timeout_seconds
        self._poll_interval = poll_interval_seconds
        self._max_polls = max_polls
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(timeout=timeout_seconds)

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def run(self, request: RunRequest) -> RunResult:
        language_id = LANGUAGE_IDS.get(request.language.strip().casefold())
        if language_id is None:
            raise SandboxConfigurationError(f"Unsupported language: {request.language}")

        token = await self._submit(request, language_id)
        body = await self._poll(token)
        return self._parse_result(body)

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["X-Auth-Token"] = self._api_key
        return headers

    async def _submit(self, request: RunRequest, language_id: int) -> str:
        payload: dict[str, Any] = {
            "source_code": request.source,
            "language_id": language_id,
            "stdin": request.stdin,
            "cpu_time_limit": max(request.timeout_ms / 1000, 0.1),
            "wall_time_limit": max(request.timeout_ms / 1000, 0.1) + 1,
            "memory_limit": request.memory_mb * 1000,
        }
        if request.expected_output is not None:
            payload["expected_output"] = request.expected_output

        try:
            response = await self._client.post(
                f"{self._base_url}/submissions",
                params={"base64_encoded": "false", "wait": "false"},
                json=payload,
                headers=self._headers(),
            )
        except httpx.TimeoutException as exc:
            raise SandboxTimeoutError("Judge0 submit timed out") from exc
        except httpx.HTTPError as exc:
            raise SandboxProviderError("Judge0 submit failed") from exc

        if response.status_code >= 400:
            raise SandboxProviderError(f"Judge0 submit error ({response.status_code})")

        body = _as_mapping(response.json(), "submit")
        token = body.get("token")
        if not isinstance(token, str) or not token:
            raise SandboxInvalidResponseError("Judge0 submit response has no token")
        return token

    async def _poll(self, token: str) -> Mapping[str, Any]:
        url = f"{self._base_url}/submissions/{token}"
        for _ in range(self._max_polls):
            try:
                response = await self._client.get(
                    url,
                    params={"base64_encoded": "false"},
                    headers=self._headers(),
                )
            except httpx.TimeoutException as exc:
                raise SandboxTimeoutError("Judge0 poll timed out") from exc
            except httpx.HTTPError as exc:
                raise SandboxProviderError("Judge0 poll failed") from exc

            if response.status_code >= 400:
                raise SandboxProviderError(f"Judge0 poll error ({response.status_code})")

            body = _as_mapping(response.json(), "poll")
            status_id = _status_id(body)
            if status_id not in _PENDING_STATUS_IDS:
                return body
            await asyncio.sleep(self._poll_interval)

        raise SandboxTimeoutError("Judge0 polling exhausted")

    def _parse_result(self, body: Mapping[str, Any]) -> RunResult:
        status_id = _status_id(body)
        status = _STATUS_MAP.get(status_id, ExecutionStatus.INTERNAL_ERROR)
        time_raw = body.get("time")
        memory_raw = body.get("memory")
        exit_raw = body.get("exit_code")
        return RunResult(
            status=status,
            stdout=_as_text(body.get("stdout")),
            stderr=_as_text(body.get("stderr")),
            compile_output=_as_text(body.get("compile_output")),
            exit_code=_as_optional_int(exit_raw),
            time_seconds=_as_optional_float(time_raw),
            memory_kb=_as_optional_int(memory_raw),
            provider_status_id=status_id,
        )


def _as_mapping(value: Any, where: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise SandboxInvalidResponseError(f"Judge0 {where} response is not an object")
    return value


def _status_id(body: Mapping[str, Any]) -> int:
    status = body.get("status")
    if not isinstance(status, Mapping):
        raise SandboxInvalidResponseError("Judge0 status is invalid")
    status_id = status.get("id")
    if not isinstance(status_id, int) or isinstance(status_id, bool):
        raise SandboxInvalidResponseError("Judge0 status id is invalid")
    return status_id


def _as_text(value: Any) -> str:
    return value if isinstance(value, str) else ""


def _as_optional_int(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _as_optional_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None
