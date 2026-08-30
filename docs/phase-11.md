# Phase 11 — EvidenceGraph Temporal Evolution & Change Intelligence

## 1. Objective

Phase 11 adds **temporal change intelligence** to EvidenceGraph. It answers the question:
*"How did the evidence state of this payment change over time?"*

Each time a payment is evaluated, Phase 11 takes a snapshot of its current evidence quality
dimensions and compares it against the most recent prior snapshot. Any meaningful difference
— a new piece of evidence, a resolved conflict, aging freshness, a methodology upgrade — is
recorded as an `EvidenceStateChange` with a deterministic human-readable explanation.

Phase 11 is **not** fraud detection, risk scoring, or automated decision-making. It is an
audit and observability layer that surfaces how the evidence base evolved.

---

## 2. Evidence State Model

`EvidenceStateSnapshot` is a **denormalised projection** of Phase 9 `EvidenceIntegritySnapshot`
data. It is:

- **Denormalised** — all relevant dimension fields are copied into one flat row so the
  evolution engine can compare two snapshots without joining back into Phase 6–9 tables.
- **Time-bound** — the `evaluation_time` field is the temporal anchor. Only evidence
  observed at or before `evaluation_time` is reflected. Future evidence cannot reach back
  into a committed snapshot.
- **Immutable and append-only** — once written, a snapshot row is never updated. New
  evaluations produce new rows. The unique constraint on
  `(payment_id, evaluation_time, methodology_version)` enforces this.

The snapshot does not re-run any computation. `EvidenceStateSnapshotService.take_snapshot()`
reads already-persisted Phase 9 data only.

---

## 3. Snapshot Model

**Table: `evidence_state_snapshots`**

| Column | Type | Nullable | Description |
|---|---|---|---|
| `internal_id` | Integer (PK, autoincrement) | No | Surrogate primary key |
| `payment_id` | String(128) | No | Razorpay payment ID |
| `evaluation_time` | DateTime(tz) | No | Temporal anchor for the snapshot |
| `integrity_snapshot_id` | Integer (FK → `evidence_integrity_snapshots.internal_id`) | No | Source Phase 9 row |
| `overall_integrity_status` | String(32) | No | Mirrored from Phase 9 `overall_status` |
| `evidence_count` | Integer | No | Observations in scope at `evaluation_time` |
| `source_count` | Integer | No | Distinct source types present |
| `claim_count` | Integer | No | Canonical claims supported by in-scope evidence |
| `conflict_count` | Integer | No | Total detected conflicts (all severities) |
| `open_conflict_count` | Integer | No | Open conflicts with severity above INFO |
| `corroboration_status` | String(64) | No | From Phase 9 `corroboration_result.status` |
| `independence_status` | String(64) | No | From Phase 9 `independence_result.status` |
| `freshness_status` | String(32) | No | From Phase 9 `freshness_result.status` |
| `consistency_status` | String(64) | No | From Phase 9 `consistency_result.status` |
| `methodology_version` | String(16) | No | Phase 9 methodology version (e.g. `EIS-1.0`) |
| `created_at` | DateTime(tz) | No | DB-generated row creation time |

**Unique constraint:** `uq_evidence_state_snapshot` on `(payment_id, evaluation_time, methodology_version)`

**Indexes:** `ix_evidence_state_snapshot_payment_id`, `ix_evidence_state_snapshot_evaluation_time`

---

## 4. Change Model

**Table: `evidence_state_changes`**

| Column | Type | Nullable | Description |
|---|---|---|---|
| `internal_id` | Integer (PK, autoincrement) | No | Surrogate primary key |
| `change_id` | String(36) | No | UUID4, globally unique |
| `payment_id` | String(128) | No | Denormalised for query efficiency |
| `previous_snapshot_id` | Integer (FK → `evidence_state_snapshots.internal_id`) | No | The "before" snapshot |
| `current_snapshot_id` | Integer (FK → `evidence_state_snapshots.internal_id`) | No | The "after" snapshot |
| `detected_at` | DateTime(tz) | No | Wall-clock time the change was detected |
| `change_type` | String(64) | No | `ChangeType` constant |
| `dimension` | String(64) | No | `ChangeDimension` constant |
| `previous_value` | String(256) | Yes | String representation of the before value |
| `current_value` | String(256) | Yes | String representation of the after value |
| `direct_cause` | String(64) | Yes | `DirectCause` constant |
| `causality` | String(16) | Yes | `CausalityLevel` constant |
| `explanation` | Text | Yes | Deterministic human-readable explanation |
| `magnitude` | String(16) | Yes | `ChangeMagnitude` constant (`MINOR`/`MODERATE`/`MAJOR`) or NULL |
| `linked_evidence_id` | Integer (FK → `evidence_observations.internal_id`) | Yes | Specific observation that caused the change (when DIRECT) |
| `linked_conflict_id` | Integer (FK → `evidence_conflicts.internal_id`) | Yes | Specific conflict that caused the change (when DIRECT) |
| `methodology_version` | String(16) | Yes | Methodology version active at detection |
| `created_at` | DateTime(tz) | No | DB-generated row creation time |

