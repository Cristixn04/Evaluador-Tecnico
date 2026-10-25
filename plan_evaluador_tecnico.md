# Evaluador-Tecnico — Plan Maestro S1 → S2

> Documento exclusivamente de planificación. No implica cambios de código.
> **Fuentes únicas:** (1) `plan_evaluador_tecnico.md` (v2.0) y (2) los requisitos de S1 y S2 escritos en el prompt de reorganización. No se adjuntó un texto oficial separado del Challenge; los requisitos de las secciones 2 y 3 son los del prompt, tal cual.
> **Convención de nombres:** "S1/S2" = entregas del Agent Challenge. "Sprint 0–6" y los IDs `S-xx` / `C-xx` = numeración del plan original. No son lo mismo.
> **Convención de estado:** "Marcado [x] en el plan" = el plan original lo marca como hecho, pero eso NO está verificado contra el código. "Planificado / estado de implementación no confirmado" = aparece solo como plan.

---

## 1. Contexto del proyecto

- **Problema:** las empresas tech, bootcamps y firmas de staffing en Colombia y LATAM filtran candidatos con procesos lentos y costosos (horas de Tech Leads). *(Sección de pitch del plan, P-02.)*
- **Objetivo:** agente de IA que hace la entrevista técnica inicial, propone un problema contextualizado, evalúa razonamiento y trayectoria de depuración, y entrega un informe defendible y auditable.
- **Qué hace el agente:** conduce una entrevista por chat escrito + editor de código a través de una máquina de estados `INTRO → PROBLEM → CLARIFY → DESIGN → CODING → PROBE → WRAPUP → EVALUATE`.
- **Arquitectura general:** FastAPI (backend) + Next.js 15 (frontend) + un único WebSocket bidireccional (ADR-0001) + LLM Gateway compatible con OpenAI (`base_url` configurable, actualmente Grok/xAI) + PostgreSQL 16 + Redis/ARQ (evaluación asíncrona) + `CodeRunnerInterface` (Judge0 con fallback).
- **Tecnologías principales:** Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2 + Alembic, Redis + ARQ, Judge0 CE, Jinja2 + WeasyPrint, TypeScript, Next.js 15, Tailwind, shadcn/ui, Monaco, Recharts, OpenAPI → `openapi-typescript` + MSW, Docker Compose, GitHub Actions.
- **Roles existentes:** Samuel = backend, motor del agente, evaluación LLM, sandbox (herramienta: `opencode`). Cristian = frontend, UX/UI, sala de entrevista, telemetría (herramienta: `Antigravity`). Revisión cruzada de PRs.

---

## 2. Requisitos oficiales del Challenge

### S1 (lista exacta)
1. Primera versión del agente funcionando end-to-end.
2. El input llega al agente.
3. Existe una llamada REAL a Grok usando la API proporcionada para el challenge.
4. El agente procesa el input siguiendo las instrucciones definidas.
5. El agente produce un resultado.
6. El repositorio es público.
7. El README explica claramente el problema y qué hace el proyecto.

### S2 (lista exacta)
1. S1 aprobado.
2. Al menos 3 herramientas reales utilizadas por el agente.
3. Manejo de errores.
4. 10 ejecuciones reales del agente.
5. Video de aproximadamente 2 minutos mostrando el agente funcionando.

> Qué NO define el Challenge según las fuentes: formato exacto de entrega, dónde/cómo se registran las 10 ejecuciones, qué cuenta como "herramienta" (¿function calling del LLM o componente invocado por el sistema?), criterios de "manejo de errores" aceptable. Ver sección 16.

---

## 3. Definición de Done de S1

