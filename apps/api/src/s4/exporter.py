"""Exportador reutilizable de la bitácora S4 a JSON y CSV reproducible desde PostgreSQL."""

from __future__ import annotations

import csv
import io
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.db.models.interview import LLMUsageRecord
from src.db.models.s4 import S4TaskExecution
from src.s4.enums import S4TaskStatus
from src.s4.schemas import (
    S4LLMCallExportRecord,
    S4LLMCallExportRow,
    S4RunExportJSON,
    S4TaskExecutionRecord,
    S4TaskExportRow,
)
from src.s4.service import S4Service


class S4Exporter:
    """Exportador de bitácoras y trazabilidad de corridas S4."""

    @classmethod
    async def export_json(
        cls,
        run_id: uuid.UUID,
        session: AsyncSession,
    ) -> dict[str, Any]:
        """Genera la exportación JSON completa de la corrida y sus tareas."""
        service = S4Service(session)
        summary = await service.get_run_statistics(run_id)

        stmt = (
            select(S4TaskExecution)
            .where(S4TaskExecution.run_id == run_id)
            .options(selectinload(S4TaskExecution.llm_usage_records))
            .order_by(S4TaskExecution.task_number)
        )
        tasks = (await session.execute(stmt)).scalars().all()

        task_records: list[dict[str, Any]] = []
        for t in tasks:
            # Recolectar gateway_request_ids únicos de las llamadas asociadas
            gw_ids: list[str] = []
            for r in t.llm_usage_records:
                if r.gateway_request_id and r.gateway_request_id not in gw_ids:
                    gw_ids.append(r.gateway_request_id)

            dur_sec: float | None = None
            if t.started_at and t.finished_at:
                dur_sec = round((t.finished_at - t.started_at).total_seconds(), 3)

            rec = S4TaskExecutionRecord(
                id=t.id,
                run_id=t.run_id,
                task_number=t.task_number,
                task_type=t.task_type,
                status=S4TaskStatus(t.status),
                validation_passed=t.validation_passed,
                input_sanitized=t.input_sanitized,
                result_summary=t.result_summary,
                worker_id=t.worker_id,
                lease_token=t.lease_token,
                lease_generation=t.lease_generation,
                heartbeat_at=t.heartbeat_at,
                started_at=t.started_at,
                finished_at=t.finished_at,
                duration_seconds=dur_sec,
                attempt_count=t.attempt_count,
                model_calls=t.model_calls,
                input_tokens=t.input_tokens,
                output_tokens=t.output_tokens,
                total_tokens=t.input_tokens + t.output_tokens,
                cost_usd=t.cost_usd,
                error_sanitized=t.error_sanitized,
                recovery_events=t.recovery_events or [],
                gateway_request_ids=gw_ids,
                created_at=t.created_at,
                updated_at=t.updated_at,
            )
            task_records.append(rec.model_dump(mode="json"))

        # Recolectar llamadas LLM individuales ordenadas cronológicamente para conciliación con el proveedor
        stmt_calls = (
            select(LLMUsageRecord, S4TaskExecution.task_number)
            .join(S4TaskExecution, S4TaskExecution.id == LLMUsageRecord.s4_task_execution_id)
            .where(S4TaskExecution.run_id == run_id)
            .order_by(LLMUsageRecord.created_at.asc())
        )
        call_rows = (await session.execute(stmt_calls)).all()
        llm_call_records: list[dict[str, Any]] = []
        for r, t_num in call_rows:
            meta = r.gateway_metadata or {}
            prov_id = meta.get("provider_id") or meta.get("provider_request_id")
            if not prov_id and r.gateway_request_id and not r.gateway_request_id.startswith("gw_mock"):
                prov_id = r.gateway_request_id

            rec_call = S4LLMCallExportRecord(
                call_id=r.id,
                task_id=r.s4_task_execution_id,
                task_number=t_num,
                call_sequence=r.call_sequence,
                created_at=r.created_at,
                model=r.model,
                tokens_input=r.tokens_input,
                tokens_output=r.tokens_output,
                tokens_total=r.tokens_total,
                cost_usd=r.cost_usd,
                measurement_status=r.measurement_status,
                gateway_request_id=r.gateway_request_id,
                response_body_id=prov_id,
                provider_request_id=prov_id,
                cf_ray=meta.get("cf_ray") or meta.get("cf-ray"),
                gateway_metadata=meta,
            )
            llm_call_records.append(rec_call.model_dump(mode="json"))

        export_data = S4RunExportJSON(
            run=summary,
            tasks=[S4TaskExecutionRecord(**tr) for tr in task_records],
            llm_calls=[S4LLMCallExportRecord(**cr) for cr in llm_call_records],
        )
        return export_data.model_dump(mode="json")

    @classmethod
    async def export_calls_csv(
        cls,
        run_id: uuid.UUID,
        session: AsyncSession,
    ) -> str:
        """Genera la exportación CSV detallada de cada llamada LLM individual para conciliación con el proveedor."""
        stmt = (
            select(LLMUsageRecord, S4TaskExecution.task_number)
            .join(S4TaskExecution, S4TaskExecution.id == LLMUsageRecord.s4_task_execution_id)
            .where(S4TaskExecution.run_id == run_id)
            .order_by(LLMUsageRecord.created_at.asc())
        )
        call_rows = (await session.execute(stmt)).all()

        output = io.StringIO()
        fieldnames = [
            "call_id",
            "task_id",
            "task_number",
            "call_sequence",
            "created_at",
            "model",
            "tokens_input",
            "tokens_output",
            "tokens_total",
            "cost_usd",
            "measurement_status",
            "gateway_request_id",
            "response_body_id",
            "provider_request_id",
            "cf_ray",
        ]
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()

        for r, t_num in call_rows:
            meta = r.gateway_metadata or {}
            prov_id = meta.get("provider_id") or meta.get("provider_request_id") or ""
            cf_ray = meta.get("cf_ray") or meta.get("cf-ray") or ""
            row = S4LLMCallExportRow(
                call_id=str(r.id),
                task_id=str(r.s4_task_execution_id or ""),
                task_number=str(t_num) if t_num is not None else "",
                call_sequence=r.call_sequence,
                created_at=r.created_at.isoformat() if r.created_at else "",
                model=r.model,
                tokens_input=str(r.tokens_input) if r.tokens_input is not None else "",
                tokens_output=str(r.tokens_output) if r.tokens_output is not None else "",
                tokens_total=str(r.tokens_total) if r.tokens_total is not None else "",
                cost_usd=f"{r.cost_usd:.6f}" if r.cost_usd is not None else "",
                measurement_status=r.measurement_status,
                gateway_request_id=r.gateway_request_id or "",
                response_body_id=prov_id,
                provider_request_id=prov_id,
                cf_ray=cf_ray,
            )
            writer.writerow(row.model_dump())

        return output.getvalue()

    @classmethod
    async def export_csv(
        cls,
        run_id: uuid.UUID,
        session: AsyncSession,
    ) -> str:
        """Genera la exportación CSV con una fila por unidad de trabajo."""
        stmt = (
            select(S4TaskExecution)
            .where(S4TaskExecution.run_id == run_id)
            .options(selectinload(S4TaskExecution.llm_usage_records))
            .order_by(S4TaskExecution.task_number)
        )
        tasks = (await session.execute(stmt)).scalars().all()

        output = io.StringIO()
        fieldnames = [
            "run_id",
            "task_id",
            "task_number",
            "task_type",
            "status",
            "validation_passed",
            "started_at",
            "finished_at",
            "duration_seconds",
            "attempt_count",
            "model_calls",
            "input_tokens",
            "output_tokens",
            "total_tokens",
            "cost_usd",
            "gateway_request_ids",
            "error_sanitized",
            "recovery_events_count",
            "input_preview",
            "result_preview",
        ]

        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()

        for t in tasks:
            gw_ids: list[str] = []
            for r in t.llm_usage_records:
                if r.gateway_request_id and r.gateway_request_id not in gw_ids:
                    gw_ids.append(r.gateway_request_id)

            dur_sec_str = ""
            if t.started_at and t.finished_at:
                dur_sec_str = f"{(t.finished_at - t.started_at).total_seconds():.3f}"

            in_prev = t.input_sanitized[:120].replace("\n", " ").replace("\r", "")
            res_prev = (t.result_summary or "")[:120].replace("\n", " ").replace("\r", "")
            err_prev = (t.error_sanitized or "")[:120].replace("\n", " ").replace("\r", "")

            row = S4TaskExportRow(
                run_id=str(t.run_id),
                task_id=str(t.id),
                task_number=t.task_number,
                task_type=t.task_type,
                status=t.status,
                validation_passed=t.validation_passed,
                started_at=t.started_at.isoformat() if t.started_at else "",
                finished_at=t.finished_at.isoformat() if t.finished_at else "",
                duration_seconds=dur_sec_str,
                attempt_count=t.attempt_count,
                model_calls=t.model_calls,
                input_tokens=t.input_tokens,
                output_tokens=t.output_tokens,
                total_tokens=t.input_tokens + t.output_tokens,
                cost_usd=f"{t.cost_usd:.6f}",
                gateway_request_ids=";".join(gw_ids),
                error_sanitized=err_prev,
                recovery_events_count=len(t.recovery_events or []),
                input_preview=in_prev,
                result_preview=res_prev,
            )
            writer.writerow(row.model_dump())

        return output.getvalue()
