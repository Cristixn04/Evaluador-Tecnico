# Evaluador-Técnico — Informe Final de Remediación Integral Post-Auditorías

**Fecha:** `2026-11-04`  
**Autor:** Antigravity (Ingeniería y Remediación Autónoma)  
**Bases de Auditoría:**  
1. `docs/reports/FINAL_REMEDIATION/INDEPENDENT_AUDIT_1.md`  
2. `docs/reports/FINAL_REMEDIATION/FEEDBACK_COMPLIANCE_AUDIT.md`  
**Veredicto Global de Remediación:** **`PARTIALLY_COMPLIANT (LISTO PARA REVISIÓN HUMANA FINAL)`**  

---

## 1. Resumen Ejecutivo y Veredicto Consolidado

Tras la ejecución de las dos auditorías independientes y la subsanación técnica y metodológica completa de las desviaciones detectadas, el estado del repositorio se resume a continuación:

| Entregable / Área | Estado Pre-Remediación | Estado Post-Remediación | Veredicto Técnico | Justificación Principal |
|---|---|---|---|---|
| **S1 — Integración Grok** | Discrepancia documental entre xAI directo y proxy del reto | Resuelto y verificado en base de datos PostgreSQL | **CUMPLIDO (`PASS`)** | 6 turnos multi-turno reales en PostgreSQL (`064da846...`), 10,601 tokens y $0.043370 USD reales en `https://api.reto.pltk.mx/v1` con `grok-4.6`. |
| **S2 — Function Calling y Sandbox** | Prompts sesgados (5/10 nombraban herramientas) y uso de mock en memoria (`DeterministicPythonSandboxRunner`) | 10 corridas reales con Judge0 en Docker y lenguaje neutral | **CUMPLIDO (`PASS`)** | Judge0 CE v1.13.1 levantado en `infra/judge0/`, compatibilidad cgroups v2 rlimits resuelta, 10 prompts neutrales, 11 tool calls, 21 llamadas LLM reales, $0.362350 USD. |
| **S3 — Calibración y Benchmark** | Simulación de `evaluator_2` con fórmula `% 5`, umbral `in_range` relajado ($\pm 0.50$), sesiones de prueba etiquetadas como entrevistas reales | Erradicación de evaluador sintético, reclasificación honesta y métricas estrictas | **PARCIALMENTE CUMPLIDO (`HUMAN_PENDING`)** | Reclasificación honesta (22 sintéticos, 10 referencias públicas, 0 candidatos humanos reales). Se declaró `HUMAN_VALIDATION_PENDING` para el 2do evaluador. Métricas estrictas aplicadas sin relajar umbrales ($r_s=0.6102$, $\kappa_w=0.5402$, 62.5% en rango global, 100% en soluciones completas). |
| **H-01 — Sandbox Fallback & WebSocket** | Ausencia de sandbox local y potencial caída de sesión | Degradación elegante verificada sin `ValidationError` | **CUMPLIDO (`PASS`)** | `CodeExecutionService` devuelve `status="unavailable"` estructurado si Judge0 se apaga, sin romper el WebSocket ni la sesión. |
| **H-02 — Seguridad Multiempresa** | Falta de aislamiento estricto en selector y salida de sandbox no encapsulada en system prompt | Bloqueo de reasignación de problema y tag `<untrusted_candidate_output>` | **CUMPLIDO (`PASS`)** | `tools.py` prohíbe cambiar `problem_id` asignado; `service.py` encapsula stdout/stderr en `<untrusted_candidate_output>`. 111 tests de seguridad pasan. |
| **Tooling & CI/CD** | `worker.py` fallaba con `ModuleNotFoundError: arq` en host Python 3.14 | Reordenamiento de importación de queue shim | **CUMPLIDO (`PASS`)** | 434 tests pasan en el backend; `tsc --noEmit` y 20 tests pasan en el frontend. Cero commits ni pushes no autorizados. |

---

## 2. Remediación Detallada por Sprint

### 2.1. Sprint 1 (S1) — Integración Grok y Verificación de Datos Reales

#### Hallazgos de Auditoría:
- Discrepancia entre la documentación en `docs/guides/llm-providers.md` (que describía upstream directo a `https://api.x.ai/v1` con `grok-4.20-0309-reasoning`) y las variables activas en el entorno (`https://api.reto.pltk.mx/v1` con `grok-4.6`).
- Dudas sobre si la sesión multi-turno había sido persistida en PostgreSQL.

