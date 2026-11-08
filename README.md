# Evaluador Técnico

**Plataforma de entrevistas técnicas en tiempo real asistidas por un agente de inteligencia artificial**, diseñada para evaluar el razonamiento algorítmico, la calidad de código y la comunicación técnica de candidatos mediante interacción socrática y evidencia verificable.

---

## 1. Nombre del proyecto

`Evaluador Técnico` es una plataforma colaborativa y automatizada orientada a la conducción, supervisión y evaluación de entrevistas técnicas en vivo, combinando un agente conversacional interactivo, ejecución de código en sandbox y un motor de evaluación objetiva post-entrevista.

---

## 2. Problema que resuelve

Las entrevistas técnicas tradicionales presentan fricciones críticas tanto para los evaluadores como para los candidatos:

1. **Subjetividad y sesgos cognitivos:** Los evaluadores humanos suelen verse influenciados por sesgos inconscientes (afinidad personal, procedencia académica o características demográficas) y por variabilidad en los criterios de corrección.
2. **Consumo excesivo de tiempo de ingeniería senior:** Cada entrevista técnica en vivo requiere entre 1 y 2 horas de dedicación exclusiva de desarrolladores senior, lo que genera cuellos de botella en los procesos de selección y desvía recursos del desarrollo de producto.
3. **Falsos positivos y memorización de ejercicios:** Las pruebas estáticas tipo LeetCode premian la memorización de algoritmos en lugar del proceso de pensamiento, la capacidad de depuración, la adaptación a pistas y la comunicación técnica.
4. **Falta de evidencia auditable:** Tras una entrevista convencional, los reportes suelen basarse en notas fragmentadas y percepciones subjetivas, careciendo de un registro trazable de cómo el candidato llegó a la solución.
5. **Cumplimiento de privacidad:** El manejo de información personal de candidatos requiere estándares estrictos de protección de datos (como la Ley 1581 de 2012 de Protección de Datos Personales en Colombia).

### Solución propuesta

Evaluador Técnico resuelve estas dificultades a través de:
- **Acompañamiento socrático:** El agente no califica en vivo ni entrega soluciones directas; actúa como un entrevistador técnico que aclara requerimientos, formula preguntas de diseño y guía mediante pistas progresivas.
- **Recopilación continua de evidencia:** El sistema registra de manera cronológica cada turno de conversación, cada intento de ejecución en el sandbox y snapshots de código periódicos con marcas de tiempo.
- **Evaluación a ciegas y defendible:** Al concluir la entrevista, un evaluador de IA independiente analiza la transcripción completa de forma anónima (usando identificadores enmascarados como `CAND-XXXX` y sin acceso a datos personales), calificando 5 dimensiones objetivas con citas textuales y evidencia verificable.
- **Supervisión humana final:** El sistema genera un dictamen inicial y un reporte auditable en PDF, pero siempre preserva la decisión final en manos de un revisor humano (*Human-in-the-Loop*).

---

## 3. Características principales

Las siguientes capacidades han sido comprobadas e implementadas en el código del repositorio:

- **Entrevista técnica en tiempo real:** Comunicación bidireccional continua mediante WebSockets (`/ws/interview/{id}`), sincronizando chat, estado del código, ejecuciones y transiciones de fase sin recargas.
- **Agente conversacional guiado por fases:** Modelo de lenguaje adaptado con prompts versionados que asume un rol socrático y colaborativo según la fase activa.
- **Selección determinista de problemas:** Carga de enunciados desde catálogo versionado en YAML (`problems/`), categorizados por rol (Backend, Frontend, etc.) y nivel de seniority (Junior, Mid, Senior).
- **Ejecución aislada de código (Sandbox):** Servicio de ejecución conectado a Judge0 CE / contenedores aislados con límites estrictos de CPU (2.0s) y memoria (128 MB), retornando stdout, stderr y resultados de pruebas unitarias.
- **Generación de pistas adaptativas multinivel:** Tres niveles progresivos de asistencia (1: Conceptual/Sintáctica, 2: Enfoque algorítmico, 3: Esqueleto de código y casos de borde) con bloqueos atómicos en Redis para prevenir peticiones redundantes.
- **Persistencia de trayectoria completa:** Almacenamiento transaccional en PostgreSQL de todos los turnos de diálogo (`turns`), snapshots periódicos de código (`code_snapshots`) y ejecuciones en sandbox (`sandbox_runs`).
- **Control formal de fases (Máquina de 8 estados):** Ciclo de vida gobernado en el servidor con transiciones unidireccionales validadas: `INTRO` $\to$ `PROBLEM` $\to$ `CLARIFY` $\to$ `DESIGN` $\to$ `CODING` $\to$ `PROBE` $\to$ `WRAPUP` $\to$ `EVALUATE`.
- **Cierre formal de entrevista:** Flujo interactivo en fase `WRAPUP` con modal de confirmación, congelamiento de la interfaz de desarrollo, transición a `EVALUATE` y actualización de estado a `EVALUATED`.
- **Evaluación automática desacoplada:** Al alcanzar la fase `EVALUATE`, el backend programa una tarea asíncrona en segundo plano que ejecuta el servicio de evaluación con deduplicación concurrente por bloqueo y transacciones aisladas.
- **Mecanismo de fallback y revisión humana:** Si la evidencia es insuficiente, el LLM excede el tiempo límite o el formato es inconsistente, el sistema marca `needs_human_review: true` con justificación explícita.
- **Telemetría estructurada observable:** Registro unificado de invocaciones de herramientas con marcas `[AGENT_TOOL_CALL:START]`, `[AGENT_TOOL_CALL:SUCCESS]` y `[AGENT_TOOL_CALL:ERROR]`, con sanitización automática de datos sensibles.

