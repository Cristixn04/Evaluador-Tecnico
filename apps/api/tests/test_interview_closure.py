"""Tests para S2-01B: Cierre formal de la entrevista (WRAPUP -> EVALUATE).

Cubre:
1. Caso 1: Transición válida WRAPUP -> EVALUATE vía WebSocket (phase=EVALUATE, status=evaluated, evento emitido).
2. Caso 2: Transición inválida EVALUATE -> EVALUATE rechazada con INVALID_TRANSITION.
3. Caso 3: Transición desde fase incorrecta CODING -> EVALUATE rechazada con INVALID_TRANSITION.
4. Caso 4: Persistencia: comprobar en sesión fresca de DB que phase == EVALUATE y status == EVALUATED.
5. Caso 5: Dos solicitudes consecutivas hacia EVALUATE no producen una segunda transición válida.
6. Caso 6: Reconexión en EVALUATE envía current_phase="EVALUATE" y available_transitions=[].
"""

import asyncio
import json
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from src.core.config import settings
from src.core.security import create_access_token
from src.core.ws_tokens import ws_token_service
from src.db.enums import InterviewPhase, InterviewStatus, Seniority, TurnSpeaker, UserRole
from src.db.models import Interview, Membership, Organization, Snapshot, Turn, User, Vacancy
from src.db.models.interview import Evaluation
from src.evaluation.service import (
    EvaluationService,
    schedule_automatic_evaluation,
    wait_for_automatic_evaluations,
)
from src.interview.exceptions import InterviewPhaseTransitionError
from src.interview.service import InterviewService
from src.llm.exceptions import LLMTimeoutError
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


