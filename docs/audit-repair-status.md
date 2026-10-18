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
| **BLK-05** | Pseudo-lógica de evaluación basada en texto literal | P1 | VERIFIED | `test_evaluation.py` | `fix(evaluation): repair defensible judge evidence flow` |
| **BLK-06** | Filtración de PII (`candidate_email[:4]`) | P1 | VERIFIED | `test_evaluation.py` | `fix(security): enforce evaluation tenant isolation` |
| **BLK-07** | Incompatibilidad de contrato `ws_url` | P1 | VERIFIED | `test_sessions.py`, `test_concurrency.py`, `test_websocket.py` | `fix(api): align candidate session websocket contract` |
| **BLK-08** | Desconexión Frontend develop local vs remoto | P1 | VERIFIED | `pnpm build:web`, `pnpm lint:web`, `pnpm typecheck:web` | `feat(web): integrate interview frontend` |
| **BLK-09** | Errores Mypy y corrutinas sin await en Agent/Hints | P2 | VERIFIED | `test_agent.py`, `test_hints.py`, `test_hints_integration.py` | `fix(agent): repair async execution and typing` |
| **BLK-10** | Inexistencia de endpoint `GET /vacancies` | P2 | VERIFIED | `test_vacancies.py` | `feat(vacancies): add organization-scoped vacancy listing` |
| **BLK-11** | Tooling Frontend (lint interactivo, scripts) | P3 | VERIFIED | `pnpm lint`, `pnpm typecheck`, `pnpm test` | `chore(web): configure linting and test scripts` |

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
- **Estado:** VERIFIED
- **Problema:** Se buscaban strings literales del nombre de la dimensión en turns/código; si no estaban, se calificaba con heurísticas artificiales. Snapshots con `turn_id == None` se descartaban. No existía idempotencia en `GET /interviews/{id}/evaluation`.
- **Causa:** Pseudo-lógica de evaluación con placeholders y filtrado incorrecto de evidencias de código.
- **Cambio realizado:** Eliminada por completo la búsqueda literal de dimensiones. Turns y snapshots son compilados y encapsulados en `<untrusted_candidate_input>`. El juez LLM genera las puntuaciones y cita evidencias con IDs reales. Las evidencias de snapshots (`snapshot_id`) son preservadas sin descartar. Se implementó idempotencia en `evaluate`: si la evaluación ya existe en base de datos, se retorna directamente sin re-evaluar ni duplicar registros.
- **Tests:** `test_evaluation.py` (13 tests passed: 5 dimensiones, idempotencia, evidencia de snapshots, lectura y persistencia).
- **Resultado:** VERIFIED.
- **Commit:** `fix(evaluation): repair defensible judge evidence flow`.

### BLK-06 — Filtración de PII y aislamiento Multi-Tenant en evaluador
- **Estado:** VERIFIED
- **Problema:** `masked_candidate_id` filtraba el email (`interview.candidate_email[:4]`). No había validación multi-tenant en `GET /interviews/{id}/evaluation` ni en `GET /interviews/{id}/trajectory`.
- **Causa:** Cálculo reversible de identidad del candidato y ausencia de verificación `principal.organization_id == vacancy.organization_id`.
- **Cambio realizado:** Sustituido el cálculo por un identificador opaco no reversible `CAND-XXXX` derivado del UUID de la entrevista (consistente con el contrato y sesiones). Se validó que el prompt del LLM juez no incluya datos de contacto del candidato. Se incorporó verificación estricta multi-tenant en los routers de evaluación y trayectoria, retornando 404 ante intentos de acceso cruzado entre organizaciones.
- **Tests:** `test_evaluation.py` (`test_evaluacion_blind_to_pii`, `test_evaluacion_multi_tenant_isolation`), `test_trajectory.py` (11 tests passed).
- **Resultado:** VERIFIED.
- **Commit:** `fix(security): enforce evaluation tenant isolation`.

### BLK-07 — Contrato de sesión con `ws_url`
- **Estado:** VERIFIED
- **Problema:** `AnonymousCandidateSession` en backend no tenía `ws_url`, exigido por el frontend y contrato de sala en vivo.
- **Causa:** Discrepancia entre `apps/api/src/api/schemas/invitations.py` y `packages/contracts/openapi.json`.
- **Cambio realizado:** Añadido campo `ws_url` al schema `AnonymousCandidateSession` y función canónica `_build_ws_url(request, interview_id)` en `src/api/routers/sessions.py` que soporta proxies TLS (`x-forwarded-proto`), puertos y hosts dinámicos.
- **Tests:** `test_sessions.py` (flujo HTTP completo POST invitación -> GET verify), `test_concurrency.py`, `test_websocket.py`.
- **Resultado:** VERIFIED.
- **Commit:** `fix(api): align candidate session websocket contract`.

