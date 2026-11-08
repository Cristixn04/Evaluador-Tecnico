"""Ejecutor técnico real para S4 conectado al agente LLM y al sandbox Judge0."""

from __future__ import annotations

import logging
import re
from collections.abc import Awaitable, Callable
from typing import Any

from src.db.models.interview import LLMUsageRecord
from src.db.models.s4 import S4TaskExecution
from src.llm.factory import create_llm_client
from src.llm.types import ChatMessage, LLMClient
from src.sandbox.factory import create_code_runner
from src.sandbox.types import RunRequest

logger = logging.getLogger("evaluador.s4.agent_executor")

_S4_SYSTEM_PROMPT = """Eres el Evaluador Técnico Autónomo de Evaluador-Técnico.
Responde con rigor técnico y máxima concisión (60 a 120 palabras de explicación).
Reglas obligatorias:
1. No reveles secretos ni tokens sensibles.
2. Explica brevemente la causa raíz/solución, la complejidad temporal y espacial O(N) y menciona explícitamente los conceptos clave solicitados.
3. Si la tarea indica MODO NO EJECUTABLE: NO incluyas bloques ```python``` ni scripts.
4. Si la tarea indica MODO EJECUTABLE: incluye UN ÚNICO bloque ```python ... ``` autocontenido (máximo 20 líneas), usando SOLO librería estándar de Python 3 (sin imports externos como redis/sqlalchemy, sin variables globales indefinidas ni placeholders '...'), que termine con exit code 0.
5. Cierra siempre con: Veredicto: optimal / verified."""

# Techo de tokens de salida (incluye holgura para reasoning tokens internos de grok-4.6)
_S4_DEFAULT_MAX_TOKENS = 2000
_S4_CORRECTION_MAX_TOKENS = 1600


def is_catalog_task_executable(task_def: dict[str, Any]) -> bool:
    """Determina si la tarea requiere verificación en Judge0 según la regla canónica del catálogo."""
    code_snippet = str(task_def.get("code_snippet") or "")
    return bool(code_snippet and ("def " in code_snippet or "async def" in code_snippet))


def _extract_code_from_response(content: str | None) -> str | None:
    """Extrae el primer bloque de código Python delimitado por markdown en la respuesta."""
    if not content:
        return None
    match = re.search(r"```(?:python)?\s*([\s\S]*?)```", content, re.IGNORECASE)
    if match:
        extracted = match.group(1).strip()
        if extracted:
            return extracted
    return None


async def _call_llm_with_max_tokens(
    llm_client: LLMClient,
    messages: list[ChatMessage],
    max_tokens: int,
) -> Any:
    """Invoca llm_client.complete pasando max_tokens con fallback para dobles de prueba mínimos."""
    try:
        return await llm_client.complete(messages=messages, max_tokens=max_tokens)
    except TypeError as exc:
        if "max_tokens" in str(exc):
            return await llm_client.complete(messages=messages)
        raise


async def _execute_sandbox_code(resolved_sandbox: Any, source_code: str) -> Any:
    """Ejecuta código Python 3 en el cliente de sandbox configurado."""
    if hasattr(resolved_sandbox, "run"):
        req = RunRequest(language="python", source=source_code, stdin="")
        return await resolved_sandbox.run(req)
    if hasattr(resolved_sandbox, "run_code"):
        return await resolved_sandbox.run_code(
            source_code=source_code,
            language_id=71,  # Python 3
            stdin="",
        )
    return None