### S1 obligatorio (cada ítem proviene de los requisitos oficiales)
- [ ] Un input real llega al sistema.
- [ ] El input llega al agente.
- [ ] El agente ejecuta el flujo definido por sus instrucciones (prompts).
- [ ] Se realiza una llamada REAL a Grok con la API del challenge (no mock, no MSW, no stub).
- [ ] Grok devuelve una respuesta válida y el agente la procesa.
- [ ] Se produce un resultado observable.
- [ ] El flujo completo puede demostrarse de punta a punta.
- [ ] Repositorio público.
- [ ] README explica el problema y qué hace el proyecto.

### S1 soporte (ayuda a lograr S1, no se evalúa por sí sola)
- [ ] API key de Grok en variables de entorno / configuración segura (ver sección 11). *Se incluye por decisión del plan (`pydantic-settings`) y por tu prompt; el Challenge no lo exige explícitamente.*
- [ ] No imprimir secretos en logs.
- [ ] Healthcheck y entorno local levantable con `just dev` (Sprint 0 / S-01).

### Trabajo posterior (no bloquea S1)
Todo lo listado en la sección 15.

---

## 4. Flujo End-to-End

### 4.1 Flujo mínimo de S1

```
Input  →  Sistema (API/WebSocket)  →  Agente (motor de estados + prompts)  →  LLM Gateway  →  Grok (real)  →  Procesamiento de respuesta  →  Resultado observable
```

El plan original define dos candidatos de flujo que ya tienen piezas marcadas [x]:

| Opción | Input | Piezas del plan involucradas | Observación |
|---|---|---|---|
| A. Entrevista | Mensaje del candidato por WebSocket | S-04 (gateway), S-09 (WebSocket + máquina de estados), S-10 (prompts), C-05/C-08 (sala y reconexión) | Es la definición de "agente" del plan: *"Agente de IA que realiza la entrevista técnica"*. |
| B. Parser de vacantes | Texto de vacante | S-04 (gateway), S-05 (parser → JSON Pydantic), C-03 (pantalla Crear Vacante) | Es una llamada LLM directa; más simple, menos "agente". |

**No definido en las fuentes proporcionadas:** cuál de las dos es el flujo S1. Se registra como decisión pendiente D-01. *(Recomendación mía, no de las fuentes: la opción A es la más fiel a la definición del producto; B puede servir como respaldo si A no está lista.)*

### 4.2 Evidencia de S1

| Tipo | Qué demostrar |
|---|---|
| Funcional | Una ejecución en vivo: input → resultado visible. Captura o grabación corta. |
| Técnica | Logs estructurados (sin secretos) que muestren el paso por cada componente del flujo; el código del flujo en el repo. |
| Uso real de Grok | Que la llamada salga al endpoint real configurado (`base_url` de xAI/challenge), con respuesta real no determinista; prueba: log de la request/response (sin key) o registro de tokens consumidos (el gateway ya prevé cálculo de tokens, S-04). Un test con mock NO cuenta. |
| Repositorio | URL pública verificable sin sesión iniciada; `.env` y secretos fuera del historial de git. |
| README | Secciones: problema, qué hace el proyecto, y cómo correrlo. *(Lo mínimo exigido es problema + qué hace; "cómo correrlo" es soporte.)* |

---

## 5. Definición de Done de S2

- [ ] S1 aprobado.
- [ ] Tool 1 real (ver 5.1).
- [ ] Tool 2 real.
- [ ] Tool 3 real.
- [ ] Las 3 herramientas son realmente usadas por el agente durante una ejecución.
- [ ] Manejo de errores implementado y demostrable (ver 5.2).
- [ ] 10 ejecuciones reales del agente.
- [ ] Evidencia de las 10 ejecuciones.
- [ ] Video de aproximadamente 2 minutos mostrando el agente funcionando.

*S2 soporte:* script o procedimiento para registrar ejecuciones (decisión pendiente D-05). *Posterior a S2:* todo lo de la sección 15.

### 5.1 Arquitectura de herramientas de S2

El plan original no usa la palabra "herramienta" ni define function calling del agente. Lo que sí tiene son componentes que pueden hacer de herramienta:

