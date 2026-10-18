# Estado de Reparación y Estabilización (BLK-01 a BLK-11)

Documento vivo para registrar el diagnóstico, causas, cambios, validación y commits de cada bloqueador identificado en la auditoría maestra.

---

## Matriz de Estado

| ID | Bloqueador | Severidad | Estado | Tests Afectados | Commit Asociado |
|---|---|---|---|---|---|
| **BLK-01** | Routers desconectados en `main.py` | P0 | OPEN | `test_websocket.py`, `test_trajectory.py` | `fix(api): mount interview lifecycle routers` |
| **BLK-02** | Funciones faltantes en `prompts.py` | P0 | OPEN | `test_prompts.py`, `test_agent.py`, `test_hints_integration.py` | `fix(llm): restore prompt loading API` |
| **BLK-03** | Falta de aislamiento en DB y fixtures | P0 | OPEN | `test_auth.py`, `test_problem_selector.py`, `test_evaluation.py` | `fix(tests): isolate backend database fixtures` |
| **BLK-04** | Migración Alembic incompleta e integridad FK | P0 | OPEN | `test_alembic.py` | `fix(db): repair evaluation migration integrity` |
| **BLK-05** | Pseudo-lógica de evaluación basada en texto literal | P1 | OPEN | `test_evaluation.py` | `fix(evaluation): repair defensible judge evidence flow` |
| **BLK-06** | Filtración de PII (`candidate_email[:4]`) | P1 | OPEN | `test_evaluation.py` | `fix(security): remove candidate PII from evaluation` |
| **BLK-07** | Incompatibilidad de contrato `ws_url` | P1 | OPEN | `test_websocket.py`, endpoints sesiones | `fix(api): align candidate session websocket contract` |
| **BLK-08** | Desconexión Frontend develop local vs remoto | P1 | OPEN | Integración Web / E2E | `feat(web): integrate interview frontend` |
| **BLK-09** | Errores Mypy y corrutinas sin await en Agent/Hints | P2 | OPEN | `test_agent.py`, `test_hints.py` | `fix(agent): repair async execution and typing` |
| **BLK-10** | Inexistencia de endpoint `GET /vacancies` | P2 | OPEN | Dashboard Reclutador / Contratos | `feat(vacancies): add organization-scoped vacancy listing` |
| **BLK-11** | Tooling Frontend (lint interactivo, scripts) | P3 | OPEN | `pnpm lint`, `pnpm test` | `chore(web): configure linting and test scripts` |

---

## Detalle por Bloqueador

### BLK-01 — Routers no montados en `main.py`
- **Estado:** OPEN
- **Problema:** `invitations`, `sessions`, `websocket` y `trajectory` no están incluidos en `apps/api/src/main.py`.
- **Causa:** Omisión de `app.include_router` para los nuevos módulos.
- **Cambio planeado:** Incluir routers con prefijos adecuados y dependencias.
- **Tests:** `test_websocket.py`, `test_trajectory.py`.
- **Resultado:** Pendiente.
- **Commit:** Pendiente.

### BLK-02 — API de prompts en `src/llm/prompts.py`
- **Estado:** OPEN
- **Problema:** Falta `load_hints()`, `load_phase_instructions()`, `get_active_prompt_version()`.
- **Causa:** Archivo quedó incompleto tras la reestructuración de prompts v2.
- **Cambio planeado:** Implementar las funciones de carga y lectura de prompts de forma robusta.
- **Tests:** `test_prompts.py`, `test_agent.py`, `test_hints_integration.py`.
- **Resultado:** Pendiente.
- **Commit:** Pendiente.

### BLK-03 — Aislamiento de base de datos en tests
- **Estado:** OPEN
- **Problema:** Basura residual en tablas (`users`, `problems`, `vacancies`) genera colisión de llaves únicas. `sample_interview` no incluye `vacancy_id`.
- **Causa:** `db_session` fixture no aísla transacciones con rollback o truncado. Fixture de entrevista viola NOT NULL en `vacancy_id`.
- **Cambio planeado:** Implementar limpieza controlada de tablas o rollback transaccional en `conftest.py`. Corregir fixture `sample_interview`.
- **Tests:** `test_auth.py`, `test_problem_selector.py`, `test_vacancies.py`, `test_evaluation.py`.
- **Resultado:** Pendiente.
- **Commit:** Pendiente.

