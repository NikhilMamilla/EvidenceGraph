# EvidenceGraph — Local Operations Manual

Complete copy-paste command reference for running, testing, and operating
EvidenceGraph on Windows (PowerShell).

All paths assume the project is at:
`C:\Users\INS 3515\OneDrive\Desktop\EvidenceGraph`

---

## 1. Prerequisites — Start Infrastructure (Terminal 1)

### Start Redis via Docker

```powershell
cd "C:\Users\INS 3515\OneDrive\Desktop\EvidenceGraph"
docker-compose up -d redis
```

### Verify containers are running

```powershell
docker ps
```

### Verify Redis is responding

```powershell
docker exec -it evidencegraph_redis redis-cli ping
# Expected output: PONG
```

---

## 2. Backend — Setup & Start (Terminal 2)

### Navigate to backend and activate virtual environment

```powershell
cd "C:\Users\INS 3515\OneDrive\Desktop\EvidenceGraph\backend"
.venv\Scripts\Activate.ps1
```

### Install / verify dependencies

```powershell
python -m pip install -r requirements.txt
```

### Run all database migrations (apply all phases to Supabase)

```powershell
python -m alembic upgrade head
```

### Check current migration status

```powershell
python -m alembic current
python -m alembic history --verbose
```

### Start the backend API server (auto-reload on file changes)

```powershell
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

The API is now live at: **http://localhost:8000**  
Interactive docs: **http://localhost:8000/docs**

> **Important:** Keep this terminal open. Do not close it while using the app.

---

## 3. Frontend — Setup & Start (Terminal 3)

### Navigate to frontend and install dependencies

```powershell
cd "C:\Users\INS 3515\OneDrive\Desktop\EvidenceGraph\frontend"
npm install
```

### Start the Vite development server

```powershell
npm run dev
```

The frontend is now live at: **http://localhost:5173**

> **Important:** Keep this terminal open.

---

## 4. Run All Tests (Terminal 4)

```powershell
cd "C:\Users\INS 3515\OneDrive\Desktop\EvidenceGraph\backend"
.venv\Scripts\Activate.ps1
```

### Run the full test suite (all phases)

```powershell
python -m pytest tests/ -v
```

### Run in quiet summary mode

```powershell
python -m pytest tests/ -q --tb=short
```

### Run individual phase test files

```powershell
# Phase 2 — Webhook ingestion
python -m pytest tests/test_webhook.py -v

# Phase 4 — Evidence
python -m pytest tests/test_evidence.py -v

# Phase 5 — Relationships
python -m pytest tests/test_relationships.py -v

# Phase 6 — Quality
python -m pytest tests/test_quality.py -v

# Phase 7 — Structure
python -m pytest tests/test_structure.py -v

# Phase 8 — Contradiction
python -m pytest tests/test_contradiction.py -v

# Phase 9 — Integrity computation
python -m pytest tests/test_integrity.py -v

# Phase 10 — Decision traces & cryptographic chains
python -m pytest tests/test_trace.py -v

# Phase 11 — Temporal evolution & change intelligence
python -m pytest tests/test_evolution.py -v

# Phase 12 — Lineage & provenance
python -m pytest tests/test_lineage.py -v

# Phase 13 — Reconciliation
python -m pytest tests/test_reconciliation.py -v

# Phase 13 — Coverage completeness
python -m pytest tests/test_coverage.py -v

# Phase 14 — Reliability calibration & uncertainty
python -m pytest tests/test_reliability.py -v

# Phase 16 — Investigation
python -m pytest tests/test_investigation.py -v

# Phase 18 — Decision replay & differential analysis
python -m pytest tests/test_decision_replay.py -v

# Phase 19 — Operational intelligence & verification
python -m pytest tests/test_operations.py -v

# Phase 20 — Final E2E acceptance & invariants
python -m pytest tests/test_final_e2e.py -v

