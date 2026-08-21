# EvidenceGraph

**Real-Time Payment-Risk Evidence Intelligence Platform**

> Razorpay AI Builder Internship 2026

---

## Problem

Payment-risk systems assign a risk score from multiple signals, but they do not
explain how **trustworthy**, **independent**, **fresh**, **consistent**, or
**historically reliable** the evidence behind that decision actually is.

EvidenceGraph will analyse the evidence layer itself — not just the score —
giving operators an *Evidence Integrity Score* they can act on, audit, and
reconcile against real payment outcomes over time.

---

## Current Phase

**Phase 1 — Production Foundation**

This phase establishes the complete engineering foundation. No payment
processing, evidence intelligence, or risk-scoring is implemented yet.

---

## Architecture (Phase 1)

```
┌─────────────────┐     HTTP      ┌──────────────────────┐
│  React Frontend │ ──────────── ▶│  FastAPI Backend      │
│  (Vite + TS)    │               │  /api/v1/health/live  │
│  port 5173      │               │  /api/v1/health/ready │
└─────────────────┘               └──────────┬────────────┘
                                             │
                              ┌──────────────┼──────────────┐
                              ▼              ▼              
                     ┌──────────────┐  ┌──────────┐
                     │  PostgreSQL  │  │  Redis   │
                     │  port 5432   │  │ port 6379│
                     └──────────────┘  └──────────┘
```

---

## Requirements

| Tool        | Minimum version | Notes                             |
|-------------|-----------------|-----------------------------------|
| Docker      | 24.x            | Docker Compose v2 included        |
| Node.js     | 20.x            | For local frontend development    |
| Python      | 3.12            | For local backend development     |
| Git         | 2.x             |                                   |

---

## Setup

### 1 — Clone

```bash
git clone <repo-url>
cd EvidenceGraph
```

### 2 — Environment

```bash
cp .env.example .env
```

