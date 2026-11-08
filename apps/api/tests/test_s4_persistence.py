"""Pruebas automatizadas de persistencia, contrato, trazabilidad y sanitización S4.

Cubre exhaustivamente los 20 requisitos de la Fase 1 sin llamadas externas ni consumo de red:
1. Creación de corrida
2. Creación de tarea
3. Unicidad de task_number dentro de una corrida
4. Rechazo de tarea asociada a corrida inexistente
5. Transiciones válidas e inválidas de estado
6. Una tarea no puede tener éxito sin resultado validado
7. Asociación de múltiples llamadas LLM a una tarea
8. Agregación correcta de tokens
9. Agregación correcta de costes
10. Ausencia de doble contabilización
11. Captura de x-request-id mediante respuesta HTTP simulada
12. Compatibilidad cuando faltan headers
13. Sanitización de API keys
14. Sanitización de JWT y Bearer tokens
15. Sanitización de correos y datos personales
16. Truncamiento determinista
17. Exportación JSON válida
18. Exportación CSV válida
19. Reconstrucción de estadísticas a partir de registros persistidos
20. Rollback transaccional ante errores
"""

from __future__ import annotations

import csv
import io
import uuid

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.llm.openai_compatible import OpenAICompatibleClient
from src.llm.types import ChatMessage
from src.s4.enums import S4RunStatus, S4TaskStatus, S4TaskType
from src.s4.exporter import S4Exporter
from src.s4.sanitizer import S4Sanitizer
from src.s4.service import (
    S4DuplicateTaskNumberError,
    S4InvalidStateTransitionError,
    S4RunIncompleteError,
    S4RunNotFoundError,
    S4Service,
    S4TaskValidationError,
)


@pytest.fixture
def s4_service(db_session: AsyncSession) -> S4Service:
    return S4Service(db_session)


# -----------------------------------------------------------------------------
# 1. Creación de Corrida
# -----------------------------------------------------------------------------
async def test_01_create_load_run(s4_service: S4Service, db_session: AsyncSession) -> None:
    run = await s4_service.create_load_run(
        target_tasks=1000,
        budget_limit_usd=40.0,
        meta={"environment": "s4_load_test", "agent_version": "v2"},
    )
    assert run.id is not None
    assert run.status == S4RunStatus.PLANNED.value
    assert run.target_tasks == 1000
    assert run.completed_tasks == 0
    assert run.budget_limit_usd == 40.0
    assert run.total_cost_usd == 0.0

    loaded = await s4_service.get_load_run(run.id)
    assert loaded.id == run.id


# -----------------------------------------------------------------------------
# 2. Creación de Tarea
# -----------------------------------------------------------------------------
async def test_02_create_task_execution(s4_service: S4Service, db_session: AsyncSession) -> None:
    run = await s4_service.create_load_run(target_tasks=50)
    task = await s4_service.create_task_execution(
        run_id=run.id,
        task_number=1,
        task_type=S4TaskType.BENCHMARK_EVALUATION,
        input_payload={"problem_id": "pse-reconciliation", "code": "def solve(): pass"},
    )
    assert task.id is not None
    assert task.run_id == run.id
    assert task.task_number == 1
    assert task.task_type == S4TaskType.BENCHMARK_EVALUATION.value
    assert task.status == S4TaskStatus.QUEUED.value
    assert task.validation_passed is False
    assert "pse-reconciliation" in task.input_sanitized


# -----------------------------------------------------------------------------
# 3. Unicidad de task_number dentro de una corrida
# -----------------------------------------------------------------------------
async def test_03_unique_task_number_per_run(s4_service: S4Service, db_session: AsyncSession) -> None:
    run = await s4_service.create_load_run(target_tasks=10)
    await s4_service.create_task_execution(
        run_id=run.id,
        task_number=1,
        input_payload="Task 1 payload",
    )

    with pytest.raises(S4DuplicateTaskNumberError):
        await s4_service.create_task_execution(
            run_id=run.id,
            task_number=1,
            input_payload="Duplicate task 1 payload",
        )


