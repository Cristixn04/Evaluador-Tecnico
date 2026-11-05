# Limitaciones Conocidas y Notas Operativas Honestamente Documentadas (Sección 10.9)

**Fecha de Registro:** `2026-11-04`  

---

## 1. Estado y Despliegue de Judge0 CE (`http://localhost:2358`)

- **Estado actual tras la remediación integral:**
  - El clúster Docker de **Judge0 CE v1.13.1** se encuentra implementado y operando localmente en `infra/judge0/docker-compose.yml` (`evaluador-judge0-server`, `evaluador-judge0-workers`, `evaluador-judge0-db`, `evaluador-judge0-redis`).
  - Para soportar hosts Linux con jerarquía unificada de **cgroups v2** sin cgroup v1 memory controller legacy, se configuró `Judge0Adapter` con los parámetros `"enable_per_process_and_thread_time_limit": True` y `"enable_per_process_and_thread_memory_limit": True`.
  - El sandbox aísla la ejecución mediante límites de tiempo de CPU (rlimit 2000 ms), memoria (128 MB), límite de subprocesos/hilos (máx 10) y `enable_network: false`.
  - La suite S2 se ejecutó en su totalidad contra esta instancia real de Judge0 (cero uso de `DeterministicPythonSandboxRunner`).
  - Cuando Judge0 no está disponible o se detiene, `CodeExecutionService` implementa degradación elegante (`status="unavailable"`) sin caídas del agente.

---

## 2. Compatibilidad de `arq` y Orden de Importación

- **Observación y corrección:** En [`apps/api/src/evaluation/worker.py`](file:///home/papisamu/Documentos/Evaluador-Tecnico/apps/api/src/evaluation/worker.py), la importación `from src.evaluation.queue import evaluation_queue` se reordenó antes de cualquier importación de `arq`. Dado que `queue.py` inicializa el shim de compatibilidad `_FallbackArqRedis` cuando `arq` no está en el host, esto garantiza que la ejecución de tests y módulos sea 100% reproducible tanto en el contenedor Docker como en entornos anfitriones Python 3.12–3.14.

---

## 3. Latencia y Costos de Inferencia de `grok-4.6` en el Gateway

- **Observación medida:** El gateway `https://api.reto.pltk.mx/v1` con el modelo `grok-4.6` realiza razonamiento interno (`reasoning_tokens` incluidos en el cómputo de tokens), con latencias por turno de entre 5s y 21s en S2, y hasta 65s en evaluaciones de rúbricas complejas S3.
- **Telemetría acumulada verificada:**
  - **S1 (Turno multi-turno real en DB `evaluador_db`):** 6 turnos, $0.043370 USD, 10,601 tokens.
  - **S2 (10 ejecuciones completas con herramientas):** 11 tool calls, 21 llamadas LLM, 74,075 tokens, $0.362350 USD medidos.
  - **S3 (32 evaluaciones de calibración):** 32 llamadas LLM, $0.877160 USD medidos.

---

## 4. Estado Metodológico del Benchmark S3 ($N = 32$ Casos)

- **Composición del corpus:**
  - `synthetic` (**22 casos**): 20 transcripciones multi-turno del corpus dorado más 2 sesiones internas de smoke test ejecutadas durante Sprint 1/2 (`064da846...` y `506f3994...`). Se reclasificaron honestamente como sintéticas tras verificar que no proceden de candidatos externos en un proceso de selección.
  - `public_reference_solution` (**10 casos**): Soluciones completas de referencia sobre problemas del catálogo técnico.
- **Erradicación de simulación algorítmica:**
  - Se eliminó por completo la fórmula determinista `case_index % 5` que generaba artificialmente a `evaluator_2`.
  - El estado del panel doble ciego se declara transparentemente como **`HUMAN_VALIDATION_PENDING`** y `is_human_verified: false` hasta que un segundo evaluador humano independiente complete la anotación ciega de los 32 casos.
  - Se adopta la rúbrica del Evaluador 1 (Senior Backend Tech Lead) como estándar de referencia dorado único.
- **Resultados bajo umbrales estrictos sin padding:**
  - Con la fórmula estricta `s_min <= pred <= s_max` (sin el margen relajado de $\pm 0.50$):
    - **Global ($N=32$):** Tasa en rango = 62.5% (20/32), Spearman $r_s = 0.6102$, Kappa $\kappa_w = 0.5402$, MAE = 0.606 puntos, Accuracy de recomendación = 53.1%.
    - **Subconjunto de código completo (`public_reference_solution`, $n=10$):** Tasa en rango = 100.0% (10/10), Spearman $r_s = 0.9724$, Kappa $\kappa_w = 1.000$, MAE = 0.220 puntos, Accuracy = 100.0%.
  - Se desacopló el error fallback en `evals/calibrate.py`: en caso de error de LLM en vivo, no se simulan predicciones offline. El arnés falla con código de salida 1 si no se alcanzan los umbrales exigidos.

---

## 5. Sincronización Pendiente `develop` $\rightarrow$ `main`

- De acuerdo con las restricciones de protección de Git (Sección 0.1), no se ejecutaron `git commit`, `git merge` ni `git push`.
- Una vez revisados los cambios en `develop` por el equipo humano, se debe promover `develop` hacia `main` siguiendo el procedimiento detallado en [`INITIAL_REPOSITORY_STATE.md`](file:///home/papisamu/Documentos/Evaluador-Tecnico/docs/reports/FINAL_REMEDIATION/INITIAL_REPOSITORY_STATE.md).
