# Phase 15 — Evidence Completeness, Coverage & Missing-Evidence Analysis

## 1. Objective

Phase 15 introduces a deterministic Evidence Completeness & Coverage layer to EvidenceGraph.
It systematically evaluates:
> *"What evidence should reasonably exist for this payment lifecycle, what evidence has actually been observed, what evidence is missing, and what can we legitimately conclude from that absence?"*

### Fundamental Invariant
**Absence of evidence $\neq$ Evidence of absence.**
- EvidenceGraph evaluates **Evidence Coverage**, NOT payment legitimacy or fraud.
- Missing evidence is never asserted as a negative real-world fact (e.g. *"Authorization evidence was not observed"* ✅ instead of *"Authorization did not happen"* ❌).

---

## 2. Evidence Profiles

An `EvidenceProfile` defines which evidence categories are expected or applicable for a specific payment lifecycle.

- **`STANDARD_PAYMENT_PROFILE_V1`** (v1.0, Methodology: `ECS-1.0`):
  Applicable to standard Razorpay online payments. Defines expectations for creation, amount, currency, payment method, authorization, capture, order linkage, customer linkage, failure diagnostics, and refund reversal records.
- **`PROFILE_UNKNOWN`**:
  Deterministic fallback when no valid payment context exists. The system returns status `UNKNOWN` rather than guessing a profile.

---

## 3. Requirement Model & Types

Each requirement under an evidence profile is explicitly classified into one of 5 requirement types:
- `REQUIRED`: Evidence is mandatory for canonical completeness evaluation.
- `EXPECTED`: Normally expected in typical payment lifecycles, but absence does not invalidate the entire evaluation.
- `OPTIONAL`: Enriching metadata (e.g. Order ID, Customer ID).
- `CONDITIONAL`: Becomes expected or required only if a specific lifecycle signal occurs (e.g. capture record when captured, refund reversal record when refunded, failure reason when failed).
- `NOT_APPLICABLE`: Requirement does not apply in the current payment context.

---

## 4. Applicability & Determinism

Conditional applicability is strictly deterministic:
- **`REQ_PAYMENT_CAPTURED`**: `REQUIRED` if payment status is `captured`, `captured=True`, or capture fact exists; otherwise `NOT_APPLICABLE`.
- **`REQ_REFUND_RECORD`**: `REQUIRED` if status includes `refund` or refund fact exists; otherwise `NOT_APPLICABLE`.
- **`REQ_FAILURE_REASON`**: `REQUIRED` if status is `failed` or failure fact exists; otherwise `NOT_APPLICABLE`.

---

## 5. Coverage States & Status Aggregation

For every requirement, expected state is compared against observed state:
- `PRESENT`: Authoritative reconciled `EvidenceFact` observed.
- `MISSING`: Expected requirement searched within temporal scope and not found.
- `PARTIAL`: Observations observed but not yet reconciled into a Fact or inactive fact.
- `CONFLICTED`: Evidence present but open contradiction detected by Phase 8.
- `NOT_APPLICABLE`: Requirement not applicable.
- `UNKNOWN`: Cannot determine applicability or evidence state.

### Overall Snapshot Status:
- `COMPLETE`: All applicable `REQUIRED` and `EXPECTED` requirements are `PRESENT` with 0 conflicts.
- `SUBSTANTIALLY_COMPLETE`: All `REQUIRED` are `PRESENT`, with minor `EXPECTED` missing.
- `PARTIAL`: Some `REQUIRED` are `MISSING` or `CONFLICTED`.
- `INSUFFICIENT`: Critical mandatory lifecycle evidence is entirely missing.
- `UNKNOWN`: Profile is `PROFILE_UNKNOWN` or zero applicable requirements.

---

## 6. Integration Across Pipeline

- **Phase 8 (Conflicts)**: Open conflicts yield `CONFLICTED` requirement states.
- **Phase 10 (Audit Traces)**: Coverage snapshots link to versioned methodology and profile version.
- **Phase 11 (Temporal Evolution)**: Historical coverage states are recorded in chronological order.
- **Phase 12 (Investigation Engine)**: Exposes requirement states and missing evidence search scopes.
- **Phase 13 (Reconciliation Facts)**: Reasons over deduplicated `EvidenceFacts` rather than raw observation counts.
- **Phase 14 (Lineage DAG)**: Traceable path from Requirement $\rightarrow$ Fact $\rightarrow$ Observation $\rightarrow$ Webhook.

---

## 7. API Endpoints

- `GET /api/v1/payments/{payment_id}/coverage`: Point-in-time coverage snapshot, metric breakdown, requirements matrix, and missing evidence search scopes.
- `GET /api/v1/payments/{payment_id}/coverage/history`: Chronological historical coverage evaluations.
- `GET /api/v1/coverage/requirements/{requirement_id}`: Detailed specification metadata for a requirement.
- `POST /api/v1/payments/{payment_id}/coverage/recompute`: Idempotent coverage recompute.

---

## 8. Frontend Inspector

The `PaymentInspector` component provides:
1. **Coverage Status & Profile Banner**: Color-coded badge (`COMPLETE`, `SUBSTANTIALLY_COMPLETE`, `PARTIAL`, `INSUFFICIENT`).
2. **Summary Metrics Grid**: Applicable, Required Present, Required Missing, Conflicted.
3. **Requirement Matrix Table**: Requirements, Priority, Observed State, Status.
4. **Evidence Not Observed Panel**: Explaining what was expected, why, search scope, and verified lack of negative assertion.

---

## 9. Verification & Testing

27 automated unit & integration test scenarios in `backend/tests/test_coverage.py`:
- All 27 tests passing.
- Full suite (356 tests) passing without regressions.
