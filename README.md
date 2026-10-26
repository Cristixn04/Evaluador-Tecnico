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

## 6. El agente técnico

### Orquestación e integración con LLM
El agente utiliza un modelo de lenguaje de última generación (`grok-4.6` o compatible con OpenAI API) configurado a través de `httpx.AsyncClient` con parámetros estrictos de timeout (30s) y reintentos automáticos (2).

La arquitectura del agente se basa en **orquestación por backend**: no delega el control de flujo ni la invocación arbitraria de funciones al modelo mediante function calling externo, sino que coordina la conversación a través de etapas controladas, inyectando el contexto de la fase activa y el historial de turnos.

### Construcción de prompts y aislamiento de seguridad
Los prompts del sistema están versionados en `apps/api/prompts/` (`v1/` y `v2/`):
- `interview_agent.md` e `interview_agent_phases.md`: Definen el tono socrático, el rol pedagógico-evaluador y las directrices de no otorgar respuestas directas.
- **Aislamiento de entradas del candidato:** Todo contenido proveniente del candidato (mensajes de chat, fragmentos de código) se encapsula de manera estricta dentro de etiquetas `<untrusted_candidate_input>` antes de enviarse al modelo, evitando ataques de inyección de instrucciones (*prompt injection*) que intenten alterar el criterio del evaluador.

### Persistencia y telemetría de turnos
Cada interacción (mensaje del candidato y respuesta del agente) se persiste de forma transaccional en la tabla `turns` de PostgreSQL con su respectivo rol (`candidate`, `agent`, `system`), número correlativo de turno y marca de tiempo ISO-8601.

---

## 7. Herramientas del agente (Sprint 2)

Para cumplir con los requerimientos técnicos de **Sprint 2 (S2)**, el sistema dispone de 3 herramientas reales integradas en la lógica del backend y completamente instrumentadas:

### 1. `ProblemSelectorTool`
- **Ubicación en código:** [`apps/api/src/problems/selector.py`](apps/api/src/problems/selector.py)
- **Propósito:** Selección automatizada y filtrado de problemas técnicos desde el catálogo en disco.
- **Entrada:** `category: Optional[str]`, `seniority: Optional[SeniorityLevel]`, `tags: Optional[list[str]]`.
- **Salida:** Instancia de `Problem` con identificador, título, descripción, plantilla de código, casos de prueba públicos y privados.
- **Manejo de errores:** Si los filtros no arrojan resultados o el catálogo YAML está corrupto, la herramienta captura la excepción, registra el error y realiza un fallback determinista al problema base (`sliding-window-rate-limiter.yaml`).

### 2. `CodeExecutionSandboxTool`
- **Ubicación en código:** [`apps/api/src/execution/service.py`](apps/api/src/execution/service.py) / [`apps/api/src/sandbox/judge0.py`](apps/api/src/sandbox/judge0.py)
- **Propósito:** Ejecución aislada y segura del código entregado por el candidato contra casos de prueba.
- **Entrada:** `source_code: str`, `language: str`, `test_cases: list[dict]`, `time_limit: float`, `memory_limit: int`.
- **Salida:** `ExecutionResult` conteniendo `status` (SUCCESS, COMPILATION_ERROR, RUNTIME_ERROR, TIME_LIMIT_EXCEEDED), `stdout`, `stderr`, tiempo de ejecución y detalle de pruebas superadas/fallidas.
- **Manejo de errores:** Control de excepciones de red contra Judge0, timeouts de ejecución y captura estructurada de stacktraces de Python sin tumbar la sesión del usuario.