### BLK-04 — Alembic e integridad de tablas de evaluación
- **Estado:** OPEN
- **Problema:** Migración `adding_evaluation_tables.py` omite FKs y crea columna `uuid` espuria. `alembic_version` tiene 0 filas en la DB de dev.
- **Causa:** Generación de migración manual o incompleta; bifurcación no sincronizada.
- **Cambio planeado:** Corregir DDL de la migración para alinear con SQLAlchemy ORM y sincronizar `alembic_version`.
- **Tests:** `test_alembic.py`.
- **Resultado:** Pendiente.
- **Commit:** Pendiente.

### BLK-05 — Lógica de evidencia en `EvaluationService`
- **Estado:** OPEN
- **Problema:** Se buscan strings literales del nombre de la dimensión en turns/código; si no están, se califica 0.0 sin llamar al LLM. Snapshots sin turn_id se descartan.
- **Causa:** Heurística de prueba temporal dejada como código de producción.
- **Cambio planeado:** Pasar turns y snapshots directamente a `<untrusted_candidate_input>` en el prompt del LLM juez.
- **Tests:** `test_evaluation.py`.
- **Resultado:** Pendiente.
- **Commit:** Pendiente.

### BLK-06 — Filtración de PII en evaluador
- **Estado:** OPEN
- **Problema:** `masked_candidate_id` usa `interview.candidate_email[:4]`.
- **Causa:** Cálculo incorrecto en lugar de usar ID enmascarado anónimo (`CAND-XXXX`).
- **Cambio planeado:** Generar `masked_candidate_id` a partir del UUID o ID de la sesión.
- **Tests:** `test_evaluation.py`.
- **Resultado:** Pendiente.
- **Commit:** Pendiente.

### BLK-07 — Contrato de sesión con `ws_url`
- **Estado:** OPEN
- **Problema:** `AnonymousCandidateSession` en backend no tiene `ws_url`, exigido por el contrato.
- **Causa:** Discrepancia entre `apps/api/src/api/schemas/invitations.py` y `packages/contracts/openapi.json`.
- **Cambio planeado:** Agregar `ws_url` en schema backend y poblarlo dinámicamente en `src/api/routers/sessions.py`.
- **Tests:** Endpoint `GET /sessions/verify`.
- **Resultado:** Pendiente.
- **Commit:** Pendiente.

### BLK-08 — Integración de Frontend
- **Estado:** OPEN
- **Problema:** La rama local `develop` no contiene el código de la sala de entrevista, Monaco ni UI de evaluación.
- **Causa:** Cambios de Cristian no integrados en `develop`.
- **Cambio planeado:** Integración cuidadosa de frontend y contratos sin romper backend.
- **Tests:** Verificación E2E de interfaz.
- **Resultado:** Pendiente.
- **Commit:** Pendiente.

### BLK-09 — Corrutinas y tipado en Agent y Hints
- **Estado:** OPEN
- **Problema:** Awaits faltantes en `src/agent/service.py`, `AsyncGenerator` awaitado en `src/hints/service.py`, `int` en lugar de `UUID`.
- **Causa:** Desajustes de tipado e invocaciones asíncronas.
- **Cambio planeado:** Corregir awaits, tipos y llamadas a `ConnectionManager`.
- **Tests:** Mypy, `test_agent.py`, `test_hints.py`.
- **Resultado:** Pendiente.
- **Commit:** Pendiente.

### BLK-10 — Endpoint `GET /vacancies`
- **Estado:** OPEN
- **Problema:** Frontend consume `GET /vacancies`, inexistente en backend y contrato.
- **Causa:** Asumido en mocks de MSW sin desarrollo previo en backend.
- **Cambio planeado:** Implementar `GET /vacancies` filtrado por `organization_id` y documentar en contrato.
- **Tests:** `test_vacancies.py`.
- **Resultado:** Pendiente.
- **Commit:** Pendiente.

### BLK-11 — Tooling y automatización en Frontend
- **Estado:** OPEN
- **Problema:** `next lint` pide selección interactiva por falta de `.eslintrc.json`. Faltan scripts de test/typecheck en `package.json`.
- **Causa:** Configuración incompleta de Next.js 15.
- **Cambio planeado:** Añadir configuración no interactiva de linting y scripts estándar.
- **Tests:** `pnpm lint`, `pnpm typecheck`.
- **Resultado:** Pendiente.
- **Commit:** Pendiente.
