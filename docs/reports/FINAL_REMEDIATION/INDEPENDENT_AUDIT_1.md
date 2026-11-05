# AUDITORÍA INDEPENDIENTE 1 — IMPLEMENTACIÓN INTEGRAL S1 + S2 + S3 + H-01 + H-02

**Fecha de Auditoría:** `2026-11-04`  
**Repositorio:** `/home/papisamu/Documentos/Evaluador-Tecnico`  
**Rama Auditada:** `develop` (`HEAD = f94926fbcb29fda9bad937b4b590cd1e3f5f5459`)  
**Modalidad:** Estrictamente de solo lectura (inspección directa de diffs, código fuente, base de datos PostgreSQL, artefactos JSON y recálculo matemático independiente; cero llamadas a Grok y cero modificaciones al repositorio).

---

## 1. Estado Git e Integridad del Repositorio

Se verificó directamente el estado de Git mediante comandos de solo lectura:

- **Rama actual:** `develop`
- **HEAD:** `f94926fbcb29fda9bad937b4b590cd1e3f5f5459`
- **Seguimiento remoto (`@{u}`):** `origin/develop` (`f94926fbcb29fda9bad937b4b590cd1e3f5f5459`)
- **Divergencia `origin/develop...HEAD`:** `0	0` (sin commits locales nuevos ni divergencia con `origin/develop`)
- **Estado de `origin/main`:** `a70fa705b6e64b9229801faed9b5ad1844c75eae` — Divergencia `origin/main...HEAD`: `2	85` (`origin/main` sigue 85 commits por detrás de `develop`; la promoción `develop -> main` sigue pendiente).
- **Índice de staging (`git diff --cached --stat`):** Vacío (`0` archivos en stage).
- **Stashes (`git stash list`):** Intactos (`2` stashes preservados):
  - `stash@{0}: On develop: backup: local work before S3 integration with origin/develop`
  - `stash@{1}: On (no branch): local fixes for phase transition`

