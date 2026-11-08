# S3 · Reporte de Demostración: Datos Reales, Evaluación Propia y Costo por Tarea

**Fecha y Hora de Generación:** 2026-11-01 18:31:35 UTC  
**Entorno de Ejecución:** `development`  
**Objetivo Reto S3:** Demostración verificable de datos reales, evaluación propia con rúbrica defendible y costo consolidado por tarea.

---

## 1. Procedencia y Clasificación de Datos

- **Problema Técnico:** `pse-payment-reconciliation` — *Conciliación de pagos PSE*
- **Dominio:** `python, payments, reconciliation, hashing` (backend)
- **Dificultad:** `mid`
- **Límites de Ejecución:** Timeout 2000ms, Memoria 128MB
- **ID de Entrevista:** `0e19d64d-5911-4dcd-88ae-988311e41883`
- **Candidato:** `Candidato Anónimo S3` (`candidato-s3-demo@evaluador.local`)
- **Turnos de Conversación:** 7 turnos registrados -> **SINTÉTICO / GENERADO POR SCRIPT (Fixture de prueba)**
- **Snapshots de Código:** 2 snapshots registrados -> **NO DISPONIBLE (Sandbox offline; no simulado)**

### Matriz de Clasificación de Evidencia:

| Componente | Origen de Datos | Clasificación Técnica | Estado de Verificación |
|---|---|:---:|:---:|
| **Problema de Ingeniería** | Catálogo oficial `problems/pse-payment-reconciliation.yaml` | **REAL** | Verificado en BD |
| **Diálogo Conversacional** | Script fixtures/demo | **SINTÉTICO / GENERADO POR SCRIPT (Fixture de prueba)** | Auditado como sintético |
| **Ejecución en Sandbox** | Sin ejecución en vivo (Judge0 offline) | **NO DISPONIBLE (Sandbox offline; no simulado)** | No simulado (status=unavailable) |
| **Evaluador LLM** | Invocación dual-judge a Grok-4.6 vía proxy | **REAL** | Verificado HTTP 200 |
| **Persistencia de Telemetría** | Tabla PostgreSQL `llm_usage_records` | **REAL** | Reconstruido post-mortem |

---

## 2. Evaluación Propia (Dual-Judge)

