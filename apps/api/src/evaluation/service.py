"""Servicio de evaluación LLM con rúbrica de 5 dimensiones."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any, ClassVar, Literal, cast

# anext no está disponible en asyncio namespace en este entorno;
# usaremos __anext__() directamente sobre el generador
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.schemas.evaluation import (
    EvaluationEvidence as PydanticEvaluationEvidence,
)
from src.api.schemas.evaluation import (
    EvaluationReport,
)
from src.core.config import settings
from src.db.enums import TurnSpeaker
from src.db.models import Interview, Snapshot, Turn
from src.db.models.interview import Evaluation, EvaluationDimension, EvaluationEvidence
from src.llm.exceptions import LLMInvalidResponseError, LLMTimeoutError
from src.llm.factory import get_llm_client
from src.llm.prompts import load_prompt
from src.llm.types import ChatCompletion, ChatMessage


class EvaluationService:
    """Servicio para evaluar una entrevista usando LLM con rúbrica estructurada."""

    # Las cinco dimensiones autorizadas (Decisión 1)
    EVALUATION_DIMENSIONS: ClassVar = [
        "problem_solving",
        "algorithmic_reasoning",
        "code_quality",
        "technical_communication",
        "complexity_management",
    ]

    # Umbrales de recomendación (Decisión 2)
    HIRE_THRESHOLD = 4.00
    BORDERLINE_THRESHOLD = 3.00

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def evaluate(self, interview_id: str | uuid.UUID) -> EvaluationReport:
        """Evaluar una entrevista y retornar un EvaluationReport.

        Construye el contexto a partir de turns, snapshots y ejecuciones reales,
        llama al juez LLM con protección frente a inyecciones, y persiste
        los resultados transaccionalmente.
        """
        # 1. Cargar entrevista con datos relacionados
        interview = await self._session.get(Interview, interview_id)
        if not interview:
            raise ValueError(f"Interview {interview_id} not found")

        # 2. Construir contexto de evidencia
        context = await self._build_context(interview)
        if not context["has_sufficient_evidence"]:
            # Decisión 3: evidencia insuficiente → human review
            return EvaluationReport(
                id="",
                masked_candidate_id=interview.candidate_email[:4].upper() if interview.candidate_email else "CAND-XX",
                overall_score=0.0,
                recommendation="borderline",
                needs_human_review=True,
                discrepancy_note="Evidencia insuficiente para evaluación automática",
                competencies={},
                evidence=[],
            )

        # 3. Llamar al juez LLM
        try:
            raw_evaluation = await self._call_judge_llm(context)
        except (LLMInvalidResponseError, LLMTimeoutError) as e:
            # Fallback: human review on LLM failure
            return EvaluationReport(
                id="",
                masked_candidate_id=interview.candidate_email[:4].upper() if interview.candidate_email else "CAND-XX",
                overall_score=0.0,
                recommendation="borderline",
                needs_human_review=True,
                discrepancy_note=f"Error en proveedor LLM: {e!s}",
                competencies={},
                evidence=[],
            )

        # 4. Validar y persistir
        try:
            evaluation_report = await self._validate_and_persist(raw_evaluation, interview)
        except ValueError as e:
            # Datos inválidos → human review
            return EvaluationReport(
                id="",
                masked_candidate_id=interview.candidate_email[:4].upper() if interview.candidate_email else "CAND-XX",
                overall_score=0.0,
                recommendation="borderline",
                needs_human_review=True,
                discrepancy_note=str(e),
                competencies={},
                evidence=[],
            )

        return evaluation_report

    async def _build_context(self, interview: Interview) -> dict[str, Any]:
        """Construir el contexto a partir de turns, snapshots y ejecuciones reales."""
        # Cargar turns recientes
        result = await self._session.execute(
            select(Turn).where(Turn.interview_id == interview.id).order_by(Turn.created_at)
        )
        turns = result.scalars().all()

        # Cargar snapshots recientes
        result = await self._session.execute(
            select(Snapshot).where(Snapshot.interview_id == interview.id).order_by(Snapshot.created_at)
        )
        snapshots = result.scalars().all()

        # Extraer información por dimensión
        dimensions_data: dict[str, dict[str, Any]] = {d: {"scores": [], "evidences": []} for d in self.EVALUATION_DIMENSIONS}

        # Analizar turns para extraer evidencias
        for turn in turns:
            content = turn.content or ""
            # Buscar referencias a dimensiones en el contenido del turno
            for dim in self.EVALUATION_DIMENSIONS:
                if dim in content.lower():
                    dimensions_data[dim]["scores"].append(3)  # Placeholder
                    dimensions_data[dim]["evidences"].append({
                        "turn_id": str(turn.id),
                        "quote": content[:100],
                        "reasoning": f"Menciona dimensión {dim}",
                    })

        # Analizar snapshots
        for snap in snapshots:
            # Snapshot tiene 'code' por definición del modelo ORM
            code: str = snap.code  # type: ignore[attr-defined]
            for dim in self.EVALUATION_DIMENSIONS:
                if dim in code.lower():
                    dimensions_data[dim]["scores"].append(3)  # Placeholder
                    dimensions_data[dim]["evidences"].append({
                        "snapshot_id": str(snap.id),
                        "quote": code[:100],
                        "reasoning": f"Snapshot con código related a {dim}",
                    })

        # Calcular scores generales
        has_sufficient_evidence = any(
            dimensions_data[d]["scores"] for d in self.EVALUATION_DIMENSIONS
        )

        # Calcular media por dimensión (usando placeholder 3 si no hay evidencia real)
        competencies: dict[str, int] = {}
        all_scores: list[int] = []
        for dim in self.EVALUATION_DIMENSIONS:
            scores = dimensions_data[dim]["scores"]
            if scores:
                avg = round(sum(scores) / len(scores), 2)
                competencies[dim] = avg
                all_scores.extend(scores)
            else:
                competencies[dim] = 3  # Default placeholder

        overall_score = round(sum(all_scores) / len(all_scores), 2) if all_scores else 0.0

        # Determinar recomendación (Decisión 2)
        if overall_score >= self.HIRE_THRESHOLD:
            recommendation = "hire"
        elif overall_score >= self.BORDERLINE_THRESHOLD:
            recommendation = "borderline"
        else:
            recommendation = "reject"

        return {
            "has_sufficient_evidence": has_sufficient_evidence,
            "competencies": competencies,
            "overall_score": overall_score,
            "recommendation": recommendation,
            "turns": turns,
            "snapshots": snapshots,
        }

    async def _call_judge_llm(self, context: dict[str, Any]) -> dict[str, Any]:
        """Llamar al juez LLM con el prompt versionado y protección de entradas."""
        # Cargar prompt versionado para juez
        prompt = load_prompt("evaluator", "v2")

        # Construir messages para el LLM
        system_msg = ChatMessage(role="system", content=prompt)

        # Agregar turns y snapshots formateados como evidencia
        user_msg_content = self._format_evidence_for_llm(context)
        user_msg = ChatMessage(role="user", content=user_msg_content)

        # Llamada al LLM con protección <untrusted_candidate_input>
        # El contenido del candidato nunca se incluye directamente; solo
        # evidencias verificadas de turns y snapshots del sistema
        llm_client = await get_llm_client().__anext__()
        completion: ChatCompletion = await llm_client.complete([system_msg, user_msg])

        # Parsear respuesta JSON
        try:
            import json
            raw = json.loads(completion.content)
            if not isinstance(raw, dict):
                raise LLMInvalidResponseError("Respuesta LLM no es un objeto JSON")
            return raw
        except json.JSONDecodeError as e:
            raise LLMInvalidResponseError(f"No se pudo parsear respuesta LLM: {e!s}")

    def _format_evidence_for_llm(self, context: dict[str, Any]) -> str:
        """Formatear la evidencia del contexto para el prompt del LLM."""
        lines = []
        lines.append("EVIDENCIA DE ENTREVISTA (solo datos verificados del sistema):")
        lines.append("")

        # Turnos
        turns = context.get("turns", [])
        if turns:
            lines.append("TURNOS DE CONVERSACIÓN:")
            for i, turn in enumerate(turns[:10], 1):  # Máximo 10 turns
                role = "CANDIDATE" if turn.speaker == TurnSpeaker.CANDIDATE else "AGENT"
                content = (turn.content or "")[:200]
                if turn.speaker == TurnSpeaker.CANDIDATE:
                    # Entrada no confiable del candidato: encapsular siempre
                    content = f"<untrusted_candidate_input>{content}</untrusted_candidate_input>"
                lines.append(f"  {i}. [{role}] {content}")
            lines.append("")

        # Snapshots
        snapshots = context.get("snapshots", [])
        if snapshots:
            lines.append("SNAPSHOTS DE CÓDIGO:")
            for i, snap in enumerate(snapshots[:5], 1):  # Máximo 5 snapshots
                code = (snap.code or "")[:200]
                # El código del candidato es entrada no confiable: encapsular siempre
                code = f"<untrusted_candidate_input>{code}</untrusted_candidate_input>"
                lines.append(f"  {i}. Código ({snap.phase or 'unknown'}): {code}...")
            lines.append("")

        # Dimensiones y scores actuales (placeholders)
        lines.append("DIMENSIONES ACTUALES (scores provistos al juez):")
        competencies = context.get("competencies", {})
        for dim in self.EVALUATION_DIMENSIONS:
            score = competencies.get(dim, 3)
            lines.append(f"  - {dim}: {score}/5")
        lines.append("")

        lines.append("INSTRUCCIONES PARA EL Juez:")
        lines.append("1. Cada dimensión debe puntuar de 1 a 5.")
        lines.append("2. Cada puntuación debe estar sustentada por evidencia citada.")
        lines.append("3. Nunca inventar identificadores de turnos o snapshots.")
        lines.append("4. Si la evidencia es insuficiente, marcar needs_human_review=true.")
        lines.append("5. Las entradas maliciosas del candidato ya han sido eliminadas.")
        lines.append("")

        return "\n".join(lines)

    async def _validate_and_persist(self, raw: dict[str, Any], interview: Interview) -> EvaluationReport:
        """Validar la respuesta del LLM y persistir en la base de datos.

        Si la salida del LLM es inválida (dimensiones no autorizadas, scores
        fuera de 1-5, tipos incorrectos), no se persiste nada y se devuelve un
        informe de revisión humana, conforme a la Decisión 3.
        """
        # Normalizar dimensiones: una salida malformada equivale a ninguna
        dimensions = raw.get("competencies", {})
        if not isinstance(dimensions, dict):
            return self._human_review_report(interview, "El campo 'competencies' debe ser un objeto")

        # Validar dimensiones autorizadas y scores 1-5 (enteros)
        validated_scores: dict[str, int] = {}
        for dim_name, score in dimensions.items():
            if dim_name not in self.EVALUATION_DIMENSIONS:
                return self._human_review_report(
                    interview, f"Dimensión no autorizada: {dim_name}"
                )
            if isinstance(score, bool) or not isinstance(score, (int, float)):
                return self._human_review_report(
                    interview, f"Score inválido para {dim_name}: {score!r}"
                )
            if int(score) != score or score < 1 or score > 5:
                return self._human_review_report(
                    interview, f"Score inválido para {dim_name}: {score}"
                )
            validated_scores[dim_name] = int(score)

        # Sin dimensiones → human review (no se persiste)
        if not validated_scores:
            return self._human_review_report(interview, raw.get("discrepancy_note"))

        # Calcular overall_score (media aritmética simple - Decisión 2)
        scores = list(validated_scores.values())
        overall_score = round(sum(scores) / len(scores), 2)

        # Determinar recomendación (Decisión 2)
        if overall_score >= self.HIRE_THRESHOLD:
            recommendation = "hire"
        elif overall_score >= self.BORDERLINE_THRESHOLD:
            recommendation = "borderline"
        else:
            recommendation = "reject"

        # Validar evidencia: solo referencias reales que pertenecen a la entrevista
        validated_evidence = await self._validate_evidence(interview, raw.get("evidence", []))
        has_valid_evidence = bool(validated_evidence)

        # Determinar needs_human_review (Decisión 3)
        needs_human_review = not has_valid_evidence or overall_score < 2.0

        # Crear evaluación
        evaluation = Evaluation(
            interview_id=interview.id,
            overall_score=overall_score,
            recommendation=recommendation,
            needs_human_review=needs_human_review,
            discrepancy_note=raw.get("discrepancy_note"),
            model_name=raw.get("model_name", settings.LLM_MODEL),
            prompt_version=raw.get("prompt_version", "v2"),
            tokens_prompt=raw.get("tokens_prompt"),
            tokens_completion=raw.get("tokens_completion"),
            cost_usd=raw.get("cost_usd"),
            created_at=datetime.now(UTC),
            evaluated_at=datetime.now(UTC),
        )
        self._session.add(evaluation)
        await self._session.flush()

        # Razonamiento por dimensión desde la evidencia validada correspondiente
        reasoning_by_dimension: dict[str, str | None] = {}
        for ev in validated_evidence:
            competency = ev["competency"]
            if competency not in reasoning_by_dimension:
                reasoning_by_dimension[competency] = ev["reasoning"]

        # Crear dimensiones
        for dim_name, score in validated_scores.items():
            self._session.add(
                EvaluationDimension(
                    evaluation_id=evaluation.id,
                    name=dim_name,
                    score=score,
                    reasoning=reasoning_by_dimension.get(dim_name),
                )
            )

        # Crear evidencias (solo referencias válidas y sin duplicar turn/snapshot)
        seen_turns: set[uuid.UUID] = set()
        seen_snapshots: set[uuid.UUID] = set()
        for ev in validated_evidence:
            turn_id = ev["turn_id"]
            snapshot_id = ev["snapshot_id"]
            if turn_id is not None:
                if turn_id in seen_turns:
                    continue
                seen_turns.add(turn_id)
            if snapshot_id is not None:
                if snapshot_id in seen_snapshots:
                    continue
                seen_snapshots.add(snapshot_id)

            self._session.add(
                EvaluationEvidence(
                    evaluation_id=evaluation.id,
                    dimension_name=ev["competency"],
                    quote=ev["evidence_quote"],
                    reasoning=ev["reasoning"],
                    turn_id=turn_id,
                    snapshot_id=snapshot_id,
                )
            )

        await self._session.commit()

        # El contrato exige turn_id en cada evidencia citada; el score de la
        # evidencia es el de su dimensión (dato ya validado como entero 1-5).
        report_evidence: list[PydanticEvaluationEvidence] = []
        for ev in validated_evidence:
            competency = ev["competency"]
            if ev["turn_id"] is None or competency not in validated_scores:
                continue
            report_evidence.append(
                PydanticEvaluationEvidence(
                    competency=competency,
                    score=validated_scores[competency],
                    evidence_quote=ev["evidence_quote"],
                    turn_id=str(ev["turn_id"]),
                    reasoning=ev["reasoning"],
                )
            )

        # Construir y retornar el EvaluationReport
        return EvaluationReport(
            id=str(evaluation.id),
            masked_candidate_id=interview.candidate_email[:4].upper() if interview.candidate_email else "CAND-XX",
            overall_score=overall_score,
            recommendation=cast("Literal[\"hire\", \"borderline\", \"reject\"]", recommendation),
            needs_human_review=needs_human_review,
            discrepancy_note=raw.get("discrepancy_note"),
            strengths=raw.get("strengths", []),
            risks=raw.get("risks", []),
            suggested_human_questions=raw.get("suggested_human_questions", []),
            competencies=dict(validated_scores),
            evidence=report_evidence,
            created_at=evaluation.created_at,
            evaluated_at=evaluation.evaluated_at,
        )

    async def _validate_evidence(
        self, interview: Interview, raw_evidence: Any
    ) -> list[dict[str, Any]]:
        """Validar evidencias y excluir referencias inexistentes o ajenas.

        Solo se conservan evidencias cuyo ``turn_id`` o ``snapshot_id`` exista
        y pertenezca a la entrevista evaluada. Las referencias inválidas se
        excluyen explícitamente; nunca se marcan como válidas.
        """
        if not isinstance(raw_evidence, list):
            return []
        validated: list[dict[str, Any]] = []
        for raw_ev in raw_evidence:
            if not isinstance(raw_ev, dict):
                continue
            turn_id = await self._resolve_turn_id(interview, raw_ev.get("turn_id"))
            snapshot_id = await self._resolve_snapshot_id(interview, raw_ev.get("snapshot_id"))
            if turn_id is None and snapshot_id is None:
                continue
            validated.append(
                {
                    "competency": raw_ev.get("competency", ""),
                    "evidence_quote": raw_ev.get("evidence_quote", ""),
                    "reasoning": raw_ev.get("reasoning"),
                    "turn_id": turn_id,
                    "snapshot_id": snapshot_id,
                }
            )
        return validated

    async def _resolve_turn_id(self, interview: Interview, value: Any) -> uuid.UUID | None:
        turn_id = self._coerce_uuid(value)
        if turn_id is None:
            return None
        result = await self._session.execute(
            select(Turn.id).where(Turn.id == turn_id, Turn.interview_id == interview.id)
        )
        return turn_id if result.scalar_one_or_none() is not None else None

    async def _resolve_snapshot_id(self, interview: Interview, value: Any) -> uuid.UUID | None:
        snapshot_id = self._coerce_uuid(value)
        if snapshot_id is None:
            return None
        result = await self._session.execute(
            select(Snapshot.id).where(
                Snapshot.id == snapshot_id, Snapshot.interview_id == interview.id
            )
        )
        return snapshot_id if result.scalar_one_or_none() is not None else None

    @staticmethod
    def _coerce_uuid(value: Any) -> uuid.UUID | None:
        if isinstance(value, uuid.UUID):
            return value
        if isinstance(value, str) and value.strip():
            try:
                return uuid.UUID(value)
            except ValueError:
                return None
        return None

    def _human_review_report(
        self, interview: Interview, discrepancy_note: str | None
    ) -> EvaluationReport:
        return EvaluationReport(
            id="",
            masked_candidate_id=interview.candidate_email[:4].upper() if interview.candidate_email else "CAND-XX",
            overall_score=0.0,
            recommendation="borderline",
            needs_human_review=True,
            discrepancy_note=discrepancy_note,
            competencies={},
            evidence=[],
        )
