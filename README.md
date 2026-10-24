# 🎯 Evaluador Técnico de Candidatos con IA (v1.0.0)
### *Evaluación técnica defendible, objetiva y adaptativa para talento TI en Colombia y Latinoamérica*

[![Backend Tests](https://img.shields.io/badge/pytest-222%20passed-brightgreen.svg)](apps/api/tests)
[![LLM Calibrate](https://img.shields.io/badge/evals-100%25%20calibrado-blue.svg)](evals/)
[![Next.js](https://img.shields.io/badge/Next.js-15.1.7-black.svg)](apps/web/)
[![Python](https://img.shields.io/badge/Python-3.12%2B-blue.svg)](apps/api/)
[![Ley 1581](https://img.shields.io/badge/Habeas%20Data-Ley%201581%20Colombia-emerald.svg)](apps/api/src/api/routers/privacy.py)

---

## 💡 1. El Problema que Resolvemos

En el ecosistema tecnológico de Colombia y América Latina, la selección técnica tradicional presenta fallas críticas:
1. **Falsos positivos por memorización o trampas con IA:** Los candidatos resuelven pruebas estáticas tipo LeetCode copiando código de ChatGPT o GitHub Copilot sin comprender realmente la arquitectura ni la complejidad algorítmica.
2. **Desperdicio masivo de horas de ingeniería:** Los Tech Leads e ingenieros Senior dedican entre **12 y 18 horas a la semana** repitiendo entrevistas técnicas preliminares, desatendiendo el desarrollo de producto.
3. **Decisiones subjetivas e indefendibles:** Las evaluaciones carecen de trazabilidad forense; se basan en notas informales o sesgos inconscientes (de género, edad o acento regional), exponiendo a las empresas a reclamos y malas contrataciones.
4. **Riesgos legales por invasión de privacidad:** Plataformas que graban vídeo o realizan monitoreo biométrico violan la **Ley 1581 de 2012 (Habeas Data Colombia)** y exponen a sanciones de la SIC.

---

## 🚀 2. La Solución: Evaluador Técnico Asistido por IA

**Evaluador Técnico** es una plataforma integral que actúa como un entrevistador técnico socrático inteligente:
- **No juzga solo el código final:** Evalúa **el proceso mental**, la capacidad de clarificar requisitos, la estructuración de la solución y la trayectoria de depuración ante errores.
- **Anti-Cheat Cognitivo (Sin Cámaras):** En la fase `PROBE`, el agente formula preguntas dinámicas sobre el código recién escrito (*"¿Qué complejidad temporal tiene este bucle y qué harías si recibes 50 millones de transacciones?"*). Si el candidato copió sin entender, su incoherencia queda al descubierto.
- **Rúbrica Armonizada de 5 Dimensiones:**
  1. *Resolución de Problemas (Problem Solving)*
  2. *Razonamiento Algorítmico (Algorithmic Reasoning)*
  3. *Calidad de Código y Tipado (Code Quality)*
  4. *Comunicación Técnica (Technical Communication)*
  5. *Gestión de Complejidad y Escalabilidad (Complexity Management)*
- **Informe Defendible en PDF con Hash SHA-256:** Generado con WeasyPrint, incluye radar de competencias interactivo, citas forenses directas de la conversación y un hash inmutable para auditorías.
- **Cumplimiento Estricto de Ley 1581 de 2012:** Anonimización ciega por defecto (`CAND-XXXX`), consentimiento informado previo y endpoints de supresión de datos / derecho al olvido.

---

## 🤖 3. Integración de Punta a Punta con Grok y la Llave del Reto

El sistema cuenta con un **LLM Gateway agnóstico y compatible con OpenAI** configurado para operar de punta a punta con **Grok (xAI)** a través del proxy oficial del reto:

```env
# Variables de Entorno del Gateway LLM (.env)
LLM_BASE_URL=https://api.reto.pltk.mx/v1
LLM_MODEL=grok-4.6
LLM_API_KEY=<TU_LLAVE_DEL_RETO_AQUI>
LLM_TIMEOUT_SECONDS=30.0
LLM_MAX_RETRIES=2
```

### Flujo de Ejecución del Agente:
1. El candidato se conecta mediante **WebSocket autenticado** con un token efímero JWT (`/ws/interview/{id}?token=...`).
2. El agente procesa la conversación en una **Máquina de Estados de 8 Fases** (`INTRO` → `PROBLEM` → `CLARIFY` → `DESIGN` → `CODING` → `PROBE` → `WRAPUP` → `EVALUATE`).
3. El agente envía **tokens en tiempo real (streaming)** al frontend con respuestas socráticas orientadas al contexto del problema seleccionado.
4. Las entradas del candidato se aíslan dentro de etiquetas `<untrusted_candidate_input>` para prevenir inyecciones de prompt.

---

## 🛠️ 4. Herramientas Reales del Sistema (Tools)

El agente y la plataforma integran herramientas de producción:

1. **Selector Inteligente de Problemas (`ProblemSelector`):**
   - Catálogo relacional y en YAML (`problems/`) con problemas reales adaptados al contexto colombiano (Conciliación de pagos PSE, Retención en la fuente UVT de la DIAN, procesamiento de logs fintech).
   - Filtrado determinista por rol, seniority, stack y dificultad.
2. **Sandbox Aislado de Ejecución de Código (`CodeRunnerInterface` / `Judge0Client`):**
   - Ejecución segura de código Python/TypeScript en micro-contenedores con límites de CPU (2s) y memoria (128MB), previniendo fork-bombs y llamadas a red no autorizadas.
3. **Juez Evaluador con Rúbrica Estructurada (`EvaluationService`):**
   - Doble evaluación analítica de turnos y snapshots de código con citas forenses exactas vinculadas a cada dimensión.
4. **Generador Criptográfico de Informes PDF (`ReportPdfGenerator`):**
   - Renderizado con Jinja2 y WeasyPrint. Calcula un hash SHA-256 inmutable de la evaluación y final code para garantizar integridad probatoria.
5. **Motor de Pistas y Telemetría Ética (`HintService`):**
   - Detección de inactividad con entrega progresiva de pistas en 3 niveles (3, 5 y 10 minutos) con candados atómicos de reserva para evitar duplicados.

---

## 🛡️ 5. Manejo de Errores y Resiliencia

- **Backoff Exponencial y Reintentos:** Manejo automático de caídas transitorias de red con reintentos controlados (`LLMTimeoutError`, `LLMProviderError`).
- **Autenticación Segura y Rechazo 401/403:** Detección de llaves inválidas (`LLMAuthenticationError`) con mensajes descriptivos.
- **Resiliencia de Conexión WebSocket:** El frontend maneja desconexiones momentáneas con auto-reconexión y restauración del último snapshot de código guardado en base de datos.
- **Protección contra Bloqueos en Sandbox:** Timeouts forzados si el candidato introduce bucles infinitos (`while True`).

---

## 📊 6. Calibración y Verificación

- **Harness de Calibración (`evals/calibrate.py`):** Ejecuta transcripciones doradas de referencia (*Senior PSE Reconciliation* y *Junior Payroll Edge Case*) logrando una **tasa de consistencia del 100%**.
- **Suite de Pruebas Automatizadas:** **222 pruebas pasadas al 100%** en el backend (unitarias, integración, concurrencia, estado de máquina, privacidad y generación de PDF).
- **Verificación de Tipos TypeScript:** 0 errores en `tsc --noEmit`.
- **Compilación de Producción:** 10 de 10 rutas compiladas en Next.js.

---

## 🚀 7. Inicio Rápido (Quickstart)

### 1. Clonar y Configurar Entorno
```bash
git clone <URL_REPOSITORIO>
cd evaluador-tecnico

# Configurar variables de entorno
cp .env.example .env   # Agregar tu LLM_API_KEY del reto
```

### 2. Levantar Servicios con Docker
```bash
# Levanta PostgreSQL 16 y Redis 7
docker compose -f infra/docker-compose.yml up -d
```

### 3. Ejecutar Pruebas Automatizadas
```bash
# Backend (222 tests)
uv run --project apps/api --extra dev pytest apps/api/tests

# Calibración de evaluación
uv run --project apps/api python evals/calibrate.py
```

### 4. Iniciar Frontend y Backend
```bash
# Backend FastAPI (Puerto 8000)
uv run --project apps/api uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload

# Frontend Next.js (Puerto 3000)
pnpm --filter @evaluador/web dev
```

---

## 🎮 8. Modo Demo Offline (Sin Claves ni Backend Requerido)

¿Quieres probar la experiencia completa de inmediato?
Abre en tu navegador:
👉 **`http://localhost:3000/demo`**

Permite seleccionar problemas reales, interactuar con el agente conversacional, editar código en vivo con Monaco Editor, ejecutar pruebas y generar el reporte defendible instantáneamente con radar de competencias.

---

## 👥 Equipo
- **Cristian (Frontend & UX/UI Lead):** Interfaz en Next.js, editor Monaco, sala en vivo, telemetría ética y modo demo.
- **Samuel (Backend & Architecture Lead):** FastAPI, máquina de estados, sandbox Judge0, generador WeasyPrint y cumplimiento Ley 1581.