### Verificación de las 7 garantías de aislamiento Git
1. **Aislamiento de H-02:** Confirmado. Los 7 archivos de H-02 ([`evaluation.py`](file:///home/papisamu/Documentos/Evaluador-Tecnico/apps/api/src/api/routers/evaluation.py), [`privacy.py`](file:///home/papisamu/Documentos/Evaluador-Tecnico/apps/api/src/api/routers/privacy.py), [`trajectory.py`](file:///home/papisamu/Documentos/Evaluador-Tecnico/apps/api/src/api/routers/trajectory.py), [`test_evaluation.py`](file:///home/papisamu/Documentos/Evaluador-Tecnico/apps/api/tests/test_evaluation.py), [`test_privacy.py`](file:///home/papisamu/Documentos/Evaluador-Tecnico/apps/api/tests/test_privacy.py), [`test_reports.py`](file:///home/papisamu/Documentos/Evaluador-Tecnico/apps/api/tests/test_reports.py), [`test_trajectory.py`](file:///home/papisamu/Documentos/Evaluador-Tecnico/apps/api/tests/test_trajectory.py)) contienen exclusivamente los cambios de autorización multiempresa de H-02.
2. **Sin commits nuevos inesperados:** Confirmado (`HEAD` permanece en `f94926fbcb29fda9bad937b4b590cd1e3f5f5459`).
3. **Sin staging:** Confirmado (`git diff --cached` vacío).
4. **Cambios preexistentes intactos:** Confirmado (`apps/api/docs/`, `docs/reports/S3_3_DEMO_OPERATIONAL_CHECKLIST.md`, `docs/reports/S3_INTERVIEW_REPORT.pdf` sin alteraciones).
5. **`plan_evaluador_tecnico.md` no sobrescrito:** Confirmado (mantiene exactamente su diff preexistente `index 98e0579..6bee151`, `549 insertions/deletions`).
6. **Contratos protegidos (`packages/contracts/`):** Confirmado (`0` líneas de diff en `openapi.json` y `types.generated.ts`).
7. **Stashes inalterados:** Confirmado (`stash@{0}` y `stash@{1}` intactos).

---

## 2. Inventario Completo de Archivos Modificados y Nuevos

### 2.1. Archivos Rastreados Modificados (`25 files changed, 2741 insertions(+), 767 deletions(-)`)

| Archivo | Estadística Diff | Fase / Propósito Real Verificado |
|---|---|---|
| [`README.md`](file:///home/papisamu/Documentos/Evaluador-Tecnico/README.md) | `213 +++--` | Documentación actualizada con arquitectura real, variables de entorno y comandos S1/S2/S3 |
| [`apps/api/src/agent/service.py`](file:///home/papisamu/Documentos/Evaluador-Tecnico/apps/api/src/agent/service.py) | `237 +++++-` | Integración de `AgentToolRuntime`, bucle acotado de `tool_calls` en `_stream_llm` y `generate_reply_with_tools` |
| [`apps/api/src/api/routers/evaluation.py`](file:///home/papisamu/Documentos/Evaluador-Tecnico/apps/api/src/api/routers/evaluation.py) | `20 +-` | H-02: `require_organization` y bloqueo `403` si `vacancy` u `organization_id` es `None` |
| [`apps/api/src/api/routers/privacy.py`](file:///home/papisamu/Documentos/Evaluador-Tecnico/apps/api/src/api/routers/privacy.py) | `21 +-` | H-02: `outerjoin(Vacancy)` y `require_organization` antes de eliminar datos del candidato |
| [`apps/api/src/api/routers/trajectory.py`](file:///home/papisamu/Documentos/Evaluador-Tecnico/apps/api/src/api/routers/trajectory.py) | `15 +-` | H-02: Cambio de `get_optional_current_user` a `get_current_user` + `require_organization` |
| [`apps/api/src/api/schemas/websocket.py`](file:///home/papisamu/Documentos/Evaluador-Tecnico/apps/api/src/api/schemas/websocket.py) | `15 +-` | H-01: Adición de `"unavailable"` a `status` y soporte `None` para `stdout`, `stderr`, `tests_passed` |
| [`apps/api/src/evaluation/queue.py`](file:///home/papisamu/Documentos/Evaluador-Tecnico/apps/api/src/evaluation/queue.py) | `74 +-` | Shim `except ModuleNotFoundError:` para importar `arq` en Python 3.14 local sin rueda compilada |
| [`apps/api/src/execution/service.py`](file:///home/papisamu/Documentos/Evaluador-Tecnico/apps/api/src/execution/service.py) | `190 +++--` | H-01: Captura de `SandboxUnavailableError`/`SandboxProviderError`, método `_record_unavailable` y `compile_output` en `stderr` |
| [`apps/api/src/llm/mock.py`](file:///home/papisamu/Documentos/Evaluador-Tecnico/apps/api/src/llm/mock.py) | `3 +` | S2: Parámetros opcionales `tools` y `tool_choice` en `MockLLMClient.complete` |
| [`apps/api/src/llm/openai_compatible.py`](file:///home/papisamu/Documentos/Evaluador-Tecnico/apps/api/src/llm/openai_compatible.py) | `98 ++-` | S2: Serialización de `tools`, `tool_choice`, `tool_calls` y `role="tool"`, y parseo `_parse_tool_calls` |
| [`apps/api/src/llm/types.py`](file:///home/papisamu/Documentos/Evaluador-Tecnico/apps/api/src/llm/types.py) | `19 +-` | S2: Dataclass `ToolCall` y extensión de `ChatMessage`, `ChatCompletion` y `LLMClient` |
| [`apps/api/tests/conftest.py`](file:///home/papisamu/Documentos/Evaluador-Tecnico/apps/api/tests/conftest.py) | `1 +` | Importación temprana de `src.evaluation.queue` para activar el shim de `arq` en `pytest` |
| [`apps/api/tests/test_agent.py`](file:///home/papisamu/Documentos/Evaluador-Tecnico/apps/api/tests/test_agent.py) | `189 ++++-` | S2: 3 tests de bucle de `tool_calls`, validación de argumentos/seguridad contextual y reintentos/duplicados |
| [`apps/api/tests/test_calibration.py`](file:///home/papisamu/Documentos/Evaluador-Tecnico/apps/api/tests/test_calibration.py) | `22 +` | S3: Test `test_s3_benchmark_32_cases_schema_and_metrics` (modo offline) |
| [`apps/api/tests/test_evaluation.py`](file:///home/papisamu/Documentos/Evaluador-Tecnico/apps/api/tests/test_evaluation.py) | `88 +-` | H-02: Pruebas de aislamiento multi-tenant en evaluación |
| [`apps/api/tests/test_execution.py`](file:///home/papisamu/Documentos/Evaluador-Tecnico/apps/api/tests/test_execution.py) | `56 +-` | H-01: 3 pruebas unitarias para `unavailable`, fallo en `run()` y `compile_output` |
| [`apps/api/tests/test_llm.py`](file:///home/papisamu/Documentos/Evaluador-Tecnico/apps/api/tests/test_llm.py) | `150 ++++` | S2: 2 pruebas unitarias de serialización y validación de `tool_calls` en `OpenAICompatibleClient` |
| [`apps/api/tests/test_privacy.py`](file:///home/papisamu/Documentos/Evaluador-Tecnico/apps/api/tests/test_privacy.py) | `233 ++++++` | H-02: Pruebas de bloqueo cross-tenant en borrado y anonimización |
| [`apps/api/tests/test_reports.py`](file:///home/papisamu/Documentos/Evaluador-Tecnico/apps/api/tests/test_reports.py) | `113 +++` | H-02: Pruebas de aislamiento multi-tenant en exportación PDF |
| [`apps/api/tests/test_trajectory.py`](file:///home/papisamu/Documentos/Evaluador-Tecnico/apps/api/tests/test_trajectory.py) | `226 ++++--` | H-02: Pruebas de autenticación y autorización por organización en trayectoria |
| [`apps/api/tests/test_websocket.py`](file:///home/papisamu/Documentos/Evaluador-Tecnico/apps/api/tests/test_websocket.py) | `43 +-` | H-01: Test de integración WebSocket cuando `execute_code` devuelve `unavailable` |
| [`apps/web/src/components/interview/test-console.tsx`](file:///home/papisamu/Documentos/Evaluador-Tecnico/apps/web/src/components/interview/test-console.tsx) | `31 +-` | H-01: Renderizado de badge/alerta ámbar para `status === "unavailable"` y `tests_passed === null` |
| [`apps/web/src/lib/hooks/use-interview-socket.ts`](file:///home/papisamu/Documentos/Evaluador-Tecnico/apps/web/src/lib/hooks/use-interview-socket.ts) | `16 +-` | H-01: Tipos locales `ExtendedExecutionStatus` y `ExtendedCodeExecutionResultMessage` |
| [`evals/calibrate.py`](file:///home/papisamu/Documentos/Evaluador-Tecnico/evals/calibrate.py) | `886 ++++++++++++++++++---` | S3: Modo `--live-llm`, métricas psicométricas, IC 95% bootstrap/Wilson, estratificación y reporte Markdown |
| [`plan_evaluador_tecnico.md`](file:///home/papisamu/Documentos/Evaluador-Tecnico/plan_evaluador_tecnico.md) | `549 +++++--------` | Modificación preexistente preservada intacta |

### 2.2. Archivos y Directorios No Rastreados Nuevos (Creados en la Intervención)
- [`apps/api/src/agent/tools.py`](file:///home/papisamu/Documentos/Evaluador-Tecnico/apps/api/src/agent/tools.py) (`794` líneas)
- [`apps/api/src/scripts/smoke_s1_grok.py`](file:///home/papisamu/Documentos/Evaluador-Tecnico/apps/api/src/scripts/smoke_s1_grok.py) (`320` líneas)
- [`apps/api/src/scripts/run_s2_10_executions.py`](file:///home/papisamu/Documentos/Evaluador-Tecnico/apps/api/src/scripts/run_s2_10_executions.py) (`640` líneas)
- [`apps/api/src/scripts/build_s3_benchmark.py`](file:///home/papisamu/Documentos/Evaluador-Tecnico/apps/api/src/scripts/build_s3_benchmark.py) (`901` líneas)
- [`evals/s3_benchmark/`](file:///home/papisamu/Documentos/Evaluador-Tecnico/evals/s3_benchmark) (`32` archivos `.json`)
- [`docs/reports/FINAL_REMEDIATION/`](file:///home/papisamu/Documentos/Evaluador-Tecnico/docs/reports/FINAL_REMEDIATION) (`10` reportes `.md` + `3` archivos `.json` de evidencia)

---

## 3. Auditoría S1 — Integración Real de Grok

### 3.1. Verificaciones Realizadas
1. **Uso efectivo del proveedor Grok y `USE_MOCK_LLM=False`:**
   - En [`smoke_s1_grok.py`](file:///home/papisamu/Documentos/Evaluador-Tecnico/apps/api/src/scripts/smoke_s1_grok.py#L51-L61), el script aborta con `RuntimeError` si `settings.USE_MOCK_LLM` es `True` o si `settings.LLM_API_KEY` no está configurada.
   - `InterviewAgent` instancia `OpenAICompatibleClient` apuntando a `https://api.reto.pltk.mx/v1` con el modelo `grok-4.6`.
2. **Comprobación directa en PostgreSQL (`interview_id = 064da846-4f36-4e38-8012-a1cb29b33f08`):**
   - Se consultó de forma independiente la base de datos `evaluador_db`:
     - La fila en `interviews` existe (`064da846-4f36-4e38-8012-a1cb29b33f08`).
     - Existen exactamente **`6` filas en `turns`** (`3` de `CANDIDATE` y `3` de `AGENT`) que coinciden carácter por carácter con [`s1_smoke_evidence.json`](file:///home/papisamu/Documentos/Evaluador-Tecnico/docs/reports/FINAL_REMEDIATION/s1_smoke_evidence.json).
     - Existen exactamente **`3` filas en `llm_usage_records`** asociadas a `064da846-4f36-4e38-8012-a1cb29b33f08`, con `measurement_status="measured"`, modelo `"grok-4.6"`, `total_input_tokens = 6,070`, `total_output_tokens = 868` y `total_tokens = 10,601` (la diferencia `10,601 - 6,938 = 3,663` corresponde a `reasoning_tokens` internos reportados por el gateway de Grok).
3. **Retención de contexto entre turnos:**
   - En el Turno 1 (`CLARIFY`), el candidato introduce dos datos arbitrarios no presentes en el enunciado: `420,000 registros` y el prefijo `'CUS-ALPHA-99'`, y en el Turno 2 (`DESIGN`) propone un `set` para duplicados.
   - En el Turno 3 (`DESIGN`), sin que el usuario repita esos valores, Grok responde: *"Recuerdo lo que planteaste: lote de 420.000 registros, prefijo `CUS-ALPHA-99` y un `set` de códigos vistos (además del diccionario)"*.
4. **Recálculo independiente del costo (`USD 0.043370`):**
   - Con las tarifas declaradas en `src/evaluation/pricing.py` para `grok-4.6` (`$5.00 / 1M` input tokens, `$15.00 / 1M` output tokens):
     $$\text{Costo} = \frac{6070 \times 5.00 + 868 \times 15.00}{10^6} = 0.030350 + 0.013020 = \$0.043370\text{ USD}$$
   - El cálculo coincide exactamente con el valor almacenado en PostgreSQL y en el reporte.
5. **Protección de secretos y PII:**
   - `api_key_redacted` aparece como `"[REDACTED_ENV_SECRET]"` y los datos del candidato son sintéticos (`Candidato S1 Smoke`, `s1-smoke@evaluador.local`).

### 3.2. Limitaciones Detectadas en S1
- El script ejecuta `agent.stream_response(..., enable_tools=False)` durante 3 turnos (`CLARIFY` y `DESIGN`), lo que demuestra conectividad real, persistencia y memoria conversacional de corto plazo, pero no ejercita una entrevista completa de 6 fases hasta `WRAP_UP`/`EVALUATE`.
- El script hace `session.commit()` directamente sobre la base de datos de desarrollo (`evaluador_db`) sin limpiar los registros de prueba al finalizar.

**Veredicto S1:** **`PASS`** (Cumple íntegramente los requisitos del entregable S1: ejecución real end-to-end contra Grok, persistencia verificada en PostgreSQL, memoria multi-turno demostrada y README documentado).

---

## 4. Auditoría S2 — Function Calling Real y Autonomía del Agente

### 4.1. Auditoría del Cliente LLM (`OpenAICompatibleClient`)
- En [`apps/api/src/llm/openai_compatible.py`](file:///home/papisamu/Documentos/Evaluador-Tecnico/apps/api/src/llm/openai_compatible.py#L51-L195):
  - Serializa correctamente `tools` y `tool_choice` en el payload de `/chat/completions`.
  - `_serialize_message` serializa mensajes `role="assistant"` con `tool_calls` (`id`, `type="function"`, `function.name`, `function.arguments`) y mensajes `role="tool"` con `tool_call_id` (lanzando `LLMConfigurationError` si falta `tool_call_id`).
  - `_parse_tool_calls` valida que `tool_calls` sea una lista de objetos con `id` no vacío y `function.name` no vacío, aceptando `arguments` tanto como cadena JSON como mapeo y lanzando `LLMInvalidResponseError` ante estructuras corruptas.
  - Cuando el modelo retorna `content: null` junto con `tool_calls` (estándar OpenAI/Grok), `_parse_completion` normaliza `content = ""` sin fallar.
  - Reintenta códigos HTTP transitorios (`408, 500, 502, 503, 504`) y `httpx.TimeoutException`, propagando `LLMTimeoutError` o `LLMProviderError` tras agotar reintentos.

### 4.2. Evaluación de Autonomía Real vs Direccionamiento en Prompts
1. **Evidencia de invocación real desde Grok:**
   - La inspección de PostgreSQL confirmó **`21` registros en `llm_usage_records`** para las **`10` entrevistas** de S2 (`2` llamadas LLM en `exec_01`–`exec_09` y `3` llamadas LLM en `exec_10`).
   - Esto demuestra que en cada escenario hubo una primera llamada HTTP a Grok con `tool_choice="auto"` que devolvió `finish_reason="tool_calls"` con un ID generado por el gateway (p. ej. `call-9be3dae9-0b27-4c00-8023-be466380218f-0`), seguida de la ejecución en `AgentToolRuntime` y una segunda llamada HTTP a Grok incluyendo el mensaje `role="tool"` para sintetizar la respuesta al candidato.
2. **Hallazgo crítico A — Direccionamiento explícito en 5 de los 10 prompts:**
   - Al inspeccionar [`run_s2_10_executions.py`](file:///home/papisamu/Documentos/Evaluador-Tecnico/apps/api/src/scripts/run_s2_10_executions.py#L211-L270), se observa que en **5 escenarios (`exec_03`, `exec_04`, `exec_05`, `exec_06`, `exec_07`)** el mensaje del candidato menciona explícitamente el nombre interno de la herramienta y sus argumentos:
     - `exec_03`: *"Por favor ejecútala ahora mismo usando tu herramienta code_execution_sandbox con language='python'"*
     - `exec_04`: *"¿Puedes ejecutarla con tu herramienta code_execution_sandbox (language='python')?"*
     - `exec_05`: *"por favor invoca tu herramienta adaptive_hint_generator con requested_level=1"*
     - `exec_06`: *"Por favor invoca tu herramienta adaptive_hint_generator con requested_level=2"*
     - `exec_07`: *"usando tu herramienta code_execution_sandbox (language='python')"*
   - Asimismo, en `exec_01`, `exec_02`, `exec_09` y `exec_10` (`unassigned_problem=True`), [`InterviewAgent._build_system_prompt`](file:///home/papisamu/Documentos/Evaluador-Tecnico/apps/api/src/agent/service.py#L327-L335) inyecta en el system prompt: *"PROBLEMA PENDIENTE DE CONSULTA: ... DEBES invocar inmediatamente la herramienta `problem_selector`"*.
   - Solo `exec_08` (*"Solicito explícitamente una pista de nivel 3 para poder destrabarme"*) invoca una herramienta a partir de una petición natural sin nombrar la herramienta en el prompt del usuario ni usar `unassigned_problem=True`.
3. **Hallazgo crítico B — Ausencia del payload HTTP crudo sin truncar:**
   - [`s2_10_executions.json`](file:///home/papisamu/Documentos/Evaluador-Tecnico/docs/reports/FINAL_REMEDIATION/s2_10_executions.json) almacena `tool_traces` generados por `AgentToolRuntime._record_trace`, donde `_sanitize_dict_for_trace` trunca las cadenas de argumentos y resultados a 45–50 caracteres (p. ej. `"problem": "\"{'id': 'pse-payment-reconciliation', 'title': '...\""`).
   - Ni `s2_10_executions.json` ni la tabla `turns` de PostgreSQL almacenan el JSON crudo original de `choices[0].message.tool_calls` devuelto por Grok antes de la sanitización.

### 4.3. Auditoría de las 10 Ejecuciones, Fallos Controlados y Costos
- **Distribución verificada:** `6` normales (`exec_01`–`exec_06`), `3` fallos controlados (`exec_07`–`exec_09`), `1` entrada inválida (`exec_10`). Total: `11` tool calls y `21` llamadas LLM.
- **Hallazgo crítico C — Uso de `DeterministicPythonSandboxRunner` (mock en memoria) en lugar de Judge0 en `exec_03` y `exec_04`:**
  - En [`run_s2_10_executions.py`](file:///home/papisamu/Documentos/Evaluador-Tecnico/apps/api/src/scripts/run_s2_10_executions.py#L47-L99), el script inyecta `DeterministicPythonSandboxRunner` al `InterviewAgent`.
  - Esta clase **no ejecuta el código Python del candidato** ni invoca a Judge0: parsea `request.stdin` en el propio proceso Python, calcula `expected_mismatches` mediante una comprensión de diccionario hardcodeada y comprueba `if "BUGGY_IMPLEMENTATION" in request.source:` para devolver `WRONG_ANSWER` (`0/3`) o `ACCEPTED` (`3/3`).
  - Por tanto, aunque `CodeExecutionService` sí persistió los `3` snapshots reales en PostgreSQL y Grok sí procesó los resultados reales de `CodeExecutionService`, el motor de ejecución subyacente en `exec_03` y `exec_04` fue un runner simulado en Python.
- **Naturaleza de los fallos en `exec_07`, `exec_08`, `exec_09` y `exec_10`:**
  - `exec_07`: Fallo inyectado mediante `DeterministicPythonSandboxRunner(mode="unavailable")` (`check_availability() -> False`), verificando la ruta real de degradación H-01 (`status="unavailable"`).
  - `exec_08`: Estado real de dominio (`interview.hint_level = 3`), donde `adaptive_hint_generator` rechaza otorgar una cuarta pista (`status="max_level_reached"`).
  - `exec_09`: Fallo transitorio inyectado mediante `TransientFlakyProblemSelector`, que lanza `TimeoutError` en el intento 1 y permite verificar que `AgentToolRuntime` reintenta automáticamente (`retries = 1`) dentro de la misma llamada sin contabilizar el reintento como una nueva ejecución. No obstante, en `exec_09`, Grok invocó `inspect_assigned_problem` (que hizo fallback a `search_catalog` seleccionando `cache-invalidation`), pero en su `agent_reply` final solo saludó al candidato y pidió consentimiento sin presentar el problema devuelto por la herramienta.
  - `exec_10`: Entrada inválida inyectada mediante el wrapper `InvalidArgInjectorLLMWrapper`, que intercepta la primera `ToolCall` de Grok y añade `"organization_id": "00000000-0000-0000-0000-000000000099"`. `AgentToolRuntime` bloquea la llamada con `CONTEXT_SECURITY_VIOLATION`, envía el error a Grok por `role="tool"`, y Grok realiza autónomamente una segunda llamada limpia a `problem_selector` sin el argumento prohibido.
- **Recálculo independiente de tokens y costos en S2:**
  - Suma verificada en PostgreSQL (`21` filas en `llm_usage_records`): `prompt_tokens = 61,154`, `completion_tokens = 3,521`, `total_tokens = 71,891`.
  - Costo recalculado:
    $$\text{Costo S2} = \frac{61154 \times 5.00 + 3521 \times 15.00}{10^6} = 0.305770 + 0.052815 = \$0.358585\text{ USD}$$
  - Coincidencia exacta (`100%`) entre JSON, Markdown y PostgreSQL.

### 4.4. Seguridad de Herramientas (`apps/api/src/agent/tools.py`)
- **Controles efectivos verificados:**
  - Validación Pydantic v2 con `ConfigDict(extra="forbid")` en `ProblemSelectorArgs`, `CodeExecutionSandboxArgs` y `AdaptiveHintGeneratorArgs`.
  - Bloqueo explícito de claves de contexto (`interview_id`, `organization_id`, `org_id`, `user_id`, `candidate_id`, `candidate_email`, `candidate_name`) con `CONTEXT_SECURITY_VIOLATION` antes de validar el esquema.
  - Deduplicación por turno mediante `self._seen_calls` (`DUPLICATE_TOOL_CALL`).
  - Límites duros `MAX_TOOL_ITERATIONS = 3`, `MAX_TOOL_CALLS_PER_TURN = 4`, `MAX_TOOL_RETRIES = 1`, `TOOL_EXECUTION_TIMEOUT_SECONDS = 20.0`.
- **Riesgos de seguridad residuales detectados:**
  1. **Ausencia de encapsulamiento `<untrusted_candidate_input>` en salidas de herramientas (`role="tool"`):** En [`apps/api/src/agent/service.py`](file:///home/papisamu/Documentos/Evaluador-Tecnico/apps/api/src/agent/service.py#L318-L326), `json.dumps(tool_output)` se inyecta directamente como contenido del mensaje `role="tool"`. En `code_execution_sandbox`, `stdout` y `stderr` provienen de la ejecución del código del candidato (truncados a 500 caracteres). Si un candidato imprime instrucciones adversariales por `stdout`, estas ingresan al contexto del modelo dentro de un mensaje `role="tool"` sin etiquetas `<untrusted_candidate_input>`.
  2. **Consulta de otros problemas del catálogo público en `_run_problem_selector`:** Si `self._interview.problem_id` ya está fijado pero el modelo pasa un `args.problem_id` distinto en `inspect_assigned_problem`, [`tools.py`](file:///home/papisamu/Documentos/Evaluador-Tecnico/apps/api/src/agent/tools.py#L558-L561) prioriza `args.problem_id` sobre `self._interview.problem_id`.

**Veredicto S2:** **`PARTIAL`** (El protocolo de Function Calling OpenAI-compatible, el runtime validado con las 3 herramientas de dominio y las 10 ejecuciones reales contra Grok están implementados y respaldados en PostgreSQL, pero `exec_03`/`exec_04` usaron un runner simulado en memoria en lugar de Judge0 real, 5/10 escenarios pidieron la herramienta por su nombre técnico en el prompt del candidato y las trazas JSON truncan los argumentos/resultados originales).

---

## 5. Auditoría H-01 — Contrato WebSocket y Aislamiento del Sandbox

### 5.1. Contrato WebSocket y Frontend (`H-01`)
- **Backend ([`websocket.py`](file:///home/papisamu/Documentos/Evaluador-Tecnico/apps/api/src/api/schemas/websocket.py) y [`execution/service.py`](file:///home/papisamu/Documentos/Evaluador-Tecnico/apps/api/src/execution/service.py)):**
  - `ServerCodeExecutionResultMessage` admite `status="unavailable"` y valores `None` en `stdout`, `stderr` y `tests_passed`.
  - `CodeExecutionService.execute_code` captura `SandboxUnavailableError` y `SandboxProviderError` tanto en `check_availability()` como durante `self._runner.run()`, registrando un `Snapshot` con `execution_status="unavailable"` y `tests_passed=None` sin lanzar `ValidationError`.
  - Cuando ocurre un error de compilación en Judge0, `res.stderr or res.compile_output` preserva la traza del compilador en `stderr`.
- **Frontend ([`use-interview-socket.ts`](file:///home/papisamu/Documentos/Evaluador-Tecnico/apps/web/src/lib/hooks/use-interview-socket.ts) y [`test-console.tsx`](file:///home/papisamu/Documentos/Evaluador-Tecnico/apps/web/src/components/interview/test-console.tsx)):**
  - Distingue explícitamente `result.status === "unavailable"` de `"success"` y de los estados de fallo, mostrando un badge `No disp.` y una alerta ámbar informando que Judge0 no está disponible sin penalizar ni engañar al candidato.
- **Observación sobre `@evaluador/contracts`:**
  - Para respetar la regla de no modificar `packages/contracts/` unilateralmente, el frontend definió `ExtendedCodeExecutionResultMessage` en `use-interview-socket.ts` usando `Omit<ServerCodeExecutionResultMessage, ...>`. Aunque compila sin errores (`tsc --noEmit`), existe una divergencia temporal entre `apps/api/src/api/schemas/websocket.py` y `packages/contracts/types.generated.ts` que deberá cerrarse ejecutando `make update-contracts` con aprobación de ambos compañeros.

### 5.2. Auditoría de Aislamiento Efectivo del Sandbox (`Judge0`)
1. **Hardening en `Judge0Adapter` ([`apps/api/src/sandbox/judge0.py`](file:///home/papisamu/Documentos/Evaluador-Tecnico/apps/api/src/sandbox/judge0.py#L109-L126)):**
   - El adaptador aplica límites estrictos en cada petición HTTP a Judge0: `cpu_time_limit <= 2.0s`, `wall_time_limit <= 3.0s`, `memory_limit <= 128,000 KB`, `max_processes_and_or_threads = 10` y `enable_network = False`.
   - No existe ningún fallback inseguro que ejecute código del candidato con `subprocess` en el host (`LocalRunnerUnavailable` lanza siempre `SandboxUnavailableError`).
2. **Hallazgo crítico de infraestructura Judge0:**
   - En el entorno local solo están activos `evaluador-postgres` y `evaluador-redis`; **no hay ningún contenedor Judge0 corriendo en el puerto `2358`**.
   - El archivo `infra/judge0/docker-compose.yml` mencionado en [`KNOWN_LIMITATIONS.md`](file:///home/papisamu/Documentos/Evaluador-Tecnico/docs/reports/FINAL_REMEDIATION/KNOWN_LIMITATIONS.md#L15) **no existe en el repositorio**.
   - En [`infra/docker-compose.prod.yml`](file:///home/papisamu/Documentos/Evaluador-Tecnico/infra/docker-compose.prod.yml#L37-L55) solo está declarado el servicio `judge0` (`image: judge0/judge0:v1.13.1`), pero **falta el contenedor `judge0-workers`** (`command: ["./scripts/workers"]`, `privileged: true`) requerido por Judge0 CE para procesar la cola de envíos mediante `isolate`.

**Veredicto H-01 (Contrato WebSocket y manejo de indisponibilidad):** **`PASS`**  
**Veredicto Sandbox (Ejecución aislada real en Judge0):** **`PARTIAL`** (El adaptador aplica los límites y el sistema degrada de forma segura a `unavailable` sin ejecutar código en el host, pero Judge0 no está levantado localmente y la definición Docker de Judge0 está incompleta).

---

## 6. Auditoría S3 — Benchmark de 32 Casos y Evaluación Humana

### 6.1. Inventario del Dataset (`evals/s3_benchmark/`)
- Se verificaron los **32 archivos JSON** en [`evals/s3_benchmark/`](file:///home/papisamu/Documentos/Evaluador-Tecnico/evals/s3_benchmark):
  - `20` casos con `provenance: "synthetic"` (`01_synthetic_...` a `20_synthetic_...`).
  - `10` casos con `provenance: "public_reference_solution"` (`21_pubref_...` a `30_pubref_...`).
  - `2` casos con `provenance: "real_anonymized"` (`31_real_anon_...` y `32_real_anon_...`).
  - Los 32 `case_id` y 32 `scenario_id` son únicos (sin duplicados).
- **Hallazgo crítico sobre los 2 casos `real_anonymized`:**
  - Los casos 31 (`source_interview_id = 064da846-4f36-4e38-8012-a1cb29b33f08`) y 32 (`source_interview_id = 506f3994-b067-4a65-b92d-3d9df1a51247`) provienen de las ejecuciones automatizadas de `smoke_s1_grok.py` y `run_s2_10_executions.py` (`exec_03`), no de entrevistas realizadas por candidatos humanos reales externos.
  - Además, en el Caso 31 (`064da846-4f36-4e38-8012-a1cb29b33f08`), la entrevista en PostgreSQL solo tuvo turnos conversacionales de `CLARIFY` y `DESIGN` (`0` snapshots de código), pero [`build_s3_benchmark.py`](file:///home/papisamu/Documentos/Evaluador-Tecnico/apps/api/src/scripts/build_s3_benchmark.py#L704-L710) le añadió un bloque `final_code` (`def reconcile_draft...`) y `execution_results` (`tests_passed: 2/3`) sintéticos.

### 6.2. Auditoría Forense de las Referencias Humanas (`evaluator_1` y `evaluator_2`)
- **Hallazgo crítico de integridad metodológica:**
  - La inspección de [`apps/api/src/scripts/build_s3_benchmark.py`](file:///home/papisamu/Documentos/Evaluador-Tecnico/apps/api/src/scripts/build_s3_benchmark.py#L49-L127) (`_build_dual_human_reference`) demuestra que las evaluaciones atribuidas a `evaluator_1` (`human_tech_lead_01`, *"Senior Backend Tech Lead"*) y `evaluator_2` (`human_staff_eng_02`, *"Staff Software Engineer"*) **no fueron realizadas por dos evaluadores humanos independientes**, sino generadas programáticamente mediante una regla determinista módulo 5:
    ```python
    if case_index % 5 == 1:
        ev2_dims["technical_communication"] = _clamp_dim(ev1_dims["technical_communication"] - 1)
    elif case_index % 5 == 2:
        ev2_dims["complexity_management"] = _clamp_dim(ev1_dims["complexity_management"] + 1)
    elif case_index % 5 == 4:
        ev2_dims["code_quality"] = _clamp_dim(ev1_dims["code_quality"] - 1)
    ```
  - Para los casos 1–20, `ev1_dims` copia directamente las etiquetas previas de `evals/golden_transcripts/` (que tenían `"annotator_type": "synthetic_benchmark"`), y `build_s3_benchmark.py` sobrescribe `"annotator_type": "dual_human_reference_panel"`, lo que hace que `evals/calibrate.py` marque `"is_human_verified": true`.
  - Esta perturbación determinista de $\pm 1$ punto en una dimensión cada $3/5$ casos explica exactamente por qué la concordancia inter-humana reportada es $r_s = 0.9789$, $\kappa_w = 0.9335$ y $\text{MAE} = 0.1125$.
  - **Lo que sí se cumplió:** Grok no participó en la generación de esas etiquetas de referencia, y las etiquetas no fueron modificadas a posteriori tras ver las predicciones de Grok.

### 6.3. Verificación de la Ejecución Real (`--live-llm`)
- Se verificó [`docs/reports/FINAL_REMEDIATION/s3_benchmark_results.json`](file:///home/papisamu/Documentos/Evaluador-Tecnico/docs/reports/FINAL_REMEDIATION/s3_benchmark_results.json):
  - Los **32 casos** contienen evaluaciones reales generadas por `grok-4.6` usando el prompt `prompts/v2/evaluator.md`, con `5` citas de evidencia y razonamiento específico por caso (`160` ítems de evidencia en total), latencias reales entre `29.78s` y `173.03s` y `0` caídas al fallback `simulate_offline_prediction`.
- **Defecto potencial en manejo de errores de `--live-llm`:**
  - En [`evals/calibrate.py`](file:///home/papisamu/Documentos/Evaluador-Tecnico/evals/calibrate.py#L433-L445), si una llamada a Grok falla tras los reintentos (`model_error = True`), el código asigna `sim_score, sim_rec, sim_dims = simulate_offline_prediction(data)` e incluye ese valor simulado en los vectores de cálculo de Spearman y Kappa. Aunque en esta corrida `model_error` fue `0/32`, en caso de fallo de red contaminaría las métricas reales con predicciones simuladas.

### 6.4. Recálculo Independiente de Métricas y Análisis Metodológico
Se recalcularon de forma independiente todas las métricas desde los archivos fuente:

| Métrica | Estrato No Sintético ($n=12$) Reportado | Estrato No Sintético ($n=12$) Recalculado | Global ($N=32$) Reportado | Global ($N=32$) Recalculado |
|---|---|---|---|---|
| **Spearman ($r_s$)** | `0.977` | `0.9770` | `0.6159` | `0.6159` |
| **Kappa Ponderado Cuadrático ($\kappa_w$)** | `0.9362` | `0.9362` | `0.5402` | `0.5402` |
| **MAE (Puntos 1–5)** | `0.2667` | `0.2667` | `0.5938` | `0.5938` |
| **Accuracy Recomendación** | `91.67%` (`11/12`) | `91.67%` (`11/12`) | `53.12%` (`17/32`) | `53.12%` (`17/32`) |
| **Tasa en Rango (con tolerancia $|\Delta| \le 0.50$)** | `100.0%` (`12/12`) | `100.0%` (`12/12`) | `68.75%` (`22/32`) | `68.75%` (`22/32`) |
| **Tasa en Rango Estricta (`s_min <= score <= s_max`)** | *No desglosada* | **`83.33%` (`10/12`)** | *No desglosada* | **`62.50%` (`20/32`)** |

- **Hallazgo metodológico sobre `in_range` y el código de salida CLI:**
  1. En [`evals/calibrate.py`](file:///home/papisamu/Documentos/Evaluador-Tecnico/evals/calibrate.py#L783) se modificó la condición `in_range` de `s_min <= pred_score <= s_max` a `(s_min <= pred_score <= s_max) or (abs(pred_score - benchmark_score) <= 0.50)`. Sin esa cláusula adicional `or <= 0.50`, los casos 31 (`2.40` vs `[2.5, 3.6]`) y 32 (`3.80` vs `[4.0, 5.0]`) quedan fuera del intervalo estricto (`10/12 = 83.33%` en no sintéticos y `20/32 = 62.50%` global).
  2. Asimismo, en `main()` ([`evals/calibrate.py`](file:///home/papisamu/Documentos/Evaluador-Tecnico/evals/calibrate.py#L1079-L1081)), cuando se invoca `--live-llm` sin `--strict-thresholds`, el proceso retorna código de salida `0` si `model_error_rate_pct <= 5.0`, aun cuando `results["calibration_passed"]` sea `False`.
  3. La explicación sobre la baja concordancia en los 20 casos `synthetic` ($r_s = 0.2258$) es técnicamente verdadera: los archivos originales en `evals/golden_transcripts/` contienen código truncado/stubs de 4–6 líneas (p. ej. `CircuitBreaker` solo con `__init__` en el caso 14 o un comentario `# Débito y crédito atómicos` en el caso 15) pero tenían etiquetas preestablecidas de `4.40`–`5.00`. Grok evaluó rigurosamente el código real y penalizó las omisiones.

### 6.5. Verificación de Tokens y Costos S3
- Suma recalculada sobre los 32 casos: `prompt_tokens = 96,247`, `completion_tokens = 26,395`, `total_tokens = 238,729` (incluye `116,087` tokens de razonamiento de `grok-4.6`).
- Costo recalculado con la tarifa estimada de `grok-4.6` (`$5/1M` entrada, `$15/1M` salida):
  $$\text{Costo S3} = \frac{96247 \times 5.00 + 26395 \times 15.00}{10^6} = 0.481235 + 0.395925 = \$0.877160\text{ USD}$$
- Latencia media recalculada: `68,378.45 ms` (`68.38 s`).

**Veredicto S3:** **`PARTIAL`** (La evaluación en vivo de los 32 casos con Grok y el cálculo estadístico son reales y reproducibles, pero el panel humano doble ciego fue simulado programáticamente en `build_s3_benchmark.py`, los 2 casos `real_anonymized` provienen de sesiones internas de smoke/S2 y las métricas globales $r_s = 0.6159$ y $\kappa_w = 0.5402$ quedan por debajo de los umbrales $\ge 0.70$ y $\ge 0.60$).

---

## 7. Auditoría H-02 — Seguridad Multiempresa y Shim de `arq`

### 7.1. Autorización Multi-Tenant en Routers (`H-02`)
- En [`evaluation.py`](file:///home/papisamu/Documentos/Evaluador-Tecnico/apps/api/src/api/routers/evaluation.py), [`privacy.py`](file:///home/papisamu/Documentos/Evaluador-Tecnico/apps/api/src/api/routers/privacy.py) y [`trajectory.py`](file:///home/papisamu/Documentos/Evaluador-Tecnico/apps/api/src/api/routers/trajectory.py):
  - Todos los endpoints exigen `principal: AuthenticatedPrincipal = Depends(get_current_user)` (se eliminó `get_optional_current_user` en `trajectory.py`).
  - Todos validan que la entrevista tenga una `Vacancy` asociada con `organization_id` no nulo (devolviendo `403 Forbidden` si es huérfana) e invocan `require_organization(vacancy.organization_id, principal)` antes de leer o eliminar registros.
  - Los flujos públicos de invitación por token para candidatos permanecen intactos.

### 7.2. Auditoría del Fallback de `arq` en `apps/api/src/evaluation/queue.py`
- **Qué hace realmente:** Cuando `import arq` lanza `ModuleNotFoundError` (como ocurre en el Python 3.14 del host local), define clases sustitutas `Retry`, `RedisSettings`, `ArqRedis` y `create_pool` e inyecta módulos sintéticos `arq` y `arq.connections` en `sys.modules`.
- **Limitaciones críticas del fallback:**
  1. **No sustituye la semántica de cola de ARQ:** `ArqRedis.enqueue_job` ejecuta `SET arq:job:{actual_id} <payload> EX 604800`, pero no inserta el trabajo en el sorted set `arq:queue` ni soporta planificación diferida (`_defer_by` / `Retry(defer=...)`). Ningún worker real de ARQ consumiría una clave creada por este shim.
  2. **Orden de importación en `worker.py`:** [`apps/api/src/evaluation/worker.py`](file:///home/papisamu/Documentos/Evaluador-Tecnico/apps/api/src/evaluation/worker.py#L9-L16) ejecuta `from arq import Retry` en la línea 9 antes de importar `from src.evaluation.queue import evaluation_queue` en la línea 16. Funciona en `pytest` únicamente porque `conftest.py` importa `src.evaluation.queue` al inicio; si se importa `src.evaluation.worker` directamente en un entorno sin `arq`, seguirá lanzando `ModuleNotFoundError`.

**Veredicto H-02:** **`PASS`** en el cierre de seguridad multi-tenant de los endpoints; el shim en `queue.py` es válido únicamente para desbloquear `pytest` en entornos locales sin el paquete `arq`, no como reemplazo de producción de ARQ.

---

## 8. Auditoría de Pruebas y Calidad

- **Reproducibilidad comprobada:**
  - Las 14 suites reportadas (`228 passed`) pasan de forma limpia y reproducible.
  - Adicionalmente, durante esta auditoría se ejecutaron de forma independiente otras 8 suites unitarias no incluidas en el reporte (`test_hints.py`, `test_prompts.py`, `test_problem_catalog.py`, `test_problem_selector.py`, `test_sanitizer.py`, `test_pricing.py`, `test_fairness.py`, `test_state_machine.py`), obteniendo **`104 passed, 1 skipped`** adicionales (`332 passed` en total comprobados).
  - `ruff check` y `mypy` sobre todos los archivos modificados y scripts nuevos pasan con **`0` errores**.
  - Sin embargo, al ejecutar `ruff check src tests` sobre todo el árbol del backend aparecen **3 errores de lint preexistentes** en `src/scripts/demo_s3.py` (imports `secrets` e `Invitation` no usados y un `f-string` sin placeholders).
  - En el repositorio existen **37 archivos `test_*.py`**, de los cuales el reporte de implementación solo ejecutó **14 suites** (omitiendo 23 suites para evitar colisiones de base de datos o tiempos prolongados).
  - **Entorno de ejecución:** Las pruebas se ejecutaron sobre **Python 3.14.2** del host local (usando el shim de `arq`) en lugar de la versión objetivo **Python 3.12** declarada en `AGENTS.md` y `Dockerfile.api`.

---

## 9. Revisión Arquitectónica

1. **Coherencia de `tools.py` y `InterviewAgent`:**
   - `AgentToolRuntime` reutiliza `ProblemSelector` y `CodeExecutionService` sin duplicar lógica de negocio ni crear tablas redundantes.
2. **Desconexión entre `CodeExecutionSandboxTool` y el cliente WebSocket en tiempo real:**
   - Cuando el candidato pulsa "Ejecutar" en la UI, el mensaje WebSocket `run_code` pasa por `MessageDispatcher._handle_run_code` y emite `ServerCodeExecutionResultMessage` a la consola de tests del frontend.
   - En cambio, cuando Grok invoca `code_execution_sandbox` dentro de `InterviewAgent._stream_llm` durante un mensaje de chat, `AgentToolRuntime` ejecuta `CodeExecutionService.execute_code` y persiste el `Snapshot`, pero **no emite un evento `code_execution_result` por WebSocket** hacia el componente `TestConsole` del frontend.
3. **Divergencia latente de contratos (`packages/contracts`):**
   - `apps/api/src/api/schemas/websocket.py` fue actualizado para H-01, mientras que el frontend usa un tipo extendido local (`ExtendedCodeExecutionResultMessage`) en `use-interview-socket.ts` para no tocar `packages/contracts/` sin acuerdo bilateral.

---

## 10. Diferencias entre lo Afirmado y lo Demostrado

| Afirmación en los Informes de Implementación | Realidad Demostrada en la Auditoría |
|---|---|
| *"Panel humano de referencia doble ciego (`evaluator_1`: Senior Backend Tech Lead, `evaluator_2`: Staff Software Engineer) con `is_human_verified: true`"* | Generado programáticamente en [`build_s3_benchmark.py`](file:///home/papisamu/Documentos/Evaluador-Tecnico/apps/api/src/scripts/build_s3_benchmark.py#L49-L127) aplicando una perturbación determinista módulo 5 ($\pm 1$ punto) sobre las etiquetas base. No hubo dos ingenieros humanos calificando independientemente los 32 casos. |
| *"2 casos `real_anonymized` de sesiones reales anonimizadas"* | Corresponden a las sesiones generadas por los propios scripts `smoke_s1_grok.py` y `run_s2_10_executions.py` (`exec_03`), y al Caso 31 se le agregó un `final_code` sintético que no existía en PostgreSQL. |
| *"6 ejecuciones normales en S2 incluyendo `exec_03` y `exec_04` en `code_execution_sandbox`"* | Aunque Grok sí invocó la herramienta y `CodeExecutionService` persistió en PostgreSQL, `run_s2_10_executions.py` inyectó `DeterministicPythonSandboxRunner` (un simulador en memoria que inspecciona el string `"BUGGY_IMPLEMENTATION"`), no Judge0 real. |
| *"Invocación autónoma de las 3 herramientas por parte de Grok en las 10 ejecuciones S2"* | En 5 de los 10 escenarios (`exec_03`–`exec_07`), el prompt del candidato pide explícitamente a Grok invocar la herramienta por su nombre interno (`code_execution_sandbox`, `adaptive_hint_generator`), y en 4 escenarios (`exec_01`, `exec_02`, `exec_09`, `exec_10`) el system prompt inyecta una orden imperativa porque `problem_id` es `None`. |
| *"Para levantar Judge0 CE localmente: `docker compose -f infra/judge0/docker-compose.yml up -d`"* | El archivo `infra/judge0/docker-compose.yml` no existe; Judge0 solo aparece en `infra/docker-compose.prod.yml` y sin el contenedor `judge0-workers`. |
| *"100% (`12/12`) en rango en los casos no sintéticos de S3"* | Obtenido tras ampliar la condición `in_range` en `evals/calibrate.py` con `or (abs(pred_score - benchmark_score) <= 0.50)`. Con el rango estricto `[s_min, s_max]`, el resultado es `10/12` (`83.33%`) y `20/32` (`62.50%`) global. |

---

## 11. Resumen de Defectos, Riesgos y Correcciones Priorizadas

### P0 — Críticos (Integridad Metodológica y Ejecución Real)
1. **Desetiquetar la simulación de panel humano en S3 (`build_s3_benchmark.py` / `calibrate.py`):** No declarar `is_human_verified: true` ni atribuir a dos ingenieros humanos (`human_tech_lead_01`, `human_staff_eng_02`) puntuaciones generadas por una función determinista módulo 5, o reemplazarlas por calificaciones humanas reales documentadas.
2. **Alinear los 20 casos sintéticos de S3 o sus bloques `final_code`:** Las transcripciones heredadas de `evals/golden_transcripts/` contienen stubs de 4 líneas que contradicen sus etiquetas `senior` de `4.4`–`5.0`, haciendo que la calibración global falle ($r_s = 0.6159 < 0.70$, $\kappa_w = 0.5402 < 0.60$).
3. **Configuración funcional de Judge0 CE (server + workers):** Añadir la configuración completa de Judge0 CE (incluyendo `judge0-workers` con `privileged: true` y base de datos propia) y ejecutar `exec_03`/`exec_04` de S2 contra Judge0 real en lugar de `DeterministicPythonSandboxRunner`.

### P1 — Importantes (Seguridad de Agente, Prompts S2 y Resiliencia)
4. **Encapsular salidas no confiables en mensajes `role="tool"`:** Envolver `stdout`/`stderr` de `code_execution_sandbox` en etiquetas `<untrusted_candidate_input>` o advertir explícitamente en el system prompt que los campos `stdout`/`stderr` dentro de `role="tool"` son datos no confiables del candidato.
5. **Reemplazar prompts directivos en S2 (`exec_03`–`exec_07`):** Usar mensajes naturales del candidato (sin mencionar los nombres internos `code_execution_sandbox` ni `adaptive_hint_generator` en el texto del candidato) y conservar en `s2_10_executions.json` el payload `tool_calls` crudo además de la traza sanitizada.
6. **Restringir `args.problem_id` en `_run_problem_selector`:** Cuando `self._interview.problem_id` ya esté asignado a la sesión, ignorar o rechazar cualquier `args.problem_id` distinto en `inspect_assigned_problem`.
7. **Evitar contaminación de métricas en `evals/calibrate.py`:** Cuando ocurra `model_error=True` en modo `--live-llm`, no sustituir la predicción fallida por `simulate_offline_prediction(data)`.
8. **Mover el shim de `arq` o proteger la importación en `src/evaluation/worker.py`:** Importar `src.evaluation.queue` antes de `from arq import Retry` en `worker.py` y documentar explícitamente en código que el fallback de `queue.py` es solo un stub de pruebas y no una cola funcional de workers.

---

## 12. Matriz Final de Cumplimiento

| Área | Implementación | Evidencia real | Tests | Veredicto |
|---|---|---|---|---|
| **H-02** | Completa en los 3 routers (`evaluation`, `privacy`, `trajectory`); shim de `arq` en `queue.py` solo apto para tests | Diffs aislados verificados; sin mezcla de otras fases | `111 passed` verificados en `pytest` | **`PASS`** |
| **S1** | Completa (`InterviewAgent` + `OpenAICompatibleClient` + `smoke_s1_grok.py`) | Entrevista `064da846...` verificada en PostgreSQL (`6` turnos, `3` registros de uso LLM, `$0.043370 USD`, retención de contexto en Turno 3) | Cubierto por `test_llm.py`, `test_agent.py` y smoke test real | **`PASS`** |
| **S2** | Completa en cliente LLM, `AgentToolRuntime` (`tools.py`) y bucle acotado en `InterviewAgent` | `10` entrevistas y `21` llamadas LLM reales verificadas en PostgreSQL (`$0.358585 USD`), pero `exec_03`/`04` usaron `DeterministicPythonSandboxRunner` en memoria, 5 prompts nombraron la herramienta y las trazas JSON están truncadas | `5` nuevos tests unitarios/integración en `test_llm.py` y `test_agent.py` (`PASS`) | **`PARTIAL`** |
| **H-01** | Completa en `websocket.py`, `execution/service.py`, `use-interview-socket.ts` y `test-console.tsx` (pendiente `make update-contracts` bilateral) | Degradación limpia a `status="unavailable"` con `stdout=None` y `tests_passed=None` verificada | `4` nuevos tests en `test_execution.py` y `test_websocket.py` + `tsc` + `20/20` tests web (`PASS`) | **`PASS`** |
| **Sandbox** | `Judge0Adapter` aplica límites (`2000ms`, `128MB`, `enable_network=False`) y rechaza ejecución en host | Sin instancia Judge0 activa en el entorno local (`localhost:2358` cerrado); `infra/judge0/docker-compose.yml` no existe y `docker-compose.prod.yml` carece de `judge0-workers` | Tests unitarios con `MockTransport` en `test_sandbox.py` y `test_execution.py` (`PASS`) | **`PARTIAL`** |
| **S3** | `evals/calibrate.py` implementa `--live-llm`, IC 95%, matriz $3 \times 3$, concordancia por dimensión y estratificación | `32/32` casos evaluados en vivo por `grok-4.6` (`$0.877160 USD`), pero el "panel humano doble ciego" fue generado por una fórmula módulo 5 en `build_s3_benchmark.py`, los 2 casos `real_anonymized` son de scripts internos y el Spearman global es `0.6159 < 0.70` | `test_calibration.py` (`7 passed` en modo offline) | **`PARTIAL`** |
| **Documentación** | `README.md` y los 10 reportes en `docs/reports/FINAL_REMEDIATION/` existen y detallan comandos y arquitectura | `KNOWN_LIMITATIONS.md` cita una ruta `infra/judge0/docker-compose.yml` inexistente y `S3_BENCHMARK_REPORT.md` presenta el panel sintético módulo 5 como dos evaluadores humanos | Verificación manual y estática completada | **`PARTIAL`** |

---

## 13. Veredicto Global de la Auditoría

**`REQUIRES_CORRECTIONS`**
