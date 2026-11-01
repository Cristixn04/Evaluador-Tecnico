# S3 · Reporte de Demostración: Datos Reales, Evaluación Propia y Costo por Tarea

**Fecha y Hora de Generación:** 2026-11-01 18:05:06 UTC  
**Entorno de Ejecución:** `development`  
**Objetivo Reto S3:** Demostración verificable de datos reales, evaluación propia con rúbrica defendible y costo consolidado por tarea.

---

## 1. Datos Reales

- **Problema Técnico:** `pse-payment-reconciliation` — *Conciliación de pagos PSE*
- **Dominio:** `python, payments, reconciliation, hashing` (backend)
- **Dificultad:** `mid`
- **Límites de Ejecución:** Timeout 2000ms, Memoria 128MB
- **ID de Entrevista:** `24f368b6-ad70-4c61-ae45-cdb0de113a78`
- **Candidato:** `Candidato Anónimo S3` (`candidato-s3-demo@evaluador.local` - anonimizado para evaluación)
- **Turnos de Conversación Registrados:** 7 turnos (candidato y evaluador)
- **Snapshots de Código Registrados:** 2 snapshots de código Python
- **Clasificación de Datos:**
  * Problema técnico: **REAL** (especificación de arquitectura bancaria del catálogo oficial `problems/`).
  * Interacción y Código: **REAL** (registros persistidos en tablas PostgreSQL `interviews`, `turns`, `snapshots`).
  * Transcripciones de calibración benchmark: **SYNTHETIC** (mantenidas estrictamente aisladas en `evals/golden_transcripts/`).

---

## 2. Evaluación Propia

- **Servicio Evaluador:** `apps.api.src.evaluation.service.EvaluationService`
- **Modelo Evaluador:** `grok-4.6` (https://api.reto.pltk.mx/v1)
- **Versión de Prompt:** `prompts/v2/evaluator.md` (con tags de sanitización `<untrusted_candidate_input>`)
- **Puntuación Global (Overall Score):** **4.20 / 5.00**
- **Recomendación Final:** **`HIRE`**
- **Requiere Revisión Humana (`needs_human_review`):** `False`
- **Nota de Discrepancia:** `El snapshot final de código está truncado en el cuerpo del bucle; la puntuación de code_quality se basa en la firma, estructuras visibles y el run 5/5.`

### Puntuación por Dimensiones Canónicas (Escala 1 a 5):

| Dimensión de la Rúbrica | Puntaje | Criterio Evaluado |
|---|:---:|---|
| `problem_solving` | **4** / 5 | Comprensión del dominio PSE, manejo de estados bancarios y reintentos |
| `algorithmic_reasoning` | **4** / 5 | Transición de búsqueda O(N*M) a tabla hash O(N+M) e idempotencia |
| `code_quality` | **4** / 5 | Modularidad, tipado estricto, estructura limpia de diccionario |
| `technical_communication` | **4** / 5 | Claridad en preguntas sobre CUS, tolerancia decimal y streaming |
| `complexity_management` | **5** / 5 | Trade-offs de memoria vs batch processing para 500k transacciones |

### Evidencias Citadas y Trazabilidad:

| Dimensión | Referencia Verificada (`turn_id` / `snapshot_id`) | Cita Textual de Evidencia |
|---|---|---|
| `problem_solving` | `bc260b39-11cd-47d4-be4b-b8f47463a894` | "estructuraré la solución en dos fases: 1) Indexación en memoria usando una tabla hash O(N) indexa..." |
| `algorithmic_reasoning` | `7f791576-8f58-41e5-a502-4e5ffa6ae459` | "orders_by_cus = {o['cus']: o for o in internal_orders}     seen_bank_cus = set()" |
| `technical_communication` | `f32c44ce-9b25-4ff8-871e-4b7f2059b20c` | "Para 500k registros, cargar todo en memoria puede consumir ~150MB. Si bien entra en RAM, la mejor..." |

---

## 3. Costo por Tarea

**Definición de Unidad:** 1 Tarea = 1 Entrevista técnica completa resuelta y evaluada.

- **Modelo / Proveedor:** `grok-4.6`
- **Tarifas Oficiales Documentadas:** $5.00 / 1M prompt, $15.00 / 1M completion
- **Fórmula Determinista:**
  $$\text{Costo (USD)} = \frac{\text{tokens\_prompt} \times \text{tarifa\_prompt} + \text{tokens\_completion} \times \text{tarifa\_completion}}{1{,}000{,}000.0}$$
- **Garantía Anti Doble-Contabilidad:** Desglose independiente por etapas mediante `TaskCostBreakdown`.

### Desglose Consolidado de Costos:

| Concepto / Etapa | Invocaciones LLM | Tokens Entrada (Prompt) | Tokens Salida (Completion) | Total Tokens | Costo USD |
|---|:---:|:---:|:---:|:---:|:---:|
| **Conversación (Agente)** | 3 | 1,850 | 260 | 2,110 | **$0.013150** |
| **Evaluación (Juez dual)** | 1 | 7,364 | 2,341 | 9,705 | **$0.071935** |
| **TOTAL DE LA TAREA** | **4** | **9,214** | **2,601** | **11,815** | **$0.085085** |

---

## 4. Limitaciones y Transparencia Metodológica

1. **Costos Medidos vs Estimados:** Los tokens de evaluación y conversación provienen directamente del campo `usage` reportado por el proveedor LLM. El costo en USD es determinista según la tabla oficial de precios.
2. **Aislamiento de Benchmarks:** Los resultados del script de calibración (`evals/calibrate.py`) emplean datos sintéticos (`synthetic_benchmark`), mientras que esta demostración opera sobre datos reales de sesión.
3. **Componentes Fuera de la Medición de Tokens:** La ejecución local en sandbox de pruebas y la latencia de red WebSocket no consumen tokens de LLM y no forman parte del costo de API de inferencia.

---

## 5. Veredicto de Demostración

**ESTADO DE DEMOSTRACIÓN:** `REAL_DEMONSTRATION_EXECUTED`  
Las tres capacidades de S3 han sido ejecutadas y validadas integralmente sobre la infraestructura real del backend.