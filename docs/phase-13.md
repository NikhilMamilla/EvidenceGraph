# Phase 13 — Multi-Source Evidence Reconciliation & Evidence Identity

## 1. Objective

Phase 13 introduces a **deterministic reconciliation and identity engine** for EvidenceGraph.
It answers the fundamental real-world question:
*"Do multiple observations collected across distinct webhooks, APIs, and systems represent the same underlying payment fact, different facts, sequentially related lifecycle events, or genuine contradictions?"*

Phase 13 establishes the `EvidenceFact` — a canonical representation of a real-world event — and the `EvidenceReconciliation` — an immutable, versioned record of pairwise identity decisions between observations.

---

## 2. Core Concepts & Taxonomy

### The Evidence Pipeline
```
Raw Provider Ingestion (Webhook / API)
        ↓
Canonical PaymentEvent & WebhookEvent
        ↓
EvidenceObservation (Raw, immutable, provenance-rich)
        ↓
Phase 13 ReconciliationEngine
   ├── EvidenceFact (Normalized real-world event)
   ├── ObservationFactLink (Provenance join)
   └── EvidenceReconciliation (Pairwise identity decision)
        ↓
Claim (Propositional truth asserted by the system)
        ↓
EvidenceIntegritySnapshot & IntegrityTrace
```

### Fact vs Claim
- **EvidenceFact**: What actually happened in reality (e.g., "A payment capture event of ₹500 was observed").
- **Claim**: What the system asserts to be true (e.g., "Payment status is currently `captured`").
- A fact is an identity anchor for observations; a claim is an assertion synthesized from facts.

### Reconciliation Decision Taxonomy
| Result | Meaning | Example |
|---|---|---|
| `SAME_FACT` | Both observations describe the exact same real-world event | Webhook retry delivery of `payment.captured` |
| `DIFFERENT_FACT` | Observations describe distinct attributes or different subjects | Observation of `amount` vs observation of `method` |
| `RELATED_FACT` | Observations represent causally/sequentially linked lifecycle events | `PAYMENT_AUTHORIZED` and `PAYMENT_CAPTURED` for the same payment |
| `CONFLICTING_FACT` | Observations assert incompatible values for the same attribute | Amount observed as 50000 in one delivery and 70000 in another |
| `UNKNOWN` | Insufficient information or temporal distance to establish identity | Same value observed 10 minutes apart without shared event IDs |

---

## 3. Deterministic Decision Tree & Rules (`v1.0`)

All pairwise decisions are evaluated in strict, deterministic order:

1. **`SAME_PROVIDER_EVENT_V1`**:
   If both observations share the same `webhook_event_id` or `payment_event_id` and have the same fact type and canonical value $\rightarrow$ `SAME_FACT`.
2. **`DIFFERENT_LIFECYCLE_V1`**:
   If observations represent distinct lifecycle facts (e.g., `PAYMENT_AUTHORIZED` vs `PAYMENT_CAPTURED`) for the same payment $\rightarrow$ `RELATED_FACT`.
3. **`CONFLICTING_VALUE_V1`**:
   If observations describe the same fact type for the same payment but assert differing canonical values $\rightarrow$ `CONFLICTING_FACT`.
4. **`SAME_FACT_DIFFERENT_SOURCE_V1`**:
   If observations have the same fact type, same canonical value, distinct source mechanisms, and timestamps within `FACT_RECONCILIATION_WINDOW_SECONDS` (5.0s) $\rightarrow$ `SAME_FACT`.
5. **`TEMPORAL_AMBIGUITY_V1`**:
   If observations assert the same value for the same fact type, but timestamps are separated by $> 5.0$ seconds without shared event metadata $\rightarrow$ `UNKNOWN`.
6. **`INSUFFICIENT_INFORMATION_V1`**:
   Default fallback when observations cannot be deterministically correlated $\rightarrow$ `UNKNOWN` or `DIFFERENT_FACT`.

---

## 4. Models & Database Architecture

### `evidence_facts`
- `internal_id` (PK)
- `payment_id` (Indexed string)
- `fact_type` (e.g., `PAYMENT_CAPTURED`, `PAYMENT_AMOUNT_OBSERVED`)
- `canonical_value` (Normalized string)
- `canonical_value_hash` (SHA-256 of `payment_id|fact_type|canonical_value`)
- `status` (`ACTIVE`, `SUPERSEDED`, `INVALIDATED`, `UNRESOLVED`)
- `first_observed_at`, `last_observed_at` (UTC timestamps)
- `observation_count`, `distinct_source_count`
- `methodology_version` (`1.0`)
- **Unique Constraint**: `(payment_id, fact_type, canonical_value_hash)` ensures idempotency.

### `observation_fact_links`
- `internal_id` (PK)
- `observation_id` (FK $\rightarrow$ `evidence_observations.internal_id`)
- `fact_id` (FK $\rightarrow$ `evidence_facts.internal_id`)
- **Unique Constraint**: `(observation_id, fact_id)`

### `evidence_reconciliations`
- `internal_id` (PK)
- `observation_a_id` (FK $\rightarrow$ `evidence_observations`, always $\min(A, B)$)
- `observation_b_id` (FK $\rightarrow$ `evidence_observations`, always $\max(A, B)$)
- `result` (`SAME_FACT`, `DIFFERENT_FACT`, `RELATED_FACT`, `CONFLICTING_FACT`, `UNKNOWN`)
- `rule_id`, `rule_version` (`1.0`), `explanation`
- `fact_id` (FK $\rightarrow$ `evidence_facts`, populated for `SAME_FACT`)
- `evaluated_at` (DateTime)
- **Unique Constraint**: `(observation_a_id, observation_b_id, rule_id, rule_version)`

---

## 5. API Endpoints

All endpoints are registered under `/api/v1`:

### `GET /api/v1/facts/{fact_id}`
Returns full canonical fact details including supporting observations, source diversity breakdown, related facts, conflicts, and claims.

### `GET /api/v1/payments/{payment_id}/facts`
Lists all canonical EvidenceFacts for a payment with optional query filters:
- `fact_type` (filter by `FactType`)
- `status` (filter by `FactStatus`)
- `from_time`, `to_time`

### `GET /api/v1/observations/{observation_id}/reconciliation`
Returns the matched `EvidenceFact` and all pairwise reconciliation decisions involving the specified observation.

### `POST /api/v1/payments/{payment_id}/reconcile`
Triggers deterministic reconciliation on all observations for the specified payment.

### `POST /api/v1/reconciliation/backfill`
Runs safe, idempotent historical backfill across all payments in the database. Returns a `BackfillReportResponse`.

---

## 6. Integrations with Existing Phases

1. **Phase 7 (Corroboration)**:
   Observations from duplicate webhook deliveries sharing the same provider event ID do not inflate `distinct_sources_count` and are classified as `SAME_SOURCE_CORROBORATION`.
2. **Phase 8 (Contradictions)**:
   Pairwise `CONFLICTING_FACT` decisions bridge into `EvidenceConflict` models.
3. **Phase 12 (Investigation Graph)**:
   The investigation graph includes `FACT` nodes with `HAS_FACT` (Payment $\rightarrow$ Fact) and `OBSERVES` (Observation $\rightarrow$ Fact) edges.

---

## 7. Verification & Test Suite

File: `tests/test_reconciliation.py` (22 tests, 100% passing).
Full project test suite: 305 tests passing.