---

## 4. Arquitectura del sistema

El proyecto está estructurado como un monorepo que separa claramente la interfaz de usuario, la API central y los contratos compartidos.

```mermaid
flowchart TD
    subgraph Frontend ["Frontend (apps/web - Next.js 15)"]
        UI["Interfaz Candidato (React 19 / Monaco Editor)"]
        WSClient["WebSocket Hook & State Sync"]
    end

    subgraph Backend ["Backend (apps/api - FastAPI)"]
        APIRouter["FastAPI Endpoints (HTTP REST)"]
        WSManager["WebSocket ConnectionManager & Dispatcher"]

        subgraph DomainServices ["Servicios de Dominio"]
            StateMachine["Gestor de Transición de Fases"]
            AgentOrchestrator["Orquestador del Agente (LLM Client)"]
            EvaluationService["Servicio de Evaluación & Fallbacks"]
        end

        subgraph S2Tools ["Herramientas Instrumentadas (S2)"]
            T1["ProblemSelectorTool"]
            T2["CodeExecutionSandboxTool"]
            T3["AdaptiveHintGeneratorTool"]
        end

        TelemetryModule["Módulo de Telemetría (telemetry.py)"]
    end

    subgraph Storage ["Infraestructura & Persistencia"]
        PG[("PostgreSQL 16\n(Entrevistas, Turnos, Snapshots, Evaluaciones)")]
        RD[("Redis 7\n(Tokens WS Efímeros, Hint Locks)")]
        J0["Sandbox Execution (Judge0 CE / Docker)"]
        LLMGateway["LLM API Gateway (Grok / OpenAI Compatible)"]
    end

    UI <-->|HTTP REST / SSE| APIRouter
    WSClient <-->|WebSocket Bidireccional| WSManager

    WSManager --> StateMachine
    WSManager --> AgentOrchestrator
    APIRouter --> EvaluationService

    AgentOrchestrator --> LLMGateway
    EvaluationService --> LLMGateway

    AgentOrchestrator --> T1
    AgentOrchestrator --> T2
    AgentOrchestrator --> T3

    T1 -.-> TelemetryModule
    T2 -.-> TelemetryModule
    T3 -.-> TelemetryModule

    T1 -->|Lee Catálogo YAML| FS["Directorio problems/"]
    T2 -->|Ejecuta Código en Sandbox| J0
    T3 -->|Verifica Locks & Estado| RD

    StateMachine --> PG
    AgentOrchestrator --> PG
    EvaluationService --> PG
    WSManager --> RD
```

---

## 5. Flujo de una entrevista

El ciclo de vida de la entrevista técnica sigue una máquina de estados estricta de 8 fases. Las transiciones son validadas en el backend y notificadas al frontend mediante eventos `phase_changed`:

```text
[INTRO] ──> [PROBLEM] ──> [CLARIFY] ──> [DESIGN] ──> [CODING] ──> [PROBE] ──> [WRAPUP] ──> [EVALUATE]
```

### Descripción paso a paso

