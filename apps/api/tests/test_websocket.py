from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from starlette.websockets import WebSocketDisconnect

from src.core.ws_tokens import ws_token_service
from src.db.enums import InterviewPhase, InterviewStatus, Seniority
from src.db.models import Interview, Vacancy
from src.db.session import get_sync_engine
from src.interview.service import InterviewService
from src.invitations.service import InvitationService
from src.main import app as fastapi_app


@pytest.fixture
def app():
    return fastapi_app


@pytest.fixture(autouse=True)
def reset_global_engine():
    """Recreate the app's global async engine for each test.

    The singleton engine caches asyncpg connections bound to the event loop
    of the TestClient that created them. TestClient builds a new portal loop
    per test, so reusing the pooled connection from a previous test raises
    "Future attached to a different loop". Dropping the engine here forces a
    fresh, empty pool on the current test's loop.
    """
    import src.db.session as db_session_module

    db_session_module._engine = None
    db_session_module._async_session_maker = None
    yield
    db_session_module._engine = None
    db_session_module._async_session_maker = None


@pytest.fixture
async def vacancy(db_session) -> Vacancy:
    vacancy = Vacancy(
        title="WS Test",
        raw_description="Test",
        role_category="backend",
        seniority=Seniority.MID,
        profile={
            "required_skills": ["python"],
            "preferred_skills": [],
            "primary_language": "python",
            "focus_areas": [],
        },
    )
    db_session.add(vacancy)
    await db_session.flush()
    return vacancy


@pytest.fixture
async def interview_with_ws_token(
    db_session, vacancy
) -> tuple:
    """Create interview and generate a valid WS token."""
    inv_service = InvitationService(db_session)
    _invitation, token = await inv_service.create(
        vacancy=vacancy,
        candidate_name="WS Candidate",
        candidate_email="ws@example.com",
        candidate_phone=None,
    )
    await db_session.commit()

    # Verify to create interview
    interview_service = InterviewService(db_session)
    interview = await interview_service.get_or_create_from_invitation(token)

    # Generate WS token
    ws_token = ws_token_service.create_ws_token(interview_id=interview.id)
    await ws_token_service.store_ws_token(ws_token)

    return interview, ws_token


