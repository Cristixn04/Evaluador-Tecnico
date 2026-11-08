# Infraestructura Judge0 CE (Sandbox de Ejecución Aislada)

Este directorio contiene la configuración oficial y reproducible para desplegar el clúster local de **Judge0 CE v1.13.1**, requerido para la ejecución aislada y segura del código de candidatos en las pruebas de `Evaluador-Técnico` (Sprint 2 y Auditorías H-01 / S2).

---

## 1. Arquitectura de Servicios

El clúster está compuesto por 4 servicios aislados en una red bridge dedicada (`judge0-net`):

| Servicio | Imagen | Puerto | Rol | Requisitos de Seguridad |
|---|---|---|---|---|
| **`judge0-server`** | `judge0/judge0:1.13.1` | `2358:2358` | API REST HTTP para recepción de submissions y consultas de estado (`GET /about`, `POST /submissions`) | No expone acceso al host |
| **`judge0-workers`** | `judge0/judge0:1.13.1` | — | Procesa la cola de envíos en segundo plano ejecutando código en sandbox | Requiere `privileged: true` para invocar el sandbox `isolate` |
| **`judge0-db`** | `postgres:16-alpine` | `5432` (interno) | Persistencia relacional de submissions y lenguajes soportados | Aislado de la base principal `evaluador_db` |
| **`judge0-redis`** | `redis:7-alpine` | `6379` (interno) | Cola de mensajería asíncrona entre el servidor y los workers de Judge0 | Aislado del Redis principal de ARQ |

---

## 2. Restricciones y Límites Aplicados (`judge0.conf`)

- **CPU Time Limit:** 2.0s por defecto (máximo 5.0s).
- **Wall Time Limit:** 3.0s por defecto (máximo 10.0s).
- **Memory Limit:** 128,000 KB (128 MB) por defecto.
- **Max Processes / Threads:** 10 por submission (previene fork bombs).
- **Red:** `ENABLE_NETWORK=false` (cero acceso a internet o redes locales desde el código del candidato).

---

## 3. Instrucciones Operativas

### Iniciar el Clúster
```bash
docker compose -f infra/judge0/docker-compose.yml up -d
```

### Verificar Disponibilidad y Salud
```bash
curl -f http://localhost:2358/about
```
Respuesta esperada: JSON con versión `1.13.1` y estado de la plataforma.

### Detener el Clúster
```bash
docker compose -f infra/judge0/docker-compose.yml down
```

### Limpiar Volúmenes de Sandbox (Opcional)
```bash
docker compose -f infra/judge0/docker-compose.yml down -v
```
