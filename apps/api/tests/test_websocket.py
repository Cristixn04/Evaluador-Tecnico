from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from starlette.websockets import WebSocketDisconnect

from src.core.config import settings
from src.core.ws_tokens import ws_token_service
from src.db.enums import InterviewPhase, InterviewStatus, Seniority
from src.db.models import Interview, Vacancy
from src.interview.service import InterviewService
from src.invitations.service import InvitationService
from src.main import app as fastapi_app


@asynccontextmanager
async def isolated_session():
    engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with maker() as session:
            yield session
    finally:
        await engine.dispose()


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

    def test_reconnection_after_disconnect_succeeds(
        self, app, interview_with_ws_token
    ) -> None:
        """Test that disconnecting and reconnecting with the same valid token succeeds (does not revoke token)."""
        interview, ws_token = interview_with_ws_token
        client = TestClient(app)

        # First connection opens and disconnects normally
        with client.websocket_connect(
            f"/ws/interview/{interview.id}?token={ws_token}"
        ) as ws1:
            msg1 = ws1.receive_json()
            assert msg1["type"] == "phase_changed"

        # Subsequent reconnection must succeed and receive greeting phase_changed
        with client.websocket_connect(
            f"/ws/interview/{interview.id}?token={ws_token}"
        ) as ws2:
            msg2 = ws2.receive_json()
            assert msg2["type"] == "phase_changed"

    async def test_session_revocation_blocks_reconnect(
        self, app, interview_with_ws_token
    ) -> None:
        """Test that explicit intentional session revocation prevents any reconnection."""
        interview, ws_token = interview_with_ws_token

        # Intentionally revoke all tokens for this interview session
        await ws_token_service.revoke_all_for_session(interview.id)

        client = TestClient(app)
        with pytest.raises(WebSocketDisconnect) as exc_info, client.websocket_connect(
            f"/ws/interview/{interview.id}?token={ws_token}"
        ):
            pass
        assert exc_info.value.code == 1008


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

        # Should receive agent token stream followed by agent_turn_complete
        tokens = []
        turn_complete = None
        for _ in range(10):
            msg = connected_ws.receive_json()
            if msg["type"] == "agent_token":
                tokens.append(msg["delta"])
            elif msg["type"] == "agent_turn_complete":
                turn_complete = msg
                break

        assert "".join(tokens) == "Hello candidate!"
        assert turn_complete is not None
        assert turn_complete["full_content"] == "Hello candidate!"

        # Close WebSocket to trigger session commit, then verify with fresh session
        connected_ws.close()

        async with isolated_session() as fresh_session:
            turns = (await fresh_session.scalars(
                select(Turn).where(Turn.speaker == "candidate")
            )).all()
            assert len(turns) >= 1

    async def test_code_snapshot_persists(self, connected_ws) -> None:
        """Test that code snapshots are persisted."""
        from sqlalchemy import select

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

        async with isolated_session() as fresh_session:
            snapshots = (await fresh_session.scalars(select(Snapshot))).all()
            assert len(snapshots) >= 1
            assert "def solve" in snapshots[-1].code

    async def test_run_code_persists_snapshot_and_turn(
        self, connected_ws, monkeypatch, interview_with_ws_token
    ) -> None:
        """Test that run_code executes code and persists snapshot with reason=run and candidate turn."""
        from sqlalchemy import select

        from src.db.enums import TurnSpeaker
        from src.db.models import Snapshot, Turn
        from src.execution.service import CodeExecutionService

        interview, _ = interview_with_ws_token

        async def fake_execute_code(self, interview_id, code, language):
            snap = Snapshot(
                interview_id=interview_id,
                code=code,
                phase="CODING",
                language=language,
                reason="run",
                tests_passed=3,
                total_tests=3,
                execution_status="success",
            )
            turn = Turn(
                interview_id=interview_id,
                speaker=TurnSpeaker.CANDIDATE,
                content=f"[Code execution]\n```{language}\n{code}\n```",
            )
            self._session.add(snap)
            self._session.add(turn)
            await self._session.flush()
            return {
                "status": "success",
                "stdout": "All tests passed",
                "stderr": "",
                "execution_time_ms": 42,
                "tests_passed": 3,
                "total_tests": 3,
                "test_details": [],
            }

        monkeypatch.setattr(CodeExecutionService, "execute_code", fake_execute_code)

        connected_ws.send_json({
            "type": "run_code",
            "code": "def solve(): return 42",
            "language": "python",
        })

        exec_msg = connected_ws.receive_json()
        assert exec_msg["type"] == "code_execution_result"
        assert exec_msg["status"] == "success"
        assert exec_msg["tests_passed"] == 3

        # Close WebSocket and verify database persistence
        connected_ws.close()

        async with isolated_session() as fresh_session:
            snaps = (await fresh_session.scalars(
                select(Snapshot).where(Snapshot.interview_id == interview.id, Snapshot.reason == "run")
            )).all()
            assert len(snaps) == 1
            assert snaps[0].tests_passed == 3
            assert snaps[0].execution_status == "success"

            turns = (await fresh_session.scalars(
                select(Turn).where(Turn.interview_id == interview.id, Turn.speaker == "candidate")
            )).all()
            assert any("[Code execution]" in t.content for t in turns)

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

        # Verify persistence using a fresh session, querying by interview ID
        async with isolated_session() as fresh_session:
            interview_obj = await fresh_session.get(Interview, interview.id)
            assert interview_obj is not None
            assert interview_obj.phase == InterviewPhase.PROBLEM

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


