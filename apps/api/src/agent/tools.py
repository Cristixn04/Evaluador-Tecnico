"""Definiciones, validación, seguridad contextual y despacho de herramientas para Function Calling (S2).

Reutiliza los tres servicios de dominio existentes sin duplicar lógica:
1. `ProblemSelectorTool` (`problem_selector`) -> `src.problems.selector.ProblemSelector`
2. `CodeExecutionSandboxTool` (`code_execution_sandbox`) -> `src.execution.service.CodeExecutionService`
3. `AdaptiveHintGeneratorTool` (`adaptive_hint_generator`) -> `src.llm.prompts.load_hints` + estado `Interview`

Garantías de seguridad y resiliencia:
- Validación estricta de argumentos con Pydantic v2 (`extra="forbid"`).
- Vinculación inmutable al `interview_id` y `organization_id` de la sesión autenticada (el modelo nunca puede
  sobrescribir `interview_id`, `organization_id`, ni consultar recursos de otra entrevista u organización).
- Manejo estructurado de JSON malformado, herramientas desconocidas, llamadas duplicadas y timeouts.
- Política de reintentos acotada ante fallos transitorios de ejecución.
- Telemetría estructurada Anti-Leak por cada invocación.
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.telemetry import _sanitize_value, tool_telemetry
from src.db.enums import Seniority
from src.db.models import Interview, Problem, Snapshot, Vacancy
from src.execution.service import CodeExecutionService
from src.interview.service import InterviewService
from src.llm.prompts import load_hints
from src.problems.loader import load_default_catalog
from src.problems.selector import ProblemSelector

if TYPE_CHECKING:
    from src.llm.types import ToolCall

MAX_TOOL_ITERATIONS: int = 3
MAX_TOOL_CALLS_PER_TURN: int = 4
TOOL_EXECUTION_TIMEOUT_SECONDS: float = 20.0
MAX_TOOL_RETRIES: int = 1


class ProblemSelectorArgs(BaseModel):
    """Esquema de entrada validado para `problem_selector`."""

    model_config = ConfigDict(extra="forbid")

    action: Literal["inspect_assigned_problem", "search_catalog"] = Field(
        default="inspect_assigned_problem",
        description=(
            "Acción a realizar: 'inspect_assigned_problem' obtiene el enunciado, límites y casos "
            "del problema asignado a la entrevista activa; 'search_catalog' busca problemas "
            "compatibles en el catálogo por rol/seniority/lenguaje."
        ),
    )
    problem_id: str | None = Field(
        default=None,
        max_length=100,
        description="Identificador slug opcional del problema en el catálogo (ej. 'pse-payment-reconciliation').",
    )
    seniority: Literal["junior", "mid", "senior", "lead"] | None = Field(
        default=None,
        description="Nivel de seniority para filtrar problemas en el catálogo.",
    )
    language: Literal["python", "javascript", "sql"] | None = Field(
        default=None,
        description="Lenguaje de programación para filtrar en el catálogo.",
    )
    skills: list[str] | None = Field(
        default=None,
        max_length=10,
        description="Lista de habilidades o etiquetas técnicas para buscar en el catálogo.",
    )


class CodeExecutionSandboxArgs(BaseModel):
    """Esquema de entrada validado para `code_execution_sandbox`."""

    model_config = ConfigDict(extra="forbid")

    code: str | None = Field(
        default=None,
        max_length=20000,
        description=(
            "Código fuente del candidato a ejecutar en el sandbox aislado. Si se omite o "
            "use_latest_snapshot es true, se utiliza el último snapshot de código de la entrevista."
        ),
    )
    language: Literal["python", "javascript", "sql"] = Field(
        default="python",
        description="Lenguaje de ejecución en el sandbox ('python', 'javascript', 'sql').",
    )
    use_latest_snapshot: bool = Field(
        default=False,
        description="Si es true, ejecuta el código del snapshot más reciente guardado en la entrevista.",
    )


class AdaptiveHintGeneratorArgs(BaseModel):
    """Esquema de entrada validado para `adaptive_hint_generator`."""

    model_config = ConfigDict(extra="forbid")

    requested_level: int = Field(
        default=1,
        ge=1,
        le=3,
        description="Nivel de pista progresiva solicitado (1: conceptual, 2: algorítmica, 3: estructura/casos borde).",
    )
    reason: str = Field(
        default="Candidato solicita orientación o presenta bloqueo técnico",
        min_length=3,
        max_length=300,
        description="Justificación breve de por qué se solicita la pista adaptativa.",
    )


OPENAI_TOOLS_SCHEMA: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "problem_selector",
            "description": (
                "Consulta o selecciona especificaciones de problemas técnicos del catálogo oficial "
                "(enunciado, restricciones de tiempo/memoria, complejidad esperada y casos de prueba) "
                "para contextualizar la entrevista o responder dudas del candidato."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["inspect_assigned_problem", "search_catalog"],
                        "description": "Usa 'inspect_assigned_problem' para inspeccionar el problema activo o 'search_catalog' para filtrar el catálogo.",
                    },
                    "problem_id": {
                        "type": "string",
                        "description": "Slug opcional del problema en el catálogo (ej. 'pse-payment-reconciliation').",
                    },
                    "seniority": {
                        "type": "string",
                        "enum": ["junior", "mid", "senior", "lead"],
                        "description": "Filtro opcional de seniority.",
                    },
                    "language": {
                        "type": "string",
                        "enum": ["python", "javascript", "sql"],
                        "description": "Filtro opcional de lenguaje.",
                    },
                    "skills": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Etiquetas o habilidades técnicas a buscar.",
                    },
                },
                "required": ["action"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "code_execution_sandbox",
            "description": (
                "Ejecuta el código del candidato de forma aislada contra la batería de pruebas del "
                "problema asignado a la entrevista activa a través del servicio de sandbox (Judge0 CE). "
                "Devuelve el estado real ('success', 'test_failure', 'compile_error', 'timeout', "
                "'runtime_error', 'unavailable'), pruebas superadas y salida estándar/error."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": "Código fuente a evaluar. Si no se envía, usa use_latest_snapshot=true.",
                    },
                    "language": {
                        "type": "string",
                        "enum": ["python", "javascript", "sql"],
                        "description": "Lenguaje del código ('python', 'javascript', 'sql').",
                    },
                    "use_latest_snapshot": {
                        "type": "boolean",
                        "description": "Si es true, toma el último snapshot de código registrado en la entrevista.",
                    },
                },
                "required": ["language"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "adaptive_hint_generator",
            "description": (
                "Genera y registra una pista progresiva multinivel (nivel 1 conceptual, nivel 2 enfoque "
                "algorítmico, nivel 3 estructura y casos de borde) cuando el candidato pide una pista o "
                "muestra un bloqueo técnico persistente durante la entrevista."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "requested_level": {
                        "type": "integer",
                        "enum": [1, 2, 3],
                        "description": "Nivel de pista solicitado (1, 2 o 3).",
                    },
                    "reason": {
                        "type": "string",
                        "description": "Motivo técnico por el que se otorga la pista.",
                    },
                },
                "required": ["requested_level", "reason"],
                "additionalProperties": False,
            },
        },
    },
]


@dataclass(slots=True)
class ToolExecutionTrace:
    """Registro estructurado y sanitizado de una llamada a herramienta por parte del agente."""

    interview_id: str
    turn_id: str | None
    tool_name: str
    tool_call_id: str
    sanitized_arguments: dict[str, Any]
    sanitized_result: dict[str, Any]
    status: str  # "success" | "error" | "unavailable"
    duration_ms: int
    retries: int
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _sanitize_dict_for_trace(data: Mapping[str, Any] | dict[str, Any]) -> dict[str, Any]:
    sanitized: dict[str, Any] = {}
    for k, v in data.items():
        if k in {"api_key", "token", "password", "secret", "candidate_email", "candidate_name"}:
            sanitized[k] = "[REDACTED]"
        elif k == "code" and isinstance(v, str):
            sanitized["code_length"] = len(v)
            sanitized["code_preview"] = _sanitize_value(v[:45])
        elif isinstance(v, (int, float, bool)) or v is None:
            sanitized[k] = v
        elif isinstance(v, list):
            sanitized[k] = [_sanitize_value(item) for item in v[:5]]
        else:
            sanitized[k] = _sanitize_value(v)
    return sanitized


class AgentToolRuntime:
    """Ejecutor validado y acotado de herramientas invocadas mediante Function Calling por Grok."""

    def __init__(
        self,
        *,
        session: AsyncSession,
        interview: Interview,
        vacancy: Vacancy | None,
        problem: Problem | None,
        interview_service: InterviewService,
        problem_selector: ProblemSelector,
        prompt_version: str = "v2",
        turn_id: str | None = None,
        sandbox_runner: Any | None = None,
        max_retries: int = MAX_TOOL_RETRIES,
        max_tool_retries: int | None = None,
        timeout_seconds: float = TOOL_EXECUTION_TIMEOUT_SECONDS,
    ) -> None:
        self._session = session
        self._interview = interview
        self._vacancy = vacancy
        self._problem = problem
        self._interview_service = interview_service
        self._problem_selector = problem_selector
        self._prompt_version = prompt_version
        self._turn_id = turn_id
        self._sandbox_runner = sandbox_runner
        effective_retries = max_tool_retries if max_tool_retries is not None else max_retries
        self._max_retries = max(0, effective_retries)
        self._timeout_seconds = timeout_seconds
        self._seen_calls: set[tuple[str, str]] = set()
        self.traces: list[ToolExecutionTrace] = []

    @property
    def tools_schema(self) -> list[dict[str, Any]]:
        return OPENAI_TOOLS_SCHEMA

    async def execute_tool_call(self, tool_call: ToolCall) -> dict[str, Any]:
        """Valida permisos, esquema y ejecuta una llamada a herramienta retornando un dict serializable."""
        start_perf = time.perf_counter()
        tool_name = (tool_call.name or "").strip()
        call_id = (tool_call.id or "").strip() or "call-unknown"
        telemetry = tool_telemetry(tool_name or "unknown_tool", "function_call")

        # 1. Validar que la herramienta exista en el catálogo autorizado
        allowed_tools = {
            "problem_selector",
            "code_execution_sandbox",
            "adaptive_hint_generator",
        }
        if tool_name not in allowed_tools:
            telemetry.start(interview_id=self._interview.id, tool_call_id=call_id)
            err_msg = f"Unknown or unauthorized tool '{tool_name}'"
            telemetry.error(err_msg, interview_id=self._interview.id, status="error")
            result = {
                "status": "error",
                "error_code": "UNKNOWN_TOOL",
                "message": err_msg,
                "allowed_tools": sorted(allowed_tools),
            }
            self._record_trace(
                tool_name=tool_name or "unknown",
                call_id=call_id,
                raw_args={},
                result=result,
                status="error",
                start_perf=start_perf,
                retries=0,
                error=err_msg,
            )
            return result

        # 2. Parsear JSON de argumentos de forma segura
        try:
            parsed_args = json.loads(tool_call.arguments) if tool_call.arguments.strip() else {}
            if not isinstance(parsed_args, dict):
                raise TypeError("Tool arguments must be a JSON object")
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            telemetry.start(interview_id=self._interview.id, tool_call_id=call_id)
            err_msg = f"Invalid JSON arguments for tool '{tool_name}': {exc}"
            telemetry.error(err_msg, interview_id=self._interview.id, status="error")
            result = {
                "status": "error",
                "error_code": "INVALID_JSON_ARGUMENTS",
                "message": err_msg,
            }
            self._record_trace(
                tool_name=tool_name,
                call_id=call_id,
                raw_args={"raw": _sanitize_value(tool_call.arguments)},
                result=result,
                status="error",
                start_perf=start_perf,
                retries=0,
                error=err_msg,
            )
            return result

        # 3. Seguridad multi-tenant y de sesión: rechazar explícitamente cualquier intento de inyectar
        #    identificadores de entrevista, organización, usuario o candidato en los argumentos
        forbidden_context_keys = {
            "interview_id",
            "organization_id",
            "org_id",
            "user_id",
            "candidate_id",
            "candidate_email",
            "candidate_name",
        }
        attempted_forbidden = forbidden_context_keys.intersection(parsed_args.keys())
        if attempted_forbidden:
            telemetry.start(interview_id=self._interview.id, tool_call_id=call_id)
            err_msg = (
                f"Context security violation: tool arguments cannot override session keys "
                f"{sorted(attempted_forbidden)}"
            )
            telemetry.error(err_msg, interview_id=self._interview.id, status="error")
            result = {
                "status": "error",
                "error_code": "CONTEXT_SECURITY_VIOLATION",
                "message": err_msg,
            }
            self._record_trace(
                tool_name=tool_name,
                call_id=call_id,
                raw_args=parsed_args,
                result=result,
                status="error",
                start_perf=start_perf,
                retries=0,
                error=err_msg,
            )
            return result

        # 4. Protección contra llamadas idénticas duplicadas dentro del mismo turno
        canonical_args = json.dumps(parsed_args, sort_keys=True, ensure_ascii=False)
        signature = (tool_name, canonical_args)
        if signature in self._seen_calls:
            telemetry.start(interview_id=self._interview.id, tool_call_id=call_id)
            err_msg = f"Duplicate tool call '{tool_name}' with identical arguments in the same turn"
            telemetry.error(err_msg, interview_id=self._interview.id, status="error")
            result = {
                "status": "error",
                "error_code": "DUPLICATE_TOOL_CALL",
                "message": err_msg,
            }
            self._record_trace(
                tool_name=tool_name,
                call_id=call_id,
                raw_args=parsed_args,
                result=result,
                status="error",
                start_perf=start_perf,
                retries=0,
                error=err_msg,
            )
            return result

        # 5. Validar esquema Pydantic específico de la herramienta
        try:
            validated_model = self._validate_args(tool_name, parsed_args)
        except ValidationError as exc:
            telemetry.start(interview_id=self._interview.id, tool_call_id=call_id)
            err_msg = f"Schema validation failed for '{tool_name}': {exc.errors()[0].get('msg', str(exc))}"
            telemetry.error(err_msg, interview_id=self._interview.id, status="error")
            result = {
                "status": "error",
                "error_code": "INVALID_TOOL_ARGUMENTS",
                "message": err_msg,
            }
            self._record_trace(
                tool_name=tool_name,
                call_id=call_id,
                raw_args=parsed_args,
                result=result,
                status="error",
                start_perf=start_perf,
                retries=0,
                error=err_msg,
            )
            return result

        self._seen_calls.add(signature)
        telemetry.start(
            interview_id=self._interview.id,
            tool_call_id=call_id,
            **_sanitize_dict_for_trace(parsed_args),
        )

        # 6. Ejecutar con timeout y política de reintentos acotada ante fallos transitorios
        retries = 0
        last_exc: Exception | None = None
        for attempt in range(self._max_retries + 1):
            retries = attempt
            try:
                result = await asyncio.wait_for(
                    self._dispatch_validated(tool_name, validated_model),
                    timeout=self._timeout_seconds,
                )
                res_status = str(result.get("status", "success"))
                if res_status in {"error", "unavailable", "compile_error", "runtime_error", "timeout"}:
                    telemetry.error(
                        str(result.get("message") or result.get("stderr") or res_status),
                        interview_id=self._interview.id,
                        status=res_status,
                        retries=retries,
                    )
                else:
                    telemetry.success(
                        interview_id=self._interview.id,
                        status=res_status,
                        retries=retries,
                    )
                err_val = result.get("message")
                self._record_trace(
                    tool_name=tool_name,
                    call_id=call_id,
                    raw_args=parsed_args,
                    result=result,
                    status=res_status,
                    start_perf=start_perf,
                    retries=retries,
                    error=str(err_val) if res_status == "error" and err_val is not None else None,
                )
                return result
            except TimeoutError as exc:
                last_exc = exc
                if attempt < self._max_retries:
                    await asyncio.sleep(0.2 * (attempt + 1))
                    continue
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                if attempt < self._max_retries and self._is_retryable_tool_error(exc):
                    await asyncio.sleep(0.2 * (attempt + 1))
                    continue
                break

        err_str = f"Tool '{tool_name}' execution failed: {last_exc}"
        telemetry.error(err_str, interview_id=self._interview.id, status="error", retries=retries)
        error_result = {
            "status": "error",
            "error_code": "TOOL_EXECUTION_ERROR",
            "message": err_str,
            "retries": retries,
        }
        self._record_trace(
            tool_name=tool_name,
            call_id=call_id,
            raw_args=parsed_args,
            result=error_result,
            status="error",
            start_perf=start_perf,
            retries=retries,
            error=err_str,
        )
        return error_result

    def _validate_args(self, tool_name: str, parsed_args: dict[str, Any]) -> BaseModel:
        if tool_name == "problem_selector":
            return ProblemSelectorArgs.model_validate(parsed_args)
        if tool_name == "code_execution_sandbox":
            return CodeExecutionSandboxArgs.model_validate(parsed_args)
        if tool_name == "adaptive_hint_generator":
            return AdaptiveHintGeneratorArgs.model_validate(parsed_args)
        raise ValueError(f"Unsupported tool: {tool_name}")

    @staticmethod
    def _is_retryable_tool_error(exc: Exception) -> bool:
        msg = str(exc).lower()
        return isinstance(exc, (TimeoutError, ConnectionError, OSError)) or "timeout" in msg or "temporary" in msg

    async def _dispatch_validated(self, tool_name: str, model_args: BaseModel) -> dict[str, Any]:
        if tool_name == "problem_selector" and isinstance(model_args, ProblemSelectorArgs):
            return await self._run_problem_selector(model_args)
        if tool_name == "code_execution_sandbox" and isinstance(model_args, CodeExecutionSandboxArgs):
            return await self._run_code_execution_sandbox(model_args)
        if tool_name == "adaptive_hint_generator" and isinstance(model_args, AdaptiveHintGeneratorArgs):
            return await self._run_adaptive_hint_generator(model_args)
        return {
            "status": "error",
            "error_code": "DISPATCH_ERROR",
            "message": f"Unable to dispatch tool '{tool_name}'",
        }

    async def _run_problem_selector(self, args: ProblemSelectorArgs) -> dict[str, Any]:
        if hasattr(self._problem_selector, "before_tool_execution"):
            await self._problem_selector.before_tool_execution(args)
        catalog = load_default_catalog()

        # Si solicita inspeccionar el problema asignado o un problem_id específico
        if args.action == "inspect_assigned_problem" or args.problem_id:
            target_spec = None
            # Prioridad de seguridad: Si la entrevista ya tiene un problema asignado, mantenerlo estrictamente
            if self._interview.problem_id:
                target_spec = next(
                    (s for s in catalog if s.persistence_id() == self._interview.problem_id),
                    None,
                )
            if target_spec is None and args.problem_id:
                slug = args.problem_id.strip().casefold()
                target_spec = next((s for s in catalog if s.id.casefold() == slug), None)
            if target_spec is not None:
                return {
                    "status": "success",
                    "tool": "problem_selector",
                    "action": args.action,
                    "problem": {
                        "id": target_spec.id,
                        "title": target_spec.title,
                        "role": target_spec.role.value,
                        "difficulty": target_spec.difficulty.value,
                        "primary_language": target_spec.primary_language,
                        "tags": list(target_spec.tags),
                        "statement": target_spec.statement[:1200],
                        "limits": {
                            "timeout_ms": target_spec.limits.timeout_ms,
                            "memory_mb": target_spec.limits.memory_mb,
                        },
                        "total_tests": len(target_spec.tests),
                        "sample_test_ids": [t.id for t in target_spec.tests[:3]],
                    },
                }
            if self._problem is not None:
                return {
                    "status": "success",
                    "tool": "problem_selector",
                    "action": args.action,
                    "problem": {
                        "id": str(self._problem.id),
                        "title": self._problem.title,
                        "difficulty": (
                            self._problem.difficulty.value
                            if hasattr(self._problem.difficulty, "value")
                            else str(self._problem.difficulty)
                        ),
                        "primary_language": self._problem.language,
                        "tags": list(self._problem.tags or []),
                        "statement": (self._problem.scenario_preview or "")[:1200],
                    },
                }

        # Búsqueda en catálogo reutilizando ProblemSelector.select_one / search
        sen_enum: Seniority | None = None
        if args.seniority:
            sen_enum = Seniority(args.seniority)
        elif self._vacancy and self._vacancy.seniority:
            sen_enum = self._vacancy.seniority

        lang = args.language
        if not lang and self._vacancy and isinstance(self._vacancy.profile, dict):
            lang = self._vacancy.profile.get("primary_language")

        skills = args.skills
        if not skills and self._vacancy and isinstance(self._vacancy.profile, dict):
            skills = self._vacancy.profile.get("required_skills")

        selected = await self._problem_selector.select_one(
            skills=skills,
            seniority=sen_enum,
            language=lang,
            seed=str(self._interview.id),
        )
        if selected is None:
            # Fallback al catálogo en disco si la sesión es un mock sin DB poblada
            fallback_spec = catalog[0] if catalog else None
            if fallback_spec is None:
                return {
                    "status": "error",
                    "error_code": "PROBLEM_NOT_FOUND",
                    "message": "No matching problem found in catalog",
                }
            return {
                "status": "success",
                "tool": "problem_selector",
                "action": "search_catalog",
                "problem": {
                    "id": fallback_spec.id,
                    "title": fallback_spec.title,
                    "difficulty": fallback_spec.difficulty.value,
                    "primary_language": fallback_spec.primary_language,
                    "tags": list(fallback_spec.tags),
                    "statement": fallback_spec.statement[:1000],
                    "limits": {
                        "timeout_ms": fallback_spec.limits.timeout_ms,
                        "memory_mb": fallback_spec.limits.memory_mb,
                    },
                    "total_tests": len(fallback_spec.tests),
                },
            }

        return {
            "status": "success",
            "tool": "problem_selector",
            "action": args.action,
            "problem": {
                "id": str(selected.id),
                "title": selected.title,
                "difficulty": (
                    selected.difficulty.value
                    if hasattr(selected.difficulty, "value")
                    else str(selected.difficulty)
                ),
                "primary_language": selected.language,
                "tags": list(selected.tags or []),
                "statement": (selected.scenario_preview or "")[:1000],
            },
        }

    async def _run_code_execution_sandbox(self, args: CodeExecutionSandboxArgs) -> dict[str, Any]:
        target_code = (args.code or "").strip()
        if not target_code or args.use_latest_snapshot:
            snap_res = await self._session.scalars(
                select(Snapshot)
                .where(Snapshot.interview_id == self._interview.id)
                .order_by(Snapshot.created_at.desc())
                .limit(1)
            )
            latest_snap = snap_res.first() if hasattr(snap_res, "first") else None
            if latest_snap and latest_snap.code:
                target_code = latest_snap.code

        if not target_code:
            return {
                "status": "error",
                "error_code": "MISSING_CODE",
                "message": "No candidate code provided and no snapshot exists for this interview.",
            }

        exec_service = CodeExecutionService(
            session=self._session,
            interview_service=self._interview_service,
            sandbox_runner=self._sandbox_runner,
        )
        try:
            exec_result = await exec_service.execute_code(
                interview_id=self._interview.id,
                code=target_code,
                language=args.language,
            )
        finally:
            if self._sandbox_runner is None:
                await exec_service.close()

        return {
            "status": exec_result.get("status", "runtime_error"),
            "tool": "code_execution_sandbox",
            "language": args.language,
            "tests_passed": exec_result.get("tests_passed"),
            "total_tests": exec_result.get("total_tests"),
            "execution_time_ms": exec_result.get("execution_time_ms", 0),
            "stdout": (exec_result.get("stdout") or "")[:500] if exec_result.get("stdout") is not None else None,
            "stderr": (exec_result.get("stderr") or "")[:500] if exec_result.get("stderr") is not None else None,
            "test_details": exec_result.get("test_details", [])[:5],
        }

    async def _run_adaptive_hint_generator(self, args: AdaptiveHintGeneratorArgs) -> dict[str, Any]:
        current_level = int(self._interview.hint_level or 0)
        if current_level >= 3:
            return {
                "status": "max_level_reached",
                "error_code": "MAX_HINT_LEVEL_REACHED",
                "tool": "adaptive_hint_generator",
                "current_level": current_level,
                "max_level": 3,
                "hint_delivered": False,
                "message": "El candidato ya alcanzó el nivel máximo de pistas (3/3).",
            }

        # Avance progresivo controlado (no saltar niveles sin pasar por el siguiente)
        next_level = min(3, current_level + 1)
        hints_text = load_hints("CODING", self._prompt_version) or load_hints("CODING", "v2") or ""

        self._interview.hint_level = next_level
        self._interview.last_hint_at = datetime.now(UTC)
        self._session.add(self._interview)
        await self._session.flush()

        level_descriptions = {
            1: "Nivel 1 (Conceptual / Orientación Socrática sin revelar algoritmo)",
            2: "Nivel 2 (Enfoque algorítmico y estructura de datos recomendada)",
            3: "Nivel 3 (Estructura detallada y casos de borde críticos; conlleva penalización en rúbrica)",
        }
        penalty_map = {1: 1.0, 2: 2.5, 3: 5.0}
        score_cap_map = {1: 4.0, 2: 3.0, 3: 2.0}

        return {
            "status": "success",
            "tool": "adaptive_hint_generator",
            "hint_delivered": True,
            "previous_level": current_level,
            "granted_level": next_level,
            "requested_level": args.requested_level,
            "penalty_applied": penalty_map.get(next_level, 0.0),
            "max_score_cap": score_cap_map.get(next_level, 5.0),
            "level_description": level_descriptions.get(next_level, f"Nivel {next_level}"),
            "hint_guidance": hints_text[:1000],
            "penalty_warning": (
                "Nivel 3 otorgado: la evaluación posterior activará needs_human_review=true."
                if next_level >= 3
                else "Pista progresiva registrada en la sesión."
            ),
        }

    def _record_trace(
        self,
        *,
        tool_name: str,
        call_id: str,
        raw_args: Mapping[str, Any],
        result: Mapping[str, Any],
        status: str,
        start_perf: float,
        retries: int,
        error: str | None,
    ) -> None:
        duration_ms = max(0, int((time.perf_counter() - start_perf) * 1000))
        self.traces.append(
            ToolExecutionTrace(
                interview_id=str(self._interview.id),
                turn_id=self._turn_id,
                tool_name=tool_name,
                tool_call_id=call_id,
                sanitized_arguments=_sanitize_dict_for_trace(raw_args),
                sanitized_result=_sanitize_dict_for_trace(result),
                status=status,
                duration_ms=duration_ms,
                retries=retries,
                error=_sanitize_value(error) if error else None,
            )
        )
