"""Pruebas para S-14: Procesamiento asíncrono durable de evaluaciones con Redis y ARQ.

Cubre:
1. Encolado e idempotencia:
   - Encolado exitoso con estado 'queued' y job_id determinista.
   - Manejo explícito de BrokerConnectionError si Redis falla.
   - Idempotencia: evaluación ya completada retorna el reporte existente sin re-invocar LLM.
   - Control de concurrencia: lock distribuido evita ejecuciones simultáneas de dos workers.
2. Worker y resiliencia:
   - Trabajo válido termina con estado 'completed'.
   - Error transitorio (LLMTimeoutError) activa política de reintento.
   - Error permanente marca estado 'failed' sin reintentos infinitos.
   - Excepciones liberan el lock distribuido y no dejan estado en curso indefinidamente.
3. Eventos y persistencia:
   - Emisión de eventos en canal Pub/Sub de la entrevista.
   - Compatibilidad con el modelo de datos y rúbrica existente.
"""

import json
import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from arq import Retry

from src.db.enums import InterviewPhase
from src.db.models.interview import Evaluation, Interview, Snapshot, Turn
from src.db.models.vacancy import Vacancy
from src.evaluation.queue import BrokerConnectionError, EvaluationQueue, evaluation_queue
from src.evaluation.service import (
    EvaluationService,
    _run_background_evaluation,
    schedule_automatic_evaluation,
)
from src.evaluation.worker import evaluate_interview_job, is_transient_error
from src.llm.exceptions import LLMTimeoutError


@pytest.fixture
async def sample_interview(db_session):
    """Create a basic interview for evaluation testing."""
    vacancy = Vacancy(
        title="Test Vacancy for Evaluation",
        raw_description="Evaluation testing vacancy",
    )
    db_session.add(vacancy)
    await db_session.flush()

    interview = Interview(
        vacancy_id=vacancy.id,
        phase=InterviewPhase.CODING,
        hint_level=0,
        last_hint_at=None,
        hint_reservation_token=None,
        candidate_email="test.candidate@example.com",
        candidate_name="Test Candidate",
        expires_at=datetime.now(UTC),
    )
    db_session.add(interview)
    await db_session.commit()
    await db_session.refresh(interview)
    return interview


@pytest.fixture
async def sample_turns(db_session, sample_interview):
    """Create turns associated with the interview."""
    turns = []
    dimension_names = [
        "problem_solving",
        "algorithmic_reasoning",
        "code_quality",
        "technical_communication",
        "complexity_management",
    ]
    for dim in dimension_names:
        turn = Turn(
            interview_id=sample_interview.id,
            speaker="candidate",
            content=f"This is evidence for {dim}",
        )
        turns.append(turn)
        db_session.add(turn)
    await db_session.commit()
    return turns


@pytest.fixture
async def sample_snapshots(db_session, sample_interview):
    """Create snapshots associated with the interview."""
    snapshots = []
    for _ in range(3):
        snap = Snapshot(
            interview_id=sample_interview.id,
            phase="CODING",
            code="# solution code here",
        )
        snapshots.append(snap)
        db_session.add(snap)
    await db_session.commit()
    return snapshots



@pytest.mark.asyncio
async def test_s14_enqueue_evaluation_success_and_state():
    """S-14: Encolar evaluación registra estado 'queued' en Redis con job_id determinista."""
    test_id = uuid.uuid4()
    job_id = await evaluation_queue.enqueue_evaluation(test_id)

    assert job_id == f"eval:{test_id}"
    status_data = await evaluation_queue.get_evaluation_status(test_id)
    assert status_data is not None
    assert status_data["status"] == "queued"
    assert status_data["interview_id"] == str(test_id)
    assert "enqueued_at" in status_data


@pytest.mark.asyncio
async def test_s14_enqueue_broker_failure_raises_explicit_exception():
    """S-14: Un fallo de conexión con Redis lanza BrokerConnectionError explícito."""
    failing_queue = EvaluationQueue(redis_url="redis://localhost:9999/0")
    with pytest.raises(BrokerConnectionError):
        await failing_queue.enqueue_evaluation(uuid.uuid4())