# -----------------------------------------------------------------------------
# 4. Rechazo de tarea asociada a corrida inexistente
# -----------------------------------------------------------------------------
async def test_04_reject_task_for_nonexistent_run(s4_service: S4Service) -> None:
    fake_run_id = uuid.uuid4()
    with pytest.raises(S4RunNotFoundError):
        await s4_service.create_task_execution(
            run_id=fake_run_id,
            task_number=1,
            input_payload="Payload",
        )


# -----------------------------------------------------------------------------
# 5. Transiciones válidas e inválidas de estado
# -----------------------------------------------------------------------------
async def test_05_state_transitions(s4_service: S4Service, db_session: AsyncSession) -> None:
    run = await s4_service.create_load_run(target_tasks=2)
    assert run.status == S4RunStatus.PLANNED.value

    # Transición válida: planned -> active
    await s4_service.start_load_run(run.id)
    assert run.status == S4RunStatus.ACTIVE.value
    assert run.started_at is not None

    # Transición inválida: active -> active (no permitido re-start)
    with pytest.raises(S4InvalidStateTransitionError):
        await s4_service.start_load_run(run.id)

    # Transición inválida: terminar como COMPLETED antes de cumplir target_tasks
    with pytest.raises(S4RunIncompleteError):
        await s4_service.finish_load_run(run.id, S4RunStatus.COMPLETED, min_duration_seconds=0.0)

    # Pausa válida
    await s4_service.pause_load_run(run.id)
    assert run.status == S4RunStatus.PAUSED.value

    # Reanudar desde pausa
    await s4_service.start_load_run(run.id)
    assert run.status == S4RunStatus.ACTIVE.value

    # Tarea: queued -> running -> failed (sin cumplir)
    task = await s4_service.create_task_execution(run_id=run.id, task_number=1, input_payload="in")
    await s4_service.start_task_execution(task.id)
    assert task.status == S4TaskStatus.RUNNING.value

    # Intentar start cuando ya está running
    with pytest.raises(S4InvalidStateTransitionError):
        await s4_service.start_task_execution(task.id)


# -----------------------------------------------------------------------------
# 6. Una tarea no puede tener éxito sin resultado validado
# -----------------------------------------------------------------------------
async def test_06_cannot_succeed_without_validation(s4_service: S4Service, db_session: AsyncSession) -> None:
    run = await s4_service.create_load_run(target_tasks=1)
    await s4_service.start_load_run(run.id)
    task = await s4_service.create_task_execution(run_id=run.id, task_number=1, input_payload="code")
    await s4_service.start_task_execution(task.id)

    # 1. validation_passed=False no puede finalizar como SUCCEEDED
    with pytest.raises(S4TaskValidationError):
        await s4_service.complete_task_execution(
            task.id,
            validation_passed=False,
            result_summary="Grok responded 200 OK",
            final_status=S4TaskStatus.SUCCEEDED,
        )

    # 2. validation_passed=True pero con result_summary vacío o None
    with pytest.raises(S4TaskValidationError):
        await s4_service.complete_task_execution(
            task.id,
            validation_passed=True,
            result_summary="",
        )

    # 3. Finalización exitosa válida con validación y resultado
    completed = await s4_service.complete_task_execution(
        task.id,
        validation_passed=True,
        result_summary="All 10 unit tests passed cleanly in sandbox",
    )
    assert completed.status == S4TaskStatus.SUCCEEDED.value
    assert completed.validation_passed is True
    assert run.completed_tasks == 1