# Adversarial & edge cases
python -m pytest tests/test_adversarial.py -v
```

---

## 5. Frontend Tests & Build

```powershell
cd "C:\Users\INS 3515\OneDrive\Desktop\EvidenceGraph\frontend"
```

### Run frontend unit tests (single pass)

```powershell
npm test -- --run
```

### TypeScript type-check (no emit)

```powershell
npx tsc --noEmit
```

### Build production bundle

```powershell
npm run build
```

---

## 6. Health & System Status Checks

> Run these from any terminal once the backend is running on port 8000.

### Basic liveness probe

```powershell
Invoke-RestMethod -Uri "http://localhost:8000/api/v1/health/live" -Method Get | ConvertTo-Json -Depth 5
```

### Readiness probe (checks DB + Redis)

```powershell
Invoke-RestMethod -Uri "http://localhost:8000/api/v1/health/ready" -Method Get | ConvertTo-Json -Depth 5
```

### Database connection info

```powershell
Invoke-RestMethod -Uri "http://localhost:8000/api/v1/health/db-info" -Method Get | ConvertTo-Json -Depth 5
```

### Unified operational health (all components)

```powershell
Invoke-RestMethod -Uri "http://localhost:8000/api/v1/operations/health" -Method Get | ConvertTo-Json -Depth 5
```

### Continuous invariant verification (INV-SYS-01 through INV-SYS-10)

```powershell
Invoke-RestMethod -Uri "http://localhost:8000/api/v1/operations/verification" -Method Get | ConvertTo-Json -Depth 5
```

### Real-time throughput & Redis queue depth

```powershell
Invoke-RestMethod -Uri "http://localhost:8000/api/v1/operations/metrics" -Method Get | ConvertTo-Json -Depth 5
```

### Pipeline watermarks & stage lag

```powershell
Invoke-RestMethod -Uri "http://localhost:8000/api/v1/operations/pipeline" -Method Get | ConvertTo-Json -Depth 5
```

### Active operational incidents

```powershell
Invoke-RestMethod -Uri "http://localhost:8000/api/v1/operations/incidents" -Method Get | ConvertTo-Json -Depth 5
```

---

## 7. Send a Test Webhook Event (End-to-End Simulation)

This sends a real `payment.captured` event through the full ingestion pipeline.

> **Replace** `YOUR_WEBHOOK_SECRET` with the value of `RAZORPAY_WEBHOOK_SECRET`
> from your `.env` file before running.

```powershell
$secret = "YOUR_WEBHOOK_SECRET"

$payload = @{
    entity     = "event"
    account_id = "acc_test_01"
    event      = "payment.captured"
    contains   = @("payment")
    payload    = @{
        payment = @{
            entity = @{
                id       = "pay_test_001"
                amount   = 50000
                currency = "INR"
                status   = "captured"
                order_id = "order_test_001"
                method   = "card"
                captured = $true
                created_at = [int][double]::Parse((Get-Date -UFormat %s))
            }
        }
    }
    created_at = [int][double]::Parse((Get-Date -UFormat %s))
} | ConvertTo-Json -Depth 10 -Compress

# Compute HMAC-SHA256 signature
$hmac      = New-Object System.Security.Cryptography.HMACSHA256
$hmac.Key  = [System.Text.Encoding]::UTF8.GetBytes($secret)
$hash      = $hmac.ComputeHash([System.Text.Encoding]::UTF8.GetBytes($payload))
$signature = [System.BitConverter]::ToString($hash).Replace("-", "").ToLower()

# Send the webhook
Invoke-RestMethod `
    -Uri "http://localhost:8000/api/v1/webhooks/razorpay" `
    -Method Post `
    -Headers @{
        "X-Razorpay-Signature" = $signature
        "Content-Type"         = "application/json"
    } `
    -Body $payload
```

Expected response: `Event accepted`

---

## 8. Query All Analytical Layers for a Payment

After sending the webhook above, query every analytical layer for `pay_test_001`.

> Change `$payId` to match the payment ID you used in section 7.

```powershell
$payId = "pay_test_001"

# List all canonical payments
Invoke-RestMethod -Uri "http://localhost:8000/api/v1/payments" -Method Get | ConvertTo-Json -Depth 5

# Payment events (webhook lifecycle)
Invoke-RestMethod -Uri "http://localhost:8000/api/v1/payments/$payId/events" -Method Get | ConvertTo-Json -Depth 5

# Evidence observations
Invoke-RestMethod -Uri "http://localhost:8000/api/v1/payments/$payId/evidence/timeline" -Method Get | ConvertTo-Json -Depth 5

# Evidence relationship graph
Invoke-RestMethod -Uri "http://localhost:8000/api/v1/graph/payments/$payId" -Method Get | ConvertTo-Json -Depth 5

# Evidence quality snapshots
Invoke-RestMethod -Uri "http://localhost:8000/api/v1/quality/payments/$payId" -Method Get | ConvertTo-Json -Depth 5

# Evidence structure, claims & corroboration
Invoke-RestMethod -Uri "http://localhost:8000/api/v1/payments/$payId/structure" -Method Get | ConvertTo-Json -Depth 5

# Contradiction & temporal consistency
Invoke-RestMethod -Uri "http://localhost:8000/api/v1/payments/$payId/consistency" -Method Get | ConvertTo-Json -Depth 5

# Evidence integrity snapshot (Phase 9)
Invoke-RestMethod -Uri "http://localhost:8000/api/v1/payments/$payId/integrity" -Method Get | ConvertTo-Json -Depth 5

# Integrity history (all snapshots)
Invoke-RestMethod -Uri "http://localhost:8000/api/v1/payments/$payId/integrity/history" -Method Get | ConvertTo-Json -Depth 5

# Decision traces (Phase 10)
Invoke-RestMethod -Uri "http://localhost:8000/api/v1/payments/$payId/integrity/traces" -Method Get | ConvertTo-Json -Depth 5

