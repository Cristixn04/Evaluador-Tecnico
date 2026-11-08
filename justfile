# Justfile para el monorepo Evaluador Técnico
# Proporciona recetas estandarizadas delegando limpiamente al Makefile base.
# Uso: just <receta> (ejemplo: 'just test-api', 'just dev-api', 'just help')

default:
    @just --list

# Muestra la ayuda de comandos disponibles
help:
    @make help

# Muestra instrucciones para levantar ambos entornos en paralelo
dev:
    @make dev

# Inicia el servidor de desarrollo del Backend (FastAPI con reload en puerto 8000)
dev-api:
    @make dev-api

# Inicia el servidor de desarrollo del Frontend (Next.js en puerto 3000)
dev-web:
    @make dev-web

# Inicia los servicios de infraestructura en segundo plano (PostgreSQL 16 en 5435 y Redis en 6379)
docker-up:
    @make docker-up

# Detiene los servicios de infraestructura
docker-down:
    @make docker-down

# Genera los tipos de TypeScript en packages/contracts desde openapi.json
update-contracts:
    @make update-contracts

# Ejecuta las pruebas del Backend con pytest utilizando el entorno virtual
test-api:
    @make test-api

# Ejecuta las pruebas del Frontend
test-web:
    @make test-web

# Ejecuta todas las pruebas del monorepo
test:
    @make test

# Ejecuta los linters de calidad del código backend (Ruff y Mypy)
lint:
    @make lint
