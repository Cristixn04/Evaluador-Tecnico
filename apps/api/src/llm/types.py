from dataclasses import dataclass
from typing import Literal, Protocol

Role = Literal["system", "user", "assistant"]


@dataclass(frozen=True, slots=True)
class ChatMessage:
    role: Role
    content: str


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


class LLMClient(Protocol):
    async def complete(
        self,
        messages: list[ChatMessage],
        *,
        model: str | None = None,
    ) -> ChatCompletion: ...