| Candidato | Origen en el plan | Estado según plan | ¿Llama a un servicio real? | Veredicto |
|---|---|---|---|---|
| Selector de problemas | S-06 (banco YAML, 12 escenarios), S-07 | Marcado [x] | Consulta a PostgreSQL real | Candidato fuerte (si se registra como herramienta que el agente invoca) |
| Ejecutor de código (`CodeRunnerInterface`) | S-08 (Judge0 con fallback) | Marcado [x] | Judge0 CE o fallback cloud; con runner local no está claro | Candidato fuerte; debe demostrarse contra Judge0/cloud real, no stub |
| Parser de vacantes | S-05 | Marcado [x] | Llama a Grok | Candidato, aunque es más un paso del flujo que del agente-entrevistador |
| Juez LLM con rúbrica | S-11 | Pendiente [ ] | Llama a LLM | Pertenece a Sprint 3; no recomendado para S2 salvo decisión explícita |
| Generador PDF | S-18 | Pendiente [ ] | WeasyPrint local | Sprint 4; no bloquea S2 |
| Persistencia de turnos/snapshots | S-09 / modelos S-02 | Marcado [x] | PostgreSQL | Es infraestructura, difícil de justificar como "herramienta" |

- **Ya existen (según el plan, sin verificar):** selector, ejecutor, parser.
- **Incompletas / sin confirmar:** que el agente las invoque como herramientas (no hay integración tool-calling descrita); que el ejecutor use un backend real.
- **Faltan:** nada confirmado como faltante para llegar a tres; falta el *cableado* agente → herramienta.
- **Necesarias para el flujo del agente:** selector (fase PROBLEM) y ejecutor (fase CODING) aparecen en el flujo de la entrevista; el parser pertenece al flujo del reclutador.
- **Pertenecen a S2:** una terna de las tres primeras filas. **Se puede dejar para después:** juez LLM, PDF, anti-cheat.
- **Decisión pendiente (D-02):** confirmar cuáles tres cuentan y si "uso por el agente" exige tool-calling del LLM o basta que el sistema las invoque dentro del flujo.

### 5.2 Manejo de errores en S2

Mecanismos ya previstos en el plan:

| Categoría | Mecanismo previsto | Origen |
|---|---|---|
| Errores de Grok/API | Timeouts y reintentos en el gateway | S-04 |
| Timeouts de herramienta | Timeout de CPU/memoria del runner | S-08 |
| Errores de infraestructura | Fallback de Judge0 a runner local/cloud; reconexión de WebSocket con restauración de estado | S-08, C-08 |
| Validación de input/respuesta | Validación estricta con Pydantic v2; salida JSON estructurada en el parser | Stack, S-05 |
| Errores en UI | Estados de carga, error y vacío (Definición de Hecho) | Sección 6 original |
| Errores del agente | Máquina de estados con transiciones controladas para evitar bucles infinitos | Stack |

Categorías del prompt **sin respaldo explícito** en el plan: respuestas inválidas de Grok más allá de la validación Pydantic, y errores de input del usuario con mensajes definidos. → "No definido en las fuentes proporcionadas." (D-03).

**Mínimo que S2 necesita realmente:** que al menos los casos *Grok no responde / timeout*, *herramienta falla* y *respuesta inválida* tengan comportamiento definido y se pueda mostrar uno en el video. *(Interpretación mía del requisito "manejo de errores", que el Challenge no detalla.)*

### 5.3 Evidencia de S2

| Qué | Cómo demostrarlo |
|---|---|
| 3 herramientas | Registro (log/trace) de una ejecución donde se vea cada herramienta invocada con su resultado real; mención en el video |
| Manejo de errores | Provocar un fallo controlado (p. ej. key inválida, timeout, herramienta caída) y mostrar la reacción del agente, en video y en un log |
| 10 ejecuciones reales | Tabla en el repo (`docs/` o README) con fecha, input, resultado, herramientas usadas, estado; logs asociados. NO cuentan los tests automatizados ni ejecuciones con mocks |
| End-to-end | Una de las ejecuciones grabada completa |
| Video ~2 min | Archivo/enlace; guion en la sección 13 |