# -----------------------------------------------------------------------------
# 7. Asociación de múltiples llamadas LLM a una tarea
# -----------------------------------------------------------------------------
async def test_07_associate_multiple_llm_calls(s4_service: S4Service, db_session: AsyncSession) -> None:
    run = await s4_service.create_load_run(target_tasks=1)
    task = await s4_service.create_task_execution(run_id=run.id, task_number=1, input_payload="in")

    c1 = await s4_service.record_task_llm_call(
        task.id,
        model="grok-4.6",
        input_tokens=1000,
        output_tokens=200,
        gateway_request_id="req-grok-001",
    )
    c2 = await s4_service.record_task_llm_call(
        task.id,
        model="grok-4.6",
        input_tokens=800,
        output_tokens=150,
        gateway_request_id="req-grok-002",
    )

    assert c1.s4_task_execution_id == task.id
    assert c2.s4_task_execution_id == task.id
    assert c1.gateway_request_id == "req-grok-001"
    assert c2.gateway_request_id == "req-grok-002"


# -----------------------------------------------------------------------------
# 8 & 9. Agregación correcta de tokens y costes
# -----------------------------------------------------------------------------
async def test_08_09_aggregation_tokens_and_cost(s4_service: S4Service, db_session: AsyncSession) -> None:
    run = await s4_service.create_load_run(target_tasks=1)
    await s4_service.start_load_run(run.id)
    task = await s4_service.create_task_execution(run_id=run.id, task_number=1, input_payload="in")
    await s4_service.start_task_execution(task.id)

    # grok-4.6 pricing: $5.00 / 1M prompt, $15.00 / 1M completion
    # Call 1: 10,000 prompt ($0.05), 1,000 completion ($0.015) = $0.065
    await s4_service.record_task_llm_call(
        task.id,
        model="grok-4.6",
        input_tokens=10000,
        output_tokens=1000,
    )
    # Call 2: 5,000 prompt ($0.025), 500 completion ($0.0075) = $0.0325
    await s4_service.record_task_llm_call(
        task.id,
        model="grok-4.6",
        input_tokens=5000,
        output_tokens=500,
    )

    finished = await s4_service.complete_task_execution(
        task.id,
        validation_passed=True,
        result_summary="Success",
    )

    assert finished.model_calls == 2
    assert finished.input_tokens == 15000
    assert finished.output_tokens == 1500
    assert finished.cost_usd == pytest.approx(0.0975, abs=1e-5)
    assert run.total_cost_usd == pytest.approx(0.0975, abs=1e-5)


# -----------------------------------------------------------------------------
# 10. Ausencia de doble contabilización
# -----------------------------------------------------------------------------
async def test_10_no_double_counting(s4_service: S4Service, db_session: AsyncSession) -> None:
    run = await s4_service.create_load_run(target_tasks=2)
    await s4_service.start_load_run(run.id)

    t1 = await s4_service.create_task_execution(run_id=run.id, task_number=1, input_payload="in1")
    t2 = await s4_service.create_task_execution(run_id=run.id, task_number=2, input_payload="in2")

    await s4_service.start_task_execution(t1.id)
    await s4_service.record_task_llm_call(t1.id, model="grok-4.6", input_tokens=1000, output_tokens=100)
    await s4_service.complete_task_execution(t1.id, validation_passed=True, result_summary="T1 done")

    await s4_service.start_task_execution(t2.id)
    await s4_service.record_task_llm_call(t2.id, model="grok-4.6", input_tokens=2000, output_tokens=200)
    await s4_service.complete_task_execution(t2.id, validation_passed=True, result_summary="T2 done")

    # t1 cost = 0.005 + 0.0015 = 0.0065
    # t2 cost = 0.010 + 0.0030 = 0.0130
    # total run cost must be exactly 0.0065 + 0.0130 = 0.0195
    assert t1.cost_usd == pytest.approx(0.0065, abs=1e-5)
    assert t2.cost_usd == pytest.approx(0.0130, abs=1e-5)
    assert run.total_cost_usd == pytest.approx(0.0195, abs=1e-5)