@pytest.mark.asyncio
async def test_s14_distributed_lock_prevents_concurrent_workers():
    """S-14: Lock distribuido en Redis evita que dos workers procesen la misma evaluación en paralelo."""
    int_id = uuid.uuid4()
    worker_1 = "worker-alpha"
    worker_2 = "worker-beta"

    # Worker 1 adquiere el lock
    acquired_1 = await evaluation_queue.acquire_lock(int_id, worker_1, ttl_seconds=60)
    assert acquired_1 is True

    # Worker 2 intenta adquirir el lock para la misma entrevista y es rechazado
    acquired_2 = await evaluation_queue.acquire_lock(int_id, worker_2, ttl_seconds=60)
    assert acquired_2 is False

    # Worker 2 ejecutando el job debe saltar la ejecución de forma segura
    ctx_2 = {"worker_id": worker_2, "job_try": 1}
    res = await evaluate_interview_job(ctx_2, str(int_id))
    assert res["status"] == "skipped"
    assert res["reason"] == "lock_active"

    # Liberar lock
    released = await evaluation_queue.release_lock(int_id, worker_1)
    assert released is True

    # Tras liberar, otro worker puede adquirirlo
    acquired_after = await evaluation_queue.acquire_lock(int_id, worker_2, ttl_seconds=60)
    assert acquired_after is True
    await evaluation_queue.release_lock(int_id, worker_2)


@pytest.mark.asyncio
async def test_s14_worker_idempotency_avoids_duplicate_evaluation(
    db_session, sample_interview, sample_snapshots, sample_turns
):
    """S-14: Si la entrevista ya fue evaluada en DB, el worker no vuelve a invocar a los jueces LLM."""
    # 1. Crear previamente una evaluación en DB
    eval_db = Evaluation(
        interview_id=sample_interview.id,
        overall_score=4.5,
        recommendation="hire",
        needs_human_review=False,
        evaluated_at=datetime.now(UTC),
    )
    db_session.add(eval_db)
    await db_session.commit()

    mock_llm = AsyncMock()
    with patch("src.llm.factory.create_llm_client", return_value=mock_llm):
        ctx = {"worker_id": "worker-test", "job_try": 1}
        res = await evaluate_interview_job(ctx, str(sample_interview.id))

        assert res["status"] == "completed"
        assert res.get("cached") is True
        # El LLM no debe haberse llamado en absoluto
        mock_llm.complete.assert_not_called()

    # El estado en Redis debe estar registrado como completed
    status_data = await evaluation_queue.get_evaluation_status(sample_interview.id)
    assert status_data is not None
    assert status_data["status"] == "completed"
    assert status_data["is_idempotent_replay"] is True


@pytest.mark.asyncio
async def test_s14_worker_transient_error_triggers_retry(sample_interview):
    """S-14: Error transitorio (LLMTimeoutError) provoca Retry en ARQ con backoff."""
    with patch("src.evaluation.service.EvaluationService.evaluate", side_effect=LLMTimeoutError("Gateway timeout 504")):
        ctx = {"worker_id": "worker-retry-test", "job_try": 1}
        with pytest.raises(Retry) as exc_info:
            await evaluate_interview_job(ctx, str(sample_interview.id))

        assert exc_info.value.defer_score is not None

    # El lock distribuido debe quedar liberado para el reintento posterior
    can_lock_again = await evaluation_queue.acquire_lock(sample_interview.id, "worker-retry-2")
    assert can_lock_again is True
    await evaluation_queue.release_lock(sample_interview.id, "worker-retry-2")



@pytest.mark.asyncio
async def test_s14_worker_permanent_error_marks_failed_without_retry(sample_interview):
    """S-14: Error permanente (ValueError) marca inmediatamente status 'failed' en Redis sin reintentos."""
    with patch("src.evaluation.service.EvaluationService.evaluate", side_effect=ValueError("Invalid interview data")):
        ctx = {"worker_id": "worker-permanent-test", "job_try": 1}
        res = await evaluate_interview_job(ctx, str(sample_interview.id))

        assert res["status"] == "failed"
        assert res["error_type"] == "permanent"

    status_data = await evaluation_queue.get_evaluation_status(sample_interview.id)
    assert status_data is not None
    assert status_data["status"] == "failed"
    assert status_data["error_type"] == "permanent"


