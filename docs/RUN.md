# Running EvidenceGraph

Two ways: **Docker (one command)** or **local dev**. Both need a `.env` with a
working Supabase `DATABASE_URL` — the database is external, everything else is
containerised or local.

---

## 0. One-time setup

```bash
cp .env.example .env
#  edit .env:
#    DATABASE_URL   -> your Supabase Session Pooler URI (?sslmode=require)
#    (RAZORPAY_* are already test-mode values; leave AI_* off for now)
```

URL-encode special characters in the DB password: `@` -> `%40`, `#` -> `%23`, `%` -> `%25`.

---

## 1. Docker — one command

```bash
docker compose up --build
```

That's it. It will:

1. start Redis
2. build + start the backend, which waits for the database, runs
   `alembic upgrade head` and (first boot) seeds the 50 golden defense cases and freezes the dataset,
   then starts FastAPI
3. build the frontend and serve it through nginx, which proxies `/api/*` to the
   backend

> **If you have run the stack before this version**, the compose network config
> changed (an MTU pin — see troubleshooting). Run `docker compose down` once
> before `docker compose up --build` so the old network is recreated cleanly.
> Skipping this shows up as the backend not resolving `redis`
> (`Name or service not known`).

| Service   | URL                              |
|-----------|----------------------------------|
| Frontend  | http://localhost:5173            |
| Backend   | http://localhost:8000            |
| API docs  | http://localhost:8000/docs       |

Stop: `Ctrl+C`, then `docker compose down` (add `-v` to also drop the Redis volume).

Rebuild after code changes: `docker compose up --build`.

To skip the golden-case seed on boot: set `SEED_GOLDEN_CASES=false` in `.env`.

---

## 2. Local dev (hot reload)

```bash
# infra
docker compose up -d redis

# backend  (terminal 1)
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1          # Windows PowerShell   (source .venv/bin/activate on macOS/Linux)
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload --port 8000

# frontend (terminal 2)
cd frontend
npm install
npm run dev
```

Vite proxies `/api` to `localhost:8000`, so the app works the same as in Docker.

---

## 3. Manual test walkthrough

Once the stack is up:

```bash
# --- health -----------------------------------------------------------------
curl http://localhost:8000/api/v1/health/live
curl http://localhost:8000/api/v1/health/ready      # DB + Redis reachable

# --- seed the golden defense dataset (skip if SEED_GOLDEN_CASES was true) ---
curl -X POST http://localhost:8000/api/v1/defense/evaluation/seed

# --- inter-annotator agreement (Cohen's kappa between the two label passes) -
curl http://localhost:8000/api/v1/defense/evaluation/agreement
#  -> cohens_kappa ~0.87, "almost perfect", 5 disagreements

# --- run the deterministic baseline evaluation -----------------------------
curl -X POST http://localhost:8000/api/v1/defense/evaluation/run
#  -> accuracy ~0.92, macro_f1 ~0.92, 0 false-supported (REF_EVAL_V2, 50 cases)

# --- freeze the dataset (idempotent; the Docker image does this on boot) ---
curl -X POST http://localhost:8000/api/v1/defense/evaluation/freeze

# --- verify a single defense statement (AI layer + deterministic authority) -
curl -X POST http://localhost:8000/api/v1/defense/verify \
  -H 'Content-Type: application/json' \
  -d '{"case_id":"GOLDEN_001","defense_text":"The customer received the package on 2026-08-18 and signed for delivery."}'

# --- three-way comparison (deterministic vs test-AI vs real-LLM) -----------
curl -X POST http://localhost:8000/api/v1/defense/ai/evaluate
#  Track C shows REAL_LLM_NOT_CONFIGURED until you set a key (see below)

# --- AI provider status ---------------------------------------------------
curl http://localhost:8000/api/v1/defense/ai/status
```

In the browser (http://localhost:5173): the **AI Verify** and **Defense Eval**
tabs are the Track-02 deliverable. The rest are platform context.

### Enable a real LLM (for the AI-vs-baseline metrics)

Add to `.env`, then `docker compose up --build` (or restart the backend):

```
AI_ENABLED=true
AI_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-...
AI_ANTHROPIC_MODEL=claude-haiku-4-5      # cheap; bump to claude-opus-5 for quality

# or, Mistral:
# AI_PROVIDER=mistral
# MISTRAL_API_KEY=...
# AI_MISTRAL_MODEL=mistral-small-latest  # free-tier ok; mistral-large-latest needs a paid tier

# or, OpenAI-compatible:
# AI_PROVIDER=openai
# AI_API_KEY=sk-...
# AI_BASE_URL=https://api.openai.com/v1
# AI_MODEL=gpt-4o-mini
```

Then `POST /api/v1/defense/ai/evaluate` again — Track C now runs the real model.

---

## 4. Tests

```bash
# backend  (platform + investigation + defense verifier + security middleware)
cd backend && .venv\Scripts\Activate.ps1 && python -m pytest -q

# just the defense verifier (golden baseline + metamorphic + adversarial + AI policy)
python -m pytest tests/test_defense_verifier.py -q

# frontend
cd frontend && npm run test
```

In Docker: `docker compose run --rm backend python -m pytest -q`.

---

## 5. Troubleshooting

| Symptom | Fix |
|---|---|
| backend logs `SSL SYSCALL error: EOF detected` / `SSL connection has been closed unexpectedly` while the same `DATABASE_URL` works from your host | **MTU.** Docker Desktop (Windows/WSL2) or a VPN routes container traffic over a link smaller than 1500 bytes, so PostgreSQL's TLS handshake packets to Supabase get dropped. The compose network is pinned to **MTU 1400**; if it still fails, lower `com.docker.network.driver.mtu` to `1350` or `1280` in `docker-compose.yml`, then `docker compose down && docker compose up --build`. A `wsl --shutdown` (then restart Docker Desktop) also clears a stale WSL MTU. |
| backend logs `Name or service not known` for `redis`, `/health/ready` shows `redis: unavailable` | stale Docker network from an earlier run with different network config — `docker compose down` (removes the network) then `docker compose up --build` |
| backend exits with the `[wait_for_db] GAVE UP` checklist | the database was unreachable for 150s — work through the printed checklist (pooler URI, project not paused, MTU) |
| `docker compose build` fails in the frontend `tsc -b` step | a TypeScript error — run `cd frontend && npm run build` locally to see it |
| frontend loads but every panel says "failed to load" | backend isn't healthy yet — first boot can take ~1–2 min (cold DB + migrations); check `docker compose logs -f backend` |
| `/api/v1/defense/...` returns 404 in the browser but works on :8000 | you're on an old frontend image — `docker compose build frontend` |
| "Live Stream" tab shows `Reconnecting…` and never events | expected when no webhooks have been ingested — the header shows `Live · synced Ns ago` from the heartbeat, so the stream is healthy; it just has nothing to show |
| port 5173 / 8000 already in use | set `FRONTEND_PORT` / `BACKEND_PORT` in `.env` |
| `429 Too Many Requests` from a script hammering `/defense/*/run` or `/webhooks/*` | the in-process rate limiter (default 120/min per IP). Raise or disable with `RATE_LIMIT_PER_MINUTE` in `.env` (`0` disables). |
