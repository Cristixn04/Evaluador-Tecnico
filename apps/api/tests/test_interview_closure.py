"""Tests para S2-01B: Cierre formal de la entrevista (WRAPUP -> EVALUATE).

Cubre:
1. Caso 1: Transición válida WRAPUP -> EVALUATE vía WebSocket (phase=EVALUATE, status=evaluated, evento emitido).
2. Caso 2: Transición inválida EVALUATE -> EVALUATE rechazada con INVALID_TRANSITION.
3. Caso 3: Transición desde fase incorrecta CODING -> EVALUATE rechazada con INVALID_TRANSITION.
4. Caso 4: Persistencia: comprobar en sesión fresca de DB que phase == EVALUATE y status == EVALUATED.
5. Caso 5: Dos solicitudes consecutivas hacia EVALUATE no producen una segunda transición válida.
6. Caso 6: Reconexión en EVALUATE envía current_phase="EVALUATE" y available_transitions=[].
"""

from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from src.core.config import settings
from src.core.ws_tokens import ws_token_service
from src.db.enums import InterviewPhase, InterviewStatus, Seniority
from src.db.models import Interview, Organization, Vacancy
from src.interview.exceptions import InterviewPhaseTransitionError
from src.interview.service import InterviewService
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


@pytest.fixture(autouse=True)
def reset_global_engine():
    import src.db.session as db_session_module

    db_session_module._engine = None
    db_session_module._async_session_maker = None
    yield
    db_session_module._engine = None
    db_session_module._async_session_maker = None


@pytest.fixture
async def organization(db_session) -> Organization:
    org = Organization(name=f"Closure Org {uuid4().hex[:6]}")
    db_session.add(org)
    await db_session.flush()
    return org


@pytest.fixture
async def vacancy(db_session, organization) -> Vacancy:
    vac = Vacancy(
        title="Closure Backend Test",
        raw_description="Backend Dev description",
        organization_id=organization.id,
        role_category="backend",
        seniority=Seniority.MID,
    )
    db_session.add(vac)
    await db_session.flush()
    return vac


@pytest.fixture
async def interview_in_wrapup(db_session, vacancy) -> tuple[Interview, str]:
    """Crea una entrevista directamente en fase WRAPUP con su token de WebSocket."""
    interview = Interview(
        vacancy_id=vacancy.id,
        candidate_email="candidato.closure@test.com",
        candidate_name="Candidato Closure",
        phase=InterviewPhase.WRAPUP,
        status=InterviewStatus.IN_PROGRESS,
        expires_at=datetime.now(UTC) + timedelta(hours=2),
    )
    db_session.add(interview)
    await db_session.flush()
    await db_session.commit()

    ws_token = ws_token_service.create_ws_token(interview_id=interview.id)
    await ws_token_service.store_ws_token(ws_token)

    return interview, ws_token


@pytest.fixture
def app():
    return fastapi_app


@pytest.fixture
async def interview_in_evaluate(db_session, vacancy) -> tuple[Interview, str]:
    """Crea una entrevista que ya se encuentra en fase terminal EVALUATE."""
    interview = Interview(
        vacancy_id=vacancy.id,
        candidate_email="candidato.eval@test.com",
        candidate_name="Candidato Evaluated",
        phase=InterviewPhase.EVALUATE,
        status=InterviewStatus.EVALUATED,
        expires_at=datetime.now(UTC) + timedelta(hours=2),
    )
    db_session.add(interview)
    await db_session.flush()
    await db_session.commit()

    ws_token = ws_token_service.create_ws_token(interview_id=interview.id)
    await ws_token_service.store_ws_token(ws_token)

    return interview, ws_token


