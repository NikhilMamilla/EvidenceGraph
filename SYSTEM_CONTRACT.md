# SYSTEM CONTRACT — EvidenceGraph Authoritative Model & Architecture Specification

## 1. Scope & Purpose

This document establishes the binding, non-negotiable **System Contract** for EvidenceGraph across all 20 phases. It formalizes the precise semantic definition, inputs, processing pipeline, outputs, and authoritative sources of truth for every domain and system entity.

Zero analytical conclusions or operational states exist without satisfying this contract.

---

## 2. Core Entities & Processing Semantics

### 2.1 WebhookEvent
- **Definition**: The raw, byte-for-byte record of an incoming webhook transmission from Razorpay or external providers.
- **Input**: Public HTTP request payload, signature header, and IP header.
- **Processing**: SHA-256 HMAC signature verification (`Razorpay-Signature`), unique event ID deduplication (`event_id`), and immediate PostgreSQL insertion.
- **Output**: Persisted `WebhookEvent` record with `processing_status` in (`RECEIVED`, `PROCESSED`, `DUPLICATE`, `FAILED`).
- **Source of Truth**: `webhook_events` PostgreSQL table.

### 2.2 Payment & PaymentEvent
- **Definition**: The canonical payment entity and its discrete state transitions.
- **Input**: Normalized `WebhookEvent` payload data.
- **Processing**: State machine evaluation (`AUTHORIZED` $\to$ `CAPTURED` $\to$ `REFUNDED` / `FAILED`), ensuring lifecycle consistency.
- **Output**: `Payment` row and appended `PaymentEvent` historical log.
- **Source of Truth**: `payments` and `payment_events` tables.

### 2.3 EvidenceObservation
- **Definition**: An atomic, immutable observation extracted from a verified provider transmission with provenance metadata.
- **Input**: Specific attributes within a processed payment event.
- **Processing**: Attribution of `source_type` (e.g. `RAZORPAY_WEBHOOK`), `extraction_method` (`DIRECT`), and computation of confidence and observation timestamp.
- **Output**: Append-only `EvidenceObservation` record.
- **Source of Truth**: `evidence_observations` table.

### 2.4 EvidenceFact
- **Definition**: A canonical real-world assertion normalized across multiple observations.
- **Input**: Multiple `EvidenceObservation` instances tied to a payment.
- **Processing**: Canonicalization via `_canonical_value_hash`, multi-source reconciliation, and fact lifetime interval tracking (`first_observed_at`, `last_observed_at`).
- **Output**: Reconciled `EvidenceFact` and links in `observation_fact_links`.
- **Source of Truth**: `evidence_facts` table.

### 2.5 Claim & Corroboration
- **Definition**: Structured propositions regarding payment attributes (e.g., `PAYMENT_CAPTURED`, `AMOUNT_MATCHES`), grouped and corroborated across distinct sources.
- **Input**: Extracted evidence observations.
- **Processing**: Grouping by semantic subject, cross-referencing source independence, calculating concentration scores (Herfindahl-Hirschman Index - HHI).
- **Output**: `Claim`, `EvidenceGroup`, and `EvidenceCorroboration` entities.
- **Source of Truth**: `claims`, `evidence_groups`, `evidence_corroborations`.

### 2.6 EvidenceConflict (Contradiction)
- **Definition**: Formal detection of mutually incompatible observations (e.g., status conflict, timestamp inversion, or amount divergence).
- **Input**: Multiple observations asserting disparate values for the same logical attribute.
- **Processing**: Deterministic conflict rules, severity assignment (`LOW`, `MEDIUM`, `HIGH`, `CRITICAL`), and status tracking (`ACTIVE`, `RESOLVED`, `ARBITRATED`).
- **Output**: `EvidenceConflict` entity.
- **Source of Truth**: `evidence_conflicts` table.

### 2.7 EvidenceCoverage (Completeness)
- **Definition**: Formal evaluation of observed evidence against an explicit profile requirement schema.
- **Input**: Current facts and observations for a payment against a `CoverageProfile` (e.g., `STANDARD_PAYMENT_PROFILE_ID`).
- **Processing**: Requirement completeness check, missing critical evidence detection, determining `CoverageState` (`COMPLETE`, `SUFFICIENT`, `PARTIAL`, `INSUFFICIENT`).
- **Output**: `EvidenceCoverageSnapshot` record.
- **Source of Truth**: `evidence_coverage_snapshots` table.

### 2.8 EvidenceReliability (Uncertainty Calibration)
- **Definition**: Multi-dimensional scoring of observation reliability and uncertainty boundaries.
- **Input**: Observations, corroborations, conflicts, and dependency depth.
- **Processing**: Scoring across 7 dimensions (Source, Provenance, Identity, Temporal, Structural, Contradiction, Dependency) and establishing epistemic uncertainty bounds ($[0.0, 1.0]$).
- **Output**: `EvidenceReliabilityAssessment` record.
- **Source of Truth**: `evidence_reliability_assessments` table.

### 2.9 EvidenceIntegrity & DecisionTrace
- **Definition**: Explainable composite integrity scoring coupled with a cryptographic SHA-256 decision trace chain.
- **Input**: Quality scores, consistency states, corroborations, and coverage evaluations.
- **Processing**: Weighted dimension aggregation, canonical payload serialization, SHA-256 digest computation, and hash-chaining to previous trace.
- **Output**: `EvidenceIntegritySnapshot` and immutable `EvidenceIntegrityTrace`.
- **Source of Truth**: `evidence_integrity_snapshots` and `evidence_integrity_traces`.

### 2.10 Decision Replay & Differential Analysis
- **Definition**: Point-in-time deterministic reconstruction of decision states and comparative delta analysis.
- **Input**: Target payment ID and timestamp $T_1$ (and optional $T_2$).
- **Processing**: Temporal filtering ($t \le T$), full pipeline reconstruction, and symmetric differential categorization (`FACT_CHANGED`, `CONFLICT_EMERGED`, `RELIABILITY_SHIFT`).
- **Output**: `DecisionReplayResponse` and `EvidenceDecisionDiffResponse`.
- **Source of Truth**: Point-in-time evaluation engine over immutable historical records.

### 2.11 Operational State & Continuous Verification
- **Definition**: Authoritative monitoring of system runtime health, queue lag, pipeline watermarks, and verification of 10 core invariants.
- **Input**: Live PostgreSQL pool probes, Redis `LLEN`, worker thread state, and database record timestamps.
- **Processing**: Lag computation $\Delta(\text{processed\_at} - \text{received\_at})$, stale analysis detection ($\text{observed\_at} > \text{evaluated\_at}$), invariant evaluation.
- **Output**: `SystemHealthResponse`, `SystemOperationalMetricsResponse`, and `VerificationRunResponse`.
- **Source of Truth**: Live system state and `OperationsService`.

---

## 3. Epistemic Principles & Non-Negotiable Axioms

1. **Unknown is distinct from Negative**: Absence of evidence is never treated as evidence of absence. Missing fields remain `UNKNOWN` or `MISSING`.
2. **Coverage is distinct from Reliability**: Having 100% of required fields present does not imply those fields are reliable or untampered.
3. **Reliability is distinct from Integrity**: High sensor/source reliability does not guarantee absence of semantic contradictions.
4. **Duplicate Idempotency**: Replaying identical provider events creates zero new facts, zero corroboration inflation, and zero integrity score drift.
5. **Temporal Immutability**: Historical evaluations and decision traces are append-only; future evidence cannot rewrite historical traces.
6. **Zero Data Fabrication**: No synthetic, hardcoded, or simulated metric or evidence is ever presented as production reality.