### 3. `AdaptiveHintGeneratorTool`
- **Ubicación en código:** [`apps/api/src/hints/service.py`](apps/api/src/hints/service.py)
- **Propósito:** Generación y dosificación progresiva de pistas contextuales cuando el candidato experimenta bloqueos.
- **Entrada:** `interview_id: UUID`, `problem: Problem`, `current_code: str`, `requested_level: int`.
- **Salida:** `HintResponse` con el texto de la pista, nivel otorgado (1 a 3) y penalización conceptual registrada para la evaluación.
- **Manejo de errores:** Bloqueo de concurrencia atómico mediante claves de Redis (`hint_lock:{interview_id}`). Si se solicita un nivel no válido o se excede el límite máximo de pistas por fase, devuelve un error descriptivo controlado.

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

## 14. Ejecución del proyecto

El monorepo cuenta con un [`Makefile`](Makefile) en la raíz que simplifica la orquestación:

### 1. Iniciar servicios de infraestructura
Inicia los contenedores de PostgreSQL 16 (puerto 5435) y Redis 7 (puerto 6379):
```bash
make docker-up
```

### 2. Iniciar el Backend (FastAPI)
Ejecuta el servidor con recarga en caliente en `http://localhost:8000`:
```bash
make dev-api
```

### 3. Iniciar el Frontend (Next.js)
Ejecuta el servidor de desarrollo en `http://localhost:3000`:
```bash
make dev-web
```

*(Opcional: para detener los contenedores de infraestructura utilice `make docker-down`).*

---

## 15. Pruebas y calidad de código

Todas las suites de prueba han sido verificadas en el entorno local del repositorio:

### Pruebas del Backend (Pytest)
```bash
# Ejecutar suite completa con pytest
make test-api
```
*Resultado actual verificado:* **273 pruebas pasadas**, 1 omitida.

### Pruebas del Frontend (Node.js Test Runner)
```bash
# Ejecutar suite de pruebas de sincronización y renderizado
make test-web
# o mediante node:
node --test apps/web/tests/*.test.mjs
```
*Resultado actual verificado:* **20 pruebas pasadas** (10 de renderizado Markdown, 10 de sincronización de fases y cierre formal).

### Linters y comprobación estática de tipos
```bash
# Linter de Backend con Ruff
apps/api/.venv/bin/ruff check apps/api/src

# Comprobación de tipos en Backend con Mypy
apps/api/.venv/bin/mypy apps/api/src

# Comprobación de tipos en Frontend con TypeScript
cd apps/web && pnpm run typecheck
```
*Resultado actual verificado:* 0 errores en todos los analizadores.

---

## 16. Entregables de Sprint 2 (S2)

Esta sección sintetiza el cumplimiento técnico formal de los requisitos establecidos para el **Sprint 2 (S2)**:

### 1. Tres herramientas reales implementadas e instrumentadas
- `ProblemSelectorTool`: Filtrado y carga de problemas desde catálogo YAML con fallback ante fallos.
- `CodeExecutionSandboxTool`: Ejecución segura de código contra Judge0 con contención de tiempo y memoria.
- `AdaptiveHintGeneratorTool`: Dosificación de pistas con bloqueo de concurrencia en Redis.

### 2. Manejo de errores y resiliencia
Las tres herramientas capturan excepciones de forma explícita, impidiendo que caídas de servicios externos (como Judge0 o LLM Gateway) afecten el ciclo de vida de la entrevista.

### 3. Telemetría estructurada observable
Cada llamada de herramienta emite registros estructurados con marcas estándar `[AGENT_TOOL_CALL:START]`, `[AGENT_TOOL_CALL:SUCCESS]` y `[AGENT_TOOL_CALL:ERROR]`, sanitizando automáticamente cualquier credencial o PII.

### 4. Registro de ejecuciones reales
Las ejecuciones de validación del agente con sus respectivas sesiones e identificadores de entrevista se encuentran auditadas en el sistema.

### 5. Video de demostración técnica
El video demostrativo que documenta el funcionamiento en vivo de las herramientas, el cierre formal de entrevista y la telemetría del sistema se encuentra disponible en:

