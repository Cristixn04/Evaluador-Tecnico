# Registro de Cambios (CHANGELOG)
Todas las modificaciones notables a **Evaluador Técnico de Candidatos** se documentan en este archivo.

El formato se basa en [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) y este proyecto se adhiere a [Semantic Versioning](https://semver.org/lang/es/).

---

## [1.0.0] - 2026-10-24 - *Release Freeze v1.0.0*

### Añadido
- **Sprint 6 (Listo para Producción & Demo Comercial):**
  - Modo Demo Interactivo Offline en la ruta `/demo` con selección de problemas colombianos (PSE Fintech y Retención en la Fuente UVT).
  - Simulación completa de interacción con agente conversacional, editor Monaco, ejecución en sandbox de pruebas y radar de competencias instantáneo.
  - Infraestructura de producción contenerizada en `infra/Dockerfile.api`, `infra/Dockerfile.web` y `infra/docker-compose.prod.yml`.
  - Pitch Deck comercial B2B (`docs/pitch-deck.md`) con análisis de mercado Latam y calculadora de ROI.
  - Guía de demostración en vivo de 7 minutos para clientes corporativos (`docs/demo-guide.md`).
- **Sprint 5 (Calibración & Aseguramiento de Calidad):**
  - Harness de calibración y evaluación comparativa (`evals/calibrate.py`) con transcripciones de referencia "Golden Transcripts" (100% de consistencia de puntuación).
  - Suite de pruebas de regresión automatizadas para Habeas Data / Privacidad (`apps/api/tests/test_privacy.py`) y generación de reportes WeasyPrint (`apps/api/tests/test_reports.py`).
  - Total de 222 pruebas automatizadas backend aprobadas (100% verde).
- **Sprint 4 (Anti-Cheat Cognitivo, Reportes Defendibles & Ley 1581):**
  - Generador de informes defendibles en PDF usando Jinja2 y WeasyPrint con vector radar y hash inmutable de auditoría SHA-256 (`GET /interviews/{id}/report.pdf`).
  - Anti-cheat cognitivo en la fase `PROBE` para verificar autoría mediante preguntas de complejidad algorítmica y diseño.
  - Telemetría ética no invasiva en el frontend (eventos de visibilidad, cambio de pestaña y pegado masivo).
  - Endpoints de cumplimiento de la Ley 1581 de 2012 de Colombia: política de tratamiento (`GET /privacy/policy`), revocatoria de consentimiento (`POST /privacy/consent/revoke`) y supresión de datos (`DELETE /privacy/candidates/{id}`).
  - Casilla de consentimiento informado obligatorio antes de iniciar la entrevista en vivo.
- **Sprint 3 (Integración de Trayectoria & Sincronización WebSocket):**
  - Endpoint de trayectoria forense `GET /interviews/{id}/trajectory` con diffs unificados y reproducción temporal paso a paso.
  - Tipado retrocompatible para snapshots históricos (`SnapshotReason = ... | "legacy"`).
  - Componente de reproducción temporal interactiva `TrajectoryPlayer`.
- **Sprint 2 (Flujo de Entrevista en Tiempo Real & Autenticación Efímera):**
  - Verificación de invitaciones y emisión de tokens efímeros para WebSocket (`GET /sessions/verify` → `ws_token`).
  - Conexión WebSocket bidireccional para mensajes de chat, sincronización de código y solicitudes de transición de fase.
  - Editor Monaco embebido con ejecución de pruebas en sandbox Judge0 CE.
- **Sprint 1 (Gestión de Vacantes & Parser con IA):**
  - Parser inteligente de vacantes con LLM (extracción de habilidades requeridas, opcionales, seniority y rol).
  - Catálogo de problemas algorítmicos contextualizados a la industria fintech y tributaria colombiana.
  - Panel de control para reclutadores con métricas y gestión de vacantes.
- **Sprint 0 (Fundamentos de Arquitectura & Configuración Monorepo):**
  - Monorepo estructurado con pnpm workspaces (`apps/api`, `apps/web`, `packages/contracts`).
  - Base de datos PostgreSQL con migraciones Alembic y soporte de Redis para estados temporales.
  - Contratos OpenAPI centralizados y generación automática de tipos TypeScript.

### Modificado
- Actualizado número de versión a `1.0.0` en `apps/api/pyproject.toml` y `package.json`.
- Mejorada la navegación principal con acceso directo al Modo Demo.