1. **`INTRO` (Bienvenida y consentimiento):**
   - El candidato accede a la sala de entrevista mediante un token de acceso seguro.
   - Se presenta el propósito de la prueba y se solicita la confirmación de consentimiento informado para el registro de telemetría y transcripción de acuerdo con la política de privacidad.
   - Al aceptar, se inicia la sesión y se transiciona a `PROBLEM`.
2. **`PROBLEM` (Presentación del enunciado):**
   - El agente selecciona el problema asignado a través de `ProblemSelectorTool` y lo presenta en el panel correspondiente.
   - El candidato revisa el enunciado, los ejemplos y las restricciones técnicas.
3. **`CLARIFY` (Aclaración de dudas y requerimientos):**
   - El candidato interactúa con el agente para formular preguntas sobre supuestos, límites de datos de entrada y comportamiento ante entradas vacías o inválidas.
   - El agente responde de forma orientativa sin revelar la solución.
4. **`DESIGN` (Discusión de arquitectura y enfoque algorítmico):**
   - Antes de escribir código definitivo, el candidato explica su propuesta de solución, estructuras de datos a utilizar y análisis preliminar de complejidad temporal y espacial ($O(n)$, $O(1)$, etc.).
5. **`CODING` (Implementación en el editor):**
   - Se habilita el editor Monaco. El candidato escribe su solución en Python.
   - El frontend emite snapshots de código periódicos con temporizador de debounce (1.5s).
   - El candidato puede ejecutar pruebas en el sandbox mediante `CodeExecutionSandboxTool` o solicitar asistencia escalonada con `AdaptiveHintGeneratorTool`.
6. **`PROBE` (Preguntas de profundización y pruebas de estrés):**
   - El agente examina la implementación del candidato y formula preguntas sobre posibles casos de borde, optimizaciones de memoria o cómo escalaría el algoritmo ante grandes volúmenes de datos.
7. **`WRAPUP` (Conclusión del ejercicio):**
   - El agente invita al candidato a realizar un resumen final de su solución.
   - La interfaz activa el botón **"Entregar y Finalizar Entrevista"** en la barra superior.
   - El candidato pulsa el botón, confirma su entrega formal en el modal y se congela el entorno de edición.
8. **`EVALUATE` (Evaluación automática y generación de reporte):**
   - El servidor registra la fase `EVALUATE` y actualiza el estado a `EVALUATED`.
   - Se despacha una tarea en segundo plano que invoca a `EvaluationService`.
   - Se genera la evaluación con las 5 dimensiones técnicas y se produce el reporte auditable en PDF.

---

## 6. El agente técnico (S1 & S2)

### Orquestación híbrida y Function Calling con Grok
El agente ([`apps/api/src/agent/service.py`](apps/api/src/agent/service.py)) se conecta en tiempo real con el proveedor LLM compatible con OpenAI (`https://api.reto.pltk.mx/v1`, modelo `grok-4.6`) a través de [`OpenAICompatibleClient`](apps/api/src/llm/openai_compatible.py), soportando:
- **Conversación multi-turno con memoria persistente (S1):** Recupera los turnos recientes de PostgreSQL (`turns`), conserva el contexto conversacional entre turnos y fases, y persiste métricas reales de tokens (`prompt_tokens`, `completion_tokens`, `total_tokens`) y costo en USD en la tabla `llm_usage_records`.
- **Function Calling acotado y autónomo (S2):** El agente expone 3 herramientas tipadas mediante JSON Schema (`OPENAI_TOOLS_SCHEMA` en [`apps/api/src/agent/tools.py`](apps/api/src/agent/tools.py)). Cuando `grok-4.6` decide invocar una herramienta (`finish_reason="tool_calls"`), [`AgentToolRuntime`](apps/api/src/agent/tools.py) valida los argumentos con Pydantic v2 (`extra="forbid"`), ejecuta el servicio de dominio, devuelve el resultado estructurado mediante un mensaje `role="tool"` con su `tool_call_id`, y el modelo sintetiza la respuesta final para el candidato dentro de un bucle acotado (`MAX_TOOL_ITERATIONS = 3`, `MAX_TOOL_CALLS_PER_TURN = 4`).

