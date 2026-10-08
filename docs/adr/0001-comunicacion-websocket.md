# ADR 0001: Comunicación Unificada en Tiempo Real vía WebSocket

## Estado
Aceptado

## Contexto
La sala de entrevista técnica requiere comunicación interactiva continua entre el candidato y el agente de IA:
- Envío y recepción de mensajes de chat.
- Streaming de tokens de respuesta del LLM para una experiencia fluida.
- Emisión periódica de deltas y snapshots de código del editor Monaco.
- Envío de comandos de ejecución y recepción de resultados de pruebas.
- Envío de telemetría de integridad (eventos de blur, pegado de código, marcas de tiempo).

El plan preliminar proponía mantener una conexión WebSocket para eventos y canales SSE (Server-Sent Events) separados para el streaming de tokens de chat.

## Decisión
Se descarta la dualidad WebSocket + SSE y se adopta un **único canal WebSocket bidireccional (`/interviews/{id}/live`)** para todos los flujos en tiempo real durante la sesión.

El protocolo interno utiliza tramas JSON tipadas con discriminador `type`:
- `agent_token`: chunk parcial de texto generado por el LLM.
- `turn_complete`: finalización del turno del agente con ID asignado.
- `code_snapshot`: versión del código enviada desde el editor Monaco.
- `run_tests`: solicitud del candidato para compilar y ejecutar código.
- `test_results`: respuesta del sandbox con stdout, stderr y estado de tests.
- `phase_transition`: notificación de cambio de fase de la entrevista (`INTRO` ➡️ `PROBLEM` ➡️ `CLARIFY` ➡️ `DESIGN` ➡️ `CODING` ➡️ `PROBE` ➡️ `WRAPUP`).
- `integrity_event`: evento de foco, pegado o tiempo de inactividad.

## Consecuencias
### Positivas
- Se elimina la necesidad de abrir y cerrar conexiones SSE por cada turno de conversación.
- Simplifica la reconexión en el frontend: un único reconector de WebSocket restaura todo el estado de la sesión.
- Menor overhead de sockets y consumo de memoria tanto en el servidor FastAPI como en el navegador del candidato.

### Negativas / Mitigaciones
- WebSocket no cuenta con reintentos HTTP nativos automáticos; el frontend debe implementar lógica de reconexión exponencial y heartbeat/ping-pong (resuelto en `useInterviewSocket`).
