# Phase 10 — Evidence Integrity Decision Traces

## Overview

Phase 10 adds a tamper-evident audit layer on top of Phase 9's integrity evaluation engine. Every integrity evaluation produces an immutable **Evidence Integrity Decision Trace** that records *what* was evaluated, *when*, *with which inputs and rules*, and *why* the result was produced — all committed to a cryptographic hash and linked into a per-payment hash chain.

The key guarantee is **tamper-evidence**, not database immutability. The system cannot prevent a sufficiently privileged actor from editing database rows, but it makes any such modification detectable through hash mismatch on re-verification.

---

## Database Tables

### `evidence_integrity_traces`

The primary record of each evaluation or replay.

| Column | Type | Nullable | Description |
|---|---|---|---|
| `internal_id` | Integer (PK, autoincrement) | No | Surrogate primary key |
| `trace_id` | String(36) | No | UUID4, globally unique, never reused |
| `trace_type` | String(16) | No | `EVALUATION` or `REPLAY` |
| `original_trace_id` | String(36) | Yes | For REPLAY traces: the `trace_id` of the original evaluation |
| `payment_id` | String(128) | No | Razorpay payment ID being assessed |
| `evaluated_at` | DateTime (TZ) | No | Explicit temporal anchor of the evaluation (`evaluation_time`) |
| `methodology_version` | String(16) | No | Phase 9 methodology version (e.g. `EIS-1.0`) |
| `methodology_snapshot_hash` | String(64) | Yes | SHA-256 of the canonical methodology snapshot in the payload |
| `trigger` | String(64) | Yes | Request provenance: `WEBHOOK_PROCESSING`, `ON_DEMAND_API`, `REPLAY_REQUEST`. Not included in the audit hash |
| `status` | String(32) | No | `EVALUATION_STARTED`, `COMPLETED`, or `FAILED` |
| `failure_stage` | String(64) | Yes | Pipeline stage where evaluation failed (FAILED traces only) |
| `failure_category` | String(64) | Yes | Exception class name (FAILED traces only) |
| `failure_detail` | Text | Yes | Short human-safe description, max 300 chars (FAILED traces only) |
| `integrity_snapshot_internal_id` | Integer (FK) | Yes | FK to `evidence_integrity_snapshots.internal_id`. EVALUATION COMPLETED traces only; never duplicated inside the payload |
| `overall_status` | String(32) | Yes | Mirrored `IntegrityStatus` for query convenience; authoritative copy lives inside `canonical_payload` |
| `canonical_payload` | JSONB | Yes | The exact structure that was hashed (see Canonical Payload section) |
| `trace_hash` | String(64) | Yes | SHA-256 hex digest of the canonical serialization of `canonical_payload` |
| `hash_algorithm` | String(32) | Yes | Always `SHA-256` |
| `canonicalization_version` | String(16) | Yes | Always `CG-1.0` |
| `previous_trace_id` | String(36) | Yes | `trace_id` of the immediately preceding finalized EVALUATION trace for this payment |
| `previous_trace_hash` | String(64) | Yes | `trace_hash` of that preceding trace. NULL for the first trace in a chain |
| `created_at` | DateTime (TZ) | No | DB-generated row creation time. Excluded from the hash |
| `finalized_at` | DateTime (TZ) | Yes | When the trace reached a terminal state |

#### Unique Constraints

- `uq_integrity_trace_trace_id` — unique on `trace_id`

#### Partial Index for Idempotency

```sql
CREATE UNIQUE INDEX uq_integrity_trace_evaluation_identity
  ON evidence_integrity_traces (payment_id, evaluated_at, methodology_version)
  WHERE trace_type = 'EVALUATION' AND status = 'COMPLETED';
```

At most **one** COMPLETED EVALUATION trace may exist per identity tuple `(payment_id, evaluated_at, methodology_version)`. FAILED traces do not consume the identity slot, so a failed attempt can be retried without rewriting the failure record.

#### Regular Indexes

- `ix_integrity_trace_payment_id` on `payment_id`
- `ix_integrity_trace_evaluated_at` on `evaluated_at`
- `ix_integrity_trace_status` on `status`
- `ix_integrity_trace_original_trace_id` on `original_trace_id`

#### Check Constraints