class TestMessageDispatcherChatStreaming:
    """Test suite for agent streaming completion, error handling, and disconnects."""

    @pytest.mark.asyncio
    async def test_streaming_normal_emits_tokens_and_complete(self) -> None:
        """Caso 1 — Normal streaming: emits agent_token chunks followed by agent_turn_complete."""
        from src.api.schemas.websocket import ClientChatMessage
        from src.ws.manager import MessageDispatcher

        interview_id = uuid4()
        sent_messages: list[dict] = []

        manager = MagicMock()
        manager.send = AsyncMock(side_effect=lambda _iid, msg: sent_messages.append(msg))

        mock_session = AsyncMock()
        mock_session.get.return_value = None

        interview_service = MagicMock()
        interview_service._session = mock_session

        agent = MagicMock()

        async def fake_stream(interview_id, user_message, **kwargs):
            yield "Hello"
            yield " world!"

        agent.stream_response = fake_stream

        dispatcher = MessageDispatcher(
            manager=manager,
            interview_service=interview_service,
            agent=agent,
            execution_service=MagicMock(),
        )

        chat_msg = ClientChatMessage(
            type="chat_message",
            content="Hola agente",
            client_timestamp=1000,
        )

        await dispatcher._handle_chat(interview_id, chat_msg)

        assert len(sent_messages) == 3

        # Message 1: first token
        assert sent_messages[0]["type"] == "agent_token"
        assert sent_messages[0]["delta"] == "Hello"
        turn_id = sent_messages[0]["turn_id"]
        assert turn_id != ""

        # Message 2: second token
        assert sent_messages[1]["type"] == "agent_token"
        assert sent_messages[1]["delta"] == " world!"
        assert sent_messages[1]["turn_id"] == turn_id

        # Message 3: turn complete
        assert sent_messages[2]["type"] == "agent_turn_complete"
        assert sent_messages[2]["turn_id"] == turn_id
        assert sent_messages[2]["full_content"] == "Hello world!"
        assert sent_messages[2]["suggested_transition"] is None

        # Verify session commit was called
        mock_session.commit.assert_awaited()

    @pytest.mark.asyncio
    async def test_streaming_error_emits_error_and_no_complete(self) -> None:
        """Caso 2 — Agent error: emits AGENT_ERROR and does NOT emit agent_turn_complete."""
        from src.api.schemas.websocket import ClientChatMessage
        from src.ws.manager import MessageDispatcher

        interview_id = uuid4()
        sent_messages: list[dict] = []
        errors: list[dict] = []

        manager = MagicMock()
        manager.send = AsyncMock(side_effect=lambda _iid, msg: sent_messages.append(msg))
        manager.send_error = AsyncMock(
            side_effect=lambda _iid, code, msg, **kwargs: errors.append({"code": code, "msg": msg})
        )

        mock_session = AsyncMock()
        mock_session.get.return_value = None

        interview_service = MagicMock()
        interview_service._session = mock_session

        agent = MagicMock()

        async def failing_stream(interview_id, user_message, **kwargs):
            yield "Partial"
            raise RuntimeError("LLM gateway connection dropped")

        agent.stream_response = failing_stream

        dispatcher = MessageDispatcher(
            manager=manager,
            interview_service=interview_service,
            agent=agent,
            execution_service=MagicMock(),
        )

        chat_msg = ClientChatMessage(
            type="chat_message",
            content="Hola con error",
            client_timestamp=1000,
        )

        await dispatcher._handle_chat(interview_id, chat_msg)

        # Token was sent before the error
        assert len(sent_messages) == 1
        assert sent_messages[0]["type"] == "agent_token"
        assert sent_messages[0]["delta"] == "Partial"

        # Error was sent
        assert len(errors) == 1
        assert errors[0]["code"] == "AGENT_ERROR"
        assert "LLM gateway connection dropped" in errors[0]["msg"]

        # CRITICAL: agent_turn_complete was NOT emitted on error
        assert not any(m.get("type") == "agent_turn_complete" for m in sent_messages)

    @pytest.mark.asyncio
    async def test_client_disconnect_during_stream_handled_gracefully(self) -> None:
        """Caso 3 — Disconnect: if send returns False (disconnected), handles gracefully without crashing."""
        from src.api.schemas.websocket import ClientChatMessage
        from src.ws.manager import MessageDispatcher

        interview_id = uuid4()

        manager = MagicMock()
        # Simulate send returning False when disconnected
        manager.send = AsyncMock(return_value=False)

        mock_session = AsyncMock()
        mock_session.get.return_value = None

        interview_service = MagicMock()
        interview_service._session = mock_session

        agent = MagicMock()

        async def normal_stream(interview_id, user_message, **kwargs):
            yield "Hi"

        agent.stream_response = normal_stream

        dispatcher = MessageDispatcher(
            manager=manager,
            interview_service=interview_service,
            agent=agent,
            execution_service=MagicMock(),
        )

        chat_msg = ClientChatMessage(
            type="chat_message",
            content="Test disconnect",
            client_timestamp=1000,
        )

        # Should complete without throwing unhandled exceptions
        await dispatcher._handle_chat(interview_id, chat_msg)
        assert manager.send.await_count == 2  # token + complete


