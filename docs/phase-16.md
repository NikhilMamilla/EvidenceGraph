# Phase 16 — Evidence Reliability Calibration & Uncertainty Boundaries

## 1. Executive Summary & Core Philosophy

In real-world payment graph architectures, "no contradiction found" and "coverage satisfied" are insufficient guarantees of truth. An entity might possess 100% required evidence, yet all observations may derive from an unverified webhook replay or a single correlated network hop. Conversely, a payment may lack optional authorization logs while its primary capture event is mathematically and cryptographically established.

Phase 16 establishes a deterministic, auditable **Evidence Reliability Calibration and Uncertainty Boundary Engine** governed by versioned methodology **`ERM-1.0`** (Evidence Reliability Methodology v1.0).

```
   ┌─────────────────────────────────────────────────────────────────────────────┐
   │                          Phase 16 Reliability Engine                        │
   ├─────────────────────────────────────────────────────────────────────────────┤
   │  ┌───────────────────────┐   ┌───────────────────────┐   ┌────────────────┐ │
   │  │ 7 Categorical Dims    │──▶│ Explicit Ceilings     │──▶│ Uncertainty    │ │
   │  │ • Source Authenticity │   │ • Floor: UNRELIABLE   │   │ Profile Matrix │ │
   │  │ • Provenance Lineage  │   │ • Ceiling: LIMITED    │   │ • ESTABLISHED  │ │
   │  │ • Entity Identity     │   │ • Ceiling: UNKNOWN    │   │ • SUPPORTED    │ │
   │  │ • Temporal Soundness  │   │ • Ceiling: MODERATE   │   │ • UNCERTAIN    │ │
   │  │ • Structural Schema   │   └───────────────────────┘   │ • CONTRADICTED │ │
   │  │ • Contradictions      │                               │ • NOT_OBSERVED │ │
   │  │ • Dependencies        │                               └────────────────┘ │
   │  └───────────────────────┘                                                  │
   └─────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Invariants & Epistemic Guardrails

1. **Rejection of Arbitrary Confidence Percentages**:
   - The engine **never** outputs synthetic probabilities like `"87% confidence"`.
   - Every rating is composed of discrete, explainable categorical states: `HIGH`, `MODERATE`, `LIMITED`, `UNRELIABLE`, `UNKNOWN`.
2. **`UNKNOWN` is a First-Class State**:
   - `UNKNOWN` is never coerced into `0.5`, `MODERATE`, or `LIMITED`.
   - Missing origin or unresolved entity links explicitly yield `UNKNOWN`.
3. **Source Authenticity $\neq$ Fact Truth**:
   - Provider HMAC authentication verifies that the transmission channel was genuine; it does **not** prove that every nested claim within the payload represents external financial reality.
4. **Coverage $\neq$ Reliability**:
   - High coverage indicates all expected evidence types have arrived. Reliability evaluates whether those present signals can be defensibly trusted.
5. **Deterministic Ceilings & Floors**:
   - If an open contradiction exists, overall state is capped at **`LIMITED`**, regardless of provider signature strength.
   - If provenance is broken (no link to raw provider event), overall state is capped at **`LIMITED`**.
   - If payload structure is invalid/malformed, overall state drops to **`UNRELIABLE`**.
   - If source is unknown or reconciliation identity unresolved, overall state is **`UNKNOWN`**.
6. **No Machine Learning, LLMs, or Risk Scoring**:
   - All evaluations are strictly rule-based, deterministic, reproducible, and explainable. No black-box customer fraud scoring.

---

## 3. The 7 Categorical Reliability Dimensions

| Dimension | Description | Valid States |
| :--- | :--- | :--- |
| **1. Source Authenticity** | Verification of data ingestion channel authenticity | `VERIFIED_PROVIDER_SOURCE`, `UNVERIFIED_SOURCE`, `UNKNOWN_SOURCE` |
| **2. Provenance Lineage** | Complete audit trail back to upstream provider event | `COMPLETE`, `PARTIAL`, `BROKEN` |
| **3. Reconciliation Identity** | Unambiguous entity fact identity across signals | `SAME_PROVIDER_EVENT`, `SAME_FACT_DIFFERENT_SOURCE`, `TEMPORAL_AMBIGUITY`, `INSUFFICIENT_INFORMATION`, `UNKNOWN` |
| **4. Temporal Soundness** | Monotonic ordering and interval validity (`valid_from` $\le$ `valid_until`) | `TEMPORALLY_SOUND`, `TEMPORALLY_AMBIGUOUS`, `TEMPORALLY_INVALID`, `OUT_OF_SEQUENCE`, `RETROACTIVE_CLAIM`, `UNKNOWN` |
| **5. Structural Integrity** | Schema conformity and canonical type completeness | `CANONICAL_FACT`, `PARTIAL_OBSERVATION`, `MALFORMED` |
| **6. Contradiction State** | Presence of active or superseded consistency conflicts | `UNCONTRADICTED`, `CONFLICTED`, `SUPERSEDED_CONFLICT` |
| **7. Dependency State** | Evaluation of correlated vs independent corroboration | `INDEPENDENT_CORROBORATION`, `DEPENDENT_REPLICATION`, `SINGLE_SOURCE`, `UNKNOWN` |

---

## 4. Uncertainty Boundaries Profile

Every evaluation produces an **Uncertainty Profile** that demarcates the system's epistemic boundaries:

| Boundary Type | Meaning | Example |
| :--- | :--- | :--- |
| **`ESTABLISHED`** | Direct, authenticated provider observation with unbroken lineage | "Webhook delivery was authenticated via configured provider HMAC secret context." |
| **`SUPPORTED`** | Structurally valid and corroborated across multiple observations | "Fact value '50000' conforms to canonical schema for PAYMENT_AMOUNT_OBSERVED." |
| **`UNCERTAIN`** | Plausible but lacking independent secondary corroboration | "Independent confirmation from a secondary banking or ledger source was not observed." |
| **`CONTRADICTED`** | Active, unadjudicated conflict detected | "Conflicting claims exist regarding the canonical state of this payment entity." |
| **`NOT_OBSERVED`** | Expected evidence omitted from ingestion | "Authorization payload missing from evidence timeline." |
| **`NOT_DETERMINABLE`** | Insufficient data to evaluate dimension | "Reconciliation identity cannot be established." |

---

## 5. API Endpoints

### 1. `GET /api/v1/facts/{fact_id}/reliability`
Evaluates reliability for an individual `EvidenceFact`.
- **Response**: `FactReliabilityResponse`

### 2. `GET /api/v1/payments/{payment_id}/reliability`
Evaluates aggregate reliability for all active facts associated with the payment.
- **Parameters**: `as_of` (optional ISO datetime for historical point-in-time assessment)
- **Response**: `PaymentReliabilityResponse`

### 3. `GET /api/v1/payments/{payment_id}/reliability/history`
Returns chronological progression of reliability evaluations.
- **Response**: `ReliabilityHistoryResponse`

### 4. `GET /api/v1/payments/{payment_id}/uncertainty`
Returns the defensive uncertainty boundary matrix.
- **Response**: `List[UncertaintyItemSchema]`

---

## 6. Frontend Integration

In `PaymentInspector.tsx`, the **Evidence Reliability & Uncertainty Calibration Panel** provides:
1. **Overall Reliability State Badge**: Distinct visual styling for `HIGH`, `MODERATE`, `LIMITED`, `UNRELIABLE`, and `UNKNOWN`.
2. **Methodology Indicator**: Explicitly flags `Methodology: ERM-1.0`.
3. **7 Dimension Cards**: Status badges and supporting evidence indicators for each evaluated dimension.
4. **"Why This Rating" Breakdown**: Side-by-side display of Supporting Factors vs Degradation Factors and Ceilings Applied.
5. **Uncertainty Boundaries Matrix**: Categorized cards for `ESTABLISHED`, `SUPPORTED`, `UNCERTAIN`, and `CONTRADICTED`.

---

## 7. Verification & Regression Metrics

- **Phase 16 Unit & Integration Tests**: 27 / 27 PASSING (`tests/test_reliability.py`)
- **Total Backend Test Suite**: 383 / 383 PASSING with 0 regressions
- **Frontend Build**: `tsc -b && vite build` succeeded in 19.54s with 0 errors