@pytest.mark.asyncio
async def test_s14_events_published_to_redis_channel(sample_interview):
    """S-14: Los cambios de estado emiten eventos estructurados al canal Pub/Sub de la entrevista."""
    client = await evaluation_queue.get_redis_client()
    channel_name = f"evaluador:interviews:{sample_interview.id}:events"

    pubsub = client.pubsub()
    await pubsub.subscribe(channel_name)

    # Emitir un cambio de estado
    await evaluation_queue.set_evaluation_status(
        sample_interview.id,
        status="in_progress",
        metadata={"worker_id": "worker-event-test"},
    )

    # Leer mensaje del canal
    msg = None
    for _ in range(5):
        m = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
        if m and m.get("type") == "message":
            msg = m
            break

    await pubsub.unsubscribe(channel_name)
    await pubsub.aclose()

    assert msg is not None
    data = json.loads(msg["data"])
    assert data["type"] == "evaluation_in_progress"
    assert data["payload"]["status"] == "in_progress"
    assert data["payload"]["interview_id"] == str(sample_interview.id)


def test_s14_transient_error_detection():
    """S-14: Clasificación precisa entre errores transitorios (reintentables) y permanentes."""
    assert is_transient_error(LLMTimeoutError("timed out")) is True
    assert is_transient_error(TimeoutError("request timeout")) is True
    assert is_transient_error(ConnectionError("connection reset by peer")) is True
    assert is_transient_error(RuntimeError("HTTP 502 Bad Gateway")) is True
    assert is_transient_error(RuntimeError("Rate limit exceeded 429")) is True

    # Errores permanentes
    assert is_transient_error(ValueError("Interview not found")) is False
    assert is_transient_error(KeyError("missing key")) is False
    assert is_transient_error(TypeError("invalid argument")) is False


@pytest.mark.asyncio
async def test_s14_schedule_durable_enqueues_without_local_evaluation(sample_interview):
    """S-14: schedule_automatic_evaluation(enqueue_durable=True) encola en ARQ y NO evalúa localmente."""
    with patch("src.evaluation.service._run_background_evaluation") as mock_local_run:
        task = schedule_automatic_evaluation(sample_interview.id, enqueue_durable=True)
        job_id = await task

        assert job_id == f"eval:{sample_interview.id}"
        # La API NO debe ejecutar la evaluación en memoria ni llamar al runner local
        mock_local_run.assert_not_called()

    status_data = await evaluation_queue.get_evaluation_status(sample_interview.id)
    assert status_data is not None
    assert status_data["status"] == "queued"


@pytest.mark.asyncio
async def test_s14_schedule_durable_broker_failure_raises_without_silent_fallback(sample_interview):
    """S-14: Si Redis falla al encolar durablemente, se propaga BrokerConnectionError y NO se ejecuta localmente."""
    with (
        patch("src.evaluation.queue.evaluation_queue.enqueue_evaluation", side_effect=BrokerConnectionError("Redis down")),
        patch("src.evaluation.service._run_background_evaluation") as mock_local_run,
    ):
        task = schedule_automatic_evaluation(sample_interview.id, enqueue_durable=True)
        with pytest.raises(BrokerConnectionError):
            await task

        # No debe haber fallback silencioso a ejecución local
        mock_local_run.assert_not_called()


@pytest.mark.asyncio
async def test_s14_schedule_explicit_in_process_mode(sample_interview):
    """S-14: schedule_automatic_evaluation(enqueue_durable=False) ejecuta el runner local sin encolar en ARQ."""
    with (
        patch("src.evaluation.queue.evaluation_queue.enqueue_evaluation") as mock_enqueue,
        patch.object(EvaluationService, "evaluate", new_callable=AsyncMock) as mock_eval,
    ):
        mock_eval.return_value = MagicMock(
            id="test-id", overall_score=4.0, recommendation="hire", needs_human_review=False
        )
        task = schedule_automatic_evaluation(sample_interview.id, enqueue_durable=False)
        res = await task

        assert res is not None
        # No debe encolar en ARQ
        mock_enqueue.assert_not_called()
        mock_eval.assert_awaited_once()


@pytest.mark.asyncio
async def test_s14_run_background_evaluation_respects_distributed_lock_contention(sample_interview):
    """S-14: _run_background_evaluation respeta el lock distribuido de Redis y se abstiene si ya está ocupado."""
    worker_id = "external-worker-123"
    # Adquirir el lock previamente simulando que un worker ARQ ya está procesando la entrevista
    acquired = await evaluation_queue.acquire_lock(sample_interview.id, worker_id, ttl_seconds=60)
    assert acquired is True

    with patch.object(EvaluationService, "evaluate", new_callable=AsyncMock) as mock_eval:
        result = await _run_background_evaluation(sample_interview.id)
        # Debe omitir ejecución y no invocar la evaluación
        assert result is None
        mock_eval.assert_not_called()

    # Liberar el lock
    await evaluation_queue.release_lock(sample_interview.id, worker_id)

