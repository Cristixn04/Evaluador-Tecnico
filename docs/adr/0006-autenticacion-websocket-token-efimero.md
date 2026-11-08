# ADR 0006: Autenticación WebSocket con Token Efímero

## Estado
Aceptado

## Contexto
La API WebSocket nativa del navegador no permite configurar libremente el header `Authorization`. Reutilizar el `access_token` de invitación como credencial permanente del socket expondría un secreto de larga duración en URLs, logs de proxy y reconexiones.

La sala necesita una sesión anónima (cero PII) ligada a una entrevista concreta, revocable, y reconectable sin perder el estado del candidato.

## Decisión
No usar `Authorization: Bearer` en el handshake WebSocket del navegador.

Flujo:

```text
access_token de invitación
        │
        ▼
GET /sessions/verify
        │
        ▼
sesión anónima válida
        │
        ▼
obtención de token WS efímero
        │
        ▼
WebSocket
```

El token WS debe:
- ser de corta duración (TTL 30 minutos, coordinado con Redis); **DR-2**
- estar asociado a una entrevista/sesión concreta (`session_id = interview.id`); **DR-3**
- tener propósito limitado al WebSocket (`purpose=ws`); **DR-1**
- poder invalidarse/rechazarse si la invitación o la entrevista dejan de ser válidas;
- no sustituir el modelo de autorización (la fila `Interview` sigue siendo la autoridad);
- no reutilizar el `access_token` de invitación como credencial permanente del socket.

El transporte debe ser compatible con el navegador. Si el token efímero viaja como query parameter, hay que redactar logs/proxies para no persistir el secreto.

### Gestión de Invitaciones y Entrevistas **DR-4, DR-5, DR-6**
- `GET /sessions/verify` crea la entrevista de forma **lazy e idempotente**: si la invitación es válida y no existe `Interview` asociada, se crea una; si ya existe, se reutiliza.
- El `access_token` de invitación se almacena **como hash** (never en texto plano). La elección del algoritmo de hash (bcrypt, Argon2, etc.) queda **pendiente** y debe alinearse con la implementación existente.
- Relación **1:1** entre `Invitation` e `Interview` (una invitación → una entrevista). **No hay borrado en cascada** desde Invitación a Interview. El comportamiento exacto de borrado (RESTRICT, SET NULL, lógica de aplicación) queda **pendiente** y debe resolverse durante la implementación según convenciones del proyecto.

### Ausencia de columnas de token WS en Interview **DR-9**
- No se añaden columnas `ws_token` ni `ws_token_hash` a la tabla `Interview`. El token WS es efímero, validado vía JWT (firma + `purpose=ws` + `session_id`) y su revocación/invalidación se coordina con Redis (TTL, lista de bloqueo si procede). El esquema de claves Redis para esta coordinación queda **pendiente** de definición técnica.

## Consecuencias
- El token de invitación autentica REST (`/sessions/verify`); el token WS autentica solo el handshake del canal en vivo.
- Una conexión ya establecida no se corta solo porque el JWT WS expire; la autorización en sesión depende del estado de `Interview`.
- Reconectar exige un token WS nuevo (re-verify) sin repetir la invitación si esta sigue vigente.
- La entrevista se crea bajo demanda en `/sessions/verify`, no en el momento de emitir la invitación.
- El hash del token de invitación permite verificación sin almacenar secretos en texto plano.

## Detalles Pendientes (Explícitamente No Resueltos)
1. **Algoritmo de hash para `access_token`**: bcrypt, Argon2 u otro — debe validarse compatibilidad con implementación existente.
2. **Esquema de claves Redis** para TTL/revocación de tokens WS — no se fija `jti`, `ws_token_hash` en Redis ni patrón de clave sin evidencia de adopción.
3. **Comportamiento de borrado** en la relación 1:1 Invitation–Interview — no se prescribe `RESTRICT` ni otro comportamiento concreto sin justificación de convenciones existentes.

(End of file - total 78 lines)