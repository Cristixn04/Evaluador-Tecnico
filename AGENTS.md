# Reglas de Colaboración para Asistentes de IA (AGENTS.md)

Este proyecto es un monorepo colaborativo desarrollado por:
- **Samuel:** Backend, IA y Arquitectura de Evaluación (`apps/api`) usando `opencode`.
- **Cristian:** Frontend, UX, Sala de Entrevista en tiempo real y Telemetría (`apps/web`) usando `Antigravity`.

Cualquier asistente de IA que trabaje en este repositorio DEBE seguir estas reglas de forma obligatoria:

---

## 1. Regla Sagrada de Contratos (`packages/contracts`)
- **NUNCA** modificar los archivos dentro de `packages/contracts/` (`openapi.json`, `types.generated.ts`) de forma unilateral.
- Cualquier cambio en la API debe ser discutido y aprobado por ambos compañeros antes de actualizar el contrato.
- El flujo de contratos es:
  1. Samuel propone un cambio de endpoint en FastAPI o borrador OpenAPI.
  2. Ambos acuerdan la estructura.
  3. Se ejecuta `make update-contracts` para regenerar los tipos TypeScript que consume Cristian.

---

## 2. Convención de Commits (Conventional Commits)
Formato obligatorio: `tipo(scope): descripción en imperativo y minúsculas sin punto final`

* **Tipos válidos:**
  - `feat`: Nueva funcionalidad.
  - `fix`: Corrección de bug.
  - `refactor`: Cambio interno sin alterar comportamiento.
  - `test`: Añadir o modificar tests.
  - `docs`: Documentación y ADRs.
  - `chore`: Tooling, scripts, dependencias.
  - `ci`: Pipelines de CI/CD.

* **Scopes obligatorios:**
  - `api`, `agent`, `eval`, `sandbox`, `problems`, `reports`, `db`, `web`, `ui`, `contracts`, `infra`.

* **Ejemplos:**
  - `feat(web): add Monaco editor with debounced snapshot emission`
  - `feat(api): add state machine with hybrid transition guards`
  - `fix(sandbox): enforce memory limit of 128MB`
  - `docs(adr): record decision on websocket over sse`

---

## 3. Estándares por Aplicación

### Backend (`apps/api` - Python 3.12 / FastAPI)
- Tipado estricto con **Pydantic v2** en todas las entradas y salidas.
- Usar `async/await` en routers y operaciones de I/O (base de datos, redis, llamadas a LLM).
- Los prompts hacia LLMs deben estar en archivos versionados (`prompts/vX/*.md`) y cargarse con identificador de versión.
- Nunca concatenar entradas no confiables del candidato en el system prompt; siempre encapsular en `<untrusted_candidate_input>`.
- Las pruebas se ejecutan con `pytest`.

### Frontend (`apps/web` - Next.js 15 / TypeScript)
- TypeScript estricto: cero uso de `any`.
- Estilos con **Tailwind CSS** y componentes basados en **shadcn/ui** y Radix UI.
- No hacer llamadas a la API sin tipado: consumir los tipos generados en `@evaluador/contracts`.
- Para desarrollo offline/independiente, utilizar **MSW (Mock Service Worker)** para simular respuestas de FastAPI.
- La sala de entrevista debe gestionar reconexiones de WebSocket sin perder el estado del candidato.

---

## 4. Filosofía del "Informe Defendible"
- Todo puntaje emitido por el agente debe estar respaldado por citas exactas de turnos de conversación, snapshots de código o resultados de tests.
- El evaluador **no ve datos personales** del candidato (nombre, edad, foto, género, universidad) para eliminar sesgos.
- La IA recomienda, pero **siempre hay un humano (Tech Lead / Reclutador)** como tomador de decisión final.