- **Servicio Evaluador:** `apps.api.src.evaluation.service.EvaluationService`
- **Modelo Evaluador:** `grok-4.6` (https://api.reto.pltk.mx/v1)
- **Versión de Prompt:** `prompts/v2/evaluator.md` (con delimitadores anti-inyección `<untrusted_candidate_input>`)
- **Puntuación Global (Overall Score):** **3.80 / 5.00**
- **Recomendación Final:** **`BORDERLINE`**
- **Requiere Revisión Humana (`needs_human_review`):** `True`
- **Nota de Discrepancia:** `Evidencia incompleta para una evaluación plenamente confiable: el snapshot final (416ab55b) está truncado a mitad del bucle; la única ejecución (reason=run) quedó status=unavailable con 3 tests, 0 éxitos y 0 fallos. El diseño y la mejora O(N*M)→hash son visibles, pero no se verificó una implementación terminada ni el paso de tests.`

### Puntuación por Dimensiones Canónicas (Escala 1 a 5):

| Dimensión de la Rúbrica | Puntaje | Criterio Evaluado |
|---|:---:|---|
| `problem_solving` | **4** / 5 | Comprensión del dominio PSE, manejo de estados bancarios y reintentos |
| `algorithmic_reasoning` | **4** / 5 | Transición de búsqueda O(N*M) a tabla hash O(N+M) e idempotencia |
| `code_quality` | **3** / 5 | Modularidad, tipado estricto, estructura limpia de diccionario |
| `technical_communication` | **4** / 5 | Claridad en preguntas sobre CUS, tolerancia decimal y streaming |
| `complexity_management` | **4** / 5 | Trade-offs de memoria vs batch processing para 500k transacciones |

### Evidencias Citadas y Trazabilidad:

| Dimensión | Referencia Verificada (`turn_id` / `snapshot_id`) | Cita Textual de Evidencia |
|---|---|---|
| `problem_solving` | `cbe4d37b-dc2b-42a1-bbf8-75fe8f8c26ba` | "estructuraré la solución en dos fases: 1) Indexación en memoria usando una tabla hash O(N) indexa..." |
| `algorithmic_reasoning` | `416ab55b-1bf8-49e5-83b6-cbc63c0c1fb6` | "orders_by_cus = {o['cus']: o for o in internal_orders}     seen_bank_cus = set()     matches = []..." |
| `code_quality` | `416ab55b-1bf8-49e5-83b6-cbc63c0c1fb6` | "def reconcile_pse_transactions(     bank_records: list[dict[str, Any]],     internal_orders: list..." |
| `technical_communication` | `c8a51dbd-5a16-4232-b674-c1538e613544` | "Tengo dos preguntas clave: primero, ¿los identificadores de transacción de PSE (`ticket_office_id..." |
| `complexity_management` | `cf7f60f5-5262-4f79-bcf0-e96eeae3d4c6` | "for b in bank_records:         for o in internal_orders:             if b['cus'] == o['cus']:    ..." |

---

## 3. Costo por Tarea (Persistido y Reconstruido de PostgreSQL)

**Definición de Unidad:** 1 Tarea = 1 Entrevista técnica resuelta y evaluada.

- **Modelo / Proveedor:** `grok-4.6` (Proxy OpenAI-compatible)
- **Tarifas Oficiales Documentadas:** $5.00 / 1M prompt, $15.00 / 1M completion (xAI Grok benchmark)
- **Fórmula Determinista:**
  $$\text{Costo (USD)} = \frac{\text{tokens\_prompt} \times \text{tarifa\_prompt} + \text{tokens\_completion} \times \text{tarifa\_completion}}{1{,}000{,}000.0}$$
- **Diferenciación de Costos:**
  * Costo Medido (Llamadas reales con `usage`): **$0.073600 USD**
  * Costo Estimado (Estimaciones o fixtures): **$0.013150 USD**
- **Garantía Anti Doble-Contabilidad:** Desglose independiente por etapas mediante `TaskCostBreakdown` y persistencia en `llm_usage_records`.

### Desglose Consolidado de Costos:

| Concepto / Etapa | Invocaciones LLM | Tokens Entrada | Tokens Salida | Total Tokens | Costo Medido | Costo Estimado | Costo Total USD |
|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **Conversación** | 3 | 1,850 | 260 | 2,110 | $0.000000 | $0.013150 | **$0.013150** |
| **Evaluación** | 1 | 7,382 | 2,446 | 9,828 | $0.073600 | $0.000000 | **$0.073600** |
| **TOTAL DE LA TAREA** | **4** | **9,232** | **2,706** | **11,938** | **$0.073600** | **$0.013150** | **$0.086750** |

---

## 4. Limitaciones Técnicas y Transparencia Metodológica

1. **Aislamiento de Base de Datos:** Las pruebas automatizadas corren exclusivamente en `evaluador_test_db`. La base de desarrollo `evaluador_db` está protegida contra truncado.
2. **Persistencia Durable:** La telemetría de cada llamada se persiste en `llm_usage_records`, permitiendo reconstruir el costo total post-mortem.
3. **Estado de Ejecución Sandbox:** NO DISPONIBLE (Sandbox offline; no simulado).
4. **Procedencia de Turnos:** SINTÉTICO / GENERADO POR SCRIPT (Fixture de prueba).

---

## 5. Veredicto de Demostración

**ESTADO DE DEMOSTRACIÓN:** `S3_1_IMPLEMENTED_MANUAL_DEMO_PENDING`  
El backend cuenta con todas las capacidades técnicas implementadas, telemetría persistida en base de datos y evaluación dual-judge verificada.