---

## 6. Estado actual del proyecto

Todo proviene de los checkboxes del plan original; **ninguno está verificado contra código**.

### Marcado [x] en el plan (implementación no verificada)
- Sprint 0 completo (S-00A–C, C-00A–C).
- Sprint 1 completo (S-01 a S-05, C-01 a C-04), incluido gateway LLM y parser.
- Sprint 2 completo (S-06 a S-10, C-05 a C-08): banco de problemas, selector, `CodeRunnerInterface`, WebSocket + máquina de estados, prompts, sala de entrevista, snapshots, controles de fase, reconexión.
- C-09 y C-10 (resultados y panel de evidencia) marcados [x] aunque su backend (S-11) está pendiente → **probablemente construidos contra mocks**; no cuentan como funcionalidad real.

### Parcialmente implementado
No hay ítems marcados parcialmente. Sospechoso a verificar: los ítems [x] que dependen de otros pendientes (C-09/C-10, ver arriba).

### Pendiente [ ]
- S-11 a S-27, C-11 a C-23, P-01 a P-03.

### Planificado / estado no confirmado
- Que la llamada a Grok del gateway haya sido probada con la API real del challenge.
- Que el ejecutor funcione contra Judge0 real y no solo en local.

### No necesario para S1/S2
Sprints 3–6 completos (ver sección 15).

---

## 7. Matriz de trazabilidad S1/S2

| Requisito | S1/S2 | Funcionalidad técnica | Estado según fuentes | Evidencia requerida | Prioridad |
|---|---|---|---|---|---|
| Agente end-to-end | S1 | Flujo elegido (D-01): S-04 + S-09 + S-10 (o S-05) | [x] en plan, sin verificar | Ejecución en vivo | Crítica |
| Input llega al agente | S1 | Endpoint/WebSocket (S-09) o endpoint de parser | [x] en plan | Log del recorrido | Crítica |
| Llamada real a Grok | S1 | LLM Gateway `base_url` + key (S-04) | [x] en plan; llamada real no confirmada | Log sin secretos + respuesta real | Crítica |
| Procesamiento + resultado | S1 | Máquina de estados / validación Pydantic | [x] en plan | Resultado visible | Crítica |
| Repo público | S1 | Configuración de GitHub | No definido en las fuentes | URL abierta sin sesión | Crítica |
| README | S1 | `README.md` | Aparece en estructura; contenido no confirmado | README revisado | Crítica |
| API key segura | S1 soporte | `pydantic-settings`, `.env` fuera de git | Parcialmente previsto (S-01) | Revisión del historial de git | Alta |
| S1 aprobado | S2 | — | Pendiente | Confirmación | Bloqueante |
| 3 herramientas | S2 | Selector (S-07), Ejecutor (S-08), Parser (S-05) *(a decidir D-02)* | [x] en plan; cableado agente→tool no descrito | Trace de una ejecución | Crítica |
| Manejo de errores | S2 | S-04 reintentos, S-08 timeouts, C-08 reconexión | Parcialmente previsto | Fallo provocado en video/log | Crítica |
| 10 ejecuciones reales | S2 | Procedimiento de registro (D-05) | No definido en las fuentes | Tabla + logs | Crítica |
| Video ~2 min | S2 | Grabación + guion (sección 13) | Pendiente | Archivo/enlace | Crítica |

---

## 8. Backlog de implementación

### FASE 0 — Preparación
1. Verificar en el repo qué [x] del plan realmente funcionan (levantar con `just dev`, correr `just test`).
2. Confirmar acceso a la API de Grok del challenge y cargarla en variable de entorno.
3. Resolver D-01 (flujo S1) y D-02 (herramientas).