| Constraint | Expression | Meaning |
|---|---|---|
| `ck_integrity_trace_status` | `status IN ('EVALUATION_STARTED', 'COMPLETED', 'FAILED')` | Only valid lifecycle values |
| `ck_integrity_trace_type` | `trace_type IN ('EVALUATION', 'REPLAY')` | Only valid trace types |
| `ck_integrity_trace_finalized_complete` | Terminal status requires payload + hash + algorithm + canonicalization version | Incomplete terminal states are unrepresentable |
| `ck_integrity_trace_completed_has_result` | COMPLETED EVALUATION must have snapshot FK + overall_status; COMPLETED REPLAY must have overall_status | No result-less completions |
| `ck_integrity_trace_failed_has_failure_info` | FAILED must have failure_stage + failure_category | Auditable failure records only |
| `ck_integrity_trace_replay_has_original` | REPLAY must have original_trace_id | Orphan replays are impossible |

---

### `integrity_trace_events`

Ordered audit event log for a trace lifecycle.

| Column | Type | Nullable | Description |
|---|---|---|---|
| `internal_id` | Integer (PK, autoincrement) | No | Surrogate primary key |
| `event_id` | String(36) | No | UUID4, globally unique |
| `trace_id` | String(36) | No | Logical reference to the parent trace |
| `sequence_number` | Integer | No | Monotonic per-trace execution order, starting at 1 |
| `event_type` | String(64) | No | `TraceEventType` constant (see below) |
| `occurred_at` | DateTime (TZ) | No | Wall-clock time the event occurred |
| `actor_type` | String(16) | No | `SYSTEM` or `USER` |
| `event_metadata` | JSONB | Yes | Safe structured metadata. Never contains raw webhook payloads or secrets |
| `created_at` | DateTime (TZ) | No | DB-generated row creation time |

#### Constraints

- `uq_integrity_trace_event_event_id` — unique on `event_id`
- `uq_integrity_trace_event_order` — unique on `(trace_id, sequence_number)` — guarantees no gaps or duplicates in a trace's event log
- `ck_integrity_trace_event_actor` — `actor_type IN ('SYSTEM', 'USER')`
- `ix_integrity_trace_events_trace_id` — index on `trace_id`
- `ix_integrity_trace_events_type` — index on `event_type`

**Ordering authority is `sequence_number`, not `occurred_at` or `internal_id`.** Database insertion order is never relied upon.

---

## TraceStatus Constants

Defined in `app/models/trace_types.py`.

| Constant | Value | Semantics |
|---|---|---|
| `EVALUATION_STARTED` | `"EVALUATION_STARTED"` | Inputs are being captured. No hash exists yet. Not a finished evaluation; must never be presented as one |
| `COMPLETED` | `"COMPLETED"` | Evaluation finished, canonical payload hashed, trace finalized and immutable |
| `FAILED` | `"FAILED"` | Evaluation failed. The failure record itself is finalized and hashed; it is an auditable failure record, not a masquerading completion |

---

## TraceEventType Constants

Events emitted during the trace lifecycle, stored with explicit `sequence_number`:

| Constant | Emitted when |
|---|---|
| `EVALUATION_STARTED` | Trace record created, inputs about to be captured |
| `EVIDENCE_SELECTED` | Included evidence set determined |
| `EVIDENCE_EXCLUDED` | At least one candidate observation was excluded |
| `QUALITY_MEASURED` | Quality measurements captured |
| `STRUCTURE_MEASURED` | Structural analysis captured |
| `CONSISTENCY_ANALYZED` | Conflict / consistency measurements captured |
| `RULE_EXECUTED` | Each individual rule execution |
| `INTEGRITY_COMPUTED` | Final integrity result produced |
| `TRACE_FINALIZED` | Terminal state (COMPLETED or FAILED) committed with hash |
| `EVALUATION_FAILED` | Evaluation raised an exception; failure record being built |

---

## Hash-Chain Mechanism

### What is chained

Only **EVALUATION** traces join a payment's hash chain. REPLAY traces are never linked into the chain and never modify chain state.

The chain is ordered by `(evaluated_at, internal_id)` per `payment_id`. For each new finalized EVALUATION trace, the service queries the immediately preceding finalized EVALUATION trace for the same payment and records:

```
trace_n.previous_trace_id   = trace_{n-1}.trace_id
trace_n.previous_trace_hash = trace_{n-1}.trace_hash
```

The first trace in a chain has `previous_trace_id = NULL` and `previous_trace_hash = NULL`.

FAILED EVALUATION traces **do** join the chain (they are finalized EVALUATION traces), so failure history is as tamper-evident as success history.

### Why it provides tamper-evidence

If any trace's `canonical_payload` is altered after finalization, recomputing its `trace_hash` will produce a different digest. Furthermore, since each successor embeds the predecessor's hash, altering any trace in the middle of the chain breaks every downstream link — the modification becomes detectable at `chain-verify` time even if the `trace_hash` column is also updated to match the tampered payload.

### What it does not guarantee