Edit `.env` with your values. For local Docker development the defaults work
without changes. See the [Environment](#environment) section for details.

---

## Environment

| Variable                 | Required        | Default                                               | Description                                    |
|--------------------------|-----------------|-------------------------------------------------------|------------------------------------------------|
| `APP_ENV`                | No              | `development`                                         | `development` / `staging` / `production`       |
| `APP_NAME`               | No              | `evidencegraph-api`                                   | Service name in logs                           |
| `BACKEND_PORT`           | No              | `8000`                                                | Exposed backend port                           |
| `FRONTEND_PORT`          | No              | `5173`                                                | Exposed frontend port                          |
| `DATABASE_URL`           | **Yes**         | `postgresql://postgres:postgres@localhost:5432/evidencegraph` | PostgreSQL connection string      |
| `REDIS_URL`              | **Yes**         | `redis://localhost:6379/0`                            | Redis connection string                        |
| `CORS_ORIGINS`           | No              | `http://localhost:5173,http://localhost:3000`         | Comma-separated allowed origins                |
| `LOG_LEVEL`              | No              | `INFO`                                                | `DEBUG` / `INFO` / `WARNING` / `ERROR`         |
| `RAZORPAY_KEY_ID`        | No (Phase 1)    | *(empty)*                                             | Razorpay API key — used in a later phase       |
| `RAZORPAY_KEY_SECRET`    | No (Phase 1)    | *(empty)*                                             | Razorpay secret — used in a later phase        |
| `RAZORPAY_WEBHOOK_SECRET`| No (Phase 1)    | *(empty)*                                             | Razorpay webhook HMAC secret — later phase     |

> Razorpay credentials are **not required** for Phase 1. The backend starts
> without them and clearly marks them as unconfigured in startup logs.

---

## Run

### Docker Compose (recommended)

Starts all four services (frontend, backend, postgres, redis):

```bash
docker-compose up --build
```

Or detached:

```bash
docker-compose up --build -d
```

| Service    | URL                         |
|------------|---------------------------  |
| Frontend   | http://localhost:5173        |
| Backend    | http://localhost:8000        |
| API Docs   | http://localhost:8000/docs   |

### Local development (services outside Docker)

Start only the infrastructure containers:

```bash
docker-compose up -d postgres redis
```

Backend:

```bash
cd backend
pip install -r requirements.txt
cp ../.env.example ../.env   # or reuse existing
uvicorn app.main:app --reload --port 8000
```

Frontend:

```bash
cd frontend
npm install
npm run dev
```

### Makefile shortcuts

```bash
make dev            # docker-compose up --build
make dev-local      # start infra only, print local run instructions
make stop           # docker-compose down
make logs           # tail compose logs
make clean          # remove containers + volumes
```

---

## Test

### Backend

```bash
cd backend
pip install -r requirements.txt
pytest tests/ -v
```

Or via Make:

```bash
make test-backend
```

### Frontend

```bash
cd frontend
npm install
npm run test
```

Or via Make:

```bash
make test-frontend
```

### All

```bash
make test
```

---

## Lint / Format

```bash
make lint          # ruff + mypy (backend) + eslint (frontend)
make lint-backend
make lint-frontend
make format        # ruff format + ruff --fix (backend only)
```

---

## Health Checks

### Liveness — `GET /api/v1/health/live`

Confirms the API process is running.

```bash
curl http://localhost:8000/api/v1/health/live
```

```json
{
  "status": "ok",
  "service": "evidencegraph-api"
}
```

### Readiness — `GET /api/v1/health/ready`

Verifies that PostgreSQL **and** Redis are reachable.
Returns `200` only when both pass. Returns `503` with failure detail otherwise.

```bash
curl http://localhost:8000/api/v1/health/ready
```

**Healthy:**
```json
{
  "status": "ready",
  "database": "connected",
  "redis": "connected"
}
```

**Degraded (e.g. Redis down):**
```json
{
  "status": "not_ready",
  "database": "connected",
  "redis": "unavailable",
  "error": {
    "code": "SERVICE_UNAVAILABLE",
    "message": "Unavailable: Redis"
  }
}
```

### Quick check via Make

```bash
make health
```

---

## Project Structure

```
EvidenceGraph/
├── backend/
│   ├── app/
│   │   ├── api/v1/          # Route handlers
│   │   ├── core/            # Config, logging, middleware, errors
│   │   ├── db/              # SQLAlchemy engine + session
│   │   ├── models/          # Business models (Phase 2+)
│   │   ├── schemas/         # Pydantic response schemas
│   │   ├── services/        # Redis client (Phase 2+ business services)
│   │   └── main.py          # FastAPI application factory
│   ├── alembic/             # Database migration infrastructure
│   ├── tests/               # Automated tests
│   ├── Dockerfile
│   ├── alembic.ini
│   ├── pytest.ini
│   └── requirements.txt
│
├── frontend/
│   ├── src/
│   │   ├── components/      # React components
│   │   ├── lib/api/         # API client abstraction
│   │   └── test/            # Vitest tests
│   ├── Dockerfile
│   ├── nginx.conf
│   └── package.json
│
├── infrastructure/
│   └── docker/              # Future: production overrides, k8s, terraform
│
├── docs/
│   └── phase-1-foundation.md
│
├── Architecture-diagrams/   # System architecture images
├── docker-compose.yml
├── .env.example
├── .gitignore
├── Makefile
└── README.md
```

---

## Security Notes

- Secrets are loaded from `.env` exclusively — never hardcoded.
- `.env` is in `.gitignore` — never committed.
- CORS is configured from `CORS_ORIGINS` — wildcard (`*`) is not used.
- Error responses never expose stack traces, credentials, or internal paths.
- Docker containers run as non-root users.
- Dependency versions are pinned.

---

## What is NOT implemented (Phase 1)

- Razorpay webhook ingestion
- Payment event processing
- Evidence extraction or graph construction
- Evidence Integrity Score
- Risk scoring or fraud detection
- ML / LLM components
- Authentication / authorisation
- Alert engine

These are implemented in subsequent phases.
