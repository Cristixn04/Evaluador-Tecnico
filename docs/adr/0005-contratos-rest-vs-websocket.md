# ADR 0005: Fuente de Verdad de Contratos REST vs WebSocket

## Estado
Aceptado

## Contexto
Samuel (backend) y Cristian (frontend) comparten `packages/contracts` como frontera del monorepo. REST ya vive en `openapi.json` y genera tipos TypeScript. El protocolo de la sala de entrevista es bidireccional, discriminado por `type`, y no encaja de forma natural en OpenAPI sin forzar un modelo HTTP que el navegador no usa.

Duplicar contratos en Pydantic, OpenAPI y TypeScript sin una regla explícita produce divergencias silenciosas (como las ya observadas entre ADR-0001 y `websocket.ts`).

## Decisión
`packages/contracts` es la fuente de verdad compartida, con dos artefactos distintos:

```text
packages/contracts/openapi.json
        ├──► tipos TypeScript/frontend
        └──► modelos Pydantic/backend

packages/contracts/websocket.ts
        ├──► TypeScript/frontend
        └──► modelos Pydantic equivalentes/backend
```

Reglas:
- No duplicar contratos arbitrariamente.
- No modificar contratos compartidos unilateralmente.
- Cualquier cambio breaking se coordina entre Samuel y Cristian.
- OpenAPI es la fuente de verdad para REST.
- `websocket.ts` es la fuente de verdad para el protocolo WS.
- No forzar el protocolo WS dentro de OpenAPI solo para conseguir generación automática.
- Los tipos Python de WS deben mantenerse alineados con `websocket.ts`.
- Deben existir tests de contrato que detecten divergencias.

## Consecuencias
- El backend valida mensajes WS con Pydantic v2 alineado a `websocket.ts`, no con schemas OpenAPI.
- ADR-0001 describe la decisión de canal único; los nombres de mensaje vigentes son los de `websocket.ts` (`agent_turn_complete`, `run_code`, `code_execution_result`, etc.).
- Un cambio de campo en la sala exige actualizar `websocket.ts` de común acuerdo antes de implementar backend o frontend.
