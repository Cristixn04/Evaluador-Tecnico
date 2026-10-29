#!/usr/bin/env bash
set -e

echo "=== Evaluador Técnico Backend Entrypoint ==="

# 1. Verificación segura de disponibilidad de PostgreSQL
if [ -n "$DATABASE_URL" ]; then
    python3 - << 'EOF'
import os
import sys
import time
import socket
from urllib.parse import urlparse

database_url = os.getenv("DATABASE_URL", "")
clean_url = database_url.replace("postgresql+asyncpg://", "postgresql://")
try:
    parsed = urlparse(clean_url)
    host = parsed.hostname or "localhost"
    port = parsed.port or 5432
except Exception as e:
    print(f"Advertencia: no se pudo parsear DATABASE_URL ({e}), continuando...", flush=True)
    sys.exit(0)

timeout_sec = int(os.getenv("DB_WAIT_TIMEOUT", "30"))
start = time.time()
connected = False

print(f"Verificando disponibilidad de PostgreSQL en {host}:{port} (timeout={timeout_sec}s)...", flush=True)
while time.time() - start < timeout_sec:
    try:
        with socket.create_connection((host, port), timeout=2.0):
            connected = True
            break
    except (socket.error, OSError):
        time.sleep(1.0)

if connected:
    elapsed = round(time.time() - start, 2)
    print(f"PostgreSQL disponible en {host}:{port} (en {elapsed}s).", flush=True)
else:
    print(f"Error crítico: Timeout ({timeout_sec}s) esperando disponibilidad de PostgreSQL en {host}:{port}.", file=sys.stderr, flush=True)
    sys.exit(1)
EOF
fi

# 2. Ejecución automática de migraciones Alembic antes de iniciar la API
if [ "${AUTO_MIGRATE:-1}" = "1" ]; then
    echo "Ejecutando migraciones automáticas de base de datos (alembic upgrade head)..."
    if ! alembic upgrade head; then
        echo "Error crítico: La migración de base de datos falló. Abortando arranque de API." >&2
        exit 1
    fi
    echo "Migraciones aplicadas exitosamente."
else
    echo "AUTO_MIGRATE=0: Omitiendo ejecución de migraciones en arranque."
fi

# 3. Iniciar el proceso de la aplicación
echo "Iniciando proceso principal: $@"
exec "$@"