- The database itself is not immutable. A sufficiently privileged actor can update any row including `trace_hash` and `canonical_payload` together.
- This is **not a blockchain**. There is no decentralized consensus or proof-of-work.

---

## Canonical Serialization — CG-1.0

Defined in `app/services/trace_canonicalization.py`. Version string: `"CG-1.0"`.

The rules pin down every formatting decision so the same logical content always produces the same byte sequence:

| Element | Rule |
|---|---|
| **Object keys** | Sorted lexicographically by Unicode code point |
| **Arrays** | Element order preserved (semantic, not sorted) |
| **Strings** | Standard JSON escaping; non-ASCII characters escaped (`ensure_ascii=True`) |
| **Datetimes** | Rendered as RFC3339 UTC with microsecond precision and `Z` suffix: `YYYY-MM-DDTHH:MM:SS.ffffffZ`. Naive datetimes are treated as UTC |
| **Integers** | Decimal digits as-is, arbitrary precision |
| **Floats** | Finite only. Integral floats (e.g. `2.0`) normalized to integers (→ `2`). Non-integral floats via shortest round-trip Python repr |
| **NaN / Infinity** | Forbidden — raise `CanonicalizationError` |
| **Booleans** | `true` / `false` |
| **Null** | `null` (explicitly preserved, never dropped) |
| **Separators** | `","` between items, `":"` after keys, **no whitespace** |
| **Encoding** | UTF-8 bytes of the resulting text are hashed |

### What is NOT included in the canonical hash

The following fields are deliberately excluded:

- `created_at` / `finalized_at` — DB-generated mutable metadata
- `trigger` — request provenance, not audit content
- `internal_id` — database surrogate key
- Request IDs, query timings, transient logging metadata

---

## SHA-256 Hashing Flow

Implemented in `trace_canonicalization.canonical_hash()`.

1. **Build the payload dict** (in `IntegrityTraceService._finalize_completed` / `_finalize_failed`):
   ```python
   payload = {
       "hash_domain":  HASH_DOMAIN,   # "evidencegraph.integrity_trace.v1"
       "schema":       TRACE_SCHEMA_VERSION,  # "TRC-1.0"
       "envelope":     { trace_id, trace_type, original_trace_id, payment_id,
                         evaluated_at, methodology_version,
                         methodology_snapshot_hash, status,
                         previous_trace_hash },
       "content":      { ...all audit sections... },
   }
   ```

2. **Canonicalize for storage** — `canonical_payload_for_storage(payload)` walks the dict recursively: datetimes become canonical strings, floats are normalized, keys are sorted. The result is plain JSON-compatible Python. This is what is persisted to `canonical_payload`.

3. **Domain separation** — the `"hash_domain": "evidencegraph.integrity_trace.v1"` key is inside the hashed payload, ensuring trace hashes cannot collide with hashes from other subsystems.

4. **Serialize** — `canonical_json(stored_payload)` calls `json.dumps` with `sort_keys=True`, `separators=(",", ":")`, `ensure_ascii=True`, `allow_nan=False`.

5. **Digest** — `sha256_hex(canonical_text)` returns `hashlib.sha256(text.encode("utf-8")).hexdigest()`.

6. **Store** — `trace.trace_hash = digest`, `trace.canonical_payload = stored_payload`.

### Canonical Payload Structure

```json
{
  "hash_domain": "evidencegraph.integrity_trace.v1",
  "schema": "TRC-1.0",
  "envelope": {
    "evaluated_at": "2026-08-23T10:00:00.000000Z",
    "methodology_snapshot_hash": "<sha256-hex>",
    "methodology_version": "EIS-1.0",
    "original_trace_id": null,
    "payment_id": "pay_xxx",
    "previous_trace_hash": "<sha256-hex or null>",
    "status": "COMPLETED",
    "trace_id": "<uuid4>",
    "trace_type": "EVALUATION"
  },
  "content": {
    "consistency": { "conflicts": [...] },
    "corroboration": { "record_internal_ids": [...], "total_records": 0 },
    "counts": { ... },
    "evaluation_context": { ... },
    "evidence_inputs": [...],
    "excluded_evidence": [...],
    "explanation_lines": [...],
    "final_result": { "overall_status": "VERIFIED", ... },
    "intermediate_results": { ... },
    "limitations": [...],
    "methodology": { "aggregation": "...", "snapshot": {...}, "snapshot_hash": "...", "version": "EIS-1.0" },
    "quality_measurements": [...],
    "rule_executions": [...],
    "structural_measurements": { ... }
  }
}
```

REPLAY traces additionally include a `"replay_comparison"` key inside `"content"`.

---

## API Endpoints