@pytest.fixture
async def interview_in_coding(db_session, vacancy) -> tuple[Interview, str]:
    """Crea una entrevista en fase CODING con su token de WebSocket."""
    interview = Interview(
        vacancy_id=vacancy.id,
        candidate_email="coding.fail@test.com",
        candidate_name="Coding Fail",
        phase=InterviewPhase.CODING,
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
async def recruiter_token(db_session, organization) -> str:
    """Crea un usuario reclutador autenticado para consultar endpoints REST."""
    user = User(
        email=f"recruiter.{uuid4().hex[:6]}@example.com",
        hashed_password="$2b$12$KjK.dummyhashedpasswordforrecruiter",
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()

    membership = Membership(user_id=user.id, organization_id=organization.id, role=UserRole.RECRUITER)
    db_session.add(membership)
    await db_session.commit()

    return create_access_token(
        user_id=user.id,
        organization_id=organization.id,
        role=UserRole.RECRUITER,
    )


@pytest.fixture
async def interview_with_evidence(db_session, vacancy) -> tuple[Interview, str, Turn, Snapshot]:
    """Crea una entrevista en WRAPUP con turnos y snapshots para evaluación con evidencia."""
    interview = Interview(
        vacancy_id=vacancy.id,
        candidate_email="candidato.evidencia@test.com",
        candidate_name="Candidato Evidencia",
        phase=InterviewPhase.WRAPUP,
        status=InterviewStatus.IN_PROGRESS,
        expires_at=datetime.now(UTC) + timedelta(hours=2),
    )
    db_session.add(interview)
    await db_session.flush()

    turn = Turn(
        interview_id=interview.id,
        speaker=TurnSpeaker.CANDIDATE,
        content="He implementado una solución O(n) con tabla hash.",
    )
    db_session.add(turn)

    snap = Snapshot(
        interview_id=interview.id,
        code="def solve(nums):\n    return {n: i for i, n in enumerate(nums)}",
        phase="CODING",
    )
    db_session.add(snap)
    await db_session.flush()
    await db_session.commit()

    ws_token = ws_token_service.create_ws_token(interview_id=interview.id)
    await ws_token_service.store_ws_token(ws_token)

    return interview, ws_token, turn, snap


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


class TestAutomaticEvaluationOnClosure:
    """Pruebas para S2-01C: Disparo automático e idempotente de EvaluationService tras WRAPUP -> EVALUATE."""

    def test_ws_closure_schedules_exactly_one_evaluation_task(self, app, interview_in_wrapup) -> None:
        """Req 1: Transición válida WRAPUP -> EVALUATE programa exactamente una evaluación."""
        interview, ws_token = interview_in_wrapup
        client = TestClient(app)

        with patch("src.evaluation.service.schedule_automatic_evaluation") as mock_schedule:
            mock_schedule.return_value = MagicMock()

            with client.websocket_connect(f"/ws/interview/{interview.id}?token={ws_token}") as ws:
                ws.receive_json()  # Handshake inicial

                ws.send_json({
                    "type": "request_phase_transition",
                    "target_phase": "EVALUATE",
                    "reason": "Candidato finaliza",
                })
                res = ws.receive_json()
                assert res["type"] == "phase_changed"
                assert res["current_phase"] == "EVALUATE"

            mock_schedule.assert_called_once_with(interview.id)

    def test_invalid_transition_does_not_schedule_evaluation(self, app, interview_in_coding) -> None:
        """Req 2: Transición inválida (ej. CODING -> EVALUATE) no programa evaluación."""
        interview, ws_token = interview_in_coding
        client = TestClient(app)
        with patch("src.evaluation.service.schedule_automatic_evaluation") as mock_schedule:
            with client.websocket_connect(f"/ws/interview/{interview.id}?token={ws_token}") as ws:
                ws.receive_json()  # Handshake inicial (CODING)

                ws.send_json({
                    "type": "request_phase_transition",
                    "target_phase": "EVALUATE",
                })
                res = ws.receive_json()
                assert res["type"] == "error"
                assert res["code"] == "INVALID_TRANSITION"

            mock_schedule.assert_not_called()

    def test_duplicate_evaluate_does_not_schedule_second_evaluation(self, app, interview_in_wrapup) -> None:
        """Req 3: Solicitud duplicada no programa una segunda evaluación."""
        interview, ws_token = interview_in_wrapup
        client = TestClient(app)

        with patch("src.evaluation.service.schedule_automatic_evaluation") as mock_schedule:
            mock_schedule.return_value = MagicMock()

            with client.websocket_connect(f"/ws/interview/{interview.id}?token={ws_token}") as ws:
                ws.receive_json()

                # Primer intento válido
                ws.send_json({"type": "request_phase_transition", "target_phase": "EVALUATE"})
                assert ws.receive_json()["type"] == "phase_changed"

                # Segundo intento consecutivo rechazado
                ws.send_json({"type": "request_phase_transition", "target_phase": "EVALUATE"})
                err = ws.receive_json()
                assert err["type"] == "error"
                assert err["code"] == "INVALID_TRANSITION"

            # Programado exactamente una vez en la primera transición
            assert mock_schedule.call_count == 1

    @pytest.mark.asyncio
    async def test_background_task_uses_isolated_session_and_closes_it(self, interview_in_evaluate) -> None:
        """Req 4 & 5: La tarea background utiliza sesión propia aislada y la cierra correctamente."""
        interview, _ = interview_in_evaluate
        from src.evaluation.service import _run_background_evaluation

        with patch("src.evaluation.service.get_session_maker") as mock_get_maker:
            mock_session = AsyncMock()
            mock_session.__aenter__.return_value = mock_session
            mock_session.__aexit__.return_value = None

            mock_maker = MagicMock(return_value=mock_session)
            mock_get_maker.return_value = mock_maker

            with patch.object(EvaluationService, "evaluate", new_callable=AsyncMock) as mock_eval:
                mock_eval.return_value = MagicMock(
                    overall_score=4.0, recommendation="hire", needs_human_review=False
                )
                await _run_background_evaluation(interview.id)

                mock_maker.assert_called_once()
                mock_session.__aexit__.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_evaluation_failure_preserves_evaluate_phase(self, db_session, interview_in_evaluate) -> None:
        """Req 6: Un error en la evaluación no deshace el cierre formal ni corrompe el estado."""
        interview, _ = interview_in_evaluate
        from src.evaluation.service import _run_background_evaluation

        with patch.object(EvaluationService, "evaluate", side_effect=RuntimeError("LLM cluster failure")):
            result = await _run_background_evaluation(interview.id)
            assert result is None  # Capturado y registrado con logger.exception

        # Comprobar en DB que la entrevista sigue intacta en EVALUATE y EVALUATED
        async with isolated_session() as fresh:
            reloaded = await fresh.get(Interview, interview.id)
            assert reloaded is not None
            assert reloaded.phase == InterviewPhase.EVALUATE
            assert reloaded.status == InterviewStatus.EVALUATED

    @pytest.mark.asyncio
    async def test_automatic_evaluation_persists_report_and_rest_retrieves_it(
        self, app, interview_with_evidence, recruiter_token
    ) -> None:
        """Req 7 & 8: Evaluación automática persiste reporte real y GET REST lo recupera."""
        interview, _, turn, snap = interview_with_evidence

        mock_llm = AsyncMock()
        mock_llm.aclose = AsyncMock()
        eval_payload: dict[str, Any] = {
            "competencies": {
                "problem_solving": 4,
                "algorithmic_reasoning": 4,
                "code_quality": 5,
                "technical_communication": 4,
                "complexity_management": 4,
            },
            "evidence": [
                {
                    "competency": "problem_solving",
                    "evidence_quote": "O(n) con tabla hash",
                    "turn_id": str(turn.id),
                    "reasoning": "Explicación algorítmica clara",
                },
                {
                    "competency": "code_quality",
                    "evidence_quote": "def solve(nums)",
                    "snapshot_id": str(snap.id),
                    "reasoning": "Código sintácticamente correcto",
                },
            ],
            "discrepancy_note": None,
            "model_name": "mock-judge-v2",
        }
        mock_llm.complete = AsyncMock(
            return_value=MagicMock(content=json.dumps(eval_payload))
        )

        with patch("src.llm.factory.create_llm_client", return_value=mock_llm):
            task = schedule_automatic_evaluation(interview.id)
            await task
            await wait_for_automatic_evaluations()

        # Comprobar persistencia directa en DB
        async with isolated_session() as fresh:
            db_eval = (
                await fresh.execute(
                    select(Evaluation).where(Evaluation.interview_id == interview.id)
                )
            ).scalar_one_or_none()
            assert db_eval is not None
            assert db_eval.overall_score == 4.2
            assert db_eval.recommendation == "hire"

        # Req 8: Consultar endpoint REST con token de reclutador
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            resp = await client.get(
                f"/interviews/{interview.id}/evaluation",
                headers={"Authorization": f"Bearer {recruiter_token}"},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["overall_score"] == 4.2
            assert data["recommendation"] == "hire"
            assert len(data["evidence"]) >= 1

    @pytest.mark.asyncio
    async def test_concurrency_automatic_and_rest_evaluate_no_duplicates(
        self, db_session, interview_with_evidence
    ) -> None:
        """Req 9: Llamada REST y tarea automática no producen resultados duplicados bajo concurrencia."""
        interview, _, _turn, _snap = interview_with_evidence

        mock_llm = AsyncMock()
        mock_llm.aclose = AsyncMock()
        eval_payload: dict[str, Any] = {
            "competencies": {
                "problem_solving": 4,
                "algorithmic_reasoning": 4,
                "code_quality": 4,
                "technical_communication": 4,
                "complexity_management": 4,
            },
            "evidence": [],
            "discrepancy_note": None,
        }
        mock_llm.complete = AsyncMock(
            return_value=MagicMock(content=json.dumps(eval_payload))
        )

        with patch("src.llm.factory.create_llm_client", return_value=mock_llm):
            service = EvaluationService(db_session)
            bg_task = schedule_automatic_evaluation(interview.id)
            sync_coro = service.evaluate(interview.id)

            res_bg, res_sync = await asyncio.gather(bg_task, sync_coro)
            assert res_bg is not None
            assert res_sync is not None
            assert res_bg.overall_score == res_sync.overall_score

        # La evaluación solo debió ejecutarse 1 vez (2 llamadas LLM por doble pasada S-13)
        assert mock_llm.complete.call_count == 2

        # En la base de datos debe existir exactamente 1 registro
        async with isolated_session() as fresh:
            count = (
                await fresh.execute(
                    select(func.count(Evaluation.id)).where(Evaluation.interview_id == interview.id)
                )
            ).scalar_one()
            assert count == 1

    @pytest.mark.asyncio
    async def test_insufficient_evidence_defensive_behavior(self, db_session, vacancy) -> None:
        """Req 10a: Evidencia insuficiente produce needs_human_review=True sin fallar."""
        interview = Interview(
            vacancy_id=vacancy.id,
            candidate_email="noevidence@test.com",
            candidate_name="No Evidence",
            phase=InterviewPhase.WRAPUP,
            status=InterviewStatus.IN_PROGRESS,
            expires_at=datetime.now(UTC) + timedelta(hours=2),
        )
        db_session.add(interview)
        await db_session.commit()

        service = EvaluationService(db_session)
        report = await service.evaluate(interview.id)
        assert report.needs_human_review is True
        assert "insuficiente" in (report.discrepancy_note or "").lower()

    @pytest.mark.asyncio
    async def test_llm_timeout_defensive_behavior(self, db_session, interview_with_evidence) -> None:
        """Req 10b: Timeout de LLM produce needs_human_review=True defensivamente."""
        interview, _, _, _ = interview_with_evidence

        mock_llm = AsyncMock()
        mock_llm.aclose = AsyncMock()
        mock_llm.complete = AsyncMock(side_effect=LLMTimeoutError("Model timed out after 30s"))

        with patch("src.llm.factory.create_llm_client", return_value=mock_llm):
            service = EvaluationService(db_session)
            report = await service.evaluate(interview.id)
            assert report.needs_human_review is True
            assert "timeout" in (report.discrepancy_note or "").lower() or "error" in (report.discrepancy_note or "").lower()