### FASE 1 — Cierre S1
1. Gateway LLM apuntando a Grok real (S-04).
2. Flujo elegido de punta a punta: input → agente → Grok → procesamiento → resultado.
   - Opción A: WebSocket mínimo con `INTRO → PROBLEM → CLARIFY` (S-09, S-10) y sala mínima de chat.
   - Opción B: endpoint del parser (S-05) con pantalla C-03.
3. Resultado visible en UI o en respuesta de API.
4. Hacer público el repositorio, revisar historial por secretos.
5. Redactar README (problema + qué hace + cómo correr).

### FASE 2 — Validación S1
1. Ejecución real documentada con evidencia (sección 4.2).
2. Checklist "S1 — READY TO SUBMIT" (sección 14).

### FASE 3 — Implementación S2
1. Cablear las 3 herramientas al agente (decisión D-02).
2. Manejo de errores mínimo definido (D-03) para Grok, herramientas y respuesta inválida.
3. Mecanismo de registro de ejecuciones (D-05).
4. Ejecutar las 10 ejecuciones reales.

### FASE 4 — Validación S2
1. Revisar que las 10 ejecuciones tengan evidencia y que ninguna sea mock.
2. Grabar video ~2 min según guion.
3. Checklist "S2 — READY TO SUBMIT".

### FASE 5 — Trabajo posterior
Ver sección 15.

---

## 9. Dependencias

```
Fase 0 (verificar estado, API key, D-01, D-02)
   ↓
S1 implementado (gateway → flujo → resultado)
   ↓
Repo público + README
   ↓
S1 validado
   ↓
S2: 3 herramientas cableadas
   ↓
Manejo de errores
   ↓
10 ejecuciones reales (+ registro)
   ↓
Video ~2 min
   ↓
Entrega S2
```

Dependencias adicionales del plan: la UI real depende de que los tipos de `packages/contracts` estén sincronizados (`just update-contracts`); la sala de entrevista depende del WebSocket (S-09); el ejecutor depende de Judge0 levantado (Docker Compose) o del fallback.

---

## 10. Estrategia de pruebas

Regla: **un test automatizado exitoso NO es una ejecución real del challenge.**

### S1
| Tipo | Qué probar |
|---|---|
| Automatizado | Gateway con mock de Grok (valida parsing, timeouts, reintentos); máquina de estados con transiciones; validación Pydantic |
| Manual | Ejecución real: Input → Agent → Grok → Output, mirando respuesta real |
| E2E | Recorrido completo desde la UI (o la API) hasta el resultado visible |
| Evidencia del challenge | Solo la ejecución manual/E2E real con Grok real |

### S2
| Tipo | Qué probar |
|---|---|
| Automatizado | Cada herramienta aislada; escenarios de error simulados (timeout, 5xx, JSON inválido) |
| Manual | Agent → Tool 1, Tool 2, Tool 3 contra servicios reales; fallo provocado real |
| E2E | Ejecución completa con las tres herramientas |
| Evidencia del challenge | Las 10 ejecuciones reales + video; los mocks de MSW/tests no cuentan |

El plan ya menciona Vitest, Playwright y cobertura ≥ 80% en `agent/` y `evaluation/` (S-24, C-17), pero esas son tareas de Sprint 5: **no bloquean S1/S2**.

---

## 11. Seguridad y configuración

Solo lo relevante a S1/S2:
- La API key de Grok **no entra al repositorio**: variables de entorno vía `pydantic-settings`.
- `.env` en `.gitignore`; se entrega un `.env.example` sin valores reales *(práctica estándar; no está literal en las fuentes)*.
- No imprimir secretos en logs (el plan usa logging estructurado, S-01).
- Separar configuración local y producción cuando corresponda (Docker Compose local; Vercel/VPS/Fly.io en Sprint 6, posterior).
- Un gestor de secretos dedicado: **no definido en las fuentes**; no se agrega.
- Si la key llegó a commitearse alguna vez, hay que rotarla; verificar historial antes de hacer público el repo.

