# Phase 19 — EvidenceGraph Operational Intelligence & Continuous Verification

## 1. Executive Summary & Core Objective

EvidenceGraph operates across two complementary planes of truth:
1. **Domain Truth**: What payment evidence, facts, corroborations, contradictions, coverage requirements, reliability assessments, and integrity snapshots state about real-world payment transactions.
2. **System Truth**: Whether EvidenceGraph itself is currently healthy, reachable, durably persisting webhooks, processing event queues, keeping downstream analytical layers synchronized with new evidence, and upholding system invariants in real time.

Phase 19 establishes the **Authoritative Operational Intelligence & Continuous Verification Layer** (`EOI-1.0`). It exposes real-time runtime state and verifiable invariants with **zero fake dashboards, zero simulated health metrics, and zero hardcoded production statistics**.

---

## 2. Unified System Health Model & Health States

Health states are formally defined:
- `HEALTHY`: All dependencies and processing pipelines are reachable, responsive, and within configured latency/queue thresholds.
- `DEGRADED`: System remains operational, but one or more non-critical components (e.g. high Redis queue depth, intermittent processing failures, or elevated lag) require attention.
- `UNHEALTHY`: Critical dependency failure (e.g., PostgreSQL connection pool unreachable, background worker thread terminated, or stuck event backlog exceeding critical threshold).
- `UNKNOWN`: Dependency or pipeline state could not be verified deterministically.

### Component Breakdown
Monitored system components:
- `DATABASE`: PostgreSQL pool responsiveness and query execution.
- `REDIS`: Ingestion queue broker reachability and queue depth.
- `WORKER`: Webhook background worker thread liveness and polling status.
- `INGESTION`: Webhook verification, duplicate rate, and rejection telemetry.
- `NORMALIZATION & EVIDENCE_PROCESSING`: Payload transformation, observation extraction, and stuck event detection.
- `RECONCILIATION`: Fact synthesis and multi-source corroboration status.
- `COVERAGE`: Completeness requirement evaluation status.
- `RELIABILITY`: Uncertainty boundary calibration status.
- `INTEGRITY`: Decision trace generation and methodology verification.
- `REPLAY`: Decision state reproducibility and differential verification engine.

---

## 3. Liveness vs. Readiness vs. Operational Health

EvidenceGraph maintains explicit semantic distinction across its health probe tiers:
- **Liveness (`GET /health/live`)**: Indicates whether the FastAPI process is alive and receiving HTTP traffic.
- **Readiness (`GET /health/ready`)**: Indicates whether mandatory infrastructure dependencies (Supabase PostgreSQL + Redis) are connected and ready for traffic (returns 503 if either dependency is unreachable).
- **Operational Health (`GET /api/v1/operations/health`)**: Full multidimensional inspection across all 10 system components, checking thread liveness, stuck event queues, and error rates.

---

## 4. Processing Lag & Evidence/Analytical Freshness

### A. Processing Lag
Processing lag is computed from real event timestamps:
$$\text{Lag} = \text{processed\_at} - \text{received\_at}$$
Distinguishes between provider event age and server processing latency.

### B. Analytical Freshness & Stale Analysis Detection
Downstream analytical layers (Reconciliation, Coverage, Reliability, Integrity) compare the latest evidence observation timestamp against the evaluation timestamp of each snapshot:
- When $\text{observed\_at} \le \text{evaluated\_at}$: Layer is **`CURRENT`**.
- When new evidence arrives with $\text{observed\_at} > \text{evaluated\_at}$: Layer explicitly reports **`STALE`** (`ANALYSIS_STALE`), with exact seconds of staleness surfaced, rather than falsely presenting outdated analysis as current.

### C. Pipeline Watermark
The **Pipeline Watermark** is the conservative minimum completed timestamp across all downstream stages:
$$\text{Watermark} = \min(\text{proc\_time}, \text{obs\_time}, \text{fact\_time}, \text{cov\_time}, \text{rel\_time}, \text{int\_time})$$

---

## 5. Continuous Verification & System Invariants

The continuous verification runner (`POST /api/v1/operations/verify`) automatically evaluates the 10 System Invariants:

| Invariant ID | Name | Formal Specification |
| :--- | :--- | :--- |
| **`INVARIANT_SYS_01`** | **Durable Webhook Persistence** | Every accepted webhook has durable persistence in PostgreSQL prior to worker processing. |
| **`INVARIANT_SYS_02`** | **Explicit Processing State** | 100% of persisted webhook events possess an explicit `processing_status`. |
| **`INVARIANT_SYS_03`** | **Canonical Lineage Linkage** | Processed payment events maintain deterministic lineage links to observations and upstream webhooks. |
| **`INVARIANT_SYS_04`** | **Duplicate Semantic Idempotency** | Duplicate provider events do not create duplicate semantic facts or inflate corroboration. |
| **`INVARIANT_SYS_05`** | **Observable Processing Failures** | Processing exceptions are recorded in `processing_error` and surfaced in metrics and incidents. |
| **`INVARIANT_SYS_06`** | **Evidence Immutability** | Observations, facts, and decision traces adhere to append-only immutability contracts. |
| **`INVARIANT_SYS_07`** | **Measurable Analytical Freshness** | Freshness delta is calculated between evidence observation and analytical evaluation. |
| **`INVARIANT_SYS_08`** | **Real Dependency Verification** | Health endpoints perform active connection probes and never fabricate dependency availability. |
| **`INVARIANT_SYS_09`** | **Sensitive Data Protection** | Credentials, Redis URLs, webhook secrets, and stack traces are excluded from operational responses. |
| **`INVARIANT_SYS_10`** | **Stale State Differentiation** | Stale analytical results are explicitly distinguishable from current evaluations. |

---

## 6. Operational Incidents & Timeline

The incident detection engine discovers active and historical operational incidents across categories:
- `DATABASE_FAILURE`
- `QUEUE_BACKLOG`
- `WORKER_FAILURE`
- `PROCESSING_FAILURE`
- `ANALYSIS_STALE`
- `RECONCILIATION_BACKLOG`

---

## 7. API Reference

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/api/v1/operations/health` | Multi-component operational health and overall state |
| `GET` | `/api/v1/operations/metrics` | Real-time queue depth, processing lag, event counters, and active entities |
| `GET` | `/api/v1/operations/pipeline` | Pipeline stage statuses, stage watermarks, and catch-up status |
| `POST` | `/api/v1/operations/verify` | Executes read-only continuous verification of the 10 System Invariants |
| `GET` | `/api/v1/operations/incidents` | Detected operational incidents within time window (default 24h) |
| `GET` | `/api/v1/payments/{payment_id}/operational-status` | Per-payment evidence vs analytical freshness and layer status |

---

## 8. Frontend Dashboard

- **System Operations View**: Live status badges, 6 key real-time metrics cards, 8-stage interactive pipeline visualizer, continuous invariant verification runner with PASS/WARN/FAIL indicators, and 24h operational incident timeline.
- **Payment Inspector**: Embedded "Processing & Freshness Status" card indicating whether downstream facts, coverage, reliability, and integrity are `CURRENT`, `STALE`, or `PROCESSING`.

---

## 9. Verification & Test Metrics

- **Backend Operational Intelligence Tests (`test_operations.py`)**: 19 / 19 tests passing (100%).
- **Full Backend Test Suite**: **460 / 460 tests passing** across all phases.
- **Frontend Production Build & Tests**: Clean build (`tsc -b && vite build`) and 8 / 8 Vitest unit tests passing.
- **Methodology Version**: Governed under **`EOI-1.0`** (Evidence Operational Intelligence v1.0).