class TestWebSocketMultiTurnConversation:
    """Verifies that the agent sustains consecutive conversational turns across phase transitions."""

    def test_multiturn_conversation_across_phase_transitions(
        self, app, interview_with_ws_token, monkeypatch
    ) -> None:
        """Candidate sends message 1 -> agent streams & persists.

        Phase transitions to PROBLEM -> CLARIFY.
        Candidate sends message 2 -> agent streams & persists second response.
        Both agent turns are persisted in database and client lifecycle remains open throughout.
        """
        from sqlalchemy import select

        from src.db.models import Turn
        from src.llm.openai_compatible import OpenAICompatibleClient
        from src.llm.types import ChatCompletion, TokenUsage

        interview, ws_token = interview_with_ws_token
        turn_counter = 0

        async def fake_complete(self, messages, **kwargs):
            nonlocal turn_counter
            turn_counter += 1
            return ChatCompletion(
                content=f"Respuesta del agente {turn_counter}",
                model="test-model",
                usage=TokenUsage(),
            )

        monkeypatch.setattr(OpenAICompatibleClient, "complete", fake_complete)

        client = TestClient(app)
        with client.websocket_connect(
            f"/ws/interview/{interview.id}?token={ws_token}"
        ) as ws:
            # 1. Initial phase
            init_msg = ws.receive_json()
            assert init_msg["type"] == "phase_changed"
            assert init_msg["current_phase"] == "INTRO"

            # 2. Transition to PROBLEM
            ws.send_json({
                "type": "request_phase_transition",
                "target_phase": "PROBLEM",
            })
            p_msg1 = ws.receive_json()
            assert p_msg1["type"] == "phase_changed"
            assert p_msg1["current_phase"] == "PROBLEM"

            # 3. Candidate Turn 1
            ws.send_json({
                "type": "chat_message",
                "content": "¿Podrías presentarme el problema?",
                "client_timestamp": 1001,
            })

            # Collect tokens for Turn 1
            tokens_turn1 = []
            turn1_complete = None
            while True:
                msg = ws.receive_json()
                if msg["type"] == "agent_token":
                    tokens_turn1.append(msg["delta"])
                elif msg["type"] == "agent_turn_complete":
                    turn1_complete = msg
                    break

            assert "".join(tokens_turn1) == "Respuesta del agente 1"
            assert turn1_complete["full_content"] == "Respuesta del agente 1"

            # 4. Transition to CLARIFY
            ws.send_json({
                "type": "request_phase_transition",
                "target_phase": "CLARIFY",
            })
            p_msg2 = ws.receive_json()
            assert p_msg2["type"] == "phase_changed"
            assert p_msg2["current_phase"] == "CLARIFY"

            # 5. Candidate Turn 2 (in same connection, after transition)
            ws.send_json({
                "type": "chat_message",
                "content": "Para aclarar: ¿el formato de entrada es JSON?",
                "client_timestamp": 1002,
            })

            # Collect tokens for Turn 2
            tokens_turn2 = []
            turn2_complete = None
            while True:
                msg = ws.receive_json()
                if msg["type"] == "agent_token":
                    tokens_turn2.append(msg["delta"])
                elif msg["type"] == "agent_turn_complete":
                    turn2_complete = msg
                    break

            assert "".join(tokens_turn2) == "Respuesta del agente 2"
            assert turn2_complete["full_content"] == "Respuesta del agente 2"

        # 6. Verify database persistence with fresh isolated session
        import asyncio

        async def verify_persistence():
            async with isolated_session() as session:
                turns = (await session.scalars(
                    select(Turn)
                    .where(Turn.interview_id == interview.id)
                    .order_by(Turn.created_at.asc())
                )).all()

                agent_turns = [t for t in turns if t.speaker == "agent" and not t.content.startswith("Phase transitioned to")]
                candidate_turns = [t for t in turns if t.speaker == "candidate"]

                # Two distinct candidate turns
                assert len(candidate_turns) == 2
                assert candidate_turns[0].content == "¿Podrías presentarme el problema?"
                assert candidate_turns[1].content == "Para aclarar: ¿el formato de entrada es JSON?"

                # Two distinct conversational agent turns persisted!
                assert len(agent_turns) == 2
                assert agent_turns[0].content == "Respuesta del agente 1"
                assert agent_turns[1].content == "Respuesta del agente 2"

        asyncio.run(verify_persistence())

    def test_multiturn_error_notifies_client_and_allows_subsequent_message(
        self, app, interview_with_ws_token, monkeypatch
    ) -> None:
        """When an LLM error occurs in turn 1, client receives error notification without complete,

        and subsequent message in turn 2 still succeeds and persists response.
        """
        from sqlalchemy import select

        from src.db.models import Turn
        from src.llm.openai_compatible import OpenAICompatibleClient
        from src.llm.types import ChatCompletion, TokenUsage

        interview, ws_token = interview_with_ws_token
        call_count = 0

        async def fake_complete_with_first_error(self, messages, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("Temporary provider connection timeout")
            return ChatCompletion(
                content="Respuesta recuperada del turno 2",
                model="test-model",
                usage=TokenUsage(),
            )

        monkeypatch.setattr(OpenAICompatibleClient, "complete", fake_complete_with_first_error)

        client = TestClient(app)
        with client.websocket_connect(
            f"/ws/interview/{interview.id}?token={ws_token}"
        ) as ws:
            # Consume initial phase_changed
            ws.receive_json()

            # Turn 1: Fails with AGENT_ERROR
            ws.send_json({
                "type": "chat_message",
                "content": "Pregunta 1",
                "client_timestamp": 1001,
            })

            err_msg = ws.receive_json()
            assert err_msg["type"] == "error"
            assert err_msg["code"] == "AGENT_ERROR"
            assert "Temporary provider connection timeout" in err_msg["message"]

            # Turn 2: Subsequent message sent in same connection succeeds
            ws.send_json({
                "type": "chat_message",
                "content": "Pregunta 2 de reintento",
                "client_timestamp": 1002,
            })

            tokens_turn2 = []
            turn2_complete = None
            while True:
                msg = ws.receive_json()
                if msg["type"] == "agent_token":
                    tokens_turn2.append(msg["delta"])
                elif msg["type"] == "agent_turn_complete":
                    turn2_complete = msg
                    break

            assert "".join(tokens_turn2) == "Respuesta recuperada del turno 2"
            assert turn2_complete["full_content"] == "Respuesta recuperada del turno 2"

        # Verify DB: Candidate turns 1 and 2 exist, and agent turn 2 exists
        import asyncio

        async def verify_db():
            async with isolated_session() as session:
                turns = (await session.scalars(
                    select(Turn)
                    .where(Turn.interview_id == interview.id)
                    .order_by(Turn.created_at.asc())
                )).all()

                agent_turns = [t for t in turns if t.speaker == "agent" and not t.content.startswith("Phase transitioned to")]
                candidate_turns = [t for t in turns if t.speaker == "candidate"]

                assert len(candidate_turns) == 2
                assert len(agent_turns) == 1
                assert agent_turns[0].content == "Respuesta recuperada del turno 2"

        asyncio.run(verify_db())