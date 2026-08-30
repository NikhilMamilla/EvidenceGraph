# Operations Runbook — EvidenceGraph Production & Demo Operations

## 1. Overview & Service Architecture

EvidenceGraph consists of:
1. **Frontend**: React 18 / Vite / TypeScript application serving the Operations Dashboard, Investigation View, and Payment Inspector on port 5173.
2. **Backend API**: FastAPI application on port 8000 handling REST routes, webhook signature validation, and analytical engines.
3. **Background Worker**: Thread/daemon processing Redis-queued webhook events into canonical entities and evidence observations.
4. **Data Infrastructure**:
   - **PostgreSQL (Supabase)**: Authoritative, immutable relational storage.
   - **Redis**: Low-latency event queue (`evidencegraph:webhook_events`) and live notification channel.

---

## 2. Startup & Deployment

### 2.1 Standard Docker Deployment
```bash
# Verify .env contains DATABASE_URL, REDIS_URL, and RAZORPAY credentials
docker compose build
docker compose up -d
```

### 2.2 Local Development Startup
```bash
# Terminal 1: Redis
docker compose up -d redis

# Terminal 2: Backend & Worker
cd backend
.venv\Scripts\Activate.ps1
python -m uvicorn app.main:app --reload --port 8000

# Terminal 3: Frontend
cd frontend
npm run dev
```

---

## 3. Health Checks & Diagnostic Probes

- **Liveness Probe**: `GET http://localhost:8000/api/v1/health/live`
  - Expected: `{"status": "ok", "service": "evidencegraph-api"}` (200 OK)
- **Readiness Probe**: `GET http://localhost:8000/api/v1/health/ready`
  - Expected: `{"status": "ready", "database": "connected", "redis": "connected"}` (200 OK)
  - Returns `503 Service Unavailable` if PostgreSQL or Redis is disconnected.
- **Operational Health**: `GET http://localhost:8000/api/v1/operations/health`
  - Provides multi-component health states and methodology version (`EOI-1.0`).

---

## 4. Failure Recovery Procedures

### 4.1 Worker Failure / Thread Stoppage
- **Symptom**: `GET /api/v1/operations/health` reports `WORKER: UNHEALTHY`. Queue depth in Redis accumulates.
- **Impact**: Webhooks continue to persist safely in PostgreSQL; event processing pauses. **Zero data loss**.
- **Action**: Restart FastAPI process or call worker initialization. The worker drains the pending backlog upon startup.

### 4.2 Redis Disconnection / Outage
- **Symptom**: `GET /api/v1/operations/health` reports `REDIS: UNHEALTHY` and system health degrades to `DEGRADED`.
- **Impact**: Webhooks persist durably in PostgreSQL with `processing_status = 'RECEIVED'`.
- **Action**: Restart Redis container (`docker compose restart redis`). The worker polling loop reconnects and resumes queue drainage.

### 4.3 Database Connection Pool Saturation
- **Symptom**: High response times or `DATABASE: UNHEALTHY`.
- **Action**: Check Supabase pooler connections and verify `pool_size` settings in `backend/app/db/session.py`.

---

## 5. Security & Sensitive Data Handling

- **Zero Exposure**: Under no circumstances should database passwords, Redis URLs, Razorpay webhook secrets, or cardholder PAN/CVV appear in logs or error messages.
- **Log Sanitation**: Structured JSON logging uses `python-json-logger` with automatic token redaction.
