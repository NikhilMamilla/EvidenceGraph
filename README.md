# EvidenceGraph

**A Chargeback Defense Verifier for payment disputes — deterministic evidence verification, with an optional AI semantic layer.**

> Razorpay Buildathon — Track 02: AI Risk Manager

---

## The problem

When a cardholder disputes a payment, the merchant has to assemble a defence: a
claim ("the item was delivered on Aug 18 and signed for") plus supporting
evidence (tracking, delivery proof, payment records, customer messages).

Existing tools help merchants *collect and format* evidence packages. None of
them verify, **before submission**, whether each material claim is actually
supported by evidence that is:

- **present** — the evidence types this dispute type requires are all there
- **temporally valid** — created at or before the point in time being defended
- **non-conflicting** — no authoritative source contradicts the claim
- **independent** — not three copies of the same underlying source

Submitting an internally inconsistent or evidentially weak defence wastes the
merchant's time and loses winnable disputes.

**EvidenceGraph answers one question:** *is this defence claim supported by the
evidence — and can we prove how we reached that verdict?*

Output per claim / case:

| Label | Meaning |
|---|---|
| `SUPPORTED` | Materially supported by authoritative, temporally valid, non-conflicting, independent evidence |
| `INSUFFICIENT_EVIDENCE` | No contradiction, but a required evidence type is missing or all evidence is from one source |
| `CONTRADICTED` | At least one authoritative source materially conflicts with the claim |
| `UNKNOWN` | Not enough information to determine support or contradiction |

The deterministic engine has **final authority**. The AI layer only extracts
claims from free text and proposes which evidence is semantically relevant — it
can never override a contradiction, a temporal exclusion, or a provenance
failure, and can never upgrade a verdict to `SUPPORTED`.

Scope for the hackathon: **delivery / merchandise-not-received disputes**.

---

## Architecture

```
Merchant defence text  +  dispute reason  +  evidence items
        │
        ▼
┌───────────────────────────────┐
│  AI SEMANTIC LAYER (optional) │   AI_ENABLED=true
│  • claim extraction (LLM)     │   provider: anthropic | openai-compatible | test-stub
│  • evidence relevance match   │
│  • hallucinated-ID rejection  │
└───────────────┬───────────────┘
                ▼
┌───────────────────────────────┐
│  EVIDENCEGRAPH (deterministic — the authority)                │
│  contradiction · temporal validity · source independence      │
│  coverage/completeness · provenance · integrity computation    │
│  SHA-256 decision trace · deterministic point-in-time replay   │
└───────────────┬───────────────┘
                ▼
   SUPPORTED / INSUFFICIENT_EVIDENCE / CONTRADICTED / UNKNOWN
   + explanation + supporting/contradicting evidence IDs + audit trace
```

```
┌─────────────────┐    HTTP     ┌──────────────────────────┐
│  React frontend │ ──────────▶ │  FastAPI backend         │
│  Vite + TS      │             │  /api/v1/...             │
│  port 5173      │             └────────────┬─────────────┘
└─────────────────┘                          │
                            ┌────────────────┼────────────────┐
                            ▼                                 ▼
                 ┌──────────────────┐               ┌──────────────┐
                 │ Supabase         │               │  Redis       │
                 │ PostgreSQL (SSL) │               │  (Docker)    │
                 └──────────────────┘               └──────────────┘
```

The browser never connects to the database — all access goes through the backend.

---

## Status

| Area | State |
|---|---|
| Evidence platform (ingestion → facts → reconciliation → coverage → reliability → integrity → traces → replay → operational monitoring) | **Built.** ~30k LOC, 445 passing tests. |
| Defense verification foundation — models, deterministic reference evaluator, 20 golden test cases, evaluation harness (confusion matrix, macro-F1, per-class P/R, frozen-split protocol) | **Built.** |
| AI semantic layer — claim extraction + evidence matching, deterministic override policy, prompt-injection isolation | **Built.** Providers: native Claude (`anthropic`), OpenAI-compatible (`openai`), and a deterministic test stub. |
| Real-LLM three-way evaluation (deterministic vs test-AI vs real-LLM) with safety metrics (false-supported rate, contradiction-miss rate) | **Wired.** Runs against a real key; reports `REAL_LLM_NOT_CONFIGURED` until `AI_ENABLED=true` + a key is set. |
| Frontend | 13 tabs, all wired to real endpoints. The two defence tabs (`Defense Eval`, `AI Verify`) are the Track-02 deliverable; the rest are platform context. |

