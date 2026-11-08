"""Generador determinista de catálogo de tareas técnicas sintéticas para S4."""

from __future__ import annotations

import hashlib
import json
import random
from typing import Any

from src.s4.enums import S4TaskType

# Plantillas base de escenarios técnicos
_CATEGORIES: list[dict[str, Any]] = [
    {
        "category": "algorithmic_complexity",
        "task_type": S4TaskType.GENERAL_TECHNICAL,
        "title": "Optimización de algoritmo O(N^2) a O(N)",
        "prompt_template": (
            "Analiza el siguiente código con complejidad cuadrática para encontrar duplicados "
            "en una lista de transacciones. Propón una solución en O(N) tiempo y O(N) espacio auxiliar."
        ),
        "code_snippet": "def find_duplicates(items):\n    dups = []\n    for i in range(len(items)):\n        for j in range(i+1, len(items)):\n            if items[i] == items[j] and items[i] not in dups:\n                dups.append(items[i])\n    return dups",
        "expected_topics": ["hash set", "dict", "O(N)", "linear time"],
    },
    {
        "category": "concurrency_race",
        "task_type": S4TaskType.GENERAL_TECHNICAL,
        "title": "Diagnóstico y corrección de race condition en saldo bancario",
        "prompt_template": (
            "Identifica la condición de carrera en este fragmento asíncrono que realiza transferencias. "
            "Implementa el bloqueo adecuado (Mutex / Lock / FOR UPDATE)."
        ),
        "code_snippet": "async def transfer(account_from, account_to, amount):\n    bal = await db.get_balance(account_from)\n    if bal >= amount:\n        await db.set_balance(account_from, bal - amount)\n        await db.set_balance(account_to, await db.get_balance(account_to) + amount)",
        "expected_topics": ["atomic", "lock", "for update", "transaction", "race condition"],
    },
    {
        "category": "security_sanitization",
        "task_type": S4TaskType.GENERAL_TECHNICAL,
        "title": "Mitigación de inyección SQL y fuga de credenciales",
        "prompt_template": (
            "Audita el siguiente endpoint vulnerable a SQL injection y fuga de token JWT en cabeceras. "
            "Refactoriza usando sentencias preparadas y redacta secretos."
        ),
        "code_snippet": "def query_user(user_id, token):\n    logger.info(f'Token: {token}')\n    return db.execute(f'SELECT * FROM users WHERE id = {user_id}')",
        "expected_topics": ["parameterized query", "prepared statement", "sanitization", "masking"],
    },
    {
        "category": "system_design_caching",
        "task_type": S4TaskType.GENERAL_TECHNICAL,
        "title": "Estrategia de caché Cache-Aside vs Write-Through",
        "prompt_template": (
            "Diseña la estrategia de invalidación de caché para un catálogo de productos con alta lectura (95/5). "
            "Justifica Cache-Aside con TTL o Write-Through y define la política de degradación ante caída de Redis."
        ),
        "code_snippet": "# Read heavy system with 10k RPS\n# Redis cluster + PostgreSQL replica",
        "expected_topics": ["cache-aside", "ttl", "stale", "fallback", "circuit breaker"],
    },
    {
        "category": "error_log_diagnosis",
        "task_type": S4TaskType.GENERAL_TECHNICAL,
        "title": "Análisis de stack trace y memory leak",
        "prompt_template": (
            "Dado el siguiente log de Uvicorn/FastAPI con error MemoryError y conexión agotada en pool: "
            "determina la causa raíz y medidas correctivas."
        ),
        "code_snippet": "ERROR: [pool.py:312] Timeout waiting for connection (pool size 10, max overflow 5)\nWARNING: Process memory reached 1.8GB / 2.0GB limit",
        "expected_topics": ["pool exhaustion", "connection leak", "generator", "context manager"],
    },
]

_SENIORITIES = ["junior", "mid", "senior", "lead"]