> [Video de demostración del agente](https://drive.google.com/drive/folders/1z3b9kK5--gMBmM_he6O93KVLxlNeojIt?usp=sharing)

---

## 17. Estructura del repositorio

```text
Evaluador-Tecnico/
├── apps/
│   ├── api/                       # Backend FastAPI (Python 3.12)
│   │   ├── alembic/               # Migraciones de base de datos
│   │   ├── prompts/               # Prompts del agente y evaluador (v1 y v2)
│   │   ├── src/                   # Código fuente del backend
│   │   │   ├── agent/             # Lógica del agente conversacional
│   │   │   ├── core/              # Configuración, base de datos y telemetría
│   │   │   ├── evaluation/        # Motor de evaluación y rúbrica
│   │   │   ├── execution/         # Servicio de ejecución de código
│   │   │   ├── hints/             # Servicio de pistas adaptativas
│   │   │   ├── problems/          # Selector de problemas del catálogo
│   │   │   ├── reports/           # Generador de reportes PDF WeasyPrint
│   │   │   ├── sandbox/           # Cliente de Judge0 y ejecución en contenedor
│   │   │   └── ws/                # Manejador y despachador de WebSockets
│   │   └── tests/                 # Suite de pruebas unitarias y de integración
│   └── web/                       # Frontend Next.js 15 (React 19 / TypeScript)
│       ├── public/                # Recursos estáticos y service worker MSW
│       ├── src/
│       │   ├── app/               # Rutas de Next.js (App Router)
│       │   ├── components/        # Componentes UI (Editor, Chat, Header, Modales)
│       │   └── lib/               # Hooks de WebSocket, clientes de API y utilidades
│       └── tests/                 # Pruebas de integración del frontend
├── packages/
│   └── contracts/                 # Contratos TypeScript generados y esquemas compartidos
├── docs/                          # Documentación y registros de arquitectura (ADRs)
│   └── adr/                       # ADR 0001 a ADR 0010
├── infra/                         # Configuración de Docker Compose para Postgres y Redis
├── problems/                      # Catálogo de 12 problemas técnicos en formato YAML
├── Makefile                       # Comandos de automatización del proyecto
├── .env.example                   # Plantilla de variables de entorno del sistema
└── README.md                      # Documentación técnica oficial
```

---

## 18. Seguridad y buenas prácticas

- **Anonimización del evaluador (Cumplimiento Ley 1581):** El evaluador no recibe nombres, correos, género ni instituciones académicas del candidato. La identificación se realiza mediante códigos temporales como `CAND-XXXX`.
- **Aislamiento de código no confiable:** Los envíos del candidato se ejecutan en un sandbox con límites duros de memoria (128 MB), tiempo de CPU (2.0s) y sin privilegios de red o sistema de archivos del servidor anfitrión.
- **Mitigación de Prompt Injection:** La entrada del candidato en el chat y editor se encapsula en `<untrusted_candidate_input>`, imposibilitando el secuestro de directivas del evaluador.
- **Autenticación efímera de WebSocket:** Las conexiones en vivo requieren un token efímero de un solo uso generado por el backend y almacenado en Redis con TTL de 60 segundos.
- **Gestión segura de secretos:** No existen llaves de API, contraseñas o credenciales en el código fuente; todos los valores sensibles son inyectados exclusivamente mediante variables de entorno.
- **Trazabilidad criptográfica:** Los reportes de evaluación generados incluyen un hash SHA-256 para evitar su alteración tras la emisión.

---

## 19. Estado del proyecto

El proyecto se encuentra en estado **funcional y verificado**, cumpliendo con los objetivos y entregables del **Sprint 2 (S2)**:
- Orquestación del agente y de las 3 herramientas técnicas en backend completada.
- Sincronización de fases en tiempo real y cierre formal (`WRAPUP` $\to$ `EVALUATE`) validado en frontend y backend.
- Evaluación automática desacoplada en segundo plano con deduplicación y reporte auditable.
- Cobertura de pruebas completa con **273 pruebas de backend** y **20 pruebas de frontend** ejecutándose exitosamente.
- Linters y chequeos de tipos estáticos al 100% sin advertencias.
