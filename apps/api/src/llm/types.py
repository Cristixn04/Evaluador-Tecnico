from dataclasses import dataclass
from typing import Any, Literal, Protocol

Role = Literal["system", "user", "assistant", "tool"]


@dataclass(frozen=True, slots=True)
class ToolCall:
    id: str
    name: str
    arguments: str
    type: str = "function"


@dataclass(frozen=True, slots=True)
class ChatMessage:
    role: Role
    content: str
    tool_calls: tuple[ToolCall, ...] | list[ToolCall] | None = None
    tool_call_id: str | None = None
    name: str | None = None


@dataclass(frozen=True, slots=True)
class TokenUsage:
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None


@dataclass(frozen=True, slots=True)
class ChatCompletion:
    content: str
    model: str
    usage: TokenUsage
    tool_calls: list[ToolCall] | None = None
    finish_reason: str | None = None


class LLMClient(Protocol):
    async def complete(
        self,
        messages: list[ChatMessage],
        *,
        model: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | dict[str, Any] | None = None,
    ) -> ChatCompletion: ...

    async def aclose(self) -> None: ...
