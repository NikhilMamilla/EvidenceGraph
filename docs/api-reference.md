# EvidenceGraph API Reference — Complete Phase 1–20 Specification

## 1. Overview & Authentication

All EvidenceGraph endpoints adhere to standard REST semantics, return typed JSON bodies, and follow standardized error envelope contracts.

- **Base URL**: `/api/v1`
- **Authentication**:
  - Public & Operator endpoints: Read-only inspection / Standard access.
  - Audit & Trace restricted endpoints: Require `X-API-Key: <ADMIN_API_KEY>` header.
- **Methodology Versioning**: Every analytical response includes an explicit version tag (e.g. `ECS-1.0`, `EOI-1.0`).

---

## 2. Standard Error Contract

All error responses return:
```json
{
  "error": {
    "code": "ERROR_CODE_STRING",
    "message": "Human-readable error description"
  }
}
```
No internal stack traces, DB credentials, or Redis URLs are ever leaked.

---

## 3. Endpoints Inventory

### 3.1 Health & Infrastructure

| Method | Endpoint | Auth | Description |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/health/live` | None | Process liveness check |
| `GET` | `/api/v1/health/ready` | None | Infrastructure readiness check (PostgreSQL + Redis) |
| `GET` | `/api/v1/health/db-info` | None | Safe database connection metadata (no credentials) |

### 3.2 Operations & Continuous Verification (Phase 19)

| Method | Endpoint | Auth | Description |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/operations/health` | None | Comprehensive multi-component operational health |
| `GET` | `/api/v1/operations/metrics` | None | Real-time queue depth, processing lag, event metrics |
| `GET` | `/api/v1/operations/pipeline` | None | 8-stage pipeline statuses and conservative watermark |
| `POST` | `/api/v1/operations/verify` | None | Runs continuous verification of 10 System Invariants |
| `GET` | `/api/v1/operations/incidents` | None | Active and recent operational incidents (default 24h) |
| `GET` | `/api/v1/payments/{payment_id}/operational-status` | None | Per-payment evidence vs analytical freshness & layer status |

### 3.3 Ingestion & Webhooks (Phase 2)

| Method | Endpoint | Auth | Description |
| :--- | :--- | :--- | :--- |
| `POST` | `/api/v1/webhooks/razorpay` | Signature | Ingests and verifies Razorpay webhook events |
| `GET` | `/api/v1/webhooks/events` | None | Lists ingested webhook events with status and timestamps |
| `GET` | `/api/v1/webhooks/events/{event_id}` | None | Detailed view of a single webhook event |

### 3.4 Canonical Payments & Orders (Phase 3)

| Method | Endpoint | Auth | Description |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/payments` | None | Lists canonical payments with latest state |
| `GET` | `/api/v1/payments/{payment_id}` | None | Fetches single payment canonical entity |
| `GET` | `/api/v1/payments/{payment_id}/events` | None | Fetches payment details and chronological event list |
| `GET` | `/api/v1/orders/{order_id}` | None | Fetches canonical order entity |

### 3.5 Evidence Observations & Quality (Phases 4, 6)

| Method | Endpoint | Auth | Description |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/evidence/observations` | None | Lists observations with source and subject filtering |
| `GET` | `/api/v1/payments/{payment_id}/evidence/timeline` | None | Chronological evidence timeline for a payment |
| `GET` | `/api/v1/quality/payments/{payment_id}` | None | Multi-dimensional evidence quality snapshot |

### 3.6 Structure, Claims & Corroboration (Phase 7)

| Method | Endpoint | Auth | Description |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/payments/{payment_id}/structure` | None | Claims, evidence groups, and corroborations |
| `POST` | `/api/v1/payments/{payment_id}/structure/recompute` | None | Recomputes claims structure from latest observations |

### 3.7 Contradictions & Consistency (Phase 8)

| Method | Endpoint | Auth | Description |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/payments/{payment_id}/consistency` | None | Active and historical evidence conflicts |
| `POST` | `/api/v1/payments/{payment_id}/consistency/check` | None | Executes conflict evaluation engine on payment |

### 3.8 Integrity & Decision Traces (Phases 9, 10)

| Method | Endpoint | Auth | Description |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/payments/{payment_id}/integrity` | None | Composite integrity score and dimensional breakdown |
| `POST` | `/api/v1/payments/{payment_id}/integrity/compute` | None | Evaluates integrity and creates decision trace |
| `GET` | `/api/v1/payments/{payment_id}/traces` | None | Lists public trace summaries for payment |
| `GET` | `/api/v1/traces/{trace_id}` | Admin Key | Full cryptographic decision trace detail |
| `GET` | `/api/v1/traces/{trace_id}/verify` | Admin Key | Verifies cryptographic hash of trace payload |
| `GET` | `/api/v1/payments/{payment_id}/traces/chain/verify` | Admin Key | Verifies complete SHA-256 hash chain for payment |

### 3.9 Temporal Evolution & Investigation (Phases 11, 12)

| Method | Endpoint | Auth | Description |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/payments/{payment_id}/state-history` | None | Chronological snapshots of payment state evolution |
| `GET` | `/api/v1/payments/{payment_id}/changes` | None | Granular change log across evidence dimensions |
| `GET` | `/api/v1/investigation/query` | None | Multi-criteria graph investigation query |

### 3.10 Reconciliation & Identity (Phase 13)

| Method | Endpoint | Auth | Description |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/payments/{payment_id}/facts` | None | Normalized canonical facts and observation links |
| `POST` | `/api/v1/payments/{payment_id}/reconcile` | None | Runs multi-source reconciliation synthesis |

### 3.11 Lineage & Causal Explanation (Phase 14)

| Method | Endpoint | Auth | Description |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/payments/{payment_id}/lineage` | None | Full DAG lineage tree from webhook to integrity |
| `GET` | `/api/v1/payments/{payment_id}/lineage/explain` | None | Causal textual explanation of payment evolution |

### 3.12 Coverage & Reliability (Phases 15, 16)

| Method | Endpoint | Auth | Description |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/payments/{payment_id}/coverage` | None | Evidence completeness against profile schema |
| `POST` | `/api/v1/payments/{payment_id}/coverage/evaluate` | None | Evaluates coverage snapshot |
| `GET` | `/api/v1/payments/{payment_id}/reliability` | None | 7-dimension reliability scores and uncertainty bounds |
| `POST` | `/api/v1/payments/{payment_id}/reliability/assess` | None | Evaluates reliability assessment |

### 3.13 Decision Replay & Differential Analysis (Phase 18)

| Method | Endpoint | Auth | Description |
| :--- | :--- | :--- | :--- |
| `POST` | `/api/v1/payments/{payment_id}/replay` | None | Deterministically replays decision state as of timestamp $T$ |
| `POST` | `/api/v1/payments/{payment_id}/replay/diff` | None | Symmetric differential analysis between $T_1$ and $T_2$ |
| `POST` | `/api/v1/payments/{payment_id}/replay/explain` | None | Causal explanation of why decision changed between $T_1$ and $T_2$ |