**Unique constraints:**
- `uq_evidence_state_change_id` on `(change_id)`
- `uq_evidence_state_change_pair` on `(previous_snapshot_id, current_snapshot_id, change_type, dimension)`

**Indexes:** `ix_evidence_state_change_payment_id`, `ix_evidence_state_change_detected_at`,
`ix_evidence_state_change_dimension`

---

## 5. Change Taxonomy

Defined in `app/models/evolution_types.py` as `ChangeType` plain string constants:

| Constant | Meaning |
|---|---|
| `NEW_EVIDENCE` | A new evidence observation was incorporated |
| `EVIDENCE_REMOVED` | Evidence observation count decreased |
| `EVIDENCE_INVALIDATED` | An existing observation's `valid_until` expired |
| `NEW_SOURCE` | A new distinct source type appeared |
| `SOURCE_LOST` | A source type that was present is no longer represented |
| `CORROBORATION_INCREASED` | Corroboration status improved |
| `CORROBORATION_DECREASED` | Corroboration status degraded |
| `INDEPENDENCE_CHANGED` | Independence / source-diversity status changed |
| `CONFLICT_CREATED` | A new Phase 8 conflict was detected |
| `CONFLICT_RESOLVED` | An existing conflict was resolved |
| `FRESHNESS_CHANGED` | Aggregate freshness status changed |
| `INTEGRITY_CHANGED` | Overall integrity status changed |
| `METHODOLOGY_CHANGED` | Methodology version changed between snapshots |
| `NO_MATERIAL_CHANGE` | Comparison produced no meaningful difference |

---

## 6. Cause Taxonomy

**`DirectCause`** — the proximate cause of a change:

| Constant | Meaning |
|---|---|
| `NEW_EVIDENCE` | A new observation was incorporated |
| `EVIDENCE_INVALIDATION` | An observation's `valid_until` expired |
| `CONFLICT` | A new semantic contradiction was detected |
| `CONFLICT_RESOLUTION` | An existing conflict was resolved |
| `TIME_PASSAGE` | Evidence aged without new observations being added |
| `SOURCE_CHANGE` | The set of source types contributing evidence changed |
| `METHODOLOGY_CHANGE` | The evaluation methodology version changed |
| `MANUAL_RECOMPUTATION` | An explicit recomputation was requested via API |
| `UNKNOWN_CAUSE` | Causality cannot be established from available data |

**`CausalityLevel`** — confidence in the established cause:

| Constant | Meaning |
|---|---|
| `DIRECT` | Cause can be directly established (e.g. evidence count increased) |
| `INFERRED` | Most likely explanation but not pinnable to a single record |
| `UNKNOWN` | System cannot establish causality |

---

## 7. Temporal Behavior

`EvidenceStateSnapshotService.take_snapshot()` operates as a **pure reader**:

- It reads from already-persisted Phase 9 `EvidenceIntegritySnapshot` data.
- It **never** calls `IntegrityEngine.compute_integrity()` or any other computation engine.
- If no Phase 9 snapshot exists for the `(payment_id, evaluation_time, methodology_version)`
  triple, it raises `ValueError` and the caller must run Phase 9 first.

**Time-passage detection:** Freshness degrades (`freshness_status` moves from `CURRENT` →
`AGING` → `STALE`) when time passes without new evidence arriving. The engine detects
time-passage when `freshness_status` differs between snapshots but `evidence_count` has not
increased. The resulting change record will have `direct_cause = TIME_PASSAGE` and
`causality = DIRECT`.

---

## 8. Causality Rules

`EvidenceChangeEngine._determine_cause()` evaluates rules in priority order and returns the
first match as `(direct_cause, causality_level)`:

| Priority | Condition | Result |
|---|---|---|
| 1 | `curr.evidence_count > prev.evidence_count` | `NEW_EVIDENCE`, `DIRECT` |
| 2 | `change_type == FRESHNESS_CHANGED` AND `curr.freshness_rank < prev.freshness_rank` AND `curr.evidence_count == prev.evidence_count` | `TIME_PASSAGE`, `DIRECT` |
| 3 | `curr.open_conflict_count > prev.open_conflict_count` | `CONFLICT`, `DIRECT` |
| 4 | `curr.open_conflict_count < prev.open_conflict_count` | `CONFLICT_RESOLUTION`, `DIRECT` |
| 5 | `curr.methodology_version != prev.methodology_version` | `METHODOLOGY_CHANGE`, `DIRECT` |
| 6 | `curr.source_count != prev.source_count` | `SOURCE_CHANGE`, `INFERRED` |
| 7 | `change_type in (CORROBORATION_INCREASED, CORROBORATION_DECREASED)` AND `curr.evidence_count != prev.evidence_count` | `NEW_EVIDENCE`, `INFERRED` |
| 8 | `change_type in (CORROBORATION_INCREASED, CORROBORATION_DECREASED)` AND `curr.evidence_count == prev.evidence_count` | `UNKNOWN_CAUSE`, `INFERRED` |
| 9 | Otherwise | `UNKNOWN_CAUSE`, `UNKNOWN` |

---

## 9. Methodology Changes

When `methodology_version` differs between the previous and current snapshot, the engine
produces a `METHODOLOGY_CHANGED` change record with:

- `change_type = METHODOLOGY_CHANGED`
- `dimension = METHODOLOGY`
- `direct_cause = METHODOLOGY_CHANGE`
- `causality = DIRECT`
- `explanation`: `"The result changed because the evaluation methodology changed from {prev} to {curr}."`

This ensures that result changes driven purely by a methodology upgrade are not
misattributed to evidence changes. The `METHODOLOGY_CHANGED` change type is always emitted
separately from any other dimension changes that may also be present in the same diff.

---

## 10. APIs

All four endpoints are in the same **public tier** as `GET /payments/.../integrity` — no
`X-API-Key` header required.

### `GET /api/v1/payments/{payment_id}/changes`

Returns all `EvidenceStateChange` records for the payment, ordered by `detected_at`
ascending.

- Optional `?dimension=` query parameter filters to a single quality dimension
  (case-insensitive match).
- Returns `EvidenceChangesResponse` with `payment_id`, `changes[]`, `total`, `dimension_filter`.
- 404 when `payment_id` does not exist.

### `GET /api/v1/payments/{payment_id}/state-history`

Returns all `EvidenceStateSnapshot` records for the payment, ordered by `evaluation_time`
ascending.

- Each snapshot item is annotated with `integrity_trace_id` — the `trace_id` of the
  nearest COMPLETED Phase 10 trace matched by `payment_id`, `methodology_version`, and
  `evaluated_at` within a 5-second window.
- Returns `StateHistoryResponse` with `payment_id`, `history[]`, `total`.
- 404 when `payment_id` does not exist.

### `GET /changes/{change_id}`

Returns the full `EvidenceStateChange` record for the given UUID.

- Only safe derived metadata is exposed (IDs, statuses, counts, timestamps, explanations).
- 404 when `change_id` does not exist.

### `POST /api/v1/payments/{payment_id}/integrity/recompute`

Triggers a fresh Phase 9 integrity evaluation at the current time, creates a new
`EvidenceStateSnapshot`, diffs it against the previous snapshot, commits, and returns the
result.

- Calls `IntegrityTraceService.record_evaluation()` (Phase 9 + 10 pipeline).
- Calls `EvidenceStateSnapshotService.take_snapshot()` (Phase 11).
- Finds the previous snapshot and calls `EvidenceChangeEngine.detect_and_persist_changes()`.
- Returns `RecomputeResponse` with `new_snapshot`, `changes_detected[]`, `change_count`,
  `no_material_change`.
- Idempotent within the same second via Phase 9 deduplication.

---

## 11. Frontend

The **Evidence Evolution** section is added as a tab in `PaymentInspector.tsx`.

**Structure:**
- Vertical timeline of `EvidenceStateSnapshot` nodes, each showing `evaluation_time`,
  `overall_integrity_status` (color-coded badge), `evidence_count`, and `conflict_count`.
- Between consecutive timeline nodes, change cards are rendered for `EvidenceStateChange`
  records whose `detected_at` falls between the two snapshot `evaluation_time` values.
- Each change card shows: WHAT (`change_type` + `dimension`), WHEN (`detected_at`), WHY
  (`explanation`), CAUSED BY (`direct_cause` + linked IDs), and PREVIOUS → NEW
  (`previous_value` → `current_value`).

**Controls:**
- Dimension filter bar with buttons: All, Evidence, Corroboration, Independence, Freshness,
  Consistency, Integrity, Conflicts. Drives a client-side filter on the `changes` array.
- "Recompute Now" button calls `POST /api/v1/payments/{paymentId}/integrity/recompute` and
  then re-fetches both `state-history` and `changes`.

**Empty state:** `"No material evidence-state change detected."` is shown when
`changes.length === 0` after loading completes.