### Construcción de prompts y aislamiento de seguridad
Los prompts del sistema están versionados en `apps/api/prompts/` (`v1/` y `v2/`):
- `interview_agent.md` y `phases/*.md`: Definen el tono socrático, el rol pedagógico-evaluador y las directrices por fase.
- **Aislamiento de entradas del candidato (S-17):** Todo contenido proveniente del candidato (mensajes de chat, fragmentos de código) se sanitiza y encapsula dentro de etiquetas `<untrusted_candidate_input>` mediante [`src/llm/sanitizer.py`](apps/api/src/llm/sanitizer.py) antes de enviarse al modelo.
- **Vinculación inmutable al contexto de sesión y organización:** `AgentToolRuntime` bloquea explícitamente (`CONTEXT_SECURITY_VIOLATION`) cualquier intento de inyectar o sobrescribir `interview_id`, `organization_id`, `user_id` o `candidate_id` en los argumentos de una herramienta.

---

## 7. Herramientas del agente (Sprint 2 — Function Calling)

Las 3 herramientas expuestas a Grok en [`apps/api/src/agent/tools.py`](apps/api/src/agent/tools.py) reutilizan los servicios de dominio del backend sin duplicar lógica:

### 1. `problem_selector` (`ProblemSelectorTool`)
- **Implementación:** [`apps/api/src/agent/tools.py`](apps/api/src/agent/tools.py) $\to$ [`apps/api/src/problems/selector.py`](apps/api/src/problems/selector.py) y [`apps/api/src/problems/loader.py`](apps/api/src/problems/loader.py).
- **Esquema de entrada (`ProblemSelectorArgs`):** `action` (`"inspect_assigned_problem"` | `"search_catalog"`), `problem_id`, `seniority` (`"junior"` | `"mid"` | `"senior"` | `"lead"`), `language` (`"python"` | `"javascript"` | `"sql"`), `skills`.
- **Propósito:** Inspeccionar el enunciado, límites de tiempo/memoria (`timeout_ms`, `memory_mb`) y casos de prueba del problema asignado o seleccionar problemas compatibles del catálogo YAML (`apps/api/src/problems/catalog/`).
- **Resiliencia:** Reintento automático acotado (`MAX_TOOL_RETRIES = 1`) ante fallos transitorios de lectura y fallback determinista al catálogo en disco.

### 2. `code_execution_sandbox` (`CodeExecutionSandboxTool`)
- **Implementación:** [`apps/api/src/agent/tools.py`](apps/api/src/agent/tools.py) $\to$ [`apps/api/src/execution/service.py`](apps/api/src/execution/service.py) y [`apps/api/src/sandbox/judge0.py`](apps/api/src/sandbox/judge0.py).
- **Esquema de entrada (`CodeExecutionSandboxArgs`):** `code`, `language` (`"python"` | `"javascript"` | `"sql"`), `use_latest_snapshot`.
- **Propósito:** Ejecutar el código del candidato de forma aislada contra la suite de pruebas del problema activo mediante Judge0 CE (`http://localhost:2358`), persistiendo el `Snapshot` y el turno correspondiente.
- **Manejo honesto de indisponibilidad (H-01):** Si Judge0 CE no está accesible en el entorno, devuelve `status="unavailable"` con `stdout=None` y `tests_passed=None`, permitiendo tanto al frontend WebSocket como al agente informar honestamente al candidato sin inventar resultados de pruebas ni romper la sesión.

### 3. `adaptive_hint_generator` (`AdaptiveHintGeneratorTool`)
- **Implementación:** [`apps/api/src/agent/tools.py`](apps/api/src/agent/tools.py) $\to$ [`apps/api/src/llm/prompts.py`](apps/api/src/llm/prompts.py) (`load_hints`) + estado transaccional `Interview.hint_level`.
- **Esquema de entrada (`AdaptiveHintGeneratorArgs`):** `requested_level` (`1`, `2` o `3`), `reason`.
- **Propósito:** Dosificar pistas progresivas multinivel (Nivel 1: conceptual, Nivel 2: enfoque algorítmico, Nivel 3: estructura detallada y casos de borde) actualizando `Interview.hint_level` y registrando la penalización/tope de puntaje correspondiente.
- **Manejo de límite máximo:** Si el candidato ya alcanzó `hint_level == 3`, devuelve `status="max_level_reached"` (`error_code="MAX_HINT_LEVEL_REACHED"`, `hint_delivered=False`).

---

## 8. Telemetría y manejo de errores

El módulo [`apps/api/src/core/telemetry.py`](apps/api/src/core/telemetry.py) implementa un mecanismo de observabilidad estructurado que registra cada ejecución de herramientas mediante eventos estándar en los logs del servidor:

```text
[AGENT_TOOL_CALL:START] tool=CodeExecutionSandboxTool action=execute_code interview_id=550e8400... input={"language":"python"}
[AGENT_TOOL_CALL:SUCCESS] tool=CodeExecutionSandboxTool action=execute_code interview_id=550e8400... duration_ms=245.12 output={"status":"SUCCESS","passed":3}
[AGENT_TOOL_CALL:ERROR] tool=CodeExecutionSandboxTool action=execute_code interview_id=550e8400... duration_ms=112.05 error="SyntaxError: invalid syntax"
```

### Sanitización y prevención de fugas de datos sensibles (Anti-Leak)
Para evitar la persistencia o exposición accidental de credenciales o PII en los registros de telemetría:
- **Redacción de credenciales:** Expresiones regulares auditan los payloads y reemplazan automáticamente tokens JWT (`ey...`), llaves de API (`sk-...`, `Bearer ...`) y correos electrónicos por marcas `[REDACTED]`.
- **Truncado de seguridad:** Cadenas de texto arbitrarias en parámetros de entrada se truncan a un máximo de 50 caracteres en los logs de telemetría para evitar el volcado de código fuente completo o enunciados extensos.
- **Resiliencia ante fallas:** Si una herramienta falla, se emite inmediatamente un evento `[AGENT_TOOL_CALL:ERROR]` con la duración y la causa del fallo, y el flujo de la entrevista continúa sin interrupción abrupta.

---

## 9. Motor de evaluación

Al finalizar la entrevista o bajo demanda a través de `GET /interviews/{id}/evaluation`, el servicio [`apps/api/src/evaluation/service.py`](apps/api/src/evaluation/service.py) califica el desempeño técnico del candidato.

### Dimensiones de evaluación (Escala 1 a 5)
1. **`problem_solving` (Resolución de problemas):** Capacidad para descomponer el problema, identificar casos de borde y formular una estrategia válida.
2. **`algorithmic_reasoning` (Razonamiento algorítmico):** Selección adecuada de estructuras de datos y análisis de complejidad temporal y espacial.
3. **`code_quality` (Calidad de código):** Modularidad, legibilidad, nomenclatura clara, manejo de excepciones y convenciones idiomáticas.
4. **`technical_communication` (Comunicación técnica):** Claridad al explicar ideas, capacidad de escucha y respuesta ante las preguntas del agente.
5. **`complexity_management` (Gestión de complejidad):** Adaptabilidad frente a requerimientos adicionales, restricciones de escala o depuración bajo presión.

### Cálculo de puntaje y veredicto
- **Puntaje global (`overall_score`):** Promedio de las 5 dimensiones evaluadas.
- **Veredicto automatizado:**
  - `overall_score >= 4.0`: Recomendación favorable (`hire`).
  - `3.0 <= overall_score < 4.0`: Recomendación neutral / revisión requerida (`borderline`).
  - `overall_score < 3.0`: Recomendación desfavorable (`reject`).

### Criterio de revisión humana obligatoria (`needs_human_review`)
El sistema marca automáticamente la entrevista para revisión humana en los siguientes casos comprobables:
- Pistas acumuladas en nivel 3 o penalizaciones altas por intervención recurrente del agente.
- Respuestas del LLM que incumplan el esquema estructurado de Pydantic tras los reintentos.
- Fallos o desconexiones en el servicio del LLM (timeout).
- Entrevistas con evidencia insuficiente (menos de 2 turnos con contenido sustantivo o sin intentos de código).

### Reporte auditable en PDF con firma criptográfica
El servicio [`apps/api/src/reports/generator.py`](apps/api/src/reports/generator.py) genera reportes descargables en PDF utilizando WeasyPrint y Jinja2 (`GET /interviews/{id}/report.pdf`). Cada reporte incluye:
- Identificador anónimo del candidato (`CAND-XXXX`).
- Desglose detallado de puntajes y citas textuales de la transcripción que respaldan cada calificación.
- **Firma digital SHA-256:** Hash criptográfico calculado sobre el contenido del reporte para garantizar su inmutabilidad frente a auditorías posteriores.

---

## 10. Persistencia y modelo de datos

El sistema utiliza **PostgreSQL 16** como base de datos relacional transaccional y **Redis 7** para operaciones de baja latencia en memoria:

- **PostgreSQL + SQLAlchemy 2.0 (Async) + Alembic:**
  - `interviews`: Entidad principal de la sesión (fase actual, estado de finalización, marcas de inicio y fin).
  - `candidates`: Datos del candidato anonimizados en la vista evaluadora.
  - `problems`: Enunciado, dificultad, categoría y configuración de pruebas.
  - `turns`: Transcripción cronológica completa de los mensajes entre candidato, agente y sistema.
  - `code_snapshots`: Historial de versiones del código en el editor emitidas en tiempo real.
  - `sandbox_runs`: Historial de ejecuciones de pruebas con entradas, salidas y tiempos.
  - `evaluations`: Puntajes por dimensión, justificaciones textuales y veredicto.
  - `audit_events`: Registro de auditoría para trazabilidad de eventos críticos.
- **Redis:**
  - Almacén de tokens efímeros para autenticación de WebSockets con TTL de 60 segundos.
  - Candados de exclusión mutua (*distributed locks*) para la solicitud y entrega de pistas.

---

## 11. Frontend (`apps/web`)

Desarrollado en **Next.js 15 (App Router)** con **React 19** y **TypeScript** en modo estricto:

- **Editor Monaco integrado:** Entorno de edición de código en vivo con resaltado de sintaxis para Python y emisión de snapshots con temporizador de debounce (1.5 segundos).
- **Diseño de pantalla dividida (*Split-View*):** Panel izquierdo con el enunciado del problema y chat socrático con renderizado de Markdown; panel derecho con el editor de código, consola de pruebas y terminal de salida de ejecución.
- **Línea de tiempo de fases:** Indicador visual que refleja la fase actual de la entrevista de acuerdo con los eventos `phase_changed` emitidos por el backend.
- **Modal de confirmación de entrega:** En fase `WRAPUP`, provee el botón de entrega que solicita confirmación del usuario antes de enviar la transición a `EVALUATE`, bloqueando el editor y mostrando la pantalla de cierre.

---

## 12. Backend (`apps/api`)

Desarrollado en **Python 3.12** utilizando **FastAPI**:

- **Rutas REST estructuradas:** Endpoints para gestión de entrevistas (`/interviews`), ejecución de código (`/sandbox`), generación de pistas (`/hints`), evaluación (`/evaluation`) y generación de reportes (`/reports`).
- **Gestor de WebSockets (`ConnectionManager`):** Administrador de conexiones concurrentes en tiempo real con soporte para autenticación por token en query string y despacho de eventos bidireccionales.
- **Evaluación en segundo plano:** Despacho de evaluaciones asíncronas con sesiones de base de datos independientes para no retener la conexión WebSocket del candidato.
- **Contratos tipados:** Esquemas de entrada y salida respaldados por Pydantic v2.

---

## 13. Configuración del entorno

### Requisitos previos
- **Python 3.12+**
- **Node.js 20+** y gestor de paquetes **pnpm**
- **Docker** y **Docker Compose**

### Variables de entorno
Copiar los archivos de ejemplo en sus respectivas rutas:

```bash
# Variables del backend y servicios de infraestructura
cp .env.example .env

# Variables del frontend
cp apps/web/.env.example apps/web/.env.local
```

#### Variables principales (`.env`):
| Variable | Descripción | Valor por defecto local |
| :--- | :--- | :--- |
| `DATABASE_URL` | Cadena de conexión async a PostgreSQL | `postgresql+asyncpg://evaluador:evaluador_password_dev@localhost:5435/evaluador_db` |
| `REDIS_URL` | Cadena de conexión a Redis | `redis://localhost:6379/0` |
| `LLM_BASE_URL` | URL base del endpoint compatible con OpenAI | Proporcionado en el entorno / proxy |
| `LLM_MODEL` | Nombre del modelo de lenguaje | `grok-4.6` |
| `LLM_API_KEY` | Llave de acceso a la API del modelo | Variable de entorno confidencial |
| `JUDGE0_BASE_URL`| URL del servicio Judge0 CE | `http://localhost:2358` |
| `SECRET_KEY` | Clave secreta para firma de tokens JWT | Cadena secreta de desarrollo |

#### Variables del frontend (`apps/web/.env.local`):
| Variable | Descripción | Valor por defecto |
| :--- | :--- | :--- |
| `NEXT_PUBLIC_API_URL` | URL de la API de FastAPI | `http://localhost:8000` |
| `NEXT_PUBLIC_ENABLE_MOCKS` | Activar Mock Service Worker (MSW) para pruebas offline | `false` |

---

## 14. Ejecución del proyecto y Scripts Reproducibles (S1, S2, S3)

