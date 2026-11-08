# Protocolo de Calibración Humana y Validación Psicométrica (S-21)

> **Estado del Entregable S-21:**
> - **Implementación de Software:** `COMPLETO` (Harness estadístico en `evals/calibrate.py`, 20 transcripciones doradas y pruebas automatizadas en `apps/api/tests/test_calibration.py`).
> - **Validación Experimental de Negocio:** `PENDIENTE DE VALIDACIÓN HUMANA EXTERNA`.
> - **Anotaciones Actuales:** `synthetic_benchmark` (Anotaciones provisionales sintéticas calibradas por rúbrica; no deben presentarse como criterio humano hasta completar el panel descrito en este documento).

---

## 1. Objetivo del Protocolo

Establecer el procedimiento científico y operativo para que dos ingenieros/Tech Leads evalúen de manera independiente y a ciegas el corpus de **20 transcripciones doradas** (`evals/golden_transcripts/`), contrastando su juicio experto con la evaluación emitida por el modelo Juez LLM para validar formalmente la defendibilidad estadística de la plataforma.

---

## 2. Definición del Panel de Evaluadores

1. **Cantidad:** Mínimo dos (2) evaluadores humanos independientes (Evaluador A y Evaluador B).
2. **Perfil Exigido:** Ingenieros de Software Senior, Tech Leads o Arquitectos con experiencia comprobada en contratación técnica y evaluación de código en Python, TypeScript o SQL.
3. **Independencia y Doble Ciego:**
   - Los evaluadores **no deben ver** la puntuación emitida por el Juez LLM ni la puntuación asignada por el otro evaluador humano.
   - Los evaluadores **no deben ver** datos de identificación personal (PII) de los candidatos (nombres, género, universidad, edad), trabajando exclusivamente sobre los turnos de chat técnicos, snapshots de código y ejecuciones de prueba.

---

## 3. Rúbrica Oficial de Evaluación (1 a 5)

Cada evaluador humano debe calificar individualmente las cinco (5) dimensiones canónicas de la rúbrica sobre una escala discreta de 1 a 5 puntos:

| Dimensión | Snake Case | Descripción |
|---|---|---|
| **Resolución de Problemas** | `problem_solving` | Clarificación inicial de límites, manejo de casos borde y cumplimiento de requerimientos. |
| **Razonamiento Algorítmico** | `algorithmic_reasoning` | Eficiencia asintótica, selección adecuada de estructuras de datos y lógica de control. |
| **Calidad de Código y Tipado** | `code_quality` | Legibilidad, buenas prácticas del lenguaje, modularidad y ausencia de anti-patrones. |
| **Comunicación Técnica** | `technical_communication` | Claridad al explicar enfoques en el chat, justificación de decisiones y formulación de preguntas. |
| **Gestión de Complejidad** | `complexity_management` | Descomposición estructurada, manejo de concurrencia/memoria y escalabilidad de la solución. |

### Puntuación Global y Recomendación:
- **Puntaje Global (`overall_score`):** Media aritmética simple de las 5 dimensiones.
- **Recomendación (`recommendation`):**
  - `hire` (Contratar): `overall_score >= 4.0`
  - `borderline` (En duda / Revisión): `3.0 <= overall_score < 4.0`
  - `reject` (Rechazar): `overall_score < 3.0`

---

## 4. Procedimiento de Ejecución del Panel

1. **Lectura Individual:** Cada evaluador revisa de forma asíncrona las 20 transcripciones doradas en `evals/golden_transcripts/`:
   - 7 casos nivel `junior`
   - 6 casos nivel `mid`
   - 7 casos nivel `senior`
2. **Hoja de Calificación:** Los evaluadores completan la matriz de registro independiente anotando las 5 dimensiones, la nota general y la recomendación cualitativa.
3. **Cálculo del Acuerdo Inter-Evaluador (Inter-Rater Reliability):**
   - Se ejecuta el cálculo de **Correlación de Rangos de Spearman ($r_s$)** y **Kappa de Cohen con ponderación cuadrática ($\kappa_w$)** entre el Evaluador A y el Evaluador B.
   - **Criterio de Consistencia Humana:** Se requiere $r_s \ge 0.75$ y $\kappa_w \ge 0.70$ para validar que la rúbrica es interpretada de forma homogénea por los evaluadores.

---

## 5. Protocolo de Resolución de Discrepancias

Si para una transcripción cualquiera la diferencia entre las notas globales de ambos evaluadores es mayor a un punto ($\Delta > 1.0$) o las recomendaciones son contradictorias (`hire` vs `reject`):
1. **Fase de Consenso:** Los evaluadores A y B sostienen una sesión de conciliación técnica de 5 minutos discutiendo la evidencia concreta de los turnos y código.
2. **Tercer Evaluador (Desempate):** Si no hay consenso, interviene un tercer evaluador ciego (Lead Evaluator) cuya nota zanja la discrepancia.
3. **Puntaje Definitivo:** Se promedian las notas consensuadas para constituir el vector de verdad fundamental humana (`human_expert`).

---

## 6. Actualización en el Repositorio y Evidencia Exigida

Una vez concluido el panel humano presencial/asíncrono:
1. En cada archivo de `evals/golden_transcripts/*.json`, se actualiza el bloque de anotación:
   ```json
   "benchmark_annotation": {
     "annotator_type": "human_expert",
     "annotator_notes": "Calibrado en panel doble ciego por 2 evaluadores expertos independientes (Tech Lead A & Tech Lead B).",
     "overall_score": 4.5,
     "recommendation": "hire",
     "competencies": { ... }
   }
   ```
2. Se ejecuta el harness estadístico:
   ```bash
   python evals/calibrate.py
   ```
3. **Criterios de Aceptación para declarar S-21 Completado:**
   - Tasa de consistencia dentro de rango $\ge 80\%$.
   - Correlación de Spearman modelo vs humano $r_s \ge 0.70$.
   - Kappa de Cohen ponderado cuadrático $\ge 0.70$.
   - Error Absoluto Medio (MAE) $\le 0.35$ puntos.
   - Registro de actas o tabla firmada de calibración archivada en `evals/panel_results.md`.
