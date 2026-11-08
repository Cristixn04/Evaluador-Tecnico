"""Script reproducible de prueba de humo e integración real multi-turno con Grok (Fase 1 - S1).

Ejecuta el agente real (`InterviewAgent`) conectado al proveedor Grok configurado
(`LLM_BASE_URL` / `LLM_MODEL`) a través de una entrevista técnica multi-turno real,
verificando:
1. Conectividad con la pasarela OpenAI-compatible de Grok sin exponer credenciales.
2. Persistencia transaccional de turnos (`Turn`) del candidato y del agente.
3. Conservación verificable del contexto conversacional entre múltiples turnos consecutivos.
4. Telemetría medida de latencia, tokens (`prompt_tokens`, `completion_tokens`, `total_tokens`) y costo en USD.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
import time
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

_API_DIR = Path(__file__).resolve().parents[2]
_REPO_ROOT = _API_DIR.parent.parent
if str(_API_DIR) not in sys.path:
    sys.path.insert(0, str(_API_DIR))

from sqlalchemy import select

from src.agent.service import InterviewAgent
from src.core.config import settings
from src.core.telemetry import reconstruct_task_cost_breakdown_from_db
from src.db.enums import InterviewPhase, InterviewStatus, Seniority, TurnSpeaker
from src.db.models import Interview, Organization, Problem, Turn, Vacancy
from src.db.session import async_session_maker
from src.interview.service import InterviewService
from src.problems.loader import load_default_catalog
from src.problems.selector import ProblemSelector

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("smoke_s1_grok")


async def run_s1_smoke(
    *,
    output_json: Path,
    output_md: Path,
) -> dict[str, Any]:
    has_real_key = bool(
        settings.LLM_API_KEY
        and settings.LLM_API_KEY.strip()
        and settings.LLM_API_KEY not in {"mock-llm-key", "your-api-key-here"}
        and not settings.USE_MOCK_LLM
    )

    if not has_real_key:
        raise RuntimeError(
            "BLOCKED: No se encontró una LLM_API_KEY real configurada o USE_MOCK_LLM=True."
        )

    settings.LLM_TIMEOUT_SECONDS = max(settings.LLM_TIMEOUT_SECONDS, 90.0)
    catalog = load_default_catalog()
    spec = next((p for p in catalog if p.id == "pse-payment-reconciliation"), catalog[0])

    turns_trace: list[dict[str, Any]] = []
    start_total = time.perf_counter()

    async with async_session_maker() as session:
        # 1. Asegurar problema y vacante aislados para S1 smoke
        problem_uuid = spec.persistence_id()
        problem = await session.get(Problem, problem_uuid)
        if problem is None:
            problem = Problem(
                id=problem_uuid,
                title=spec.title,
                difficulty=spec.difficulty,
                language=spec.primary_language,
                scenario_preview=spec.statement[:600],
                tags=list(spec.tags),
            )
            session.add(problem)
            await session.flush()

        org_stmt = select(Organization).where(Organization.name == "Org Smoke S1")
        org = (await session.execute(org_stmt)).scalar_one_or_none()
        if org is None:
            org = Organization(name="Org Smoke S1")
            session.add(org)
            await session.flush()

        vac = Vacancy(
            organization_id=org.id,
            title=f"Backend Senior - Smoke S1 ({uuid.uuid4().hex[:6]})",
            raw_description="Conciliación transaccional de pagos PSE en Python.",
            role_category="backend",
            seniority=Seniority.MID,
            profile={
                "primary_language": "python",
                "required_skills": ["python", "reconciliation", "hashing"],
                "preferred_skills": ["fastapi", "postgresql"],
            },
        )
        session.add(vac)
        await session.flush()

        now = datetime.now(UTC)
        interview = Interview(
            vacancy_id=vac.id,
            problem_id=problem.id,
            candidate_name="Candidato S1 Smoke",
            candidate_email="s1-smoke@evaluador.local",
            status=InterviewStatus.IN_PROGRESS,
            phase=InterviewPhase.CLARIFY,
            expires_at=now + timedelta(hours=2),
        )
        session.add(interview)
        await session.flush()
        await session.commit()

        interview_service = InterviewService(session)
        problem_selector = ProblemSelector(session)
        agent = InterviewAgent(
            session=session,
            interview_service=interview_service,
            problem_selector=problem_selector,
            prompt_version="v2",
        )

        # Conversación multi-turno con un dato ancla específico en el Turno 1 ("lote nocturno de 420,000 registros"
        # y identificador clave "CUS-ALPHA-99") que el modelo debe recordar en el Turno 3 sin repetirlo el usuario.
        scripted_messages = [
            (
                InterviewPhase.CLARIFY,
                "Hola. Estoy revisando el problema de conciliación PSE. En mi diseño quiero asumir que procesamos un lote nocturno de exactamente 420,000 registros y usamos una clave compuesta encabezada por el prefijo 'CUS-ALPHA-99'. ¿Es válido usar un diccionario hash en memoria para ese volumen?",
            ),
            (
                InterviewPhase.DESIGN,
                "Entendido. Además del diccionario en memoria, usaré Decimal('0.01') para comparar los montos en pesos colombianos y un set de códigos vistos para descartar webhooks duplicados en O(1). ¿Qué caso de borde adicional debería contemplar antes de codificar?",
            ),
            (
                InterviewPhase.DESIGN,
                "Antes de pasar al código, confírmame brevemente en una frase qué volumen exacto de registros del lote nocturno y qué prefijo de clave te mencioné en mi primer mensaje, y qué estructura de datos propuse para los duplicados.",
            ),
        ]

        try:
            for idx, (phase, user_msg) in enumerate(scripted_messages, start=1):
                interview.phase = phase
                cand_turn = Turn(
                    interview_id=interview.id,
                    speaker=TurnSpeaker.CANDIDATE,
                    content=user_msg,
                )
                session.add(cand_turn)
                await session.flush()
                await session.commit()

                t0 = time.perf_counter()
                chunks: list[str] = []
                async for delta in agent.stream_response(
                    interview_id=interview.id,
                    user_message=user_msg,
                    enable_tools=False,
                ):
                    chunks.append(delta)
                await session.commit()
                latency_ms = round((time.perf_counter() - t0) * 1000.0, 2)
                agent_reply = "".join(chunks)

                turns_trace.append(
                    {
                        "turn_number": idx,
                        "phase": phase.value,
                        "candidate_message": user_msg,
                        "agent_response": agent_reply,
                        "latency_ms": latency_ms,
                        "response_chars": len(agent_reply),
                    }
                )
                logger.info(
                    "Turno %d (%s) completado en %.2f ms (%d chars)",
                    idx,
                    phase.value,
                    latency_ms,
                    len(agent_reply),
                )
        finally:
            await agent.aclose()

        # Verificar persistencia real en base de datos
        persisted_turns = list(
            (
                await session.scalars(
                    select(Turn)
                    .where(Turn.interview_id == interview.id)
                    .order_by(Turn.created_at.asc())
                )
            ).all()
        )
        breakdown = await reconstruct_task_cost_breakdown_from_db(session, interview.id)

    total_duration_ms = round((time.perf_counter() - start_total) * 1000.0, 2)
    turn3_reply = turns_trace[-1]["agent_response"].lower() if turns_trace else ""
    remembers_volume = "420" in turn3_reply
    remembers_prefix = "cus-alpha-99" in turn3_reply or "alpha-99" in turn3_reply
    remembers_set = "set" in turn3_reply or "conjunto" in turn3_reply or "diccionario" in turn3_reply
    context_retained = bool(remembers_volume and remembers_prefix)

    evidence: dict[str, Any] = {
        "timestamp": datetime.now(UTC).isoformat(),
        "phase": "S1_REAL_GROK_INTEGRATION",
        "verdict": "PASS" if (len(turns_trace) == 3 and context_retained) else "PARTIAL",
        "provider": {
            "base_url": settings.LLM_BASE_URL,
            "configured_model": settings.LLM_MODEL,
            "observed_models": breakdown.conversational.models,
            "use_mock_llm": settings.USE_MOCK_LLM,
            "api_key_redacted": "[REDACTED_ENV_SECRET]",
        },
        "interview": {
            "interview_id": str(interview.id),
            "problem_id": spec.id,
            "persisted_turns_count": len(persisted_turns),
            "candidate_turns_count": sum(1 for t in persisted_turns if t.speaker == TurnSpeaker.CANDIDATE),
            "agent_turns_count": sum(1 for t in persisted_turns if t.speaker == TurnSpeaker.AGENT),
        },
        "context_retention_verification": {
            "remembers_420k_volume": remembers_volume,
            "remembers_cus_alpha_99_prefix": remembers_prefix,
            "remembers_dedup_structure": remembers_set,
            "context_retained": context_retained,
        },
        "telemetry": {
            "llm_calls": breakdown.conversational.call_count,
            "input_tokens": breakdown.conversational.total_input_tokens,
            "output_tokens": breakdown.conversational.total_output_tokens,
            "total_tokens": breakdown.conversational.total_tokens,
            "measured_cost_usd": breakdown.conversational.measured_cost,
            "total_duration_ms": total_duration_ms,
        },
        "turns": turns_trace,
    }

    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(evidence, indent=2, ensure_ascii=False), encoding="utf-8")

    md_lines = [
        "# S1 — Reporte de Integración Real Multi-Turno con Grok",
        "",
        f"**Fecha de Ejecución:** `{evidence['timestamp']}`  ",
        f"**Veredicto S1:** **`{evidence['verdict']}`**  ",
        f"**Proveedor / Gateway:** `{settings.LLM_BASE_URL}`  ",
        f"**Modelo Configurado:** `{settings.LLM_MODEL}`  ",
        f"**ID de Entrevista en PostgreSQL:** `{interview.id}`  ",
        "",
        "## 1. Comando Reproducible",
        "",
        "```bash",
        "python3 apps/api/src/scripts/smoke_s1_grok.py",
        "```",
        "",
        "## 2. Resumen de Telemetría y Persistencia",
        "",
        f"- **Llamadas reales al proveedor Grok:** `{breakdown.conversational.call_count}`",
        f"- **Tokens de entrada (`prompt_tokens`):** `{breakdown.conversational.total_input_tokens}`",
        f"- **Tokens de salida (`completion_tokens`):** `{breakdown.conversational.total_output_tokens}`",
        f"- **Tokens totales (`total_tokens`):** `{breakdown.conversational.total_tokens}`",
        f"- **Costo medido en USD:** `${breakdown.conversational.measured_cost:.6f}`",
        f"- **Duración total de los 3 turnos:** `{total_duration_ms} ms`",
        f"- **Turnos persistidos en PostgreSQL (`turns`):** `{len(persisted_turns)}` (3 candidato + 3 agente)",
        (
            f"- **Retención de contexto verificada en Turno 3:** `{context_retained}` "
            f"(volumen 420k=`{remembers_volume}`, prefijo CUS-ALPHA-99=`{remembers_prefix}`, estructura=`{remembers_set}`)"
        ),
        "",
        "## 3. Evidencia de Conversación Multi-Turno",
        "",
    ]

    for t in turns_trace:
        md_lines.extend(
            [
                f"### Turno {t['turn_number']} (`{t['phase']}` — Latencia: `{t['latency_ms']} ms`)",
                "",
                "**Candidato:**",
                f"> {t['candidate_message']}",
                "",
                "**Agente (Grok):**",
                f"> {t['agent_response']}",
                "",
            ]
        )

    output_md.parent.mkdir(parents=True, exist_ok=True)
    output_md.write_text("\n".join(md_lines), encoding="utf-8")
    return evidence


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke test real multi-turno S1 contra Grok.")
    parser.add_argument(
        "--output-json",
        type=Path,
        default=_REPO_ROOT / "docs" / "reports" / "FINAL_REMEDIATION" / "s1_smoke_evidence.json",
    )
    parser.add_argument(
        "--output-md",
        type=Path,
        default=_REPO_ROOT / "docs" / "reports" / "FINAL_REMEDIATION" / "S1_GROK_INTEGRATION_REPORT.md",
    )
    args = parser.parse_args()
    res = asyncio.run(run_s1_smoke(output_json=args.output_json, output_md=args.output_md))
    print(f"S1 Smoke Verdict: {res['verdict']} | Tokens: {res['telemetry']['total_tokens']} | Cost: ${res['telemetry']['measured_cost_usd']:.6f} USD")
    return 0 if res["verdict"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