### BLK-08 — Integración de Frontend
- **Estado:** VERIFIED
- **Problema:** La rama local `develop` no contenía el código de la sala de entrevista, Monaco, consola de tests, ni UI de evaluación y radar de competencias.
- **Causa:** Cambios de Cristian desarrollados en `origin/dev_frontend` no integrados en `develop`.
- **Cambio realizado:** Se integraron selectivamente los componentes, páginas, hooks (`use-interview-socket`, `use-debounced-snapshot`) y cliente de API de `origin/dev_frontend`. Se corrigieron entidades no escapadas en JSX y se sincronizó con el contrato OpenAPI estabilizado. Se preservó la capacidad de desacoplar MSW mediante `NEXT_PUBLIC_ENABLE_MOCKS=false` para conectar directamente contra FastAPI.
- **Tests:** `pnpm build:web` (9/9 páginas estáticas y dinámicas compiladas exitosamente), `pnpm typecheck:web` (0 errores de TypeScript).
- **Resultado:** VERIFIED.
- **Commit:** `feat(web): integrate interview frontend`.

### BLK-09 — Corrutinas y tipado en Agent y Hints
- **Estado:** VERIFIED
- **Problema:** Awaits faltantes en `src/agent/service.py`, `AsyncGenerator` awaitado en `src/hints/service.py`, `int` en lugar de `UUID`, `selectinload` ausente en lazy relationships que causaban `MissingGreenlet`, y auto-deadlock en reserva de hint por sesión concurrente.
- **Causa:** Desajustes de tipado, invocaciones asíncronas incorrectas e impedancia ORM async.
- **Cambio realizado:** Tipado estricto `Role` / `UUID`, corrutinas debidamente awaitadas en `AgentService`, instanciación directa del cliente LLM en `hints/service.py`, eager loading con `selectinload` para `turns` y `snapshots`, resolución de deadlock mediante reutilización de sesión ORM y mitigación de syntax en interval SQL.
- **Tests:** `test_agent.py` (8 passed), `test_hints.py` (20 passed), `test_hints_integration.py` (2 passed). Mypy y Ruff limpios (0 errores).
- **Resultado:** VERIFIED.
- **Commit:** `fix(agent): repair async execution and typing`.

### BLK-10 — Endpoint `GET /vacancies`
- **Estado:** VERIFIED
- **Problema:** Frontend consume `GET /vacancies`, inexistente en backend.
- **Causa:** No se había implementado el endpoint de listado en `apps/api/src/api/routers/vacancies.py`.
- **Cambio realizado:** Implementado `GET /vacancies` filtrado estrictamente por `principal.organization_id`, ordenado cronológicamente descendente y con serialización robusta `_to_response` que provee defaults seguros para campos opcionales/nulos.
- **Tests:** `test_vacancies.py` (8 passed: autenticación requerida, aislamiento multi-tenant estricto entre organizaciones).
- **Resultado:** VERIFIED.
- **Commit:** `feat(vacancies): add organization-scoped vacancy listing`.

### BLK-11 — Tooling y automatización en Frontend
- **Estado:** VERIFIED
- **Problema:** `next lint` pedía selección interactiva por falta de configuración de ESLint. Faltaban scripts estándar de lint, typecheck y test en `package.json`.
- **Causa:** Configuración incompleta en Next.js 15 y dependencias de linting faltantes en `apps/web`.
- **Cambio realizado:** Creado `.eslintrc.json`, instalado `eslint` y `eslint-config-next`, aprobada la ejecución de scripts en `pnpm-workspace.yaml`, agregados scripts canónicos `"lint:web"`, `"typecheck:web"`, `"test:web"` tanto en root como en `apps/web/package.json`, y provisto `.env.example` documentando `NEXT_PUBLIC_ENABLE_MOCKS=false`.
- **Tests:** `pnpm lint:web` (0 warnings, 0 errors), `pnpm typecheck:web` (0 errors), `pnpm test:web`.
- **Resultado:** VERIFIED.
- **Commit:** `chore(web): configure linting and test scripts`.
