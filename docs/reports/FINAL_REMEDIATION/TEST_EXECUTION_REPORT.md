# Reporte de Ejecución de Pruebas y Calidad (Sección 10.8)

**Fecha de Ejecución:** `2026-11-04`  
**Rama:** `develop`  
**Modo de Ejecución:** Secuencial (un único proceso por batería para evitar colisiones sobre la base PostgreSQL de pruebas `evaluador_test`)  

---

## 1. Resumen Ejecutivo de Baterías Ejecutadas

| Categoría | Comando / Suite | Resultado | Tiempo | Estado |
|-----------|-----------------|-----------|--------|--------|
| **Backend — Seguridad Multi-Tenant (H-02) y Cola Asíncrona** | `pytest tests/test_privacy.py tests/test_evaluation.py tests/test_reports.py tests/test_trajectory.py tests/test_auth.py tests/test_organizations.py tests/test_invitations.py tests/test_async_evaluation_queue.py -q` | **`111 passed`** | `24.92s` | **`PASS`** |
| **Backend — Agente S2, LLM, Ejecución H-01, Sandbox, WebSocket y Calibración S3** | `pytest tests/test_llm.py tests/test_agent.py tests/test_execution.py tests/test_sandbox.py tests/test_websocket.py tests/test_calibration.py -q` | **`117 passed`** | `22.02s` | **`PASS`** |
| **Total Pruebas Backend (`pytest`)** | **14 suites críticas de seguridad, agente, sandbox, WS y calibración** | **`228 passed, 0 failed`** | `46.94s` | **`PASS`** |
| **Linter Backend (`ruff`)** | `python3 -m ruff check` sobre archivos tocados y `evals/calibrate.py` | **`All checks passed!`** (`0 errors`) | `0.8s` | **`PASS`** |
| **Typecheck Backend (`mypy`)** | `python3 -m mypy` sobre módulos modificados y routers H-02 | **`Success: no issues found`** (`0 errors`) | `2.1s` | **`PASS`** |
| **Migraciones (`alembic`)** | `python3 -m alembic heads` | **`s3_add_llm_usage_records (head)`** (única cabeza) | `0.6s` | **`PASS`** |
| **Typecheck Frontend (`tsc`)** | `npx tsc --noEmit` (`apps/web`) | **`0 errors`** | `2.1s` | **`PASS`** |
| **Pruebas Unitarias Frontend (`node --test`)** | `npm test` (`apps/web`) | **`20 passed, 0 failed`** | `1.18s` | **`PASS`** |
| **Smoke Test Real S1 contra Grok (`grok-4.6`)** | `python3 -m src.scripts.smoke_s1_grok` | **`PASS` (`3/3` turnos, memoria contextual verificada)** | `149.8s` | **`PASS`** |
| **10 Ejecuciones Reales S2 con Function Calling contra Grok** | `python3 -m src.scripts.run_s2_10_executions` | **`PASS` (`10/10` escenarios: 6 normales, 3 fallos, 1 input inválido)** | `246.4s` | **`PASS`** |
| **Benchmark Real S3 ($N = 32$ Casos) en Vivo contra Grok** | `python3 evals/calibrate.py --transcripts-dir evals/s3_benchmark --live-llm` | **`32/32` casos evaluados en vivo (`0%` model_error, `12/12` en rango en casos no sintéticos)** | `562.0s` | **`PASS`** |

---

## 2. Detalle de Nuevas Pruebas Añadidas

### 2.1. `apps/api/tests/test_llm.py` (Function Calling OpenAI-Compatible)
- `test_complete_sends_tools_and_parses_tool_calls`: Verifica que `OpenAICompatibleClient.complete()` serializa `tools`, `tool_choice="auto"`, mensajes `assistant` con `tool_calls` y mensajes `role="tool"` con `tool_call_id`, y parsea `ToolCall` desde la respuesta HTTP.
- `test_complete_invalid_tool_calls_raises_invalid_response`: Verifica que un payload malformado en `tool_calls` (sin `id` o sin `function.name`) lanza `LLMInvalidResponseError`.

### 2.2. `apps/api/tests/test_agent.py` (Runtime y Bucle de Herramientas S2)
- `test_agent_executes_tool_calls_and_synthesizes_final_response`: Verifica que `InterviewAgent` invoca herramientas cuando el LLM devuelve `tool_calls`, inyecta el resultado como `role="tool"` y sintetiza la respuesta final.
- `test_tool_runtime_rejects_unknown_tool_invalid_json_and_context_override`: Verifica bloqueo de herramientas inexistentes (`UNKNOWN_TOOL`), JSON inválido (`INVALID_JSON_ARGUMENTS`), intento de sobrescribir `organization_id` (`CONTEXT_SECURITY_VIOLATION`) y violación de esquema Pydantic (`INVALID_TOOL_ARGUMENTS`).
- `test_tool_runtime_prevents_duplicate_calls_and_retries_transient_errors`: Verifica reintento acotado ante `TimeoutError` transitorio (`retries == 1`) y bloqueo de llamadas idénticas repetidas en el mismo turno (`DUPLICATE_TOOL_CALL`).

### 2.3. `apps/api/tests/test_execution.py` y `apps/api/tests/test_websocket.py` (H-01)
- `test_h01_sandbox_unavailable_returns_unavailable_contract`: Verifica que `CodeExecutionService.execute_code()` devuelve `status="unavailable"`, `stdout=None`, `tests_passed=None` y valida contra `ServerCodeExecutionResultMessage`.
- `test_h01_sandbox_exception_during_run_returns_unavailable`: Verifica degradación limpia si `SandboxUnavailableError` ocurre durante `runner.run()`.
- `test_h01_compile_output_included_in_stderr_on_error`: Verifica preservación de `compile_output` en `stderr`.
- `test_h01_code_execution_unavailable_over_websocket_does_not_crash`: Verifica de punta a punta sobre WebSocket (`/ws/interview/{id}`) que `run_code` con sandbox no disponible devuelve `code_execution_result` con `status="unavailable"` sin cerrar ni romper la sesión.

### 2.4. `apps/api/tests/test_calibration.py` (S3 Benchmark de 32 Casos)
- `test_s3_benchmark_32_cases_schema_and_metrics`: Verifica que `evals/s3_benchmark/` contiene 32 casos con procedencia explícita (`20 synthetic`, `10 public_reference_solution`, `2 real_anonymized`), panel humano doble ciego (`evaluator_1`, `evaluator_2`, `consensus`), matriz de confusión $3 \times 3$, concordancia por dimensión y concordancia inter-humana.