### Phase log

| Phase | Title |
|---|---|
| 1–3 | Foundation · immutable webhook ingestion · canonical payment/entity model |
| 4–6 | Evidence observation & provenance · relationship graph · quality & temporal reliability |
| 7–9 | Claims / corroboration / independence · contradiction & temporal consistency · explainable integrity computation |
| 10–12 | SHA-256 decision traces · temporal evolution · graph investigation |
| 13–16 | Multi-source reconciliation & identity · lineage & causal explanation · coverage / missing-evidence · reliability calibration & uncertainty |
| 17–19 | Adversarial evidence validation · deterministic decision replay & diff · operational intelligence & continuous verification |
| 20 | Production hardening, zero-fabrication audit, end-to-end tests |
| 21 | Defense verification foundation — golden cases, deterministic reference evaluator, evaluation harness |
| 22 | AI claim understanding & evidence matching (provider-abstracted) |
| 23 | Real-LLM evaluation, calibration & false-support safety gate |

### Not implemented (by design)

- No fraud probability / risk-score output feeds the verdict — the verdict is
  deterministic. (The `Fraud`, `Risk`, `Revenue`, `Merchant Risk` UI tabs are
  read-only analytical views over the same evidence data, not part of the
  chargeback verifier.)
- No automated submission to card networks / issuers.
- No LLM fine-tuning — prompting only.
- No authentication / RBAC beyond an admin key for restricted trace endpoints.
- The Phase 12 graph-investigation engine is currently a thin stub;
  `investigation_center` is the live path.

---

## Requirements

| Tool | Minimum | Notes |
|---|---|---|
| Python | 3.11+ | Backend |
| Node.js | 20.x | Frontend |
| Docker | 24.x | Redis (+ optional full stack) |
| Supabase | — | Free-tier PostgreSQL project |

---

## Environment

```bash
cp .env.example .env
```

| Variable | Required | Description |
|---|---|---|
| `DATABASE_URL` | **Yes** | Supabase PostgreSQL URI (Session Pooler, `?sslmode=require`) |
| `REDIS_URL` | **Yes** | Redis connection (default: local Docker) |
| `CORS_ORIGINS` | No | Comma-separated allowed frontend origins |
| `LOG_LEVEL` | No | `DEBUG` / `INFO` / `WARNING` / `ERROR` |
| `RAZORPAY_KEY_ID` / `_KEY_SECRET` / `_WEBHOOK_SECRET` | For ingestion | Razorpay **Test Mode** credentials |
| `ADMIN_API_KEY` | For trace endpoints | `X-API-Key` for restricted audit-trace / replay endpoints |
| `AI_ENABLED` | No | `false` (default) → deterministic test stub, no network |
| `AI_PROVIDER` | No | `test` (default) · `anthropic` · `openai` |
| `ANTHROPIC_API_KEY` | If `AI_PROVIDER=anthropic` | Read directly by the Claude SDK |
| `AI_ANTHROPIC_MODEL` | No | Default `claude-opus-5`; `claude-haiku-4-5` / `claude-sonnet-5` are cheaper for bulk eval runs |
| `AI_API_KEY` / `AI_BASE_URL` / `AI_MODEL` | If `AI_PROVIDER=openai` | Any OpenAI-compatible endpoint (OpenAI, OpenRouter, Groq, local) |

**Security:** `.env` is gitignored and must never be committed. `.env.example`
holds placeholders only. Rotate any secret that has been shared or reused.

