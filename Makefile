# =============================================================================
# EvidenceGraph — Makefile  (thin wrappers around docker compose + pytest)
# =============================================================================
# The database is external (Supabase). Everything else is containerised.
#
# FIRST TIME:
#   cp .env.example .env      # then set DATABASE_URL to your Supabase URI
#   make up                   # build + start the whole stack
#
# Local dev (hot reload) needs a backend venv:
#   cd backend && python -m venv .venv
#   .venv/Scripts/activate            (Windows)   /   source .venv/bin/activate
#   pip install -r requirements.txt
#
# Targets:
#   make up | up-d | down | logs | ps | restart | clean   docker compose stack
#   make redis                                             just Redis (local dev)
#   make test | test-backend | test-frontend | test-defense
#   make lint | migrate | migrate-new MSG="..."
#   make health | seed | evaluate
# =============================================================================

.PHONY: up up-d down logs ps restart clean redis \
        test test-backend test-frontend test-defense \
        lint migrate migrate-new health seed evaluate

BACKEND_DIR   := backend
FRONTEND_DIR  := frontend
BACKEND_PORT  ?= 8000
COMPOSE       := docker compose
VENV_PYTHON   := $(BACKEND_DIR)/.venv/Scripts/python
API           := http://localhost:$(BACKEND_PORT)/api/v1

# ---------------------------------------------------------------------------
# Docker Compose — full stack (frontend + backend + redis)
# ---------------------------------------------------------------------------
up:
	$(COMPOSE) up --build

up-d:
	$(COMPOSE) up --build -d

down:
	$(COMPOSE) down

restart:
	$(COMPOSE) restart

logs:
	$(COMPOSE) logs -f

ps:
	$(COMPOSE) ps

clean:
	$(COMPOSE) down -v --remove-orphans

# Only Redis — for local dev where you run backend/frontend by hand
redis:
	$(COMPOSE) up -d redis

# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
test: test-backend test-frontend

test-backend:
	$(VENV_PYTHON) -m pytest $(BACKEND_DIR)/tests -q

test-defense:
	$(VENV_PYTHON) -m pytest $(BACKEND_DIR)/tests/test_defense_verifier.py -q

test-frontend:
	cd $(FRONTEND_DIR) && npm run test

# In Docker (no local venv needed):
#   docker compose run --rm backend python -m pytest -q

# ---------------------------------------------------------------------------
# Lint
# ---------------------------------------------------------------------------
lint:
	-$(VENV_PYTHON) -m ruff check $(BACKEND_DIR)/app $(BACKEND_DIR)/tests
	cd $(FRONTEND_DIR) && npm run lint

# ---------------------------------------------------------------------------
# Database migrations (run from backend/ with the venv active in real use)
# ---------------------------------------------------------------------------
migrate:
	cd $(BACKEND_DIR) && .venv/Scripts/python -m alembic upgrade head

migrate-new:
	cd $(BACKEND_DIR) && .venv/Scripts/python -m alembic revision --autogenerate -m "$(MSG)"

# ---------------------------------------------------------------------------
# Convenience API calls (stack must be up)
# ---------------------------------------------------------------------------
health:
	@curl -sf $(API)/health/live  && echo
	@curl -sf $(API)/health/ready && echo

seed:
	curl -X POST $(API)/defense/evaluation/seed

evaluate:
	curl -X POST $(API)/defense/evaluation/run