El monorepo cuenta con un [`Makefile`](Makefile) en la raíz que simplifica la orquestación:

### 1. Iniciar servicios de infraestructura (PostgreSQL 16 y Redis 7)
```bash
make docker-up
```
*(Opcional: para levantar también el clúster aislado de Judge0 CE en el puerto `2358`, ejecute `docker compose -f infra/judge0/docker-compose.yml up -d`. Si Judge0 CE no está levantado, el sistema opera de forma segura devolviendo `status="unavailable"` sin interrumpir la entrevista).*

### 2. Iniciar el Backend (FastAPI) y Frontend (Next.js)
```bash
make dev-api   # http://localhost:8000
make dev-web   # http://localhost:3000
```

### 3. Comandos Reproducibles de Validación contra Grok (`grok-4.6`)
Con `USE_MOCK_LLM=false` y una `LLM_API_KEY` válida en `.env`:

```bash
# S1: Prueba de humo multi-turno real con Grok, persistencia en PostgreSQL y telemetría de costos
python3 apps/api/src/scripts/smoke_s1_grok.py

# S2: Ejecución de los 10 escenarios reales de Function Calling (6 normales, 3 fallos controlados, 1 entrada inválida)
python3 apps/api/src/scripts/run_s2_10_executions.py

# S3: Benchmark estadístico de 32 casos con panel humano doble ciego y evaluación en vivo con Grok
python3 evals/calibrate.py \
  --transcripts-dir evals/s3_benchmark \
  --live-llm \
  --concurrency 4 \
  --output-json docs/reports/FINAL_REMEDIATION/s3_benchmark_results.json \
  --output-md docs/reports/FINAL_REMEDIATION/S3_BENCHMARK_REPORT.md
```

---

## 15. Pruebas y calidad de código

### Pruebas del Backend (Pytest)
```bash
cd apps/api && pytest -q
```

### Pruebas del Frontend (Vitest / Node Test Runner)
```bash
cd apps/web && npm run typecheck
node --test apps/web/tests/*.test.mjs
```

### Linters y comprobación estática de tipos
```bash
cd apps/api && ruff check src tests
cd apps/api && mypy src
```

---

## 16. Evidencia de Entregables (S1, S2, S3, H-01, H-02)