# Evidence state history (Phase 11 — temporal evolution)
Invoke-RestMethod -Uri "http://localhost:8000/api/v1/payments/$payId/state-history" -Method Get | ConvertTo-Json -Depth 5

# Evidence state changes (Phase 11)
Invoke-RestMethod -Uri "http://localhost:8000/api/v1/payments/$payId/changes" -Method Get | ConvertTo-Json -Depth 5

# Trigger fresh recomputation + change detection (Phase 11)
Invoke-RestMethod -Uri "http://localhost:8000/api/v1/payments/$payId/integrity/recompute" -Method Post | ConvertTo-Json -Depth 5

# Reconciled facts (Phase 13)
Invoke-RestMethod -Uri "http://localhost:8000/api/v1/payments/$payId/facts" -Method Get | ConvertTo-Json -Depth 5

# Evidence coverage & completeness
Invoke-RestMethod -Uri "http://localhost:8000/api/v1/payments/$payId/coverage" -Method Get | ConvertTo-Json -Depth 5

# Reliability calibration & uncertainty profile
Invoke-RestMethod -Uri "http://localhost:8000/api/v1/payments/$payId/reliability" -Method Get | ConvertTo-Json -Depth 5

# Operational freshness status
Invoke-RestMethod -Uri "http://localhost:8000/api/v1/payments/$payId/operational-status" -Method Get | ConvertTo-Json -Depth 5

# Lineage & provenance graph
Invoke-RestMethod -Uri "http://localhost:8000/api/v1/payments/$payId/lineage" -Method Get | ConvertTo-Json -Depth 5
```

---

## 9. Admin-Only Endpoints (Require X-API-Key header)

> Replace `YOUR_ADMIN_API_KEY` with the value of `ADMIN_API_KEY` from your `.env` file.

```powershell
$adminKey = "YOUR_ADMIN_API_KEY"
$traceId  = "PASTE_TRACE_ID_HERE"   # get from /payments/{id}/integrity/traces

# Full decision trace detail
Invoke-RestMethod `
    -Uri "http://localhost:8000/api/v1/integrity/$traceId" `
    -Headers @{ "X-API-Key" = $adminKey } | ConvertTo-Json -Depth 10

# Cryptographic hash verification
Invoke-RestMethod `
    -Uri "http://localhost:8000/api/v1/integrity/$traceId/verify" `
    -Headers @{ "X-API-Key" = $adminKey } | ConvertTo-Json -Depth 5

# Per-payment hash chain verification
Invoke-RestMethod `
    -Uri "http://localhost:8000/api/v1/payments/pay_test_001/integrity/chain-verify" `
    -Headers @{ "X-API-Key" = $adminKey } | ConvertTo-Json -Depth 5

# Replay a trace (re-execute and compare)
Invoke-RestMethod `
    -Uri "http://localhost:8000/api/v1/integrity/$traceId/replay" `
    -Method Post `
    -Headers @{ "X-API-Key" = $adminKey } | ConvertTo-Json -Depth 10
```

---

## 10. Useful URLs Summary

| Service | URL | Notes |
|---|---|---|
| Frontend dashboard | http://localhost:5173 | React / Vite |
| Backend API | http://localhost:8000 | FastAPI |
| Swagger UI (interactive docs) | http://localhost:8000/docs | Try all endpoints |
| ReDoc (spec viewer) | http://localhost:8000/redoc | Read-only docs |
| PostgreSQL | Supabase cloud | See `.env` for connection string |
| Redis | localhost:6379 | Local Docker |

---

## 11. Stopping Everything

### Stop the backend (Terminal 2)
```
Ctrl+C
```

### Stop the frontend (Terminal 3)
```
Ctrl+C
```

### Stop Docker services
```powershell
cd "C:\Users\INS 3515\OneDrive\Desktop\EvidenceGraph"
docker-compose down
```

---

## 12. Common Troubleshooting

### Port 8000 already in use
```powershell
# Find what is using port 8000
netstat -ano | findstr :8000

# Kill by PID (replace 12345 with the actual PID)
taskkill /PID 12345 /F
```

### Backend not picking up new routes after code changes
The `--reload` flag handles this automatically. If it doesn't, restart uvicorn:
```powershell
# Ctrl+C in Terminal 2, then:
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### Database migrations out of sync
```powershell
cd "C:\Users\INS 3515\OneDrive\Desktop\EvidenceGraph\backend"
.venv\Scripts\Activate.ps1
python -m alembic current        # see where you are
python -m alembic upgrade head   # apply all pending migrations
```

### opencode PATH fix (one-time setup)
```powershell
# Add npm global bin to PATH permanently
[System.Environment]::SetEnvironmentVariable(
    "PATH",
    $env:PATH + ";C:\Users\INS 3515\AppData\Roaming\npm",
    "User"
)
# Then restart your terminal and run: opencode
```
