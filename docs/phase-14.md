# Phase 14 — End-to-End Evidence Lineage & Causal Explanation Engine

## 1. Executive Summary

Phase 14 delivers a deterministic, time-aware Evidence Lineage & Causal Explanation Engine for EvidenceGraph. It answers:
> *"Show me the complete chain of reasoning from the original Razorpay event to the final Evidence Integrity result, and explain exactly what each transformation contributed."*

The engine traverses authoritative database Foreign Keys (FKs) and documented temporal linkages, assembling an explainable Directed Acyclic Graph (DAG) without guessing, predictive modeling, or LLM hallucinations.

---

## 2. Lineage Taxonomy & Schema

### 2.1 Node Types (`LineageNodeType`)
- `PAYMENT`: Canonical payment anchor (`Payment`)
- `WEBHOOK_EVENT`: Raw provider webhook ingestion record (`WebhookEvent`)
- `PAYMENT_EVENT`: Normalized payment event (`PaymentEvent`)
- `OBSERVATION`: Immutable evidence observation (`EvidenceObservation`)
- `FACT`: Canonical reconciled fact (`EvidenceFact`)
- `CLAIM`: Canonical proposition claim (`Claim`)
- `QUALITY_SNAPSHOT`: Point-in-time quality evaluation (`EvidenceQualitySnapshot`)
- `STRUCTURE_SNAPSHOT`: Structural concentration evaluation (`EvidenceStructureSnapshot`)
- `CORROBORATION`: Independence and corroboration record (`EvidenceCorroboration`)
- `CONFLICT`: Recorded contradiction or value mismatch (`EvidenceConflict`)
- `RECONCILIATION`: Pairwise observation reconciliation (`EvidenceReconciliation`)
- `INTEGRITY_SNAPSHOT`: Authoritative integrity evaluation (`EvidenceIntegritySnapshot`)
- `INTEGRITY_TRACE`: Tamper-evident evaluation trace (`EvidenceIntegrityTrace`)
- `STATE_SNAPSHOT`: Temporal evolution state snapshot (`EvidenceStateSnapshot`)
- `STATE_CHANGE`: Observable state transition (`EvidenceStateChange`)

### 2.2 Edge & Linkage Types
- `LineageEdgeType`:
  - `PRODUCED`: Event produced an observation (`WebhookEvent` -> `EvidenceObservation`)
  - `REPRESENTS`: Observation represents a fact (`EvidenceObservation` -> `EvidenceFact`)
  - `SUPPORTS`: Observation supports a claim (`EvidenceObservation` -> `Claim`)
  - `EVALUATED_BY`: Snapshot evaluated by decision trace (`EvidenceIntegritySnapshot` -> `EvidenceIntegrityTrace`)
  - `CORROBORATED_BY`: Claim corroborated by evidence (`Claim` -> `EvidenceCorroboration`)
  - `CONFLICTED_BY`: Claim involved in contradiction (`Claim` -> `EvidenceConflict`)
  - `RECONCILED_INTO`: Observation reconciled into fact (`EvidenceObservation` -> `EvidenceFact`)
  - `STATE_TRANSITION`: State transition over time (`EvidenceStateSnapshot` -> `EvidenceStateChange`)
  - `CONTRIBUTES_TO`: Component contributes to integrity assessment
- `LinkageType`:
  - `FOREIGN_KEY`: Explicit DB foreign key relationship
  - `DERIVED_TEMPORAL`: Documented temporal/payment association where no explicit FK exists
- `CausalRole`:
  - `ROOT_CAUSE`: Originating event trigger
  - `DIRECT_INPUT`: Direct parameter to transformation
  - `CONTRIBUTING_INPUT`: Contextual input
  - `DERIVED_FROM`: Output of transformation rule
  - `EVALUATIVE`: Audit trace / assessment
  - `UNKNOWN`: Unverifiable causal relationship

### 2.3 Completeness & Gaps
- `LineageCompleteness`:
  - `COMPLETE`: Full chain exists from `WebhookEvent` to `EvidenceIntegrityTrace`
  - `PARTIAL`: Observations or facts exist, but integrity trace is missing
  - `BROKEN`: Critical prerequisite links (e.g. observations) are absent
- `LineageGap`: Explicit records for expected but missing relationships in the lineage graph.

---

## 3. Core Engine Architecture

The `LineageEngine` (`app/services/lineage_engine.py`) provides:
1. `build_payment_lineage(db, payment_id, as_of, max_nodes, max_depth)`: Forward lineage traversal from raw event to integrity decision trace.
2. `build_trace_lineage(db, trace_id, max_nodes)`: Backward lineage traversal from an integrity trace to its originating webhook inputs.
3. `build_fact_lineage(db, fact_id, as_of)`: Sub-lineage centered on a specific `EvidenceFact`.
4. `find_lineage_path(db, source_type, source_id, target_type, target_id, max_depth, as_of)`: Bounded BFS pathfinder between arbitrary entities in the lineage graph.

### Safety & Invariants
- **Strictly Bounded**: Hard limit of 500 nodes and depth 10 to avoid performance degradation.
- **Time-Aware (`as_of`)**: Future observations observed after `as_of` are strictly excluded.
- **Zero Sensitive Exposure**: Metadata strips `raw_payload`, signatures, secrets, and auth tokens.
- **Deterministic Explanations**: Generated strictly from rule IDs, fact types, and status fields without LLMs.

---

## 4. API Endpoints

- `GET /api/v1/payments/{payment_id}/lineage`: Forward payment lineage DAG.
- `GET /api/v1/integrity/{trace_id}/lineage`: Backward trace lineage DAG.
- `GET /api/v1/facts/{fact_id}/lineage`: Fact-scoped lineage.
- `GET /api/v1/lineage/path`: Shortest path between two lineage nodes.

---

## 5. Verification & Testing

24 automated unit and API integration tests in `backend/tests/test_lineage.py`:
- Completeness classifications (`COMPLETE`, `PARTIAL`, `BROKEN`)
- Lineage gap detection
- Forward and backward traversals
- Authoritative FK edges (`ObservationFactLink`, `EvidenceClaimLink`, etc.)
- Temporal `as_of` boundaries
- Safety bounds and node deduplication
- Zero sensitive data exposure
- Deterministic explainability