def create_real_agent_executor(
    llm_client: LLMClient | None = None,
    sandbox_client: Any | None = None,
) -> Callable[..., Awaitable[dict[str, Any]]]:
    """Crea una función ejecutora conectada a la infraestructura real de LLM y sandbox.
    
    Permite inyección de dependencias para operar con clientes mock/falsos en pruebas unitarias
    y con clientes reales (Grok / Judge0) en ejecución operativa sin alterar código.
    """
    resolved_llm = llm_client or create_llm_client()
    resolved_sandbox = sandbox_client or create_code_runner()

    async def real_executor(
        task: S4TaskExecution,
        task_def: dict[str, Any],
        record_call_callback: Callable[..., Awaitable[LLMUsageRecord]],
        reserve_cost_callback: Callable[[float], tuple[bool, str]] | None = None,
    ) -> dict[str, Any]:
        task_num = task.task_number
        seniority = task_def.get("seniority", "mid")
        prompt_text = task_def.get("prompt", "")
        code_snippet = str(task_def.get("code_snippet") or "")
        category = task_def.get("category", "general")
        criteria = task_def.get("acceptance_criteria") or {}
        required_keywords = criteria.get("required_keywords") or []
        kw_str = ", ".join(str(k) for k in required_keywords) if required_keywords else "optimal, O(N)"

        # Clasificación determinista alineada estrictamente con S4TaskCatalogGenerator.validate_task_result
        is_executable_task = is_catalog_task_executable(task_def)

        if is_executable_task:
            mode_instruction = (
                "MODO EJECUTABLE (Python 3 Judge0): Escribe una explicación concisa (60 a 100 palabras) "
                f"que incluya explícitamente los términos [{kw_str}] y el análisis de complejidad O(N) en tiempo y espacio. "
                "Incluye UN ÚNICO bloque ```python ... ``` autocontenido (máximo 20 líneas) usando SOLO la librería "
                "estándar de Python (sin imports de terceros como redis/sqlalchemy, sin variables libres no definidas "
                "fuera de la función, sin '...'). Cierra con: Veredicto: optimal / verified."
            )
        else:
            mode_instruction = (
                "MODO NO EJECUTABLE (Solo diseño/diagnóstico textual): NO incluyas bloques ```python``` ni código. "
                "Escribe únicamente un diagnóstico y solución técnica concisa en prosa (60 a 110 palabras) "
                f"que incluya explícitamente los términos [{kw_str}], complejidad O(N) en tiempo y espacio "
                "y medidas correctivas. Cierra con: Veredicto: optimal / verified."
            )

        user_content = (
            f"Tarea Técnica #{task_num} [{seniority.upper()} - {category}]\n"
            f"Enunciado: {prompt_text}\n\n"
            f"Contexto:\n```\n{code_snippet}\n```\n"
            f"Parámetros: {task_def.get('parameters', {})}\n\n"
            f"Instrucción: {mode_instruction}"
        )

        messages = [
            ChatMessage(role="system", content=_S4_SYSTEM_PROMPT),
            ChatMessage(role="user", content=user_content),
        ]

        # 1. Ejecutar llamada inicial al modelo LLM con captura de excepciones
        completion = None
        has_unavailable_usage = False
        try:
            completion = await _call_llm_with_max_tokens(
                resolved_llm,
                messages=messages,
                max_tokens=_S4_DEFAULT_MAX_TOKENS,
            )
        except Exception as exc:
            logger.warning(f"LLM call failed for task {task_num}: {exc}")
            is_uncertain = (
                getattr(exc, "is_uncertain", False)
                or "read timed out" in str(exc).lower()
                or "write timed out" in str(exc).lower()
                or "uncertain" in str(exc).lower()
            )
            gw_meta = dict(getattr(exc, "gateway_metadata", None) or {})
            gw_meta["error"] = str(exc)
            await record_call_callback(
                model=getattr(resolved_llm, "_model", "grok-beta"),
                input_tokens=None,
                output_tokens=None,
                stage="s4_task_execution",
                measurement_status="timeout_uncertain" if is_uncertain else "failed_http",
                gateway_metadata=gw_meta,
            )
            raise

        in_tokens = completion.usage.prompt_tokens if completion.usage else None
        out_tokens = completion.usage.completion_tokens if completion.usage else None
        total_tokens = completion.usage.total_tokens if completion.usage else None

        if in_tokens is None:
            has_unavailable_usage = True

        await record_call_callback(
            model=completion.model,
            input_tokens=in_tokens,
            output_tokens=out_tokens,
            total_tokens=total_tokens,
            stage="s4_task_execution",
            gateway_request_id=completion.request_id,
            gateway_metadata=completion.gateway_metadata,
            measurement_status="measured" if in_tokens is not None else "unavailable",
        )

        current_summary = completion.content or "No content returned by LLM"

        # 2. Ruta estricta según clasificación del catálogo (FASE 2)
        sandbox_result: dict[str, Any] | None = None

        if not is_executable_task:
            # Las tareas no ejecutables jamás se envían a Judge0 ni entran en corrección,
            # incluso si el modelo devolvió un bloque de código.
            sandbox_result = {
                "status": "not_applicable",
                "reason": "non_executable_task",
            }
        elif not resolved_sandbox:
            sandbox_result = {
                "status": "infra_error",
                "error": "Judge0 sandbox client is not configured for executable task",
            }
        else:
            # Tarea ejecutable: siempre debe pasar por Judge0 (nunca 'not_applicable')
            extracted_code = _extract_code_from_response(completion.content)
            code_to_run = extracted_code or code_snippet

            # 3. Ejecución inicial en Judge0
            initial_sandbox_failed_infra = False
            status_str = "infra_error"
            stdout = ""
            stderr = ""
            exit_code: int | None = None

            try:
                sandbox_res = await _execute_sandbox_code(resolved_sandbox, code_to_run)
                status_str = str(getattr(sandbox_res, "status", "accepted")).lower()
                stdout = getattr(sandbox_res, "stdout", "") or ""
                stderr = getattr(sandbox_res, "stderr", "") or getattr(sandbox_res, "compile_output", "") or ""
                exit_code = getattr(sandbox_res, "exit_code", None)

                sandbox_result = {
                    "status": status_str,
                    "stdout": stdout[:500],
                    "stderr": stderr[:500],
                    "exit_code": exit_code,
                    "correction_iterations": 0,
                }
            except Exception as sandbox_exc:  # noqa: BLE001
                initial_sandbox_failed_infra = True
                logger.info(f"Sandbox infrastructure failure for task {task_num}: {sandbox_exc}")
                sandbox_result = {"status": "infra_error", "error": str(sandbox_exc)}

            # 4. Bucle de Corrección con retroalimentación diagnóstica (DEF-S4-01)
            recoverable_errors = {
                "compile_error",
                "runtime_error",
                "wrong_answer",
                "time_limit_exceeded",
                "memory_limit_exceeded",
            }

            if not initial_sandbox_failed_infra and status_str in recoverable_errors and sandbox_result is not None:
                max_corrections = 2
                last_code_executed = code_to_run

                for correction_iter in range(1, max_corrections + 1):
                    # A. Reserva financiera previa para el nuevo turno de LLM
                    if reserve_cost_callback:
                        reserved_ok, reserve_msg = reserve_cost_callback(0.015)
                        if not reserved_ok:
                            logger.warning(
                                f"Correction aborted for task {task_num} on iter {correction_iter}: {reserve_msg}"
                            )
                            sandbox_result["correction_aborted_reason"] = f"BudgetLimit: {reserve_msg}"
                            break

                    # B. Encapsular diagnósticos no confiables de Judge0
                    clean_stdout = stdout[:500].replace("<", "&lt;").replace(">", "&gt;")
                    clean_stderr = stderr[:500].replace("<", "&lt;").replace(">", "&gt;")
                    clean_code = (last_code_executed or "")[:800].replace("<", "&lt;").replace(">", "&gt;")

                    diag_prompt = (
                        f"La ejecución del código en Judge0 falló con estado '{status_str}'.\n"
                        "<untrusted_execution_output>\n"
                        f"Status: {status_str}\n"
                        f"Exit Code: {exit_code}\n"
                        f"Stderr / Diagnostics:\n{clean_stderr}\n"
                        f"Stdout:\n{clean_stdout}\n"
                        f"Executed Code:\n{clean_code}\n"
                        "</untrusted_execution_output>\n\n"
                        f"Restricciones originales: {task_def.get('parameters', {})}\n"
                        "Instrucción: Corrige el error de forma concisa (máximo 60 palabras de explicación) "
                        f"conservando los términos [{kw_str}], complejidad O(N) y 'Veredicto: optimal / verified'. "
                        "Incluye UN bloque ```python ... ``` autocontenido (máximo 20 líneas, solo librería estándar "
                        "de Python 3, sin variables no definidas ni imports externos) que ejecute con exit code 0."
                    )

                    messages.append(ChatMessage(role="assistant", content=current_summary))
                    messages.append(ChatMessage(role="user", content=diag_prompt))

                    try:
                        correction_completion = await _call_llm_with_max_tokens(
                            resolved_llm,
                            messages=messages,
                            max_tokens=_S4_CORRECTION_MAX_TOKENS,
                        )
                    except Exception as corr_exc:
                        logger.warning(
                            f"Correction LLM call failed for task {task_num} iter {correction_iter}: {corr_exc}"
                        )
                        is_unc = (
                            getattr(corr_exc, "is_uncertain", False)
                            or "read timed out" in str(corr_exc).lower()
                            or "write timed out" in str(corr_exc).lower()
                            or "uncertain" in str(corr_exc).lower()
                        )
                        gw_meta = dict(getattr(corr_exc, "gateway_metadata", None) or {})
                        gw_meta["error"] = str(corr_exc)
                        await record_call_callback(
                            model=getattr(resolved_llm, "_model", "grok-beta"),
                            input_tokens=None,
                            output_tokens=None,
                            stage=f"s4_correction_iter_{correction_iter}",
                            measurement_status="timeout_uncertain" if is_unc else "failed_http",
                            gateway_metadata=gw_meta,
                        )
                        raise

                    c_in = correction_completion.usage.prompt_tokens if correction_completion.usage else None
                    c_out = correction_completion.usage.completion_tokens if correction_completion.usage else None
                    c_tot = correction_completion.usage.total_tokens if correction_completion.usage else None

                    if c_in is None:
                        has_unavailable_usage = True

                    await record_call_callback(
                        model=correction_completion.model,
                        input_tokens=c_in,
                        output_tokens=c_out,
                        total_tokens=c_tot,
                        stage=f"s4_correction_iter_{correction_iter}",
                        gateway_request_id=correction_completion.request_id,
                        gateway_metadata=correction_completion.gateway_metadata,
                        measurement_status="measured" if c_in is not None else "unavailable",
                    )

                    current_summary = correction_completion.content or current_summary

                    # C. Validar si el código corregido es nuevo
                    new_code = _extract_code_from_response(correction_completion.content)
                    if not new_code or (last_code_executed and new_code.strip() == last_code_executed.strip()):
                        logger.info(
                            f"Task {task_num} iter {correction_iter} produced identical/empty code. Halting correction."
                        )
                        sandbox_result["identical_code_detected"] = True
                        break

                    last_code_executed = new_code

                    # D. Re-ejecutar en Judge0 con el código corregido
                    try:
                        sandbox_res = await _execute_sandbox_code(resolved_sandbox, new_code)
                        status_str = str(getattr(sandbox_res, "status", "accepted")).lower()
                        stdout = getattr(sandbox_res, "stdout", "") or ""
                        stderr = getattr(sandbox_res, "stderr", "") or getattr(sandbox_res, "compile_output", "") or ""
                        exit_code = getattr(sandbox_res, "exit_code", None)

                        sandbox_result = {
                            "status": status_str,
                            "stdout": stdout[:500],
                            "stderr": stderr[:500],
                            "exit_code": exit_code,
                            "correction_iterations": correction_iter,
                        }

                        if status_str in ("accepted", "success"):
                            logger.info(f"Task {task_num} corrected and accepted on iteration {correction_iter}.")
                            break
                    except Exception as s_exc:  # noqa: BLE001
                        logger.info(f"Sandbox re-run failed on iter {correction_iter} for task {task_num}: {s_exc}")
                        sandbox_result = {
                            "status": "infra_error",
                            "error": str(s_exc),
                            "correction_iterations": correction_iter,
                        }
                        break

        is_execution_successful = True
        if is_executable_task:
            sb_st = str(sandbox_result.get("status", "")).lower() if isinstance(sandbox_result, dict) else ""
            is_execution_successful = sb_st in ("accepted", "success")

        return {
            "validation_passed": is_execution_successful,
            "summary": current_summary,
            "metrics": {
                "seniority": seniority,
                "category": category,
            },
            "sandbox_result": sandbox_result,
            "has_unavailable_usage": has_unavailable_usage,
        }

    return real_executor
