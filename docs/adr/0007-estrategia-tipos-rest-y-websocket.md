# ADR 0007: Estrategia de Tipos Python para REST y WebSocket

## Estado
Aceptado

## Contexto
El frontend genera TypeScript desde OpenAPI (`openapi-typescript`). El backend ya escribe Pydantic v2 a mano en `apps/api/src/api/schemas/`. Meter el protocolo WS en OpenAPI solo para generar tipos rompería ADR-0005. Copiar uniones TypeScript a Python sin tests dejaría drift.

## Decisión
REST:

```text
openapi.json
    ├──► TypeScript (generado, responsabilidad de contracts)
    └──► Pydantic/backend (manual, alineado, con tests de contrato)
```

WebSocket:

```text
websocket.ts
    ├──► TypeScript/frontend
    └──► Pydantic/backend equivalente (manual, discriminado por `type`)
```

- No implementar generación automática de WS desde OpenAPI.
- No copiar tipos manualmente sin una validación que detecte divergencias.
- No instalar ni ejecutar generadores de Pydantic en esta fase.
- Los schemas Python de REST y WS viven junto al patrón existente (`apps/api/src/api/schemas/`), no en un árbol paralelo.

## Consecuencias
- Los enums públicos de ejecución WS/REST (`success`, `test_failure`, …) son distintos del enum interno del sandbox (`accepted`, `wrong_answer`, …) y se mapean en un servicio de aplicación.
- Un test de contrato debe fallar si `websocket.ts` o `openapi.json` cambian literales que el backend afirma soportar.