# -----------------------------------------------------------------------------
# 11 & 12. Captura de x-request-id y compatibilidad ante headers ausentes
# -----------------------------------------------------------------------------
async def test_11_12_capture_gateway_request_id() -> None:
    fake_body = {
        "id": "chatcmpl-123",
        "model": "grok-4.6",
        "choices": [{"message": {"role": "assistant", "content": "Hola mundo"}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120},
    }

    # Caso 1: Headers presentes con x-request-id y rate limits
    async def handler_with_headers(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code=200,
            json=fake_body,
            headers={
                "x-request-id": "req-pltk-987654321",
                "cf-ray": "ray-abc-123",
                "x-ratelimit-remaining-requests": "995",
            },
        )

    transport = httpx.MockTransport(handler_with_headers)
    async with httpx.AsyncClient(transport=transport) as mock_http:
        client = OpenAICompatibleClient(
            api_key="dummy-key",
            base_url="https://api.reto.pltk.mx/v1",
            model="grok-4.6",
            client=mock_http,
        )
        res = await client.complete([ChatMessage(role="user", content="Test")])
        assert res.request_id == "req-pltk-987654321"
        assert res.gateway_metadata is not None
        assert res.gateway_metadata["cf-ray"] == "ray-abc-123"
        assert res.gateway_metadata["x-ratelimit-remaining-requests"] == "995"

    # Caso 2: Headers ausentes (compatibilidad estricta sin fallos)
    async def handler_without_headers(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code=200, json=fake_body)

    transport_no_hdrs = httpx.MockTransport(handler_without_headers)
    async with httpx.AsyncClient(transport=transport_no_hdrs) as mock_http_no_hdrs:
        client2 = OpenAICompatibleClient(
            api_key="dummy-key",
            base_url="https://api.reto.pltk.mx/v1",
            model="grok-4.6",
            client=mock_http_no_hdrs,
        )
        res2 = await client2.complete([ChatMessage(role="user", content="Test")])
        assert res2.request_id is None
        assert res2.gateway_metadata is None
        assert res2.content == "Hola mundo"


# -----------------------------------------------------------------------------
# 13, 14, 15 & 16. Sanitización Anti-Leak y Truncamiento Determinista
# -----------------------------------------------------------------------------
def test_13_14_15_16_sanitizer() -> None:
    dirty_text = (
        "Connecting with sk-1234567890abcdef1234, token Bearer my-session-token-12345 and token eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c. "
        "User email is samuel.candidate@example.com with password='SuperSecretPassword123!' and CC: 1098765432."
    )
    cleaned = S4Sanitizer.sanitize_text(dirty_text)

    # 13. API key sanitizada
    assert "sk-1234567890abcdef1234" not in cleaned
    assert "[REDACTED_API_KEY]" in cleaned

    # 14. JWT y Bearer sanitizados
    assert "eyJhbGciOiJIUzI1NiJ9" not in cleaned
    assert "[REDACTED_JWT]" in cleaned
    assert "Bearer [REDACTED_TOKEN]" in cleaned

    # 15. Correo y PII sanitizados
    assert "samuel.candidate@example.com" not in cleaned
    assert "[REDACTED_EMAIL]" in cleaned
    assert "SuperSecretPassword123!" not in cleaned
    assert "password=[REDACTED]" in cleaned
    assert "1098765432" not in cleaned
    assert "id=[REDACTED_PII]" in cleaned

    # 16. Truncamiento determinista
    huge_text = "A" * 3000
    truncated = S4Sanitizer.sanitize_text(huge_text, max_length=500)
    assert len(truncated) < 650
    assert "[TRUNCATED: remaining 2500 characters redacted]" in truncated


# -----------------------------------------------------------------------------
# 17 & 18. Exportación JSON y CSV válida
# -----------------------------------------------------------------------------
async def test_17_18_json_and_csv_export(s4_service: S4Service, db_session: AsyncSession) -> None:
    run = await s4_service.create_load_run(target_tasks=1)
    await s4_service.start_load_run(run.id)

    task = await s4_service.create_task_execution(
        run_id=run.id,
        task_number=1,
        task_type=S4TaskType.AUTONOMOUS_CODING,
        input_payload={"test": "input"},
    )
    await s4_service.start_task_execution(task.id)
    await s4_service.record_task_recovery_event(
        task.id,
        event_type="transient_retry",
        attempt=2,
        details="Recovered after network glitch",
    )
    await s4_service.record_task_llm_call(
        task.id,
        model="grok-4.6",
        input_tokens=500,
        output_tokens=50,
        gateway_request_id="req-export-001",
    )
    await s4_service.complete_task_execution(
        task.id,
        validation_passed=True,
        result_summary="Clean execution",
    )
    await s4_service.finish_load_run(run.id, S4RunStatus.COMPLETED, min_duration_seconds=0.0)

    # 17. Exportación JSON
    json_data = await S4Exporter.export_json(run.id, db_session)
    assert json_data["run"]["run_id"] == str(run.id)
    assert json_data["run"]["completed_tasks"] == 1
    assert len(json_data["tasks"]) == 1
    t_json = json_data["tasks"][0]
    assert t_json["task_number"] == 1
    assert t_json["validation_passed"] is True
    assert "req-export-001" in t_json["gateway_request_ids"]
    assert len(t_json["recovery_events"]) == 1

    # 18. Exportación CSV
    csv_str = await S4Exporter.export_csv(run.id, db_session)
    reader = csv.DictReader(io.StringIO(csv_str))
    rows = list(reader)
    assert len(rows) == 1
    r = rows[0]
    assert r["run_id"] == str(run.id)
    assert r["task_number"] == "1"
    assert r["status"] == "succeeded"
    assert r["validation_passed"] == "True"
    assert r["gateway_request_ids"] == "req-export-001"
    assert r["recovery_events_count"] == "1"


# -----------------------------------------------------------------------------
# 19. Reconstrucción de estadísticas a partir de registros persistidos
# -----------------------------------------------------------------------------
async def test_19_reconstruct_statistics(s4_service: S4Service, db_session: AsyncSession) -> None:
    run = await s4_service.create_load_run(target_tasks=3)
    await s4_service.start_load_run(run.id)

    # Tarea 1: éxito
    t1 = await s4_service.create_task_execution(run_id=run.id, task_number=1, input_payload="t1")
    await s4_service.start_task_execution(t1.id)
    await s4_service.record_task_llm_call(t1.id, model="grok-4.6", input_tokens=1000, output_tokens=100)
    await s4_service.complete_task_execution(t1.id, validation_passed=True, result_summary="T1 pass")

    # Tarea 2: fallo
    t2 = await s4_service.create_task_execution(run_id=run.id, task_number=2, input_payload="t2")
    await s4_service.start_task_execution(t2.id)
    await s4_service.record_task_llm_call(t2.id, model="grok-4.6", input_tokens=1000, output_tokens=100)
    await s4_service.complete_task_execution(t2.id, validation_passed=False, error="Syntax error")

    stats = await s4_service.get_run_statistics(run.id)
    assert stats.total_tasks_recorded == 2
    assert stats.completed_tasks == 1
    assert stats.failed_tasks == 1
    assert stats.success_rate_percent == 50.0
    assert stats.total_model_calls == 2
    assert stats.total_input_tokens == 2000
    assert stats.total_output_tokens == 200
    assert stats.total_cost_usd == pytest.approx(0.013, abs=1e-5)
    assert stats.average_cost_per_task_usd == pytest.approx(0.0065, abs=1e-5)


# -----------------------------------------------------------------------------
# 20. Rollback transaccional ante errores
# -----------------------------------------------------------------------------
async def test_20_transactional_rollback(s4_service: S4Service, db_session: AsyncSession) -> None:
    run = await s4_service.create_load_run(target_tasks=1)
    await s4_service.create_task_execution(run_id=run.id, task_number=1, input_payload="t1")

    # Intentar insertar un número duplicado debe hacer rollback y no dejar estado corrupto
    with pytest.raises(S4DuplicateTaskNumberError):
        await s4_service.create_task_execution(run_id=run.id, task_number=1, input_payload="t1_dup")

    # Verificar que la base de datos se mantiene consistente y puede seguir operando
    t2 = await s4_service.create_task_execution(run_id=run.id, task_number=2, input_payload="t2")
    assert t2.task_number == 2
