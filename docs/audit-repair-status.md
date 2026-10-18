# Estado de Reparación y Estabilización (BLK-01 a BLK-11)

Documento vivo para registrar el diagnóstico, causas, cambios, validación y commits de cada bloqueador identificado en la auditoría maestra.

---

## Matriz de Estado

| ID | Bloqueador | Severidad | Estado | Tests Afectados | Commit Asociado |
|---|---|---|---|---|---|
| **BLK-01** | Routers desconectados en `main.py` | P0 | VERIFIED | `test_websocket.py`, `test_trajectory.py`, `test_concurrency.py` | `fix(api): mount interview lifecycle routers` |
| **BLK-02** | Funciones faltantes en `prompts.py` | P0 | VERIFIED | `test_prompts.py`, `test_agent.py`, `test_hints_integration.py` | `fix(llm): restore prompt loading API` |
| **BLK-03** | Falta de aislamiento en DB y fixtures | P0 | FIXED | `test_auth.py`, `test_problem_selector.py`, `test_evaluation.py` | `cff15ca fix(tests): isolate backend database fixtures` |
| **BLK-04** | Migración Alembic incompleta e integridad FK | P0 | VERIFIED | `test_alembic.py` | `fix(db): repair evaluation migration integrity` |
| **BLK-05** | Pseudo-lógica de evaluación basada en texto literal | P1 | OPEN | `test_evaluation.py` | `fix(evaluation): repair defensible judge evidence flow` |
| **BLK-06** | Filtración de PII (`candidate_email[:4]`) | P1 | OPEN | `test_evaluation.py` | `fix(security): remove candidate PII from evaluation` |
| **BLK-07** | Incompatibilidad de contrato `ws_url` | P1 | VERIFIED | `test_sessions.py`, `test_concurrency.py`, `test_websocket.py` | `fix(api): align candidate session websocket contract` |
| **BLK-08** | Desconexión Frontend develop local vs remoto | P1 | OPEN | Integración Web / E2E | `feat(web): integrate interview frontend` |
| **BLK-09** | Errores Mypy y corrutinas sin await en Agent/Hints | P2 | VERIFIED | `test_agent.py`, `test_hints.py`, `test_hints_integration.py` | `fix(agent): repair async execution and typing` |
| **BLK-10** | Inexistencia de endpoint `GET /vacancies` | P2 | OPEN | Dashboard Reclutador / Contratos | `feat(vacancies): add organization-scoped vacancy listing` |
| **BLK-11** | Tooling Frontend (lint interactivo, scripts) | P3 | OPEN | `pnpm lint`, `pnpm test` | `chore(web): configure linting and test scripts` |

---

## Detalle por Bloqueador

### BLK-01 — Routers no montados en `main.py`
- **Estado:** VERIFIED
- **Problema:** `invitations`, `sessions`, `websocket` y `trajectory` no estaban incluidos en `apps/api/src/main.py`.
- **Causa:** Omisión de `app.include_router` para los nuevos módulos en el punto de entrada de FastAPI.
- **Cambio realizado:** Montados `invitations_router`, `sessions_router`, `websocket_router` y `trajectory_router` con sus prefijos canónicos. Corregido commit en transiciones de fase y sincronizados timestamps y commits en tests de trayectoria.
- **Tests:** `test_websocket.py` (14 passed), `test_trajectory.py` (11 passed), `test_concurrency.py` (2 passed). Verificación exitosa de endpoints en `app.openapi()`.
- **Resultado:** VERIFIED.
- **Commit:** `fix(api): mount interview lifecycle routers`.

### BLK-02 — API de prompts en `src/llm/prompts.py`
- **Estado:** VERIFIED
- **Problema:** Falta `load_hints()`, `load_phase_instructions()`, `get_active_prompt_version()`.
- **Causa:** Archivo quedó incompleto tras la reestructuración de prompts v2.
- **Cambio realizado:** Implementadas `load_hints`, `load_phase_instructions`, `get_active_prompt_version` y extractor modular de secciones markdown con lru_cache.
- **Tests:** `test_prompts.py` (23 tests passed), `test_agent.py` (8 tests passed).
- **Resultado:** VERIFIED.
- **Commit:** `fix(llm): restore prompt loading API`.

