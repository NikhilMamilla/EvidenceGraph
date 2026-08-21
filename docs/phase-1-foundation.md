# Phase 1 — Production Foundation

## Scope

Phase 1 establishes the engineering foundation for EvidenceGraph.
No payment processing, evidence intelligence, or risk-scoring logic is
implemented at this stage.

## What is running after Phase 1

| Component        | Technology                  | Purpose                          |
|------------------|-----------------------------|----------------------------------|
| Frontend         | React 19 + Vite + Tailwind  | System status UI                 |
| Backend API      | FastAPI 0.115 + Python 3.12 | Health endpoints, structured API |
| PostgreSQL       | postgres:16.3-alpine        | Primary datastore (empty schema) |
| Redis            | redis:7.2-alpine            | Cache / pub-sub layer (unused)   |

## Endpoints

| Endpoint                  | Description                                      |
|---------------------------|--------------------------------------------------|
| GET /api/v1/health/live   | Liveness — confirms process is running           |
| GET /api/v1/health/ready  | Readiness — verifies PostgreSQL + Redis are up   |
| GET /docs                 | OpenAPI (development only)                       |

## Design decisions

- **Vite, not Next.js** — the frontend scaffolding was already Vite-based;
  switching to Next.js would require restructuring with no Phase 1 benefit.
- **Synchronous SQLAlchemy** — psycopg2 is sufficient for Phase 1. Async
  upgrade (asyncpg) will be evaluated when query throughput requires it.
- **Single-worker uvicorn** — appropriate for Phase 1 development; production
  scaling (Gunicorn + multiple workers) is configured in a later phase.
- **No Kafka/Redpanda** — streaming infrastructure is deferred to the phase
  where Razorpay webhooks are integrated.

## Extension points for future phases

- `backend/app/models/` — business entity models (Payment, Evidence, etc.)
- `backend/app/api/v1/` — new route modules
- `backend/alembic/versions/` — schema migrations
- `backend/app/services/` — service layer (evidence analysis, scoring)
- `frontend/src/components/` — dashboard, evidence graph UI