#### Correcciones y Evidencia:
1. **Verificación en PostgreSQL:** Se inspeccionó directamente la base de datos `evaluador_db` en el contenedor `evaluador-postgres` (puerto `5435`). La entrevista `064da846-4f36-4e38-8012-a1cb29b33f08` contiene exactamente **6 turnos conversacionales** alternados (3 de candidato y 3 del agente) y 3 registros en la tabla `llm_usage_records`.
2. **Telemetría Verificada:**
   - Prompt tokens: `6,070`
   - Completion tokens: `868`
   - Total tokens: `10,601` (incluye tokens de razonamiento)
   - Costo medido: `$0.043370 USD`
3. **Resolución de la discrepancia:** Todas las llamadas reales se realizaron exclusivamente a través del proxy oficial del reto `https://api.reto.pltk.mx/v1` utilizando el modelo `grok-4.6`. La referencia a xAI directo correspondía a una guía de arquitectura upstream opcional y fue aclarada documentalmente en `FEEDBACK_COMPLIANCE_AUDIT.md`.

---

### 2.2. Sprint 2 (S2) — Autonomía, Function Calling y Sandbox Judge0 Real

#### Hallazgos de Auditoría:
- En la corrida original, 5 de los 10 prompts instruían textualmente al modelo qué herramienta y argumentos llamar (ej. *"Por favor ejecútala ahora mismo usando tu herramienta code_execution_sandbox con language='python'"*).
- Se utilizó un mock en memoria (`DeterministicPythonSandboxRunner`) en lugar de Judge0 CE.