### BLK-03 — Aislamiento de base de datos en tests
- **Estado:** FIXED
- **Problema:** Basura residual en tablas (`users`, `problems`, `vacancies`) genera colisión de llaves únicas. `sample_interview` no incluye `vacancy_id`.
- **Causa:** `db_session` fixture no aísla transacciones con rollback o truncado. Fixture de entrevista viola NOT NULL en `vacancy_id`.
- **Cambio realizado:** Implementada fixture autouse `isolate_database_and_engine` con recreación/truncado por test y reseteo de engine asyncpg. Corregidas fixtures con `vacancy_id` y `default` de `Evaluation.created_at`.
- **Tests:** `test_auth.py`, `test_problem_selector.py`, `test_vacancies.py`, `test_evaluation.py`.
- **Resultado:** 32 tests passed 100% reproducibles consecutivamente.
- **Commit:** `cff15ca fix(tests): isolate backend database fixtures`.

### BLK-04 — Alembic e integridad de tablas de evaluación
- **Estado:** VERIFIED
- **Problema:** Migración `adding_evaluation_tables.py` omitía FKs en cascada e índices, y creaba columna `uuid` espuria. `test_alembic.py` no validaba las nuevas tablas ni el grafo completo.
- **Causa:** DDL incompleto y desactualización del conjunto esperado de tablas y revisiones en los tests.
- **Cambio realizado:** Corregida migración `adding_evaluation_tables.py` agregando FKs a `interviews`, `evaluations`, `turns`, `snapshots`, eliminando columna `uuid` espuria e indexando llaves foráneas. Actualizado `test_alembic.py` para validar todo el grafo hasta el head `merge_evaluation_invitations` y las 12 tablas públicas resultantes tanto en upgrade como downgrade a base.
- **Tests:** `test_alembic.py` (2 passed: registro de revisiones y upgrade/downgrade desde cero).
- **Resultado:** VERIFIED.
- **Commit:** `fix(db): repair evaluation migration integrity`.

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
- **Estado:** VERIFIED
- **Problema:** `AnonymousCandidateSession` en backend no tenía `ws_url`, exigido por el frontend y contrato de sala en vivo.
- **Causa:** Discrepancia entre `apps/api/src/api/schemas/invitations.py` y `packages/contracts/openapi.json`.
- **Cambio realizado:** Añadido campo `ws_url` al schema `AnonymousCandidateSession` y función canónica `_build_ws_url(request, interview_id)` en `src/api/routers/sessions.py` que soporta proxies TLS (`x-forwarded-proto`), puertos y hosts dinámicos.
- **Tests:** `test_sessions.py` (flujo HTTP completo POST invitación -> GET verify), `test_concurrency.py`, `test_websocket.py`.
- **Resultado:** VERIFIED.
- **Commit:** `fix(api): align candidate session websocket contract`.

### BLK-08 — Integración de Frontend
- **Estado:** OPEN
- **Problema:** La rama local `develop` no contiene el código de la sala de entrevista, Monaco ni UI de evaluación.
- **Causa:** Cambios de Cristian no integrados en `develop`.
- **Cambio planeado:** Integración cuidadosa de frontend y contratos sin romper backend.
- **Tests:** Verificación E2E de interfaz.
- **Resultado:** Pendiente.
- **Commit:** Pendiente.

### BLK-09 — Corrutinas y tipado en Agent y Hints
- **Estado:** VERIFIED
- **Problema:** Awaits faltantes en `src/agent/service.py`, `AsyncGenerator` awaitado en `src/hints/service.py`, `int` en lugar de `UUID`, `selectinload` ausente en lazy relationships que causaban `MissingGreenlet`, y auto-deadlock en reserva de hint por sesión concurrente.
- **Causa:** Desajustes de tipado, invocaciones asíncronas incorrectas e impedancia ORM async.
- **Cambio realizado:** Tipado estricto `Role` / `UUID`, corrutinas debidamente awaitadas en `AgentService`, instanciación directa del cliente LLM en `hints/service.py`, eager loading con `selectinload` para `turns` y `snapshots`, resolución de deadlock mediante reutilización de sesión ORM y mitigación de syntax en interval SQL.
- **Tests:** `test_agent.py` (8 passed), `test_hints.py` (20 passed), `test_hints_integration.py` (2 passed). Mypy y Ruff limpios (0 errores).
- **Resultado:** VERIFIED.
- **Commit:** `fix(agent): repair async execution and typing`.

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
