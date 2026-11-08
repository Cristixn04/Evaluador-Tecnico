# ADR 0008: Máquina de Estados de Entrevista (InterviewPhase)

## Estado
Aceptado

## Contexto
El contrato WebSocket (`packages/contracts/websocket.ts`) define un enum `InterviewPhase` con ocho fases que estructuran la sala de entrevista. El modelo de datos actual tiene un campo `InterviewStatus` que representa el estado de ciclo de vida de la entidad (creada, en progreso, completada, cancelada, etc.), distinto de las fases operativas de la entrevista.

Se requiere alinear el modelo con las fases contractuales sin perder la distinción semántica entre "estado de ciclo de vida" y "fase de entrevista".

## Decisión

### Fases de Entrevista (InterviewPhase) — **DR-7**
El enum `InterviewPhase` tiene exactamente ocho valores, según contrato vigente:

1. `INTRO` — Fase inicial obligatoria
2. `PROBLEM_SELECTION`
3. `CODING`
4. `CODE_REVIEW`
5. `TESTING`
6. `DISCUSSION`
7. `CLOSING`
8. `COMPLETED`

- La fase **inicial es `INTRO`** para toda entrevista nueva.
- Las fases son **definidas por contrato** (`websocket.ts`) y no pueden modificarse unilateralmente.

### Relación con InterviewStatus — **Pendiente de Resolución Técnica**
- `InterviewStatus` **existe actualmente** y representa un estado distinto (ciclo de vida: p. ej., `PENDING`, `IN_PROGRESS`, `COMPLETED`, `CANCELLED`).
- **No se declara** que `phase` sustituye automáticamente a `status`.
- **No se eliminan** estados de `InterviewStatus` ni se inventan equivalencias fijas.
- La **coexistencia y alineación** entre `InterviewPhase` (fase operativa) y `InterviewStatus` (ciclo de vida) queda **pendiente de resolución técnica durante la implementación**.
- Cualquier migración o unificación debe preservar la semántica de ambos campos hasta que se decida lo contrario.

### Preservación de PII Histórica — **DR-8**
- Durante S-09, **toda PII histórica se preserva** tal como está (no se anonimiza, no se borra, no se transforma).
- La evolución prevista para tratamiento de PII (anonimización, seudonimización, borrado selectivo) está planificada para **S-19** y no debe anticiparse en S-09.

### IntegrityEvent — **DR-10**
- `IntegrityEvent` **no es requisito obligatorio de S-09**.
- Cualquier implementación opcional de eventos de integridad **debe mantener compatibilidad** con los contratos vigentes (OpenAPI y `websocket.ts`).
- **No se decide silenciosamente** descartarlo, persistirlo o cambiar el contrato. La decisión de incluirlo, cómo y cuándo, queda para fases posteriores.

## Reglas de Transición — **Explícitamente No Definidas en Este ADR**
- No se inventa una máquina de transiciones híbrida (basada en tests, timeout, condiciones compuestas, etc.).
- No se definen reglas de autorización por fase no confirmadas.
- El ADR **registra las fases definidas por contrato** y **deja las reglas de transición pendientes** de verificación técnica y acuerdo entre Samuel y Cristian durante la implementación.

## Consecuencias
- El backend y frontend comparten la misma fuente de verdad para `InterviewPhase` (`websocket.ts`).
- La fase inicial `INTRO` es contrato: cualquier entrevista válida comienza ahí.
- La distinción entre `phase` (operativo) y `status` (ciclo de vida) se mantiene explícita hasta resolución técnica.
- PII histórica intacta en S-09; trabajo de privacidad diferido a S-19.
- `IntegrityEvent` fuera de alcance obligatorio; compatibilidad contractual garantizada.

## Detalles Pendientes (Explícitamente No Resueltos)
1. **Reglas de transición entre fases**: condiciones, guards, timeouts, autorización — por definir en implementación.
2. **Alineación/migración InterviewStatus ↔ InterviewPhase**: estrategia técnica por resolver.
3. **Inclusión y forma de IntegrityEvent**: decisión futura, fuera de S-09.

(End of file - total 72 lines)