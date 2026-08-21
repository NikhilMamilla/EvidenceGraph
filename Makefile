# =============================================================================
# EvidenceGraph — Makefile
# Phase 1: Production Foundation
# =============================================================================
# All backend commands run inside the .venv virtual environment.
#
# FIRST TIME SETUP:
#   cd backend
#   python -m venv .venv
#   .venv\Scripts\activate        (Windows PowerShell)
#   pip install -r requirements.txt
#
# Usage:
#   make dev           Start full stack via Docker Compose
#   make dev-local     Start only infrastructure (postgres + redis)
#   make stop          Stop Docker Compose stack
#   make test          Run all tests (backend + frontend)
#   make test-backend  Run backend tests only
#   make test-frontend Run frontend tests only
#   make lint          Run backend linter (ruff)
#   make health        Check live and readiness endpoints
#   make logs          Tail Docker Compose logs
#   make clean         Remove containers and volumes
# =============================================================================

.PHONY: dev dev-local dev-infra stop test test-backend test-frontend \
        lint health logs clean migrate migrate-new

BACKEND_DIR  := backend
FRONTEND_DIR := frontend
BACKEND_PORT ?= 8000
COMPOSE      := docker-compose

# ---------------------------------------------------------------------------
# Venv-aware Python / pytest
# ---------------------------------------------------------------------------
VENV_PYTHON  := $(BACKEND_DIR)/.venv/Scripts/python
VENV_PYTEST  := $(BACKEND_DIR)/.venv/Scripts/pytest

# ---------------------------------------------------------------------------
# Docker Compose — full stack
# ---------------------------------------------------------------------------
dev:
	@echo "==> Starting full stack via Docker Compose..."
	$(COMPOSE) up --build

dev-detached:
	$(COMPOSE) up --build -d

stop:
	$(COMPOSE) down

logs:
	$(COMPOSE) logs -f

clean:
	$(COMPOSE) down -v --remove-orphans

# ---------------------------------------------------------------------------
# Local development (infra in Docker, services run locally)
# ---------------------------------------------------------------------------
dev-local: dev-infra
	@echo ""
	@echo "Infrastructure is up. Start services manually:"
	@echo "  Backend:  cd backend && .venv/Scripts/activate && uvicorn app.main:app --reload --port 8000"
	@echo "  Frontend: cd frontend && npm run dev"

dev-infra:
	$(COMPOSE) up -d postgres redis

# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
test: test-backend test-frontend

test-backend:
	@echo "==> Running backend tests (requires .venv activated or venv Python)..."
	$(VENV_PYTHON) -m pytest $(BACKEND_DIR)/tests/ -v --tb=short

test-frontend:
	@echo "==> Running frontend tests..."
	cd $(FRONTEND_DIR) && npm run test

# ---------------------------------------------------------------------------
# Lint
# ---------------------------------------------------------------------------
lint:
	@echo "==> Linting backend (ruff — if installed)..."
	-$(VENV_PYTHON) -m ruff check $(BACKEND_DIR)/app/ $(BACKEND_DIR)/tests/
	@echo "==> Linting frontend (eslint)..."
	cd $(FRONTEND_DIR) && npm run lint

# ---------------------------------------------------------------------------
# Database migrations
# ---------------------------------------------------------------------------
migrate:
	$(VENV_PYTHON) -m alembic -c $(BACKEND_DIR)/alembic.ini upgrade head

migrate-new:
	$(VENV_PYTHON) -m alembic -c $(BACKEND_DIR)/alembic.ini revision --autogenerate -m "$(MSG)"

# ---------------------------------------------------------------------------
# Health checks
# ---------------------------------------------------------------------------
health:
	@echo "==> Checking /api/v1/health/live ..."
	@curl -sf http://localhost:$(BACKEND_PORT)/api/v1/health/live | python -m json.tool || echo "FAILED - is the backend running?"
	@echo ""
	@echo "==> Checking /api/v1/health/ready ..."
	@curl -sf http://localhost:$(BACKEND_PORT)/api/v1/health/ready | python -m json.tool || echo "FAILED - is the backend running?"