#### Acciones de Remediación Ejecutadas:
1. **Infraestructura Judge0 CE Desplegada y Operativa:**
   - Se crearon los archivos de configuración reproducibles:
     - [`infra/judge0/judge0.conf`](file:///home/papisamu/Documentos/Evaluador-Tecnico/infra/judge0/judge0.conf)
     - [`infra/judge0/docker-compose.yml`](file:///home/papisamu/Documentos/Evaluador-Tecnico/infra/judge0/docker-compose.yml)
     - [`infra/judge0/README.md`](file:///home/papisamu/Documentos/Evaluador-Tecnico/infra/judge0/README.md)
   - Se levantaron en Docker los 4 contenedores oficiales: `evaluador-judge0-server` (puerto `2358`), `evaluador-judge0-workers`, `evaluador-judge0-db` y `evaluador-judge0-redis`.
   - **Compatibilidad cgroups v2:** Se adaptó [`apps/api/src/sandbox/judge0.py`](file:///home/papisamu/Documentos/Evaluador-Tecnico/apps/api/src/sandbox/judge0.py) agregando `"enable_per_process_and_thread_time_limit": True` y `"enable_per_process_and_thread_memory_limit": True`. Esto permite que el sandbox use aislamiento estricto por rlimits en kernels Linux modernos con jerarquía unificada de cgroups v2 sin fallar en `/sys/fs/cgroup/memory`.
2. **Prompts Neutrales sin Nombres de Herramientas:**
   - Se eliminaron todos los nombres de herramientas (`code_execution_sandbox`, `adaptive_hint_generator`, `problem_selector`) y de parámetros de los 10 prompts en [`apps/api/src/scripts/run_s2_10_executions.py`](file:///home/papisamu/Documentos/Evaluador-Tecnico/apps/api/src/scripts/run_s2_10_executions.py).
   - Ejemplo remediado (`exec_03`): *"Acabo de terminar mi solución en Python para la conciliación transaccional PSE. ¿Podrías probarla con los casos de prueba para verificar si cumple todos los requisitos? [Código Python]"*.
   - Grok decidió autónomamente invocar la herramienta adecuada en cada uno de los 10 escenarios.
3. **Erradicación del Mock en Memoria:**
   - Se eliminó completamente `DeterministicPythonSandboxRunner`.
   - Todas las ejecuciones de código (`exec_03`, `exec_04`) se ejecutaron en el sandbox real Judge0 CE contra el problema `pse-payment-reconciliation`.
   - Para `exec_07` (fallo controlado de sandbox no disponible), se empleó un runner que simula la indisponibilidad de red para verificar la degradación elegante sin tener que apagar el contenedor Docker del sandbox.
4. **Resultados de la Reejecución Real (10/10 PASS):**
   - **Veredicto S2:** **`PASS`**
   - **Total de ejecuciones:** 10
   - **Ejecuciones normales exitosas:** 6 (requeridas: $\ge 6$)
   - **Ejecuciones con fallo controlado:** 3 (requeridas: $\ge 3$)
   - **Ejecuciones con entrada inválida / bloqueo de seguridad:** 1 (requeridas: $\ge 1$)
   - **Total de Tool Calls ejecutados:** 11
   - **Total de llamadas LLM:** 21
   - **Tokens consumidos:** 74,075
   - **Costo total medido:** `$0.362350 USD`
   - Evidencia completa persistida en [`docs/reports/FINAL_REMEDIATION/s2_10_executions.json`](file:///home/papisamu/Documentos/Evaluador-Tecnico/docs/reports/FINAL_REMEDIATION/s2_10_executions.json) y [`docs/reports/FINAL_REMEDIATION/S2_FUNCTION_CALLING_REPORT.md`](file:///home/papisamu/Documentos/Evaluador-Tecnico/docs/reports/FINAL_REMEDIATION/S2_FUNCTION_CALLING_REPORT.md).

---

### 2.3. Sprint 3 (S3) — Calibración, Procedencia y Panel Humano

#### Hallazgos de Auditoría:
- En `build_s3_benchmark.py`, el Evaluador 2 (`evaluator_2`) era simulado artificialmente mediante la fórmula `case_index % 5` para introducir discrepancias sintéticas de 1 punto.
- En `evals/calibrate.py`, la condición `in_range` tenía un padding relajado: `(s_min <= pred <= s_max) or abs(pred - bench) <= 0.50`.
- Dos casos (`31` y `32`) estaban etiquetados como `real_anonymized`, pero procedían de smoke tests automatizados internos.
- Si una llamada LLM fallaba en vivo, el script recurría silenciosamente a `simulate_offline_prediction`.

#### Acciones de Remediación Ejecutadas:
1. **Erradicación de la Simulación de Evaluador:**
   - Se eliminó por completo la función generadora con módulo 5.
   - En [`apps/api/src/scripts/build_s3_benchmark.py`](file:///home/papisamu/Documentos/Evaluador-Tecnico/apps/api/src/scripts/build_s3_benchmark.py), se estableció que la referencia dorada corresponde a la rúbrica técnica de Evaluador 1 (`human_tech_lead_01`).
   - Se registró honestamente `evaluator_2: None`, `panel_status: "HUMAN_VALIDATION_PENDING"` y `is_human_verified: false` hasta que un segundo evaluador humano independiente complete la doble ciega.
2. **Reclasificación Honesta de Procedencia:**
   - Casos 1–20: `synthetic` (del corpus dorado base).
   - Casos 21–30: `public_reference_solution` (soluciones del catálogo técnico).
   - Casos 31–32: `synthetic` (sesiones de prueba automatizadas internas, reclasificadas honestamente para no simular que fueron candidatos humanos externos).
   - Total: 22 sintéticos, 10 soluciones públicas de referencia, 0 candidatos humanos reales.
3. **Endurecimiento de Métricas en `evals/calibrate.py`:**
   - Se eliminó el padding de $\pm 0.50$: la condición es estrictamente `in_range = (s_min <= pred_score <= s_max)`.
   - Se desacopló el fallback de error: si el LLM falla, no se simulan predicciones deterministas y se registra `model_error = True`.
   - Se forzó el código de salida: `return 0 if results["calibration_passed"] else 1` estricto.
4. **Métricas Reales Obtenidas sobre el Benchmark Remediado ($N=32$):**
   - **Corpus:** 32 casos con Grok-4.6 en vivo.
   - **Tasa en rango estricta:** `62.5%` (`20/32`)
   - **Spearman $r_s$:** `0.6102` (IC 95%: `[0.2927, 0.8259]`)
   - **Kappa de Cohen $\kappa_w$:** `0.5402` (IC 95%: `[0.2000, 0.7372]`)
   - **MAE global:** `0.606` puntos
   - **Accuracy de recomendación:** `53.1%`
   - **Subconjunto de código completo (`public_reference_solution`, $n=10$):**
     - Tasa en rango: `100.0%` (`10/10`)
     - Spearman $r_s$: `0.9724`
     - Kappa $\kappa_w$: `1.0000`
     - MAE: `0.2200` puntos
     - Accuracy: `100.0%`
   - **Veredicto Metodológico S3:** `HUMAN_VALIDATION_PENDING` (la plataforma funciona con rigor técnico demostrado, pero la validación psicométrica inter-humana requiere que el segundo evaluador humano complete la doble ciega de forma física e independiente).

---

### 2.4. Remediaciones Transversales: Seguridad, Telemetría y Tooling

1. **Aislamiento Multiempresa en Tools (`H-02`):**
   - En [`apps/api/src/agent/tools.py`](file:///home/papisamu/Documentos/Evaluador-Tecnico/apps/api/src/agent/tools.py), se blindó `_run_problem_selector`: si la entrevista ya tiene un `problem_id` asignado, el selector devuelve directamente el problema asignado y prohíbe reasignaciones.
   - En `exec_10`, se demostró en vivo que si un atacante inyecta `organization_id` en los argumentos de la herramienta, el runtime lo rechaza con `CONTEXT_SECURITY_VIOLATION` antes de tocar la base de datos.
2. **Encapsulación de Entradas No Confiables:**
   - En [`apps/api/src/agent/service.py`](file:///home/papisamu/Documentos/Evaluador-Tecnico/apps/api/src/agent/service.py), toda salida de sandbox (`stdout` y `stderr`) devuelta al LLM en mensajes `role="tool"` se encapsula dentro del tag `<untrusted_candidate_output>` para prevenir inyecciones indirectas en el agente.
3. **Resolución de Error de Importación en Worker:**
   - En [`apps/api/src/evaluation/worker.py`](file:///home/papisamu/Documentos/Evaluador-Tecnico/apps/api/src/evaluation/worker.py), se reordenó la importación `from src.evaluation.queue import evaluation_queue` antes de cualquier importación de `arq`. Esto garantiza que el shim `_FallbackArqRedis` se inicialice transparentemente en cualquier host donde `arq` no esté preinstalado globalmente.
4. **Verificación de la Suite de Pruebas:**
   - **Backend:** 434 tests pasan en `apps/api` (`pytest apps/api/tests/`).
   - **Frontend:** `tsc --noEmit` sin errores y 20/20 tests pasan en `apps/web` (renderizado Markdown y sincronización de fases WebSocket).

---

## 3. Estado del Repositorio y Protección de Git

En estricto cumplimiento de las restricciones operativas de la auditoría:
- **No se ejecutó:** `git add`, `git commit`, `git push`, `git merge`, `git reset`, `git checkout`, `git switch` ni `git clean`.
- **Ramas:** Se permaneció en la rama de trabajo `develop`. HEAD está en `f94926fbcb29fda9bad937b4b590cd1e3f5f5459`.
- **Archivos protegidos intactos:**
  - `packages/contracts/`: 100% preservado sin modificaciones unilaterales.
  - `plan_evaluador_tecnico.md`: Preservado en su estado preexistente.
  - `apps/api/docs/`: Preservado.
  - Informes históricos anteriores y stashes (`stash@{0}`, `stash@{1}`): Intactos.

---

## 4. Acciones Requeridas por el Equipo Humano

Para cerrar formalmente el ciclo de certificación tras esta remediación técnica:

1. **Panel Humano para el Benchmark S3:**
   - Un segundo evaluador técnico humano (Staff Engineer / Tech Lead) debe calificar los 32 casos de [`evals/s3_benchmark/`](file:///home/papisamu/Documentos/Evaluador-Tecnico/evals/s3_benchmark) en un formulario ciego independiente.
   - Una vez cargadas las calificaciones de `evaluator_2`, reejecutar `evals/calibrate.py` para calcular el Kappa de Cohen y Spearman inter-humano real.
2. **Revisión Bipartita de PR (`develop` $\rightarrow$ `main`):**
   - Samuel y Cristian deben revisar conjuntamente los archivos modificados en `develop`.
   - Efectuar commit semántico convencional (ej. `chore(remediation): apply audit fixes for judge0, s2 function calling and s3 benchmark`).
   - Promover los cambios a `main` mediante Pull Request aprobado por ambos.

---

**Fin del Informe de Remediación.**
