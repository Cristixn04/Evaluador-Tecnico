API_DIR := apps/api
VENV_BIN := $(shell if [ -x "$$(pwd)/$(API_DIR)/.venv/bin/pytest" ]; then echo "$$(pwd)/$(API_DIR)/.venv/bin/"; elif [ -x "$$(pwd)/.venv/bin/pytest" ]; then echo "$$(pwd)/.venv/bin/"; else echo ""; fi)
PYTHON ?= $(VENV_BIN)python
PYTEST ?= $(VENV_BIN)pytest
UVICORN ?= $(VENV_BIN)uvicorn
RUFF ?= $(VENV_BIN)ruff
MYPY ?= $(VENV_BIN)mypy

.PHONY: help dev dev-web dev-api docker-up docker-down update-contracts test test-api test-web lint-api lint install

help: ## Muestra la ayuda de comandos disponibles
	@echo "Comandos disponibles en el monorepo:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

install: ## Instala dependencias en frontend y backend
	@echo "==> Instalando dependencias en apps/web..."
	@cd apps/web && pnpm install
	@echo "==> Instalando dependencias en packages/contracts..."
	@cd packages/contracts && pnpm install

docker-up: ## Inicia los servicios de infraestructura (PostgreSQL 16 y Redis)
	docker compose -f infra/docker-compose.yml up -d

docker-down: ## Detiene los servicios de infraestructura
	docker compose -f infra/docker-compose.yml down

dev-web: ## Inicia el servidor de desarrollo del Frontend (Next.js)
	cd apps/web && pnpm dev

dev-api: ## Inicia el servidor de desarrollo del Backend (FastAPI)
	cd $(API_DIR) && $(UVICORN) src.main:app --reload --port 8000

dev: ## Instrucciones para levantar ambos entornos en paralelo
	@echo "Para desarrollo concurrente:"
	@echo "  Terminal 1: make docker-up && make dev-api"
	@echo "  Terminal 2: make dev-web"

update-contracts: ## Genera los tipos de TypeScript desde openapi.json
	cd packages/contracts && pnpm run generate-types

test-api: ## Ejecuta las pruebas del Backend con pytest
	cd $(API_DIR) && $(PYTEST) -v

test-web: ## Ejecuta las pruebas del Frontend con vitest
	cd apps/web && pnpm test

test: test-api test-web ## Ejecuta todas las pruebas

lint-api: ## Ejecuta los linters del Backend (ruff y mypy)
	cd $(API_DIR) && $(RUFF) check src tests
	cd $(API_DIR) && $(MYPY) src

lint: lint-api ## Ejecuta linters del proyecto