Los reportes auditables y artefactos JSON de ejecución real se encuentran en [`docs/reports/FINAL_REMEDIATION/`](docs/reports/FINAL_REMEDIATION/):
- **S1 (Integración Real Multi-Turno con Grok):** [`S1_GROK_INTEGRATION_REPORT.md`](docs/reports/FINAL_REMEDIATION/S1_GROK_INTEGRATION_REPORT.md) y [`s1_smoke_evidence.json`](docs/reports/FINAL_REMEDIATION/s1_smoke_evidence.json).
- **S2 (Function Calling y 10 Ejecuciones Reales):** [`S2_FUNCTION_CALLING_REPORT.md`](docs/reports/FINAL_REMEDIATION/S2_FUNCTION_CALLING_REPORT.md) y [`s2_10_executions.json`](docs/reports/FINAL_REMEDIATION/s2_10_executions.json).
- **H-01 (Contrato WebSocket y Sandbox Aislado):** [`H01_SANDBOX_WEBSOCKET_REPORT.md`](docs/reports/FINAL_REMEDIATION/H01_SANDBOX_WEBSOCKET_REPORT.md).
- **S3 (Benchmark de 32 Casos con Panel Humano y Grok en Vivo):** [`S3_BENCHMARK_REPORT.md`](docs/reports/FINAL_REMEDIATION/S3_BENCHMARK_REPORT.md) y [`s3_benchmark_results.json`](docs/reports/FINAL_REMEDIATION/s3_benchmark_results.json).
- **H-02 (Seguridad Multi-Tenant):** [`SECURITY_H02_VALIDATION_REPORT.md`](docs/reports/FINAL_REMEDIATION/SECURITY_H02_VALIDATION_REPORT.md).
- **Video de demostración técnica:** [Carpeta de demostración en Google Drive](https://drive.google.com/drive/folders/1z3b9kK5--gMBmM_he6O93KVLxlNeojIt?usp=sharing).

---

## 17. Estructura del repositorio

```text
Evaluador-Tecnico/
├── apps/
│   ├── api/                       # Backend FastAPI (Python 3.12+)
│   │   ├── alembic/               # Migraciones de base de datos
│   │   ├── prompts/               # Prompts versionados del agente y evaluador (v1 y v2)
│   │   ├── src/                   # Código fuente del backend
│   │   │   ├── agent/             # InterviewAgent y AgentToolRuntime (Function Calling S2)
│   │   │   ├── api/               # Routers REST/WebSocket y esquemas Pydantic v2
│   │   │   ├── core/              # Configuración, seguridad RBAC y telemetría Anti-Leak
│   │   │   ├── db/                # Modelos SQLAlchemy 2.0 y sesiones async
│   │   │   ├── evaluation/        # Motor de evaluación doble juez, cola ARQ y precios
│   │   │   ├── execution/         # CodeExecutionService y manejo de estado unavailable (H-01)
│   │   │   ├── problems/          # Catálogo YAML de 12 problemas y ProblemSelector
│   │   │   ├── reports/           # Generador de reportes PDF WeasyPrint con firma SHA-256
│   │   │   ├── sandbox/           # Cliente Judge0 CE aislado
│   │   │   └── scripts/           # Scripts reproducibles S1, S2 y S3
│   │   └── tests/                 # Suite de pruebas unitarias, multi-tenant y de integración
│   └── web/                       # Frontend Next.js 15 (React 19 / TypeScript estricto)
│       ├── src/
│       │   ├── app/               # Rutas de Next.js (App Router)
│       │   ├── components/        # Sala de entrevista, Monaco Editor, TestConsole
│       │   └── lib/               # Hooks WebSocket con reconexión y cliente API tipado
│       └── tests/                 # Pruebas de frontend
├── evals/
│   ├── calibrate.py               # Harness estadístico offline y --live-llm contra Grok
│   ├── golden_transcripts/        # 20 transcripciones base de regresión rápida
│   └── s3_benchmark/              # 32 casos S3 con procedencia explícita y panel humano dual
├── packages/
│   └── contracts/                 # Contratos OpenAPI y tipos TypeScript generados
├── docs/                          # Guías, ADRs y reportes de remediación final
├── infra/                         # Docker Compose para PostgreSQL, Redis y Judge0 CE
├── Makefile                       # Comandos de automatización del monorepo
└── README.md                      # Documentación técnica oficial
```

---

## 18. Seguridad y buenas prácticas

- **Aislamiento Multi-Tenant estricto (H-02):** Todos los endpoints de privacidad (`DELETE /privacy/candidates/{id}`), trayectoria (`GET /interviews/{id}/trajectory`) y evaluación verifican pertenencia a `current_user.organization_id`, respondiendo `404 Not Found` ante accesos cruzados entre organizaciones.
- **Anonimización del evaluador (Cumplimiento Ley 1581):** El evaluador no recibe nombres, correos, género ni instituciones académicas del candidato (`CAND-XXXX`).
- **Aislamiento de código no confiable:** Los envíos del candidato se ejecutan en Judge0 CE con límites de memoria (`128 MB`), tiempo de CPU (`2.0s`) y procesos (`10`), sin usar `subprocess` local sin aislar.
- **Mitigación de Prompt Injection:** La entrada del candidato se encapsula en `<untrusted_candidate_input>`, y `AgentToolRuntime` prohíbe sobrescribir claves de contexto (`interview_id`, `organization_id`) desde argumentos de herramientas.
- **Autenticación efímera de WebSocket:** Las conexiones en vivo requieren un token efímero almacenado en Redis con TTL de 60 segundos.

---

## 19. Estado del proyecto

El proyecto se encuentra **operativo, auditado y verificado end-to-end contra Grok (`grok-4.6`)**:
- **S1:** Conversación técnica multi-turno real con retención de contexto, persistencia en PostgreSQL y telemetría de costos verificada.
- **S2:** Autonomía del agente mediante Function Calling (`tools` / `tool_calls` / `role="tool"`) con 3 herramientas de dominio, validación Pydantic v2 (`extra="forbid"`), reintentos acotados y 10 ejecuciones reales documentadas.
- **H-01:** Contrato WebSocket y UI alineados para reportar honestamente `status="unavailable"` cuando Judge0 CE no está activo.
- **H-02:** Aislamiento multi-tenant verificado con pruebas automatizadas de no regresión.
- **S3:** Benchmark de 32 casos con clasificación explícita de procedencia, evaluación humana de referencia por pares (`evaluator_1`, `evaluator_2`, `consensus`) y calibración estadística en vivo contra Grok.