class TestInterviewClosureBackend:
    """Pruebas de servicio de máquina de estados para cierre formal."""

    @pytest.mark.asyncio
    async def test_service_wrapup_to_evaluate_valid(self, db_session, interview_in_wrapup) -> None:
        """Caso 1 & 4 (Servicio): WRAPUP -> EVALUATE persiste phase=EVALUATE y status=EVALUATED."""
        interview, _ = interview_in_wrapup
        service = InterviewService(db_session)

        # Transición autorizada
        updated = await service.transition_phase(interview, InterviewPhase.EVALUATE, reason="Formal closure")
        await db_session.commit()

        assert updated.phase == InterviewPhase.EVALUATE
        assert updated.status == InterviewStatus.EVALUATED

        # Caso 4: Verificar en sesión aislada fresca
        async with isolated_session() as fresh:
            saved = await fresh.get(Interview, interview.id)
            assert saved is not None
            assert saved.phase == InterviewPhase.EVALUATE
            assert saved.status == InterviewStatus.EVALUATED

    @pytest.mark.asyncio
    async def test_service_evaluate_to_evaluate_rejected(self, db_session, interview_in_wrapup) -> None:
        """Caso 2: EVALUATE -> EVALUATE debe ser rechazada."""
        interview, _ = interview_in_wrapup
        service = InterviewService(db_session)

        await service.transition_phase(interview, InterviewPhase.EVALUATE)
        await db_session.commit()

        # Segundo intento consecutivo
        with pytest.raises(InterviewPhaseTransitionError):
            await service.transition_phase(interview, InterviewPhase.EVALUATE)

    @pytest.mark.asyncio
    async def test_service_invalid_phase_to_evaluate_rejected(self, db_session, vacancy) -> None:
        """Caso 3: CODING -> EVALUATE debe ser rechazada sin pasar por PROBE y WRAPUP."""
        interview = Interview(
            vacancy_id=vacancy.id,
            candidate_email="test.coding@test.com",
            candidate_name="Test Coding",
            phase=InterviewPhase.CODING,
            status=InterviewStatus.IN_PROGRESS,
            expires_at=datetime.now(UTC) + timedelta(hours=2),
        )
        db_session.add(interview)
        await db_session.flush()

        service = InterviewService(db_session)
        with pytest.raises(InterviewPhaseTransitionError):
            await service.transition_phase(interview, InterviewPhase.EVALUATE)


class TestInterviewClosureWebSocket:
    """Pruebas del protocolo WebSocket en tiempo real para el cierre formal."""

    def test_ws_wrapup_to_evaluate_transition_flow(self, app, interview_in_wrapup) -> None:
        """Caso 1: Envío de request_phase_transition(EVALUATE) en WRAPUP emite phase_changed."""
        interview, ws_token = interview_in_wrapup
        client = TestClient(app)

        with client.websocket_connect(f"/ws/interview/{interview.id}?token={ws_token}") as ws:
            # Mensaje inicial de sincronización de fase
            init_msg = ws.receive_json()
            assert init_msg["type"] == "phase_changed"
            assert init_msg["current_phase"] == "WRAPUP"
            assert "EVALUATE" in init_msg["available_transitions"]

            # Candidato confirma entrega en WRAPUP
            ws.send_json({
                "type": "request_phase_transition",
                "target_phase": "EVALUATE",
                "reason": "Candidato confirma entrega definitiva",
            })

            # Servidor responde con phase_changed(EVALUATE)
            res_msg = ws.receive_json()
            assert res_msg["type"] == "phase_changed"
            assert res_msg["current_phase"] == "EVALUATE"
            assert res_msg["available_transitions"] == []

    def test_ws_duplicate_evaluate_request_rejected(self, app, interview_in_wrapup) -> None:
        """Caso 5: Dos solicitudes consecutivas de EVALUATE rechazan el segundo intento."""
        interview, ws_token = interview_in_wrapup
        client = TestClient(app)

        with client.websocket_connect(f"/ws/interview/{interview.id}?token={ws_token}") as ws:
            ws.receive_json()  # Handshake inicial (WRAPUP)

            # Primer cierre
            ws.send_json({
                "type": "request_phase_transition",
                "target_phase": "EVALUATE",
            })
            first_res = ws.receive_json()
            assert first_res["type"] == "phase_changed"
            assert first_res["current_phase"] == "EVALUATE"

            # Segundo cierre consecutivo (doble confirmación o frame duplicado)
            ws.send_json({
                "type": "request_phase_transition",
                "target_phase": "EVALUATE",
            })
            second_res = ws.receive_json()
            assert second_res["type"] == "error"
            assert second_res["code"] == "INVALID_TRANSITION"

    def test_ws_reconnect_after_evaluate_preserves_closed_state(self, app, interview_in_evaluate) -> None:
        """Caso 6: Reconectar tras haber cerrado la entrevista envía EVALUATE y available_transitions=[]."""
        interview, ws_token = interview_in_evaluate
        client = TestClient(app)

        with client.websocket_connect(f"/ws/interview/{interview.id}?token={ws_token}") as ws:
            msg = ws.receive_json()
            assert msg["type"] == "phase_changed"
            assert msg["current_phase"] == "EVALUATE"
            assert msg["available_transitions"] == []
