# Phase 8 — Contradiction & Temporal Consistency Engine

## What Phase 8 Establishes

Phase 7 gave us structural understanding: how many independent sources, claims, and corroborations exist.

Phase 8 asks a different question:

> **Are those observations consistent with one another?**

Phases 1–7 can tell us that we have 10 observations, 3 sources, 2 claims, and high concentration — but none of that tells us whether the observations *agree* with each other. Phase 8 builds the engine that detects when they don't.

---

## What Phase 8 Does NOT Do

Phase 8 is strictly structural observation. It does **not**:

- Calculate a fraud score
- Calculate a risk score
- Calculate a trust score
- Make automated payment decisions
- Block payments
- Use ML, LLM, or any AI reasoning

> **Contradiction != Fraud.**

A conflict is a structural observation about evidence inconsistency. Severity describes the degree of *semantic inconsistency*, not fraud likelihood.

---

## Architecture

### Payment State Machine

Encodes the deterministic Razorpay payment lifecycle:

    created -> authorized -> captured -> refunded
                           -> failed
    authorized -> failed

Normalization: Razorpay's `paid` status is treated as equivalent to `captured`.

### Contradiction Engine

Evaluates all claims for a given payment and produces EvidenceConflict records.

#### Conflict Types

| Type | Severity | What it detects |
|---|---|---|
| STATE_CONFLICT | HIGH | Two terminal states that cannot both be true (e.g., captured + failed) |
| VALUE_CONFLICT | HIGH | Two different canonical values for the same claim key |
| RELATIONSHIP_CONFLICT | MEDIUM | Two different entity relationships that cannot both be valid |
| TEMPORAL_CONFLICT | MEDIUM | A backward state transition with clear time ordering |
| ORDERING_AMBIGUITY | INFO | Two statuses within clock tolerance — ambiguous, not contradictory |

#### Key Design Decisions

- **Pair normalization**: claim_a_id < claim_b_id always
- **Idempotency**: unique constraint on (payment_id, claim_a_id, claim_b_id, conflict_type, rule_version)
- **Clock tolerance**: Configurable. Default 2.0 seconds.
- **Rule versioning**: Every conflict records the rule_version that produced it
- **Datetime normalization**: _ensure_utc() normalizes SQLite naive datetimes

---

## Data Model

### EvidenceConflict

    evidence_conflicts
    - internal_id        PK
    - payment_id         str
    - claim_a_id         int FK -> claims
    - claim_b_id         int FK -> claims (always > claim_a_id)
    - conflict_type      str ConflictType enum
    - severity           str ConflictSeverity enum
    - status             str OPEN|RESOLVED|SUPERSEDED|UNRESOLVED
    - detected_at        datetime(tz)
    - rule_version       str
    - explanation        JSONB {what, why, rule, timestamp_a, timestamp_b, sources_a, sources_b}
    - created_at         datetime(tz)

### ConflictResolution

    conflict_resolutions
    - internal_id             PK
    - conflict_id             int FK -> evidence_conflicts
    - resolving_evidence_id   int FK -> evidence_observations (nullable)
    - resolution_type         str ResolutionType enum
    - explanation             str
    - resolved_at             datetime(tz)
    - rule_version            str
    - metadata_               JSONB
    - created_at              datetime(tz)

A ConflictResolution marks a conflict as resolved without deleting the original EvidenceConflict.

---

## API Layer

| Method | Route | Description |
|---|---|---|
| GET | /api/v1/payments/{id}/conflicts | All conflicts for a payment |
| GET | /api/v1/payments/{id}/consistency | Consistency summary with is_consistent flag |
| GET | /api/v1/conflicts/{conflict_id} | Single conflict by ID |

### is_consistent definition

is_consistent = True when no OPEN conflict with severity greater than INFO exists.

ORDERING_AMBIGUITY (INFO severity) does not make a payment inconsistent.

---

## Integration

The ContradictionEngine is invoked at the end of webhook_worker.py after:

1. Evidence extraction
2. Provenance recording
3. Relationship graph construction
4. Quality measurement
5. Structure evaluation (claims, corroboration)
6. Contradiction evaluation (Phase 8)

---

## Tests

tests/test_contradiction.py — 28 tests, all passing.

| Class | Coverage |
|---|---|
| TestStateMachine | Valid/invalid transitions, terminal contradictions, paid normalization |
| TestValidLifecycle | Full created -> authorized -> captured produces zero conflicts |
| TestOutOfOrderDelivery | Out-of-order webhook delivery produces zero conflicts |
| TestStateConflict | captured + failed = STATE_CONFLICT (HIGH) |
| TestValueConflict | Two amounts = VALUE_CONFLICT (HIGH); same amount = no conflict |
| TestRelationshipConflict | Two order_ids = RELATIONSHIP_CONFLICT (MEDIUM) |
| TestOrderingAmbiguity | Within clock tolerance = ORDERING_AMBIGUITY (INFO) |
| TestIdempotency | No duplicate conflicts on re-evaluation |
| TestConflictResolution | Conflict resolved; original record preserved |
| TestEdgeCases | No claims, single claim, rule version, structured explanation |
| TestConflictAPI | Conflicts list, consistency summary, 404 for missing |

---

## What Phase 8 Produces

After Phase 8, for any payment we can answer:

    Are all observations of this payment's lifecycle consistent
    with one another across time, values, and entity relationships?

The answer is a structured set of conflict observations, each with:
- A conflict type
- A severity
- A status (open or resolved)
- A rule version
- A structured explanation (what happened, why it's a conflict, timestamps, sources)

---

## What Phase 9 Will Add

Phase 9 will synthesize the outputs of Phases 5-8 into the Evidence Integrity Score.

Score inputs:
- Freshness status (Phase 6)
- Source quality (Phase 6)
- Independence / concentration (Phase 7)
- Contradiction observations (Phase 8)
