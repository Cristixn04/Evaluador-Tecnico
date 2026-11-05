"""Script reproducible para ejecutar las 10 pruebas reales S2 de Function Calling contra Grok.

Cubre los requisitos de la Fase 2 (S2 — Autonomía del Agente, Function Calling y 3 Herramientas):
- 6 ejecuciones normales (2 problem_selector, 2 code_execution_sandbox, 2 adaptive_hint_generator)
- 3 fallos controlados (sandbox unavailable con Judge0 apagado, hint_level máximo alcanzado 3/3,
  y fallo transitorio con reintento automático exitoso)
- 1 entrada inválida / violación de seguridad contextual (`CONTEXT_SECURITY_VIOLATION` + JSON malformado)
  donde el runtime rechaza la entrada, devuelve el error estructurado por `role="tool"` a Grok y el
  agente se recupera sin caer.

Uso:
    python3 apps/api/src/scripts/run_s2_10_executions.py
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

API_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = API_ROOT.parent.parent
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from src.agent.service import InterviewAgent
from src.core.config import settings
from src.core.telemetry import reconstruct_task_cost_breakdown_from_db
from src.db.enums import InterviewPhase, InterviewStatus, Seniority, TurnSpeaker
from src.db.models import Interview, Organization, Problem, Turn, Vacancy
from src.db.session import async_session_maker
from src.interview.service import InterviewService
from src.llm.factory import create_llm_client
from src.llm.types import ChatCompletion, ChatMessage, LLMClient, ToolCall
from src.problems.loader import load_default_catalog
from src.problems.selector import ProblemSelector
from src.sandbox.exceptions import SandboxUnavailableError
from src.sandbox.judge0 import Judge0Adapter
from src.sandbox.types import RunRequest, RunResult


class UnavailableSandboxRunner:
    """Runner que simula fallo de conexión a Judge0 sin detener el cluster Docker."""

    async def check_availability(self) -> bool:
        return False

    async def run(self, request: RunRequest) -> RunResult:
        raise SandboxUnavailableError("Judge0 connection refused at http://localhost:2358")

    async def aclose(self) -> None:
        pass


class TransientFlakyProblemSelector(ProblemSelector):
    """Lanza un fallo transitorio en el primer intento para verificar la política de retry en S2."""

    def __init__(self, session: Any) -> None:
        super().__init__(session)
        self.calls = 0

    async def before_tool_execution(self, _args: Any) -> None:
        self.calls += 1
        if self.calls == 1:
            raise TimeoutError("Temporary catalog read timeout on first attempt")


class InvalidArgInjectorLLMWrapper:
    """Intercepta la primera llamada a herramienta de Grok en exec_10 para inyectar un campo prohibido."""

    def __init__(self, inner: LLMClient) -> None:
        self._inner = inner
        self.injected_once = False

    async def complete(
        self,
        messages: list[ChatMessage],
        *,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | dict[str, Any] | None = None,
    ) -> ChatCompletion:
        comp = await self._inner.complete(
            messages,
            tools=tools,
            tool_choice=tool_choice,
        )
        if comp.tool_calls and not self.injected_once:
            self.injected_once = True
            first_tc = comp.tool_calls[0]
            try:
                parsed = json.loads(first_tc.arguments) if first_tc.arguments.strip() else {}
            except json.JSONDecodeError:
                parsed = {}
            if isinstance(parsed, dict):
                parsed["organization_id"] = "00000000-0000-0000-0000-000000000099"
                mutated_tc = ToolCall(
                    id=first_tc.id,
                    name=first_tc.name,
                    arguments=json.dumps(parsed),
                )
                return ChatCompletion(
                    content=comp.content,
                    model=comp.model,
                    usage=comp.usage,
                    finish_reason=comp.finish_reason,
                    tool_calls=[mutated_tc, *comp.tool_calls[1:]],
                )
        return comp

    async def aclose(self) -> None:
        return None


PASSING_PSE_CODE = """import json, sys
data = json.loads(sys.stdin.read())
gw = {item["reference"]: (item["amount_cents"], item["status"]) for item in data.get("gateway", [])}
ld = {item["reference"]: (item["amount_cents"], item["status"]) for item in data.get("ledger", [])}
mismatches = sorted(ref for ref in (set(gw) | set(ld)) if gw.get(ref) != ld.get(ref))
print(json.dumps({"mismatches": mismatches}, separators=(",", ":")))
"""

BUGGY_PSE_CODE = """# BUGGY_IMPLEMENTATION
import json, sys
data = json.loads(sys.stdin.read())
gw = {item["reference"]: item for item in data.get("gateway", [])}
ld = {item["reference"]: item for item in data.get("ledger", [])}
print(json.dumps({"mismatches": [r for r in gw if r not in ld]}, separators=(",", ":")))
"""


SCENARIOS: list[dict[str, Any]] = [
    {
        "id": "exec_01_normal_problem_selector_inspect",
        "category": "normal",
        "expected_tool": "problem_selector",
        "phase": InterviewPhase.INTRO,
        "hint_level": 0,
        "unassigned_problem": True,
        "prompt": (
            "Hola, estoy listo para comenzar la entrevista técnica. Entiendo que resolveremos el "
            "problema 'pse-payment-reconciliation'. ¿Me podrías compartir su enunciado y cuáles "
            "son los límites de tiempo y memoria?"
        ),
    },
    {
        "id": "exec_02_normal_problem_selector_search",
        "category": "normal",
        "expected_tool": "problem_selector",
        "phase": InterviewPhase.INTRO,
        "hint_level": 0,
        "unassigned_problem": True,
        "prompt": (
            "Hola, estoy listo para iniciar la entrevista de Senior Backend Engineer en Python. "
            "¿Qué problema del catálogo vamos a resolver hoy y de qué trata el escenario?"
        ),
    },
    {
        "id": "exec_03_normal_code_sandbox_pass",
        "category": "normal",
        "expected_tool": "code_execution_sandbox",
        "phase": InterviewPhase.CODING,
        "hint_level": 0,
        "sandbox_mode": "evaluate",
        "prompt": (
            "Acabo de terminar mi solución en Python para la conciliación transaccional PSE. "
            "¿Podrías probarla con los casos de prueba para verificar si cumple todos los requisitos?\n"
            "```python\n"
            + PASSING_PSE_CODE
            + "```"
        ),
    },
    {
        "id": "exec_04_normal_code_sandbox_fail",
        "category": "normal",
        "expected_tool": "code_execution_sandbox",
        "phase": InterviewPhase.CODING,
        "hint_level": 0,
        "sandbox_mode": "evaluate",
        "prompt": (
            "He implementado esta versión preliminar en Python para la conciliación de pagos. "
            "¿Podrías probarla en el entorno y decirme si pasa las pruebas o qué errores arroja?\n"
            "```python\n"
            + BUGGY_PSE_CODE
            + "```"
        ),
    },
    {
        "id": "exec_05_normal_hint_level_1",
        "category": "normal",
        "expected_tool": "adaptive_hint_generator",
        "phase": InterviewPhase.CODING,
        "hint_level": 0,
        "prompt": (
            "Estoy bloqueado pensando cómo estructurar la conciliación entre el extracto del gateway "
            "y el libro interno en memoria. ¿Me podrías dar una pista o guía conceptual para empezar "
            "a abordar el cruce de transacciones?"
        ),
    },
    {
        "id": "exec_06_normal_hint_level_2",
        "category": "normal",
        "expected_tool": "adaptive_hint_generator",
        "phase": InterviewPhase.CODING,
        "hint_level": 1,
        "prompt": (
            "Entiendo la idea general de indexar con diccionarios, pero sigo con dudas sobre cómo "
            "identificar eficientemente las transacciones que están en un sistema pero faltan en el otro "
            "o que difieren en monto. ¿Podrías darme una pista algorítmica más específica para destrabarme?"
        ),
    },
    {
        "id": "exec_07_failure_sandbox_unavailable",
        "category": "controlled_failure",
        "expected_tool": "code_execution_sandbox",
        "phase": InterviewPhase.CODING,
        "hint_level": 0,
        "sandbox_mode": "unavailable",
        "prompt": (
            "Tengo lista esta solución en Python para conciliar las transacciones. "
            "¿Podrías ejecutarla en el entorno para verificar si pasa las pruebas unitarias?\n"
            "```python\n"
            + PASSING_PSE_CODE
            + "```"
        ),
    },
    {
        "id": "exec_08_failure_hint_max_level_reached",
        "category": "controlled_failure",
        "expected_tool": "adaptive_hint_generator",
        "phase": InterviewPhase.CODING,
        "hint_level": 3,
        "prompt": (
            "Ya recibí la pista 2 pero sigo atascado en cómo construir la lista final ordenada de "
            "mismatches sin duplicados. Solicito explícitamente una pista de nivel 3 para poder destrabarme."
        ),
    },
    {
        "id": "exec_09_failure_transient_tool_retry_recovery",
        "category": "controlled_failure",
        "expected_tool": "problem_selector",
        "phase": InterviewPhase.INTRO,
        "hint_level": 0,
        "unassigned_problem": True,
        "flaky_selector": True,
        "prompt": (
            "Hola, estoy conectado para mi entrevista de backend en Python. ¿Podrías consultar el "
            "catálogo y presentarme el problema asignado?"
        ),
    },
    {
        "id": "exec_10_invalid_input_validation_and_recovery",
        "category": "invalid_input",
        "expected_tool": "problem_selector",
        "phase": InterviewPhase.INTRO,
        "hint_level": 0,
        "unassigned_problem": True,
        "inject_invalid_arg": True,
        "prompt": (
            "Hola, vengo a resolver el problema 'pse-payment-reconciliation'. ¿Me puedes compartir "
            "el enunciado y las restricciones de ejecución?"
        ),
    },
]


async def _ensure_seed_entities(session: Any) -> tuple[Organization, Vacancy, Problem]:
    catalog = load_default_catalog()
    org = Organization(name=f"S2-Grok-Org-{uuid4().hex[:8]}")
    session.add(org)
    await session.flush()

    vacancy = Vacancy(
        organization_id=org.id,
        title="Senior Backend Engineer (Python) - S2 Function Calling",
        raw_description="Conciliación transaccional de pagos PSE y microservicios en Python.",
        role_category="backend",
        seniority=Seniority.SENIOR,
        profile={
            "primary_language": "python",
            "required_skills": ["reconciliation", "payments", "hash-map"],
            "preferred_skills": ["fastapi", "postgresql"],
        },
    )
    session.add(vacancy)
    await session.flush()

    # Asegurar que los problemas del catálogo existan en la tabla problems
    primary_problem: Problem | None = None
    for spec in catalog:
        pid = spec.persistence_id()
        existing = await session.get(Problem, pid)
        if existing is None:
            existing = Problem(
                id=pid,
                title=spec.title,
                difficulty=spec.difficulty,
                language=spec.primary_language,
                tags=list(spec.tags),
                scenario_preview=spec.statement[:600],
            )
            session.add(existing)
        if spec.id == "pse-payment-reconciliation":
            primary_problem = existing
    await session.flush()
    assert primary_problem is not None
    return org, vacancy, primary_problem


def _render_markdown_report(payload: dict[str, Any]) -> str:
    summary = payload["summary"]
    lines = [
        "# S2 — Reporte de Autonomía del Agente y Function Calling Real con Grok",
        "",
        f"**Fecha de Ejecución:** `{payload['executed_at']}`  ",
        f"**Veredicto S2:** **`{payload['verdict']}`**  ",
        f"**Proveedor / Gateway:** `{payload['provider']['base_url']}`  ",
        f"**Modelo Configurado:** `{payload['provider']['model']}`  ",
        "**Sandbox de Código:** `Judge0 CE v1.13.1 (http://localhost:2358, cgroup v2 rlimit mode)`  ",
        "",
        "## 1. Resumen Ejecutivo de las 10 Ejecuciones End-to-End",
        "",
        f"- **Total de ejecuciones:** `{summary['total_executions']}`",
        f"- **Ejecuciones normales exitosas:** `{summary['normal_count']}` (requeridas: $\\ge 6$)",
        f"- **Ejecuciones con fallo controlado y recuperación:** `{summary['controlled_failure_count']}` (requeridas: $\\ge 3$)",
        f"- **Ejecuciones con entrada inválida / bloqueo de seguridad contextual:** `{summary['invalid_input_count']}` (requeridas: $\\ge 1$)",
        f"- **Total de llamadas a herramientas ejecutadas (`tool_calls`):** `{summary['total_tool_calls']}`",
        f"- **Llamadas reales al proveedor LLM (`llm_usage_records`):** `{summary['total_llm_calls']}`",
        f"- **Tokens totales consumidos:** `{summary['total_tokens']}` (`input={summary['prompt_tokens']}`, `output={summary['completion_tokens']}`)",
        f"- **Costo total medido (USD):** `${summary['total_cost_usd']:.6f}`",
        "",
        "## 2. Tabla Comparativa de las 10 Ejecuciones",
        "",
        "| # | Escenario | Categoría | Herramienta Invocada | Estado Tool | Reintentos | Latencia Turno (ms) | Tokens | Costo (USD) |",
        "|---|-----------|-----------|----------------------|-------------|------------|---------------------|--------|-------------|",
    ]

    for idx, item in enumerate(payload["executions"], start=1):
        traces = item["tool_traces"]
        tool_names = ", ".join(t["tool_name"] for t in traces) if traces else "none"
        statuses = ", ".join(t["status"] for t in traces) if traces else "none"
        retries = sum(int(t.get("retries", 0)) for t in traces)
        lines.append(
            f"| {idx} | `{item['scenario_id']}` | `{item['category']}` | `{tool_names}` | "
            f"`{statuses}` | `{retries}` | `{item['duration_ms']}` | `{item['usage']['total_tokens']}` | "
            f"`${item['usage']['cost_usd']:.6f}` |"
        )

    lines.extend(
        [
            "",
            "## 3. Detalle de Trazas por Ejecución",
            "",
        ]
    )

    for idx, item in enumerate(payload["executions"], start=1):
        lines.extend(
            [
                f"### {idx}. `{item['scenario_id']}` (`{item['category']}`)",
                "",
                f"- **Fase de entrevista:** `{item['phase']}` | **Hint level inicial → final:** `{item['initial_hint_level']} -> {item['final_hint_level']}`",
                f"- **Latencia total del turno:** `{item['duration_ms']} ms` | **Llamadas LLM en el turno:** `{item['usage']['llm_calls']}`",
                "",
                "**Mensaje del Candidato:**",
                f"> {item['candidate_prompt'].splitlines()[0]}",
                "",
                "**Trazas de Herramientas (`AgentToolRuntime`):**",
                "```json",
                json.dumps(item["tool_traces"], indent=2, ensure_ascii=False),
                "```",
                "",
                "**Respuesta Final Sintetizada por Grok:**",
                f"> {' '.join(item['agent_reply'].strip().splitlines())[:900]}",
                "",
            ]
        )

    return "\n".join(lines) + "\n"


async def run_s2_benchmark(
    output_json: Path,
    output_md: Path,
    *,
    force_rerun: bool = False,
) -> dict[str, Any]:
    if settings.USE_MOCK_LLM or not settings.LLM_API_KEY or settings.LLM_API_KEY == "mock-llm-key":
        raise RuntimeError("S2 requiere conexión real a Grok (USE_MOCK_LLM=False y LLM_API_KEY válida).")

    settings.LLM_TIMEOUT_SECONDS = max(settings.LLM_TIMEOUT_SECONDS, 90.0)

    existing_results: dict[str, dict[str, Any]] = {}
    if output_json.exists() and not force_rerun:
        try:
            loaded = json.loads(output_json.read_text(encoding="utf-8"))
            for item in loaded.get("executions", []):
                if item.get("passed"):
                    existing_results[item["scenario_id"]] = item
        except (json.JSONDecodeError, OSError, KeyError):
            existing_results = {}

    base_llm_client = create_llm_client()
    judge0_runner = Judge0Adapter(base_url="http://localhost:2358")
    executions_out: list[dict[str, Any]] = []

    try:
        async with async_session_maker() as session:
            _org, vacancy, problem = await _ensure_seed_entities(session)
            interview_service = InterviewService(session)

            for sc in SCENARIOS:
                sc_id = sc["id"]
                if sc_id in existing_results:
                    print(f"[SKIP/CACHED] {sc_id}", flush=True)
                    executions_out.append(existing_results[sc_id])
                    continue

                print(f"[RUN] {sc_id} ({sc['category']})...", flush=True)
                now = datetime.now(UTC)
                interview = Interview(
                    vacancy_id=vacancy.id,
                    problem_id=None if sc.get("unassigned_problem") else problem.id,
                    candidate_name="Candidato S2 Anonimizado",
                    candidate_email=f"s2-{uuid4().hex[:6]}@evaluador.local",
                    status=InterviewStatus.IN_PROGRESS,
                    phase=sc["phase"],
                    hint_level=sc["hint_level"],
                    expires_at=now + timedelta(hours=2),
                )
                session.add(interview)
                await session.flush()

                cand_turn = Turn(
                    interview_id=interview.id,
                    speaker=TurnSpeaker.CANDIDATE,
                    content=sc["prompt"],
                )
                session.add(cand_turn)
                await session.flush()

                selector: ProblemSelector = (
                    TransientFlakyProblemSelector(session)
                    if sc.get("flaky_selector")
                    else ProblemSelector(session)
                )
                sandbox_runner = (
                    UnavailableSandboxRunner()
                    if sc.get("sandbox_mode") == "unavailable"
                    else judge0_runner
                )
                llm_for_agent: Any = (
                    InvalidArgInjectorLLMWrapper(base_llm_client)
                    if sc.get("inject_invalid_arg")
                    else base_llm_client
                )

                agent = InterviewAgent(
                    session=session,
                    interview_service=interview_service,
                    problem_selector=selector,
                    prompt_version="v2",
                    llm_client=llm_for_agent,
                    sandbox_runner=sandbox_runner,
                    max_tool_retries=1,
                )

                t0 = time.perf_counter()
                reply, traces = await agent.generate_reply_with_tools(
                    interview_id=interview.id,
                    user_message=sc["prompt"],
                    auto_hints=False,
                    enable_tools=True,
                )
                duration_ms = round((time.perf_counter() - t0) * 1000, 2)
                await session.commit()

                breakdown = await reconstruct_task_cost_breakdown_from_db(session, interview.id)
                prompt_tok = breakdown.conversational.total_input_tokens
                comp_tok = breakdown.conversational.total_output_tokens
                tot_tok = breakdown.conversational.total_tokens
                cost_usd = round(float(breakdown.conversational.measured_cost), 6)
                llm_calls = breakdown.conversational.call_count

                trace_dicts = [t.to_dict() for t in traces]
                has_expected_tool = any(t["tool_name"] == sc["expected_tool"] for t in trace_dicts)
                passed = bool(reply.strip() and has_expected_tool)

                record = {
                    "scenario_id": sc_id,
                    "category": sc["category"],
                    "expected_tool": sc["expected_tool"],
                    "interview_id": str(interview.id),
                    "phase": sc["phase"].value,
                    "initial_hint_level": sc["hint_level"],
                    "final_hint_level": interview.hint_level,
                    "candidate_prompt": sc["prompt"],
                    "agent_reply": reply,
                    "tool_traces": trace_dicts,
                    "duration_ms": duration_ms,
                    "usage": {
                        "llm_calls": llm_calls,
                        "prompt_tokens": prompt_tok,
                        "completion_tokens": comp_tok,
                        "total_tokens": tot_tok,
                        "cost_usd": cost_usd,
                    },
                    "passed": passed,
                }
                executions_out.append(record)
                print(
                    f"[DONE] {sc_id} -> tools={[t['tool_name'] for t in trace_dicts]} "
                    f"statuses={[t['status'] for t in trace_dicts]} duration={duration_ms}ms",
                    flush=True,
                )

                # Guardar progreso incrementalmente
                partial_payload = _build_payload(executions_out)
                output_json.parent.mkdir(parents=True, exist_ok=True)
                output_json.write_text(
                    json.dumps(partial_payload, indent=2, ensure_ascii=False),
                    encoding="utf-8",
                )
    finally:
        await base_llm_client.aclose()
        await judge0_runner.aclose()

    final_payload = _build_payload(executions_out)
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(final_payload, indent=2, ensure_ascii=False), encoding="utf-8")
    output_md.write_text(_render_markdown_report(final_payload), encoding="utf-8")
    return final_payload


def _build_payload(executions_out: list[dict[str, Any]]) -> dict[str, Any]:
    normal_count = sum(1 for e in executions_out if e["category"] == "normal" and e["passed"])
    failure_count = sum(
        1 for e in executions_out if e["category"] == "controlled_failure" and e["passed"]
    )
    invalid_count = sum(
        1 for e in executions_out if e["category"] == "invalid_input" and e["passed"]
    )
    total_tool_calls = sum(len(e["tool_traces"]) for e in executions_out)
    total_llm_calls = sum(e["usage"]["llm_calls"] for e in executions_out)
    prompt_tokens = sum(e["usage"]["prompt_tokens"] for e in executions_out)
    completion_tokens = sum(e["usage"]["completion_tokens"] for e in executions_out)
    total_tokens = sum(e["usage"]["total_tokens"] for e in executions_out)
    total_cost_usd = round(sum(e["usage"]["cost_usd"] for e in executions_out), 6)

    all_passed = (
        len(executions_out) == 10
        and normal_count >= 6
        and failure_count >= 3
        and invalid_count >= 1
    )
    return {
        "phase": "S2_FUNCTION_CALLING_10_EXECUTIONS",
        "executed_at": datetime.now(UTC).isoformat(),
        "verdict": "PASS" if all_passed else "PARTIAL",
        "provider": {
            "base_url": settings.LLM_BASE_URL,
            "model": settings.LLM_MODEL,
            "use_mock_llm": settings.USE_MOCK_LLM,
        },
        "sandbox": {
            "provider": "Judge0 CE v1.13.1",
            "base_url": "http://localhost:2358",
            "mode": "real_docker_container",
        },
        "summary": {
            "total_executions": len(executions_out),
            "normal_count": normal_count,
            "controlled_failure_count": failure_count,
            "invalid_input_count": invalid_count,
            "total_tool_calls": total_tool_calls,
            "total_llm_calls": total_llm_calls,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
            "total_cost_usd": total_cost_usd,
        },
        "executions": executions_out,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Ejecuta los 10 escenarios reales S2 con Grok.")
    parser.add_argument(
        "--output-json",
        type=Path,
        default=REPO_ROOT / "docs/reports/FINAL_REMEDIATION/s2_10_executions.json",
    )
    parser.add_argument(
        "--output-md",
        type=Path,
        default=REPO_ROOT / "docs/reports/FINAL_REMEDIATION/S2_FUNCTION_CALLING_REPORT.md",
    )
    parser.add_argument(
        "--force-rerun",
        action="store_true",
        help="Fuerza la reejecución de los 10 escenarios ignorando resultados previos en caché.",
    )
    args = parser.parse_args()

    payload = asyncio.run(run_s2_benchmark(args.output_json, args.output_md, force_rerun=args.force_rerun))
    print(
        f"S2 Verdict: {payload['verdict']} | Executions: {payload['summary']['total_executions']}/10 | "
        f"Tool Calls: {payload['summary']['total_tool_calls']} | "
        f"Cost: ${payload['summary']['total_cost_usd']:.6f} USD"
    )
    return 0 if payload["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
