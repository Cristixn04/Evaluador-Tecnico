from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING
from uuid import UUID

from fastapi import WebSocket
from pydantic import ValidationError

from src.api.schemas.websocket import (
    ClientChatMessage,
    ClientCodeSnapshotMessage,
    ClientIntegrityEventMessage,
    ClientPingMessage,
    ClientRequestPhaseTransitionMessage,
    ClientRunCodeMessage,
    ClientWebSocketMessage,
    ServerAgentTokenMessage,
    ServerCodeExecutionResultMessage,
    ServerErrorMessage,
    ServerPhaseChangedMessage,
    ServerPongMessage,
)

if TYPE_CHECKING:
    from src.agent.service import InterviewAgent
    from src.execution.service import CodeExecutionService
    from src.interview.service import InterviewService


class ConnectionManager:
    def __init__(self) -> None:
        self._connections: dict[UUID, WebSocket] = {}
        self._interview_sessions: dict[UUID, dict] = {}

    async def connect(self, interview_id: UUID, websocket: WebSocket) -> None:
        await websocket.accept()
        # Close existing connection if any
        if interview_id in self._connections:
            old_ws = self._connections[interview_id]
            try:
                await old_ws.close(code=1000, reason="New connection established")
            except Exception:  # noqa: BLE001, S110
                pass
        self._connections[interview_id] = websocket
        self._interview_sessions[interview_id] = {
            "websocket": websocket,
            "connected_at": asyncio.get_event_loop().time(),
        }

    def disconnect(self, interview_id: UUID) -> None:
        self._connections.pop(interview_id, None)
        self._interview_sessions.pop(interview_id, None)

    async def send(self, interview_id: UUID, message: dict) -> bool:
        websocket = self._connections.get(interview_id)
        if websocket is None:
            return False
        try:
            await websocket.send_json(message)
            return True
        except Exception:  # noqa: BLE001
            self.disconnect(interview_id)
            return False

    async def send_error(self, interview_id: UUID, code: str, message: str, recoverable: bool = True) -> None:
        error_msg = ServerErrorMessage(type="error", code=code, message=message, recoverable=recoverable)
        await self.send(interview_id, error_msg.model_dump())

    def is_connected(self, interview_id: UUID) -> bool:
        return interview_id in self._connections