### Authorization tiers

- **Public** (standard auth): accessible by any authenticated caller  
- **Admin** (`X-API-Key`): requires `require_admin_api_key` dependency

There is **no** endpoint that creates, updates, or deletes traces through the API. Completed traces are immutable and history is never rewritten.

---

### Public endpoints

#### `GET /payments/{payment_id}/integrity/traces`

Returns historical trace summaries for a payment, ordered by `evaluated_at` ascending.

- **Authorization**: standard (public)
- **Returns**: `TraceListResponse` — list of `TraceSummaryItem` objects containing identity, lifecycle status, result, and hash metadata. No full audit content.
- **404**: when `payment_id` does not exist
- **Note**: only EVALUATION traces are included by default (replays excluded)

---

### Admin endpoints

#### `GET /integrity/{trace_id}`

Returns the full decision trace: canonical payload + ordered audit event timeline.

- **Authorization**: `X-API-Key`
- **Returns**: `TraceDetailResponse` — complete evaluation context, evidence inputs/exclusions, measurements, structure, corroboration, conflicts, rule executions, intermediate results, final result, limitations, canonical payload, and event log ordered by `sequence_number`
- **404**: when `trace_id` does not exist

#### `GET /integrity/{trace_id}/verify`

Cryptographic verification of one trace's integrity.

- **Authorization**: `X-API-Key`
- **Returns**: `TraceVerificationResponse` with a `status` of:
  - `VALID` — recomputed SHA-256 matches stored `trace_hash`
  - `INVALID` — hash mismatch (trace content was modified after finalization), or structural payload error
  - `VERIFICATION_UNAVAILABLE` — trace is not yet finalized (no hash exists)
  - `NOT_FOUND` → HTTP 404
- **Implementation**: uses `hmac.compare_digest` for constant-time comparison; never returns a false VALID

#### `GET /payments/{payment_id}/integrity/chain-verify`

Verifies the full per-payment EVALUATION hash chain.

- **Authorization**: `X-API-Key`
- **Returns**: `TraceChainVerificationResponse` with a `status` of:
  - `CHAIN_VALID` — all links verified; every trace connects cryptographically to its predecessor
  - `CHAIN_INVALID` — one or more problems detected (hash mismatch, broken link)
  - `CHAIN_START` — single-link chain, first trace verified, no predecessor exists
  - `NO_TRACES` — no finalized evaluation traces exist for this payment
- **404**: when `payment_id` does not exist
- **Note**: REPLAY traces are excluded from chain verification

#### `POST /integrity/{trace_id}/replay`

Re-executes the evaluation for an original trace's context and compares results.

- **Authorization**: `X-API-Key`
- **Returns**: `TraceReplayResponse` (see Replay Behavior section)
- **409 Conflict**: `ReplayNotPossibleError` — trace doesn't exist, is a REPLAY trace, is FAILED, or is not yet COMPLETED

---

## Replay Behavior

Implemented in `app/services/replay_service.py`.

### What replay does