class S4TaskCatalogGenerator:
    """Generador pseudoaleatorio determinista y reproducible con semilla fija."""

    def __init__(self, seed: int = 42) -> None:
        self.seed = seed
        self._rng = random.Random(seed)

    def generate_task_definition(self, task_number: int) -> dict[str, Any]:
        """Genera una definición reproducible para una tarea específica basada en su número y la semilla."""
        # Derivamos una semilla determinista por número de tarea
        task_hash = hashlib.sha256(f"{self.seed}:{task_number}".encode()).hexdigest()
        task_rng = random.Random(int(task_hash[:16], 16))

        template = task_rng.choice(_CATEGORIES)
        seniority = task_rng.choice(_SENIORITIES)
        scenario_id = f"s4_task_{self.seed}_{task_number:05d}"

        # Parámetros técnicos variables según semilla y número
        items_count = task_rng.randint(50, 5000)
        timeout_ms = task_rng.choice([1000, 2000, 5000])

        task_type_val = getattr(template["task_type"], "value", str(template["task_type"]))

        return {
            "task_number": task_number,
            "scenario_id": scenario_id,
            "task_type": task_type_val,
            "category": template["category"],
            "title": f"[{seniority.upper()}] {template['title']} #{task_number}",
            "seniority": seniority,
            "prompt": template["prompt_template"],
            "code_snippet": template["code_snippet"],
            "parameters": {
                "items_count": items_count,
                "timeout_ms": timeout_ms,
                "seniority": seniority,
                "difficulty_weight": round(task_rng.uniform(1.0, 3.0), 2),
            },
            "acceptance_criteria": {
                "required_keywords": template["expected_topics"][:2],
                "min_response_length": 60,
                "must_contain_verdict": True,
            },
        }

    def generate_catalog(self, count: int = 1000) -> list[dict[str, Any]]:
        """Genera el catálogo completo de N tareas deterministas."""
        return [self.generate_task_definition(i) for i in range(1, count + 1)]

    @classmethod
    def validate_task_result(
        cls,
        task_def: dict[str, Any],
        result: dict[str, Any] | str,
    ) -> tuple[bool, str]:
        """Valida deterministamente el resultado contra los criterios técnicos y estructurales de aceptación."""
        if not result:
            return False, "Empty or missing result"

        if isinstance(result, str):
            try:
                parsed = json.loads(result)
            except (json.JSONDecodeError, TypeError, ValueError):
                parsed = {"summary": result}
        else:
            parsed = result

        summary = parsed.get("summary", "")
        if not isinstance(summary, str) or len(summary.strip()) < 10:
            return False, "Result summary is missing or too short (< 10 chars)"

        criteria = task_def.get("acceptance_criteria", {})
        category = task_def.get("category", "").lower()
        min_len = criteria.get("min_response_length", 20)
        summary_clean = summary.strip()

        if len(summary_clean) < min_len:
            return False, f"Result summary length ({len(summary_clean)}) below minimum ({min_len})"

        words = summary_clean.split()
        if len(words) < 8:
            return False, f"Result lacks sufficient technical explanation depth ({len(words)} words, min 8 required)"

        summary_lower = summary_clean.lower()

        # 1. Validación técnica de ejecución en Judge0 para tareas con código ejecutable
        code_snippet = task_def.get("code_snippet", "")
        task_requires_execution = bool(code_snippet and ("def " in code_snippet or "async def" in code_snippet))
        sandbox_res = parsed.get("sandbox_result")

        if task_requires_execution:
            if not isinstance(sandbox_res, dict):
                return False, "Executable task requires technical sandbox verification, but sandbox_result is missing"

            sb_status = str(sandbox_res.get("status", "")).lower()

            if sb_status in ("accepted", "success"):
                pass  # Verificación técnica superada en sandbox
            elif sb_status in (
                "compile_error",
                "runtime_error",
                "wrong_answer",
                "time_limit_exceeded",
                "memory_limit_exceeded",
            ):
                err_detail = (
                    sandbox_res.get("error")
                    or sandbox_res.get("stderr")
                    or sandbox_res.get("compile_output")
                    or sb_status
                )
                return False, f"Executable task failed candidate code verification with status '{sb_status}': {err_detail[:120]}"
            elif sb_status in ("infra_error", "timeout", "sandbox_timeout", "http_error", "connection_error"):
                err_detail = sandbox_res.get("error") or "Judge0 sandbox service unavailable or infrastructure timeout"
                return False, f"Executable task failed due to sandbox infrastructure failure: {err_detail[:120]}"
            elif sb_status == "not_applicable":
                return False, "Executable task cannot bypass sandbox verification with status 'not_applicable'"
            else:
                return False, f"Executable task failed with unrecognized or non-passing sandbox status '{sb_status}'"
        else:
            # Tarea no ejecutable (diseño de arquitectura, logs, caching)
            if isinstance(sandbox_res, dict):
                sb_status = str(sandbox_res.get("status", "")).lower()
                sb_reason = str(sandbox_res.get("reason", "")).lower()
                if sb_status == "not_applicable":
                    if sb_reason != "non_executable_task":
                        return False, f"Non-executable task returned invalid reason for not_applicable: '{sb_reason}'"
                elif sb_status not in ("accepted", "success"):
                    return False, f"Non-executable task returned unexpected failing sandbox status '{sb_status}'"

        # 2. Validación de palabras clave de dominio técnico
        req_kw = criteria.get("required_keywords", [])
        if req_kw:
            matched_kw = [kw for kw in req_kw if kw.lower() in summary_lower]
            if not matched_kw:
                return False, f"Result missing required domain keywords: {req_kw}"

        # 3. Rechazo de respuestas evasivas o que declaran no poder resolver
        evasive_phrases = [
            "no solution found",
            "no he podido resolver",
            "as an ai",
            "como modelo de lenguaje",
            "unverified response",
            "insufficient information to solve",
            "cannot provide a solution",
        ]
        if any(phrase in summary_lower for phrase in evasive_phrases):
            return False, "Result contains evasive or unverified boilerplate phrasing"

        # 4. Coherencia técnica: análisis de complejidad si la categoría o enunciado lo exige
        prompt_text = task_def.get("prompt", "").lower()
        if "complejidad" in prompt_text or "o(" in prompt_text or category == "algorithmic_complexity":
            complexity_markers = ["o(", "complejidad", "complexity", "tiempo", "espacio", "cuadrática", "linear", "lineal"]
            if not any(marker in summary_lower for marker in complexity_markers):
                return False, "Result lacks required computational complexity analysis (time/space bounds)"

        # 5. Detección de keyword stuffing superficial (repetición artificial sin prosa coherente)
        unique_words = {w.lower() for w in words}
        if len(unique_words) < 8 or (len(unique_words) / len(words) < 0.25 and len(words) > 30):
            return False, "Result rejected due to repetitive or superficial keyword stuffing without analytical substance"

        # 6. Marcador de veredicto técnico afirmativo
        if criteria.get("must_contain_verdict"):
            verdict_markers = ["optimal", "verified", "passed", "resuelto", "solución", "solution", "complexity", "mitigado", "corregido"]
            if not any(marker in summary_lower for marker in verdict_markers):
                return False, "Result lacks definitive technical verdict or resolution markers"

        return True, "All acceptance criteria verified successfully"