class MessageDispatcher:
    def __init__(
        self,
        manager: ConnectionManager,
        interview_service: InterviewService,
        agent: InterviewAgent,
        execution_service: CodeExecutionService,
    ) -> None:
        self._manager = manager
        self._interview_service = interview_service
        self._agent = agent
        self._execution_service = execution_service

    async def dispatch(self, interview_id: UUID, raw_message: dict) -> None:
        try:
            message = self._parse_message(raw_message)
        except ValidationError as e:
            await self._manager.send_error(interview_id, "INVALID_MESSAGE", f"Invalid message format: {e}")
            return

        if isinstance(message, ClientPingMessage):
            await self._handle_ping(interview_id, message)
        elif isinstance(message, ClientChatMessage):
            await self._handle_chat(interview_id, message)
        elif isinstance(message, ClientCodeSnapshotMessage):
            await self._handle_code_snapshot(interview_id, message)
        elif isinstance(message, ClientRunCodeMessage):
            await self._handle_run_code(interview_id, message)
        elif isinstance(message, ClientRequestPhaseTransitionMessage):
            await self._handle_phase_transition(interview_id, message)
        elif isinstance(message, ClientIntegrityEventMessage):
            await self._handle_integrity_event(interview_id, message)
        else:
            await self._manager.send_error(interview_id, "UNKNOWN_MESSAGE_TYPE", "Unknown message type")

    def _parse_message(self, raw: dict) -> ClientWebSocketMessage:
        msg_type = raw.get("type")
        if msg_type == "chat_message":
            return ClientChatMessage.model_validate(raw)
        elif msg_type == "code_snapshot":
            return ClientCodeSnapshotMessage.model_validate(raw)
        elif msg_type == "run_code":
            return ClientRunCodeMessage.model_validate(raw)
        elif msg_type == "request_phase_transition":
            return ClientRequestPhaseTransitionMessage.model_validate(raw)
        elif msg_type == "integrity_event":
            return ClientIntegrityEventMessage.model_validate(raw)
        elif msg_type == "ping":
            return ClientPingMessage.model_validate(raw)
        else:
            # Use a proper ValidationError with error details for pydantic v2
            from pydantic_core import InitErrorDetails
            raise ValidationError.from_exception_data(
                title="ClientWebSocketMessage",
                line_errors=[
                    InitErrorDetails(
                        type="literal_error",
                        loc=("type",),
                        input=msg_type,
                        ctx={"expected": "one of the valid message types"},
                    )
                ],
            )

    async def _handle_ping(self, interview_id: UUID, message: ClientPingMessage) -> None:
        pong = ServerPongMessage(
            type="pong",
            client_timestamp=message.client_timestamp,
            server_timestamp=int(asyncio.get_event_loop().time() * 1000),
        )
        await self._manager.send(interview_id, pong.model_dump())

    async def _handle_chat(self, interview_id: UUID, message: ClientChatMessage) -> None:
        # Persist candidate turn
        from src.db.enums import TurnSpeaker
        from src.db.models import Interview, Turn

        # Get interview to persist turn
        interview = await self._interview_service._session.get(
            Interview, interview_id
        )
        if interview:
            turn = Turn(
                interview_id=interview_id,
                speaker=TurnSpeaker.CANDIDATE,
                content=message.content,
            )
            self._interview_service._session.add(turn)
            await self._interview_service._session.flush()
            await self._interview_service._session.commit()

        # Generate agent response
        try:
            async for delta in self._agent.stream_response(
                interview_id=interview_id,
                user_message=message.content,
            ):
                # Send streaming tokens
                token_msg = ServerAgentTokenMessage(
                    type="agent_token",
                    turn_id="",  # Will be filled by agent
                    delta=delta,
                )
                await self._manager.send(interview_id, token_msg.model_dump())
        except Exception as e:  # noqa: BLE001
            await self._manager.send_error(interview_id, "AGENT_ERROR", f"Agent error: {e}")

    async def _handle_code_snapshot(self, interview_id: UUID, message: ClientCodeSnapshotMessage) -> None:
        # Persist snapshot
        from src.db.models import Interview, Snapshot

        interview = await self._interview_service._session.get(Interview, interview_id)
        if not interview:
            return

        snapshot = Snapshot(
            interview_id=interview_id,
            code=message.code,
            phase=interview.phase.value,
            language=message.language,
            reason=message.reason,
        )
        self._interview_service._session.add(snapshot)
        await self._interview_service._session.flush()
        await self._interview_service._session.commit()

    async def _handle_run_code(self, interview_id: UUID, message: ClientRunCodeMessage) -> None:
        try:
            result = await self._execution_service.execute_code(
                interview_id=interview_id,
                code=message.code,
                language=message.language,
            )
            exec_msg = ServerCodeExecutionResultMessage(**result)
            await self._manager.send(interview_id, exec_msg.model_dump())
        except Exception as e:  # noqa: BLE001
            await self._manager.send_error(interview_id, "EXECUTION_ERROR", f"Code execution failed: {e}")

    async def _handle_phase_transition(self, interview_id: UUID, message: ClientRequestPhaseTransitionMessage) -> None:
        from src.db.enums import InterviewPhase
        from src.db.models import Interview
        from src.interview.exceptions import InterviewPhaseTransitionError

        try:
            target_phase = InterviewPhase(message.target_phase)
        except ValueError:
            await self._manager.send_error(interview_id, "INVALID_PHASE", f"Invalid phase: {message.target_phase}")
            return

        interview = await self._interview_service._session.get(Interview, interview_id)
        if not interview:
            await self._manager.send_error(interview_id, "INTERVIEW_NOT_FOUND", "Interview not found")
            return

        try:
            interview = await self._interview_service.transition_phase(interview, target_phase, reason=message.reason)
        except InterviewPhaseTransitionError as e:
            await self._manager.send_error(interview_id, "INVALID_TRANSITION", str(e))
            return

        # Send phase changed message
        phase_msg = ServerPhaseChangedMessage(
            type="phase_changed",
            current_phase=interview.phase.value,
            available_transitions=[p.value for p in self._interview_service.get_available_transitions(interview.phase)],
        )
        await self._manager.send(interview_id, phase_msg.model_dump())

    async def _handle_integrity_event(self, interview_id: UUID, message: ClientIntegrityEventMessage) -> None:
        # Log integrity event (not persisted to DB per ADR-0008 DR-10)
        # Could be sent to monitoring/logging system
        pass


# Global connection manager
connection_manager = ConnectionManager()