---

## 12. Idempotency

**`EvidenceStateSnapshotService.take_snapshot()`** is idempotent via two layers:

1. **Application-level check** — the service queries for an existing snapshot by
   `(payment_id, evaluation_time, methodology_version)` before inserting. If found, it
   returns the existing row immediately.
2. **Database-level constraint** — the `uq_evidence_state_snapshot` unique constraint
   provides defense-in-depth against concurrent races. An `IntegrityError` on concurrent
   insert triggers a rollback and re-query of the winning row.

**`EvidenceChangeEngine.detect_and_persist_changes()`** is idempotent via:

1. **Database unique constraint** `uq_evidence_state_change_pair` on
   `(previous_snapshot_id, current_snapshot_id, change_type, dimension)` prevents duplicate
   change records for the same transition.
2. **Savepoint-level race handling** — each change insert uses a savepoint. An
   `IntegrityError` causes savepoint rollback and re-query of the existing record. The
   outer transaction is not aborted.

---

## 13. Security

All API responses expose only safe derived metadata:

- IDs, status strings, integer counts, UTC timestamps, and human-readable explanations.
- **Not exposed**: raw webhook payloads, Razorpay secrets, API keys, CVV, PIN, OTP,
  credentials, or any field from the Phase 2 immutable webhook store.

The `ChangeDetailResponse` Pydantic schema is the enforcement boundary — it excludes all
credential-adjacent field names by construction.

---

## 14. Testing

**File:** `backend/tests/test_evolution.py`

**Database:** SQLite in-memory with `@compiles(JSONB, "sqlite")` polyfill (matches
`test_trace.py` pattern).

**20 test cases across 4 classes (plus 4 API tests):**

| Class | Tests | What it covers |
|---|---|---|
| `TestSnapshotService` (4) | snapshot creation, idempotency, field fidelity, missing Phase 9 guard | `EvidenceStateSnapshotService.take_snapshot()` |
| `TestSnapshotComparison` (4) | no-change, single-field diff, multi-field diff, methodology diff | `EvidenceChangeEngine.compare_snapshots()` — pure function |
| `TestChangeEngine` (7) | new evidence, corroboration increase, conflict created, conflict resolved, freshness/time-passage, methodology change, causality assignment | `EvidenceChangeEngine.detect_and_persist_changes()` |
| `TestHistoricalIsolation` (1) | new evidence cannot alter pre-existing snapshots | Immutability contract |
| `TestEvolutionAPI` (4) | all four endpoints: status codes, response shapes, 404 paths | FastAPI `TestClient` |

---

## 15. Real Razorpay Validation

Phase 11 is integrated into `webhook_worker.py`. When a real Razorpay webhook is processed:

1. The existing Phase 9 + 10 pipeline runs first (`IntegrityTraceService.record_evaluation()`).
2. `EvidenceStateSnapshotService.take_snapshot()` is called with the same `measurement_time`.
3. `EvidenceChangeEngine.detect_and_persist_changes()` is called, comparing the new snapshot
   against the most recent prior snapshot for the same payment.

**Non-blocking:** The entire Phase 11 block is wrapped in `try/except Exception`. Failures
are logged as warnings but do not roll back webhook processing, do not change
`event.processing_status`, and do not trigger the outer exception handler.

The `POST /api/v1/payments/{payment_id}/integrity/recompute` endpoint allows triggering
change detection on demand without waiting for a new webhook.

---

## 16. Known Limitations

- **`claim_count` fallback** — when no `EvidenceStructureSnapshot` exists at or before
  `evaluation_time`, `claim_count` falls back to counting `Claim` records joined through
  `EvidenceClaimLink` and `EvidenceObservation`. This is a best-effort approximation.

- **`linked_evidence_id` and `linked_conflict_id` not populated** — in the current webhook
  pipeline, causality links are rule-derived (based on field comparisons) rather than
  record-linked. These FK columns are always NULL in practice.

- **REPLAY traces not linked** — Phase 10 REPLAY traces are not linked to
  `EvidenceStateSnapshot` records. The `integrity_trace_id` annotation on state history
  only matches EVALUATION traces.

- **No automatic freshness scheduler** — there is no background job that re-evaluates
  freshness as time passes. Freshness changes are only detected when a new evaluation is
  triggered (via webhook or `POST /recompute`).

- **`evaluation_time` exact match required** — `EvidenceStateSnapshot.evaluation_time`
  must exactly match `EvidenceIntegritySnapshot.evaluated_at` for `take_snapshot()` to
  locate the Phase 9 row. Sub-second drift between the two calls will cause a `ValueError`.
  The recompute endpoint avoids this by passing the same `measurement_time` to both calls.