1. Loads the original COMPLETED EVALUATION trace (read-only).
2. Creates a new **REPLAY** trace with `original_trace_id` pointing to the original.
3. Re-executes `IntegrityEngine._execute_computation` using the **same** `(payment_id, evaluated_at, methodology_version)` context — reading current database state. The computation is the same engine; the evidence and data visible to it are as they exist now.
4. Compares the replayed `content` sections against the original's stored `canonical_payload.content`.
5. Finalizes the REPLAY trace with its own hash (REPLAY traces are hashed, but **never join the payment's EVALUATION chain**).
6. Returns the comparison result.

### What replay never does

- The original trace is **never modified**. Replay is purely read → new-write.
- REPLAY traces do not set `previous_trace_hash` / `previous_trace_id` (they are not EVALUATION traces).

### Comparison plan

The diff identifies the **first meaningful difference by category**, in priority order:

| Priority | Category | Sections examined |
|---|---|---|
| 1 | `METHODOLOGY_CHANGED` | `methodology` |
| 2 | `EVIDENCE_SET_CHANGED` | `evidence_inputs`, `excluded_evidence` |
| 3 | `MEASUREMENT_CHANGED` | `quality_measurements` |
| 4 | `RELATIONSHIP_CHANGED` | `structural_measurements`, `corroboration` |
| 5 | `CONFLICT_CHANGED` | `consistency` |
| 6 | `RULE_OUTPUT_CHANGED` | `rule_executions`, `intermediate_results` |
| 7 | `FINAL_RESULT_CHANGED` | `evaluation_context`, `counts`, `final_result`, `explanation_lines`, `limitations` |

Both sides are run through `canonicalize()` before comparison so raw datetimes from the live capture compare equal to the stored canonical string forms. `final_result.integrity_snapshot_internal_id` is stripped before comparison since the original references its persisted snapshot while a replay persists nothing.

### Replay response fields

| Field | Description |
|---|---|
| `original_trace_id` | The trace that was replayed |
| `original_payment_id` | Payment ID |
| `evaluated_at` | The original evaluation time anchor |
| `methodology_version` | Methodology version used |
| `replay_trace_id` | The newly-created REPLAY trace |
| `original_result` | `overall_status` from the original |
| `replay_result` | `overall_status` from the replay |
| `comparison_result` | `MATCH` or `MISMATCH` |
| `first_difference` | `{category, sections, paths}` or `null` |
| `differences` | Full list of per-category differences |

A `MISMATCH` is not an error condition — it means the current state of the database (e.g. new evidence arrived) differs from what was visible at the original evaluation time.

---

## Service: `IntegrityTraceService`

`app/services/integrity_trace_service.py`

### Idempotency

`record_evaluation()` performs an application-level deduplication check before creating a trace. The database partial unique index on `(payment_id, evaluated_at, methodology_version) WHERE trace_type = 'EVALUATION' AND status = 'COMPLETED'` provides defense-in-depth against concurrent races. If a concurrent transaction wins the identity slot, the service rolls back and returns the winner's COMPLETED trace.

### Legacy data handling

If an `EvidenceIntegritySnapshot` already exists for the identity tuple but no COMPLETED EVALUATION trace does (data produced before Phase 10 existed), the service **refuses to fabricate audit history** and returns `None`. The original computation path cannot be honestly reconstructed.

### Transactional finalization

Payload, hash, chain linkage, and terminal status (`COMPLETED` or `FAILED`) are written in a single `db.flush()` call inside the caller's transaction. Database CHECK constraints make it impossible for a COMPLETED/FAILED row to exist without all required columns populated.

---

## Service: `TraceVerificationService`

`app/services/trace_verification.py`

Reconstructs the canonical serialization from the stored `canonical_payload` JSONB and recomputes SHA-256. Uses `hmac.compare_digest` for constant-time comparison to prevent timing attacks. The service is deliberately conservative — it never returns a false `VALID`:

- Unfinalized traces → `VERIFICATION_UNAVAILABLE` (not VALID or INVALID)
- Structural problems in the stored payload → `INVALID`

---

## Known Limitations

1. **No immutable database storage.** The database can be modified by a privileged actor. The hash chain makes tampering *detectable* but not *impossible*. 

2. **Hash-chain is tamper-evidence, not a blockchain.** There is no decentralized consensus, proof-of-work, or smart-contract enforcement. It is a linear audit chain suitable for detecting post-hoc modifications in a trusted operational context.

3. **Pre-Phase-10 snapshots produce no trace.** Integrity evaluations that ran before Phase 10 was deployed left `EvidenceIntegritySnapshot` records without corresponding decision traces. The service will not fabricate a trace for these snapshots; they appear as gaps in the trace history.

4. **REPLAY traces read current database state.** A replay does not time-travel to the exact database snapshot at `evaluated_at`. It re-runs the computation with the same temporal anchor parameter but against current data — new evidence observations or updated records will cause a `MISMATCH` comparison result.

5. **`evaluated_at` vs `created_at`.** The temporal anchor is the caller-provided `evaluation_time`, not the wall-clock time the trace was created. A `MISMATCH` between these two is expected and normal; the distinction is by design.

6. **`trigger` field is informational only.** It is not included in the canonical hash and carries no audit authority. It records request provenance (`WEBHOOK_PROCESSING`, `ON_DEMAND_API`, `REPLAY_REQUEST`) as a convenience field.

---

## Version Constants

| Constant | Value | Meaning |
|---|---|---|
| `TRACE_SCHEMA_VERSION` | `"TRC-1.0"` | Version of the canonical payload structure |
| `HASH_ALGORITHM` | `"SHA-256"` | Hash algorithm for all digests |
| `CANONICALIZATION_VERSION` | `"CG-1.0"` | Serialization rules version |
| `HASH_DOMAIN` | `"evidencegraph.integrity_trace.v1"` | Domain separation prefix in every payload |
| `INTEGRITY_METHODOLOGY_VERSION` | `"EIS-1.0"` | Phase 9 methodology version (from `integrity_types`) |

---

## Migration

Alembic revision: `0009_phase10` (`backend/alembic/versions/20260823_0009_phase10_traces.py`)

Revises: `0008_phase9`

Creates both tables in one upgrade. Downgrade drops both tables in reverse dependency order.
