# Phase 9 — Explainable Evidence Integrity Computation Engine

## Summary

Phase 9 introduces the first complete **Evidence Integrity** computation framework for the EvidenceGraph system. It synthesises the outputs of Phases 5–8 into a single, traceable, rule-based assessment of whether the evidence available for a payment is **sufficient, independent, fresh, and internally consistent**.

Phase 9 **does not produce a fraud score, risk score, trust score, or automated decision**. It produces an evidence quality assessment for human review.

---

## What Phase 9 Computes

For each payment at a given `evaluation_time`, the engine computes five independent dimensions:

| Dimension | Source phases | What it measures |
|---|---|---|
| **Freshness** | Phase 6 | Whether observations are current, aging, or stale |
| **Source** | Phase 6 | Authority level and directness of evidence sources |
| **Independence** | Phase 7 | Distinct sources and events feeding evidence |
| **Corroboration** | Phase 7 | Whether claims have multi-source support |
| **Consistency** | Phase 8 | Presence and severity of detected contradictions |

These five dimensions are then aggregated by documented rule gates into an **overall integrity status**.

---

## Overall Integrity Statuses

| Status | Meaning |
|---|---|
| `VERY_STRONG` | Fresh, primary-source, multi-source, corroborated, no detected conflict |
| `STRONG` | Fresh, primary-source, no detected conflict — single-source is acceptable here |
| `LIMITED` | Fresh data or conflict present; evidence quality is sufficient but limited |
| `WEAK` | Stale or tertiary-source evidence |
| `INSUFFICIENT_DATA` | Zero evidence observations in scope |
| `UNRESOLVED` | One or more open conflicts with severity > INFO |

These labels describe evidence quality only. They are **not** fraud verdicts.

---

## Architecture

### New Files

```
backend/
  alembic/versions/
    20260822_0008_phase9_integrity.py       # DB migration
  app/
    models/
      integrity_types.py                    # Status constants
      integrity_methodology.py             # EIS-1.0 rule registry
      evidence_integrity.py                # SQLAlchemy snapshot model
    services/
      integrity_engine.py                  # Core computation service
    schemas/
      integrity.py                         # Pydantic response schemas
    api/v1/
      integrity.py                         # API endpoints
  tests/
    test_integrity.py                      # 50 tests, 14 test classes
docs/
  phase-9.md                              # This file
```

### Updated Files

```
app/models/__init__.py      — registers EvidenceIntegritySnapshot
app/api/v1/router.py        — mounts integrity router
app/services/webhook_worker.py — calls IntegrityEngine after Phase 8
frontend/src/components/
  PaymentInspector.tsx      — Evidence Integrity panel
```

---

## Database Schema

### `evidence_integrity_snapshots`

```sql
CREATE TABLE evidence_integrity_snapshots (
    internal_id          SERIAL PRIMARY KEY,

    -- Identity
    payment_id           VARCHAR(128)  NOT NULL,
    evaluated_at         TIMESTAMPTZ   NOT NULL,
    methodology_version  VARCHAR(16)   NOT NULL,

    -- Overall result
    overall_status       VARCHAR(32)   NOT NULL,

    -- Evidence scope
    evidence_count       INTEGER       NOT NULL DEFAULT 0,
    source_count         INTEGER       NOT NULL DEFAULT 0,
    conflict_count       INTEGER       NOT NULL DEFAULT 0,
    open_conflict_count  INTEGER       NOT NULL DEFAULT 0,

    -- Per-dimension results (JSONB {status, reason, inputs})
    freshness_result     JSONB,
    source_result        JSONB,
    independence_result  JSONB,
    corroboration_result JSONB,
    consistency_result   JSONB,

    -- Human-readable explanation and limitations
    explanation_lines    JSONB,
    limitations          JSONB,

    -- Audit
    created_at           TIMESTAMPTZ   NOT NULL DEFAULT now(),

    CONSTRAINT uq_integrity_snapshot
        UNIQUE (payment_id, evaluated_at, methodology_version)
);
```

**Design note:** The unique constraint on `(payment_id, evaluated_at, methodology_version)` enforces both idempotency (repeated computation returns the existing snapshot) and historical immutability (different `evaluated_at` values produce distinct rows that are never overwritten).

---

## Methodology: EIS-1.0

The methodology is defined as a named, versioned registry in `integrity_methodology.py`. Every rule is documented and hard-coded — no weights, no ML, no LLM.

### Aggregation Rules (EIS-1.0)

Applied in priority order, top rule wins (short-circuit — gates after the
first firing gate are not executed). Implemented verbatim in
`IntegrityEngine._aggregate_status_detailed`, which also emits a rule-execution
record for every gate that actually ran:

| Priority | Condition | Resulting status |
|---|---|---|
| 1 | `evidence_count == 0` | `INSUFFICIENT_DATA` |
| 2 | `open_conflict_count >= 1` | `UNRESOLVED` |
| 3 | `freshness_status in {STALE, UNKNOWN}` **OR** `source_status == WEAK` | `WEAK` |
| 4 | `freshness == STRONG AND source == STRONG AND independence == HIGH_SOURCE_DIVERSITY AND corroboration == STRONGLY_CORROBORATED AND consistency == NO_DETECTED_CONFLICT AND evidence_count >= 2` | `VERY_STRONG` |
| 5 | `freshness in {STRONG, LIMITED} AND source in {STRONG, LIMITED} AND consistency in {NO_DETECTED_CONFLICT, ORDERING_AMBIGUITY_ONLY} AND freshness != STALE` | `STRONG` |
| default | Anything else | `LIMITED` |

Note: there is no `EXPIRED` freshness state — the possible states are
`CURRENT`, `AGING`, `STALE`, `UNKNOWN`. An indeterminable freshness (`UNKNOWN`)
is treated conservatively as WEAK, never assumed positive.

### Dimension Scoring Rules

**Freshness dimension** — reads `EvidenceQualitySnapshot.freshness_state` for all in-scope evidence IDs:
- All `CURRENT` or `AGING` → `STRONG`
- Any `STALE` → `LIMITED`
- Mixed states with none stale (e.g. some UNKNOWN) → `LIMITED`
- No quality snapshots → `UNKNOWN`

**Source dimension** — reads `source_authority_level` and `source_directness`:
- Any TERTIARY authority present → `WEAK`
- All PRIMARY + all DIRECT → `STRONG`
- All PRIMARY/SECONDARY otherwise → `LIMITED`
- Mixed authority levels → `LIMITED`
- No quality snapshots → `UNKNOWN`

**Independence dimension** — reads latest `EvidenceStructureSnapshot` at or before evaluation time:
- `distinct_sources >= 2 AND distinct_events >= 2` → `HIGH_SOURCE_DIVERSITY`
- `distinct_sources >= 2 OR distinct_events >= 2` (not both) → `LIMITED_SOURCE_DIVERSITY`
- `distinct_sources == 1 AND distinct_events == 1` → `SINGLE_SOURCE`
- No structure snapshot → `UNKNOWN`

**Corroboration dimension** — reads `EvidenceCorroboration` records for the payment:
- Any claim with `distinct_sources_count >= 2` → `STRONGLY_CORROBORATED`
- Any claim with `observation_count >= 2` (single source) → `PARTIALLY_CORROBORATED`
- Only single-observation claims → `SINGLE_OBSERVATION`
- No corroboration records → `UNKNOWN`

**Consistency dimension** — reads `EvidenceConflict` records for the payment:
- Zero conflicts → `NO_DETECTED_CONFLICT`
- Any UNRESOLVED-status conflict → `UNRESOLVABLE`
- Any non-INFO OPEN conflict → `HAS_OPEN_CONFLICTS`
- Only INFO-severity conflicts → `ORDERING_AMBIGUITY_ONLY`

---

## Temporal Isolation

Integrity assessments are point-in-time snapshots. The `evaluated_at` field is the temporal anchor.

**All evidence queries are filtered:** `observed_at <= evaluation_time`  
**All quality/structure queries are filtered:** `evaluated_at <= evaluation_time`

This prevents future evidence from leaking backward into historical assessments. A snapshot created at T=10:00 will never change even if new evidence arrives at T=12:00. A new snapshot at T=12:00 will include the new evidence.

---

## Explainability Design

The engine generates two output lists:

### `explanation_lines`

Human-readable sentences explaining the overall status, derived from actual dimension values. Generated by `_build_explanation()` using a deterministic if/else tree.

Rules:
- All claims are hedged: "No contradiction was **detected**" (not "no contradictions exist")
- No fraud or risk language in any generated sentence
- No probabilistic statements
- Only what the data actually shows

### `limitations`

Explicit list of what the assessment cannot tell you. Always included when:
- Historical reliability data is missing (always missing in Phase 9 — no outcome data exists yet)
- Evidence diversity is single-source
- Any dimension status is UNKNOWN

Missing data is surfaced as a limitation, **never coerced** to a default value or assumed to be positive.

---

## Forbidden Behaviour

The following are explicitly prohibited in the codebase and enforced by tests:

| Prohibited | Why |
|---|---|
| Fraud score, risk score, trust score | Outside scope — integrity is about evidence quality |
| ML or LLM reasoning | No non-deterministic or opaque decision making |
| Magic weights | All rules are documented and hard-coded |
| Retroactive mutation of snapshots | Historical snapshots are immutable |
| Coercing missing data to 0 or 0.5 | Missing is `UNKNOWN` or `INSUFFICIENT_DATA`, never a default |
| Future evidence leaking into historical evaluations | Blocked by SQL temporal filter |

---

## API Endpoints

### `GET /api/v1/payments/{payment_id}/integrity`

Returns the most recent integrity snapshot for the payment. If no snapshot exists, one is computed on-demand at the current time.

**Response** — `IntegritySnapshotResponse`:

```json
{
  "payment_id": "pay_abc123",
  "evaluated_at": "2026-08-22T10:00:00Z",
  "methodology_version": "EIS-1.0",
  "overall_status": "STRONG",
  "evidence_count": 4,
  "source_count": 1,
  "conflict_count": 0,
  "open_conflict_count": 0,
  "freshness_result": {
    "status": "STRONG",
    "reason": "All 4 observation(s) are current or aging.",
    "inputs": {"current_count": 4, "aging_count": 0, "stale_count": 0, "total": 4}
  },
  "source_result": { ... },
  "independence_result": { ... },
  "corroboration_result": { ... },
  "consistency_result": { ... },
  "explanation_lines": [
    "Evidence is current or aging.",
    "All sources are primary or authoritative.",
    "No contradiction was detected in available evidence."
  ],
  "limitations": [
    "Historical reliability data is not yet available — past performance of these sources cannot be assessed."
  ],
  "created_at": "2026-08-22T10:01:00Z"
}
```

### `GET /api/v1/payments/{payment_id}/integrity/history`

Returns all historical integrity snapshots ordered by `evaluated_at` ascending. Demonstrates how evidence integrity changed over time as new webhooks arrived.

---

## Webhook Pipeline Integration

Phase 9 is called automatically for every processed webhook:

```
webhook arrives
  → Phase 6: EvidenceQualityEngine.measure_quality()
  → Phase 7: StructureEngine.analyse_structure() / corroboration
  → Phase 8: ContradictionEngine.evaluate_payment_consistency()
  → Phase 9: IntegrityEngine.compute_integrity()           ← NEW
```

---

## Tests

`tests/test_integrity.py` — 50 tests, 14 test classes

| Class | What it tests |
|---|---|
| `TestFreshnessDimension` | CURRENT/AGING→STRONG, STALE→LIMITED, no snapshots→UNKNOWN |
| `TestSourceDimension` | PRIMARY→STRONG, SECONDARY→LIMITED, TERTIARY→WEAK |
| `TestIndependenceDimension` | Multi-source/event diversity, future snapshot exclusion |
| `TestCorroborationDimension` | Multi-source→STRONGLY, single-source multi-obs→PARTIALLY, single→SINGLE |
| `TestConsistencyDimension` | No conflict, INFO-only, HIGH-severity open |
| `TestAggregation` | All 6 possible overall statuses |
| `TestTemporalIsolation` | Future evidence excluded, historical snapshots immutable |
| `TestIdempotency` | Duplicate computation returns existing row, no duplicate DB rows |
| `TestMethodologyVersion` | EIS-1.0 and EIS-2.0 snapshots are distinct rows |
| `TestExplanation` | Explanation generated, no fraud language, hedged claims |
| `TestLimitations` | Historical reliability always surfaced, single-source surfaced |
| `TestHistory` | Ascending order, count grows monotonically |
| `TestEndToEnd` | Full pipeline scenarios: strong, unresolved, insufficient data, concentrated evidence |
| `TestIntegrityAPI` | 200/404 responses, schema completeness, API-level idempotency |

**184 cumulative tests passed at Phase 9 completion (Phases 1–9).**
See `docs/phase-10.md` for the current totals including Phase 10.

---

## What Phase 9 Does Not Do

Phase 9 explicitly does **not**:

- Produce a fraud score or risk score
- Make payment blocking or routing decisions
- Use any ML model, LLM, or probabilistic reasoning
- Compare this payment to a population of payments
- Produce a final "truth" about whether a payment is legitimate
- Predict future outcomes

These are intentional design constraints. Evidence integrity is an assessment of **what we know**, **how well we know it**, and **what we cannot yet determine**. Nothing more.

---

## Next Phase

Phase 10 builds on Phase 9's integrity snapshots to produce the **Evidence
Integrity Decision Trace** — a tamper-evident (SHA-256 hashed, hash-chained),
replayable record of exactly what each evaluation knew, considered, executed,
and concluded, exposed through restricted APIs and an audit UI.