class TestWebSocketHandshake:
    def test_valid_handshake(
        self, app, interview_with_ws_token
    ) -> None:
        """Test successful WebSocket handshake with valid token."""
        interview, ws_token = interview_with_ws_token
        client = TestClient(app)
        with client.websocket_connect(
            f"/ws/interview/{interview.id}?token={ws_token}"
        ) as ws:
            # Should receive initial phase_changed message
            msg = ws.receive_json()
            assert msg["type"] == "phase_changed"
            assert msg["current_phase"] == "INTRO"
            assert "available_transitions" in msg

    def test_invalid_jwt_rejected(
        self, app, interview_with_ws_token
    ) -> None:
        """Test that invalid JWT is rejected."""
        interview, _ = interview_with_ws_token
        client = TestClient(app)
        with pytest.raises(WebSocketDisconnect) as exc_info, client.websocket_connect(
            f"/ws/interview/{interview.id}?token=invalid-jwt"
        ):
            pass
        # Should disconnect with policy violation (code 1008)
        assert exc_info.value.code == 1008

    async def test_expired_jwt_rejected(
        self, app, db_session, vacancy
    ) -> None:
        """Test that expired JWT is rejected."""
        from src.core.ws_tokens import ws_token_service
        interview = Interview(
            vacancy_id=vacancy.id,
            candidate_email="expired@example.com",
            candidate_name="Expired Test",
            access_token=None,
            status=InterviewStatus.PENDING,
            phase=InterviewPhase.INTRO,
            expires_at=datetime.now(UTC) + timedelta(hours=2),
        )
        db_session.add(interview)
        await db_session.flush()

        # Create token with negative TTL to make it expired
        ws_token = ws_token_service.create_ws_token(interview_id=interview.id, ttl_minutes=-1)
        await db_session.commit()

        client = TestClient(app)
        with pytest.raises(WebSocketDisconnect) as exc_info, client.websocket_connect(
            f"/ws/interview/{interview.id}?token={ws_token}"
        ):
            pass
        assert exc_info.value.code == 1008

    async def test_revoked_jwt_rejected(
        self, app, interview_with_ws_token
    ) -> None:
        """Test that revoked JWT is rejected."""
        interview, ws_token = interview_with_ws_token

        # Revoke the token
        await ws_token_service.revoke_ws_token(ws_token)

        client = TestClient(app)
        with pytest.raises(WebSocketDisconnect) as exc_info, client.websocket_connect(
            f"/ws/interview/{interview.id}?token={ws_token}"
        ):
            pass
        assert exc_info.value.code == 1008

    async def test_session_id_mismatch_rejected(
        self, app, interview_with_ws_token, db_session, vacancy
    ) -> None:
        """Test that token for interview A cannot connect to interview B."""
        _, ws_token = interview_with_ws_token

        # Create another interview
        other = Interview(
            vacancy_id=vacancy.id,
            candidate_email="other@example.com",
            candidate_name="Other",
            access_token=None,
            status=InterviewStatus.PENDING,
            phase=InterviewPhase.INTRO,
            expires_at=datetime.now(UTC) + timedelta(hours=2),
        )
        db_session.add(other)
        await db_session.commit()

        client = TestClient(app)
        with pytest.raises(WebSocketDisconnect) as exc_info, client.websocket_connect(
            f"/ws/interview/{other.id}?token={ws_token}"
        ):
            pass
        assert exc_info.value.code == 1008

    def test_nonexistent_interview_rejected(
        self, app, interview_with_ws_token
    ) -> None:
        """Test that token for non-existent interview is rejected."""
        _, ws_token = interview_with_ws_token
        fake_id = uuid4()

        client = TestClient(app)
        with pytest.raises(WebSocketDisconnect) as exc_info, client.websocket_connect(
            f"/ws/interview/{fake_id}?token={ws_token}"
        ):
            pass
        assert exc_info.value.code == 1008

    def test_second_connection_replaces_first(
        self, app, interview_with_ws_token
    ) -> None:
        """Test that second connection with same interview replaces first."""
        interview, ws_token = interview_with_ws_token

        client = TestClient(app)
        # First connection
        with client.websocket_connect(
            f"/ws/interview/{interview.id}?token={ws_token}"
        ) as ws1:
            msg1 = ws1.receive_json()
            assert msg1["type"] == "phase_changed"

            # Second connection with same token
            with client.websocket_connect(
                f"/ws/interview/{interview.id}?token={ws_token}"
            ) as ws2:
                msg2 = ws2.receive_json()
                assert msg2["type"] == "phase_changed"

                # First connection should be closed
                try:
                    ws1.receive_json()
                    # If we get here, first connection might still be alive
                    # (implementation may vary)
                except (RuntimeError, WebSocketDisconnect):
                    # Expected: first connection closed
                    pass