---

## 12. Frontend + Backend

### Backend mínimo necesario
- FastAPI levantado, configuración y healthcheck (S-01).
- LLM Gateway con Grok real (S-04).
- Flujo del agente (S-09/S-10) o parser (S-05), según D-01.
- Para S2: selector, ejecutor y su integración con el agente.

### Frontend mínimo necesario
- Una pantalla donde se ingrese el input y se vea el resultado: sala de entrevista básica (C-05) u opción B (C-03). *(Lo mínimo exacto: ver D-01.)*
- Para S2: ver la ejecución de código y sus resultados (consola de tests de C-05).

### Integración E2E
- Frontend real conectado al backend real, **sin MSW** durante las ejecuciones que cuentan como evidencia. MSW (C-01) es para desarrollo.

### Funcionalidades frontend posteriores
C-11 (timeline player), C-12 (tabla comparativa), C-13 a C-20, C-21 a C-23; C-09/C-10 si dependen de la evaluación (Sprint 3).

> Si el tiempo apremia, una interfaz mínima o incluso llamadas directas al API pueden bastar para S1 **si el Challenge acepta input vía API**: no definido en las fuentes (D-06).

---

## 13. Demo final

### Demo S1 (guion práctico)
1. Mostrar el repo público y el README (problema + qué hace). ~20 s.
2. Escribir/enviar un input real en la UI (o API).
3. Mostrar que llega al agente (log/estado de fase).
4. Mostrar la respuesta del agente y, en logs, la llamada real a Grok (sin mostrar la key).
5. Mostrar el resultado final observable.

### Demo S2 (video ~2 min)
| Tiempo aprox. | Contenido |
|---|---|
| 0:00–0:15 | Qué es el proyecto, una frase |
| 0:15–0:45 | Ejecución end-to-end: input → agente → Grok → resultado |
| 0:45–1:25 | Las 3 herramientas siendo usadas (en logs/UI se ve cuál y con qué resultado) |
| 1:25–1:45 | Provocar un error y mostrar cómo lo maneja el agente |
| 1:45–2:00 | Mostrar la tabla de 10 ejecuciones reales y cierre |

---

## 14. Checklist final de entrega

### S1 — READY TO SUBMIT
- [ ] Input llega al sistema y al agente
- [ ] Flujo del agente se ejecuta según sus instrucciones
- [ ] Llamada REAL a Grok con la API del challenge (comprobada, no mock)
- [ ] Respuesta de Grok procesada
- [ ] Resultado observable producido
- [ ] Flujo demostrable de punta a punta
- [ ] Repositorio público (verificado sin sesión)
- [ ] README explica problema y qué hace el proyecto
- [ ] Sin API key en el repo ni en el historial

**S1: NOT READY** *(no se puede marcar READY sin verificar el código y las ejecuciones; las fuentes solo confirman planificación)*

### S2 — READY TO SUBMIT
- [ ] S1 aprobado
- [ ] Tool 1 real usada por el agente
- [ ] Tool 2 real usada por el agente
- [ ] Tool 3 real usada por el agente
- [ ] Manejo de errores implementado y demostrado
- [ ] 10 ejecuciones reales realizadas
- [ ] Evidencia de las 10 ejecuciones (tabla + logs)
- [ ] Video de ~2 minutos con el agente funcionando

**S2: NOT READY**

---

## 15. Roadmap posterior (no se elimina nada; no bloquea S1/S2)

