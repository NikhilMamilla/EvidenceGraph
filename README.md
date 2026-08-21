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

**Phase 1 — Production Foundation + Supabase Migration**

Engineering foundation is complete. Database migrated from local Docker PostgreSQL
to Supabase PostgreSQL. No payment processing or intelligence implemented yet.

---

## Architecture

```
┌─────────────────┐     HTTP      ┌──────────────────────────┐
│  React Frontend │ ────────────▶ │  FastAPI Backend          │
│  Vite + TS      │               │  /api/v1/health/live      │
│  port 5173      │               │  /api/v1/health/ready     │
└─────────────────┘               │  /api/v1/health/db-info   │
                                  └────────────┬─────────────┘
                                               │
                               ┌───────────────┼───────────────┐
                               ▼               ▼
                    ┌──────────────────┐  ┌──────────┐
                    │ Supabase         │  │  Redis   │
                    │ PostgreSQL       │  │  Docker  │
                    │ SSL / port 5432  │  │  port    │
                    └──────────────────┘  │  6379    │
                                          └──────────┘
```

The browser **never** connects directly to the database.
All database access goes through the FastAPI backend.

---

## Requirements

| Tool        | Minimum version | Notes                          |
|-------------|-----------------|--------------------------------|
| Docker      | 24.x            | Docker Compose v2 included     |
| Node.js     | 20.x            | Local frontend development     |
| Python      | 3.11+           | Local backend development      |
| Git         | 2.x             |                                |
| Supabase    | —               | Free tier project required     |

---

## Database — Supabase PostgreSQL

EvidenceGraph uses **Supabase** as its PostgreSQL provider.

### Getting your connection string

1. Go to [supabase.com](https://supabase.com) → your project
2. Click **Project Settings** → **Database**
3. Scroll to **Connection string** → select **URI** tab
4. Copy the **Direct connection** string (port 5432)
5. It looks like:
   ```
   postgresql://postgres:[YOUR-PASSWORD]@db.[PROJECT-REF].supabase.co:5432/postgres
   ```
6. Append `?sslmode=require` for SSL enforcement
7. Paste into your `.env` as `DATABASE_URL`

### SSL

All connections use `sslmode=require`. Supabase enforces SSL by default.

For maximum security (`verify-full`), download the CA certificate from
**Supabase Dashboard → Settings → Database → SSL Certificate** and configure:
```
DATABASE_URL=postgresql://...?sslmode=verify-full&sslrootcert=certs/supabase-ca.crt
```

---

## Environment

Copy `.env.example` to `.env` and fill in your values:

```bash
cp .env.example .env
```

| Variable                  | Required     | Description                                    |
|---------------------------|--------------|------------------------------------------------|
| `DATABASE_URL`            | **Yes**      | Supabase PostgreSQL URI with `?sslmode=require`|
| `REDIS_URL`               | **Yes**      | Redis connection (default: local Docker)       |
| `APP_ENV`                 | No           | `development` / `staging` / `production`       |
| `CORS_ORIGINS`            | No           | Comma-separated allowed frontend origins       |
| `LOG_LEVEL`               | No           | `DEBUG` / `INFO` / `WARNING` / `ERROR`         |
| `RAZORPAY_KEY_ID`         | No (Phase 1) | Set in later phases                            |
| `RAZORPAY_KEY_SECRET`     | No (Phase 1) | Set in later phases                            |
| `RAZORPAY_WEBHOOK_SECRET` | No (Phase 1) | Set in later phases                            |

### Security

- Credentials live in `.env` only — never in source code, docker-compose, or README
- `.env` is in `.gitignore` and must never be committed
- `.env.example` contains placeholder values only

---

## Run

### Docker Compose (recommended)

```bash
# Make sure .env has your Supabase DATABASE_URL
docker-compose up --build
```

| Service    | URL                        |
|------------|--------------------------- |
| Frontend   | http://localhost:5173       |
| Backend    | http://localhost:8000       |
| API Docs   | http://localhost:8000/docs  |

### Local development

Start Redis only via Docker:

```bash
docker-compose up -d redis
```

Backend (inside virtual environment):

```bash
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1        # Windows PowerShell
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Frontend:

```bash
cd frontend
npm install
npm run dev
```

---

## Test

### Backend tests

```bash
cd backend
.venv\Scripts\Activate.ps1
python -m pytest tests/ -v
```

### Frontend tests

```bash
cd frontend
npm run test
```

---

## Health Checks

### Liveness — `GET /api/v1/health/live`

Confirms the process is running.

```bash
curl http://localhost:8000/api/v1/health/live
```
```json
{"status": "ok", "service": "evidencegraph-api"}
```

### Readiness — `GET /api/v1/health/ready`

Verifies Supabase PostgreSQL **and** Redis are reachable.

```bash
curl http://localhost:8000/api/v1/health/ready
```
```json
{"status": "ready", "database": "connected", "redis": "connected"}
```

### Database verification — `GET /api/v1/health/db-info`

Confirms the backend is connected to the correct Supabase project.
Returns safe metadata only — no credentials.

```bash
curl http://localhost:8000/api/v1/health/db-info
```
```json
{
  "status": "ok",
  "database_info": {
    "pg_version": "PostgreSQL 15.x",
    "database": "postgres",
    "user": "postgres",
    "host": "..."
  }
}
```

---

## Project Structure

```
EvidenceGraph/
├── backend/
│   ├── app/
│   │   ├── api/v1/       # health endpoints
│   │   ├── core/         # config, logging, middleware, errors
│   │   ├── db/           # SQLAlchemy engine + session (Supabase)
│   │   ├── models/       # business models (Phase 2+)
│   │   ├── schemas/      # Pydantic response schemas
│   │   ├── services/     # Redis client
│   │   └── main.py
│   ├── alembic/          # migration infrastructure
│   ├── tests/
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   ├── lib/api/      # API client abstraction
│   │   └── test/
│   └── package.json
├── infrastructure/docker/
├── docs/
├── docker-compose.yml    # redis + backend + frontend (no local postgres)
├── .env.example
└── README.md
```

---

## What is NOT implemented yet

- Razorpay webhook ingestion
- Payment event processing
- Evidence extraction or graph construction
- Evidence Integrity Score
- Risk scoring or fraud detection
- ML / LLM components
- Authentication / authorisation