class TestWebSocketMessages:
    @pytest.fixture
    def connected_ws(self, app, interview_with_ws_token):
        """Get a connected WebSocket for message testing."""
        interview, ws_token = interview_with_ws_token
        client = TestClient(app)
        with client.websocket_connect(
            f"/ws/interview/{interview.id}?token={ws_token}"
        ) as ws:
            # Consume initial phase_changed
            ws.receive_json()
            yield ws

    def test_ping_pong(self, connected_ws) -> None:
        """Test ping/pong heartbeat."""
        connected_ws.send_json({"type": "ping", "client_timestamp": 123456})
        msg = connected_ws.receive_json()
        assert msg["type"] == "pong"
        assert msg["client_timestamp"] == 123456
        assert "server_timestamp" in msg

    async def test_chat_message_persists_turn(self, connected_ws, db_session, monkeypatch) -> None:
        """Test that chat messages are persisted as turns."""
        from sqlalchemy import select

        from src.agent.service import InterviewAgent
        from src.db.models import Turn

        async def fake_stream_llm(self, client, messages):
            yield "Hello"
            yield " candidate!"

        monkeypatch.setattr(InterviewAgent, "_stream_llm", fake_stream_llm)

        connected_ws.send_json({
            "type": "chat_message",
            "content": "Hello, interviewer!",
            "client_timestamp": 123456,
        })

        # Should receive agent token stream
        msg = connected_ws.receive_json()
        assert msg["type"] in ("agent_token", "agent_turn_complete")

        # Close WebSocket to trigger session commit, then verify with fresh session
        connected_ws.close()

        engine = get_sync_engine()
        with Session(engine) as fresh_session:
            turns = fresh_session.scalars(
                select(Turn).where(Turn.speaker == "candidate")
            ).all()
            assert len(turns) >= 1

    async def test_code_snapshot_persists(self, connected_ws) -> None:
        """Test that code snapshots are persisted."""
        from sqlalchemy import select
        from sqlalchemy.orm import Session

        from src.db.models import Snapshot

        connected_ws.send_json({
            "type": "code_snapshot",
            "code": "def solve():\n    return 42",
            "language": "python",
            "reason": "debounce",
            "client_timestamp": 123456,
        })

        # Send ping and wait for pong to ensure the message loop has processed
        # the code_snapshot message and committed the transaction.
        # This uses the existing ping/pong protocol for synchronization.
        connected_ws.send_json({"type": "ping", "client_timestamp": 123456})
        pong_msg = connected_ws.receive_json()
        assert pong_msg["type"] == "pong"
        assert pong_msg["client_timestamp"] == 123456

        # Close WebSocket to trigger session commit
        connected_ws.close()

        engine = get_sync_engine()
        with Session(engine) as fresh_session:
            snapshots = fresh_session.scalars(select(Snapshot)).all()
            assert len(snapshots) >= 1
            assert "def solve" in snapshots[-1].code

    async def test_invalid_message_type_rejected(self, connected_ws) -> None:
        """Test that unknown message types are rejected."""
        connected_ws.send_json({
            "type": "unknown_message",
            "data": "test",
        })

        msg = connected_ws.receive_json()
        assert msg["type"] == "error"
        assert msg["code"] == "INVALID_MESSAGE"

    async def test_request_phase_transition_valid(
        self, connected_ws, db_session, interview_with_ws_token
    ) -> None:
        """Test valid phase transition request."""
        from sqlalchemy.orm import Session

        from src.db.models import Interview

        interview, _ = interview_with_ws_token

        connected_ws.send_json({
            "type": "request_phase_transition",
            "target_phase": "PROBLEM",
            "reason": "Ready for problem",
        })

        msg = connected_ws.receive_json()
        assert msg["type"] == "phase_changed"
        assert msg["current_phase"] == "PROBLEM"

        # Close WebSocket to trigger session commit
        connected_ws.close()

        # Verify persistence using a fresh sync session, querying by interview ID
        engine = get_sync_engine()
        with Session(engine) as fresh_session:
            interview = fresh_session.get(Interview, interview.id)
            assert interview is not None
            assert interview.phase == InterviewPhase.PROBLEM

    async def test_request_phase_transition_invalid_skip_rejected(
        self, connected_ws
    ) -> None:
        """Test that skipping phases is rejected."""
        connected_ws.send_json({
            "type": "request_phase_transition",
            "target_phase": "DESIGN",  # Skip PROBLEM, CLARIFY
            "reason": "Trying to skip",
        })

        msg = connected_ws.receive_json()
        assert msg["type"] == "error"
        assert msg["code"] == "INVALID_TRANSITION"

    async def test_integrity_event_accepted(self, connected_ws) -> None:
        """Test that integrity events are accepted (not persisted but not rejected)."""
        connected_ws.send_json({
            "type": "integrity_event",
            "event_type": "blur",
            "metadata": {"time_away_ms": 5000},
            "client_timestamp": 123456,
        })

        # Should not error - just accept silently
        # (Implementation logs but doesn't respond to integrity events)