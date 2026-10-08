# 🎯 Evaluador Técnico de Candidatos

Agente de Inteligencia Artificial que realiza la entrevista técnica inicial a candidatos de desarrollo de software, propone un problema real en un entorno interactivo en vivo, evalúa el **razonamiento y la capacidad de resolución de problemas** (más allá del resultado binario de pruebas) y genera un **informe defendible y auditable**.

Diseñado para empresas de tecnología, bootcamps y firmas de selección técnica en Colombia y Latinoamérica.

---

## 👥 Equipo y Módulos

* **Samuel:** Backend, LLM Gateway, Motor del Agente, Sandboxing y Juez de Evaluación (`apps/api`).
* **Cristian:** Frontend, Experiencia de Usuario (UI/UX), Sala de Entrevista en Vivo y Telemetría (`apps/web`).

---

## 🏗️ Arquitectura del Monorepo

```
evaluador-tecnico/
├── Makefile                  # Comandos globales estandarizados
├── apps/
│   ├── api/                  # Backend FastAPI (Python 3.12)
│   └── web/                  # Frontend Next.js 15 (TypeScript, Tailwind, shadcn/ui)
├── packages/
│   └── contracts/            # Contratos OpenAPI v0 y tipos TypeScript generados
├── problems/                 # Banco de problemas técnicos en YAML
├── evals/                    # Transcripciones doradas y métricas de calibración
├── infra/                    # Docker Compose (PostgreSQL 16 y Redis 7)
├── docs/                     # Registros de Decisiones de Arquitectura (ADRs)
└── AGENTS.md                 # Reglas compartidas para asistentes de IA
```

---

## 🚀 Inicio Rápido (Quickstart)

### 1. Prerrequisitos
- Node.js 20+ y `pnpm`
- Python 3.12+
- Docker y Docker Compose
- `make`

### 2. Instalación de dependencias
```bash
make install
```

### 3. Levantar infraestructura local (PostgreSQL & Redis)
```bash
make docker-up
```

### 4. Ejecución en desarrollo
* **Frontend (Next.js):**
  ```bash
  make dev-web
  # Abre http://localhost:3000
  ```
* **Backend (FastAPI):**
  ```bash
  make dev-api
  # Documentación interactiva en http://localhost:8000/docs
  ```

### 5. Sincronización de Contratos API
Cuando se actualice `openapi.json`:
```bash
make update-contracts
```

---

## 🛡️ Principios del Informe Defendible
1. **Evidencia Obligatoria:** Cada puntaje (1 a 5) está respaldado por turnos exactos de conversación o deltas de código.
2. **Anonimización Ciega:** El evaluador no recibe datos demográficos ni personales del candidato.
3. **Decisión Asistida:** El agente recomienda y fundamenta; el líder técnico humano toma la decisión de contratación.
4. **Cumplimiento Legal:** Diseñado conforme a la **Ley 1581 de 2012** (Protección de Datos Personales en Colombia).
