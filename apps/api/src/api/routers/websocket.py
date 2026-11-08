from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.agent.service import InterviewAgent
from src.core.ws_tokens import (
    WSTokenError,
    WSTokenExpiredError,
    WSTokenInvalidError,
    WSTokenRevokedError,
    ws_token_service,
)
from src.db.session import get_db
from src.execution.service import CodeExecutionService
from src.interview.service import InterviewService
from src.invitations.service import InvitationService
from src.problems.selector import ProblemSelector
from src.ws.manager import MessageDispatcher, connection_manager

router = APIRouter(prefix="/ws", tags=["WebSocket"])


async def get_ws_interview_id(
    token: str = Query(...),
    session: AsyncSession = Depends(get_db),
) -> UUID:
    """Validate WS token and return interview_id (session_id)."""
    try:
        interview_id = await ws_token_service.validate_ws_token(token)
        return interview_id
    except WSTokenExpiredError:
        raise WebSocketDisconnect(code=status.WS_1008_POLICY_VIOLATION, reason="Token expired")
    except WSTokenRevokedError:
        raise WebSocketDisconnect(code=status.WS_1008_POLICY_VIOLATION, reason="Token revoked")
    except WSTokenInvalidError:
        raise WebSocketDisconnect(code=status.WS_1008_POLICY_VIOLATION, reason="Invalid token")
    except WSTokenError:
        raise WebSocketDisconnect(code=status.WS_1011_INTERNAL_ERROR, reason="Token validation failed")


@router.websocket("/interview/{interview_id}")
async def websocket_interview(
    websocket: WebSocket,
    interview_id: UUID,
    token: str | None = Query(default=None),
    session: AsyncSession = Depends(get_db),
) -> None:
    # 1. Reject if token is missing
    if not token:
        await websocket.accept()
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Missing token")
        return

    # 2. Validate token
    try:
        validated_interview_id = await ws_token_service.validate_ws_token(token)
    except WSTokenExpiredError:
        await websocket.accept()
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Token expired")
        return
    except WSTokenRevokedError:
        await websocket.accept()
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Token revoked")
        return
    except (WSTokenInvalidError, WSTokenError):
        await websocket.accept()
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Invalid token")
        return

    # 3. Verify interview_id matches token
    if interview_id != validated_interview_id:
        await websocket.accept()
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Session ID mismatch")
        return

    # 4. Load interview to verify it exists
    from src.db.models import Interview

    interview = await session.get(Interview, interview_id)
    if not interview:
        await websocket.accept()
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Interview not found")
        return

    # 5. Connect
    await connection_manager.connect(interview_id, websocket)

    # Initialize services
    InvitationService(session)
    interview_service = InterviewService(session)
    problem_selector = ProblemSelector(session)
    agent = InterviewAgent(session, interview_service, problem_selector)
    execution_service = CodeExecutionService(session, interview_service)

    # Initialize dispatcher
    dispatcher = MessageDispatcher(connection_manager, interview_service, agent, execution_service)

    try:
        # Send initial phase state
        phase_msg = {
            "type": "phase_changed",
            "current_phase": interview.phase.value,
            "available_transitions": [p.value for p in interview_service.get_available_transitions(interview.phase)],
        }
        await connection_manager.send(interview_id, phase_msg)

        # Message loop
        while True:
            data = await websocket.receive_json()
            await dispatcher.dispatch(interview_id, data)

    except WebSocketDisconnect:
        pass
    except Exception as e:  # noqa: BLE001
        await connection_manager.send_error(interview_id, "INTERNAL_ERROR", f"Server error: {e}")
    finally:
        connection_manager.disconnect(interview_id)
        await agent.aclose()
        await execution_service.close()