from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class ClientChatMessage(BaseModel):
    type: Literal["chat_message"]
    content: str
    client_timestamp: int


class ClientCodeSnapshotMessage(BaseModel):
    type: Literal["code_snapshot"]
    code: str
    language: Literal["python", "javascript", "sql"]
    reason: Literal["debounce", "run", "blur", "phase_transition"]
    cursor_line: int | None = None
    cursor_column: int | None = None
    client_timestamp: int


class ClientRunCodeMessage(BaseModel):
    type: Literal["run_code"]
    code: str
    language: Literal["python", "javascript", "sql"]


class ClientRequestPhaseTransitionMessage(BaseModel):
    type: Literal["request_phase_transition"]
    target_phase: str
    reason: str | None = None


class ClientIntegrityEventMessage(BaseModel):
    type: Literal["integrity_event"]
    event_type: Literal["blur", "focus", "paste", "paste_large", "tab_switch"]
    metadata: dict | None = None
    client_timestamp: int


class ClientPingMessage(BaseModel):
    type: Literal["ping"]
    client_timestamp: int


ClientWebSocketMessage = (
    ClientChatMessage
    | ClientCodeSnapshotMessage
    | ClientRunCodeMessage
    | ClientRequestPhaseTransitionMessage
    | ClientIntegrityEventMessage
    | ClientPingMessage
)


class ServerAgentTokenMessage(BaseModel):
    type: Literal["agent_token"]
    turn_id: str
    delta: str


class ServerAgentTurnCompleteMessage(BaseModel):
    type: Literal["agent_turn_complete"]
    turn_id: str
    full_content: str
    suggested_transition: str | None = None


class ServerPhaseChangedMessage(BaseModel):
    type: Literal["phase_changed"]
    current_phase: str
    available_transitions: list[str]
    phase_instructions: str | None = None


class ServerCodeExecutionResultMessage(BaseModel):
    type: Literal["code_execution_result"]
    status: Literal["success", "test_failure", "compile_error", "timeout", "runtime_error"]
    stdout: str
    stderr: str
    execution_time_ms: int
    tests_passed: int
    total_tests: int
    test_details: list[dict] | None = None


class ServerSessionTickMessage(BaseModel):
    type: Literal["session_tick"]
    time_remaining_seconds: int
    current_phase: str


class ServerErrorMessage(BaseModel):
    type: Literal["error"]
    code: str
    message: str
    recoverable: bool


class ServerPongMessage(BaseModel):
    type: Literal["pong"]
    client_timestamp: int
    server_timestamp: int


ServerWebSocketMessage = (
    ServerAgentTokenMessage
    | ServerAgentTurnCompleteMessage
    | ServerPhaseChangedMessage
    | ServerCodeExecutionResultMessage
    | ServerSessionTickMessage
    | ServerErrorMessage
    | ServerPongMessage
)