---

## Run

### Local development

```bash
# infra
docker-compose up -d redis

# backend
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1          # Windows PowerShell
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# frontend
cd frontend
npm install
npm run dev
```

| Service | URL |
|---|---|
| Frontend | http://localhost:5173 |
| Backend | http://localhost:8000 |
| API docs | http://localhost:8000/docs |

### Docker Compose (full stack)

```bash
docker-compose up --build          # needs .env with a Supabase DATABASE_URL
```

---

## Test

```bash
# backend
cd backend
.venv\Scripts\Activate.ps1
python -m pytest -q                 # 445 tests

# frontend
cd frontend
npm run test
```

---

## Defense verifier — quick tour

```bash
# 1. seed the 20 golden delivery-dispute cases
curl -X POST http://localhost:8000/api/v1/defense/evaluation/seed

# 2. run the deterministic baseline evaluation
curl -X POST http://localhost:8000/api/v1/defense/evaluation/run

# 3. verify a single defence statement (AI layer + deterministic authority)
curl -X POST http://localhost:8000/api/v1/defense/verify \
  -H 'Content-Type: application/json' \
  -d '{"case_id":"GOLDEN_001","defense_text":"The customer received the package on 2026-08-18 and signed for delivery."}'

# 4. three-way comparison — deterministic vs test-AI vs real-LLM (needs AI_ENABLED=true + key for track C)
curl -X POST http://localhost:8000/api/v1/defense/ai/evaluate
```

In the UI: **AI Verify** tab → interactive demo scenarios and the three-way
evaluation panel; **Defense Eval** tab → dataset, runs, and confusion matrix.

---

## Health checks

```bash
curl http://localhost:8000/api/v1/health/live      # process liveness
curl http://localhost:8000/api/v1/health/ready     # PostgreSQL + Redis reachable
curl http://localhost:8000/api/v1/health/db-info   # safe DB metadata (no credentials)
```

---

## Epistemic axioms (enforced across the codebase)

1. **Unknown ≠ negative.** Absence of evidence is never evidence of absence — missing fields stay `UNKNOWN` / `MISSING`.
2. **Coverage ≠ reliability ≠ integrity.** Having every required field present does not make those fields reliable or internally consistent.
3. **Duplicate idempotency.** Replaying identical provider events creates zero new facts and zero corroboration inflation.
4. **Temporal immutability.** Historical evaluations and decision traces are append-only; future evidence cannot rewrite a past verdict.
5. **Zero data fabrication.** No synthetic, hardcoded, or simulated metric is ever presented as a real result. What cannot be computed is returned as `UNKNOWN`.

---

## Project layout

```
backend/
  app/
    api/v1/        # route modules (health, webhooks, defense_*, evidence, integrity, …)
    core/          # config, logging, middleware, errors
    db/            # SQLAlchemy engine + session (Supabase)
    integrations/  # Razorpay REST client, webhook signature, normalizer
    models/        # SQLAlchemy models
    schemas/       # Pydantic request/response schemas
    services/      # engines: reference evaluator, defense_verifier, ai_* providers, three_way_evaluation, …
  alembic/         # migrations
  tests/           # pytest suite
frontend/
  src/components/  # DefenseVerification, DefenseEvaluation, + platform tabs
  src/lib/api/     # typed API client
docs/              # per-phase design docs, api-reference, demo-runbook, limitations
SYSTEM_CONTRACT.md
EVIDENCEGRAPH_AI_RISK_MANAGER_EVALUATION_GATE.md   # Track-02 scoping / GO decision
```

---

## Limitations

See [`docs/limitations.md`](docs/limitations.md). In short: this is a hackathon
demonstration on Razorpay **Test Mode** events plus controlled synthetic
perturbations — not a production-validated system, and not trained on real
historical chargeback outcomes. Evaluation sets are small; per-class metrics
have wide confidence intervals. Report measured performance on a held-out set
with documented methodology — never "production-ready".