- **Evaluación LLM y rúbrica:** S-11, S-12, S-13, S-15 (Sprint 3).
- **Pipeline asíncrono Redis + ARQ:** S-14.
- **Resultados avanzados / UX de evidencia:** C-11, C-12 (C-09 y C-10 ya marcados [x], revisar).
- **Anti-cheat cognitivo y defensa de prompt injection:** S-16, S-17, ADR-0004.
- **Informe PDF:** S-18, C-15, C-16.
- **Anonimización y Ley 1581:** S-19, S-20, C-14.
- **Telemetría de integridad:** C-13.
- **Calibración y fairness:** S-21, S-22, S-24.
- **Sandbox endurecido:** S-23 (red desactivada, 128 MB, 2 s, fork bombs).
- **E2E, accesibilidad, performance, micro-interacciones:** C-17 a C-20.
- **Despliegue y observabilidad:** S-25 a S-27, C-21.
- **Modo demo y pitch:** C-22, C-23, P-01 a P-03.
- **Post-MVP:** `pgvector` cuando el catálogo supere 100 problemas (ADR-0003).

---

## 16. Decisiones pendientes

| ID | Decisión | Por qué importa | Impacta S1/S2 | Responsable | Estado |
|---|---|---|---|---|---|
| D-01 | Flujo concreto de S1 (entrevista A vs parser B) | Define qué se implementa y demuestra | S1 | No definido en las fuentes | Abierta |
| D-02 | Qué 3 herramientas cuentan y si exige tool-calling del LLM | El plan no define tools del agente | S2 | No definido en las fuentes | Abierta |
| D-03 | Casos de error mínimos aceptables | El Challenge no detalla el criterio | S2 | No definido en las fuentes | Abierta |
| D-04 | Si Judge0/cloud real está disponible para las ejecuciones | Un runner local puede no ser "herramienta real" | S2 | Samuel (sandbox) *según el plan* | Abierta |
| D-05 | Cómo se registran y se entregan las 10 ejecuciones | Sin formato definido | S2 | No definido en las fuentes | Abierta |
| D-06 | Si el Challenge exige UI o basta API para el input | Afecta cuánto frontend se necesita | S1/S2 | No definido en las fuentes | Abierta |
| D-07 | Si el endpoint/key de Grok del challenge difiere de la xAI configurada | El gateway usa `base_url` configurable | S1 | Samuel (gateway) *según el plan* | Abierta |

---

# Anexos para la revisión

## A. Principales cambios respecto al documento original
1. Reordenado por entregables (S1 → S2 → posterior) en lugar de sprints semanales.
2. Los Sprints 3–6 pasan al roadmap posterior sin eliminar tareas.
3. Se separa requisito oficial de decisión técnica.
4. Se marca el estado [x] como "no verificado".
5. Se agregan checklists, matriz de trazabilidad, guion de demo y decisiones pendientes.

## B. Contradicciones y ambigüedades
- "Sprint 1/2" del plan vs "S1/S2" del Challenge: no son equivalentes; si coincidieran en contenido, no está declarado.
- Plan: "ejecuta tests reales" en Sprint 2 vs requisito S2 de "herramientas reales": no se aclara si Judge0 real fue probado. Prioridad: los requisitos oficiales.
- C-09/C-10 marcados [x] mientras S-11 está pendiente: evidencia de uso de mocks.
- El plan no define "herramientas del agente" ni function calling; el Challenge las exige. Prioridad: Challenge; se mantiene la arquitectura de componentes del plan.
- El plan fija Grok/xAI como proveedor; el Challenge habla de "la API proporcionada": puede coincidir o no (D-07).
- El plan prevé evaluación asíncrona con Redis/ARQ; no es necesaria para S1/S2.

## C. Resumen ejecutivo S1
Elegir el flujo (D-01), verificar que el gateway realmente llama a Grok con la API del challenge, hacer que un input recorra agente → Grok → resultado visible, hacer público el repo y escribir el README. Todo lo demás espera.

## D. Resumen ejecutivo S2
Con S1 validado: decidir y cablear tres herramientas reales al agente (candidatas: selector, ejecutor, parser), definir y demostrar manejo de errores, ejecutar y documentar 10 ejecuciones reales, y grabar el video de ~2 min con el guion de la sección 13.

## E. Checklists finales
Ver sección 14. Ambos estados: **NOT READY**.