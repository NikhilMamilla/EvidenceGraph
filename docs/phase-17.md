# Phase 17 — Adversarial Evidence Validation & Failure-Safety Engine

## 1. Executive Summary & Core Philosophy

As evidence graph architectures grow in analytical sophistication, the most dangerous vulnerability is **epistemic overconfidence**: producing convincing, mathematically detailed, yet fundamentally flawed verdicts under messy or hostile real-world conditions.

Phase 17 establishes the **Deterministic Evidence Adversarial & Failure-Safety Engine**. Its explicit mission is not to add speculative predictive models, but to **adversarially stress-test and formally prove** that EvidenceGraph fails safely under corrupted, duplicated, reordered, delayed, conflicting, and tampered evidence streams.

```
   ┌─────────────────────────────────────────────────────────────────────────────┐
   │                        Phase 17 Adversarial Engine                          │
   ├─────────────────────────────────────────────────────────────────────────────┤
   │  ┌───────────────────────┐   ┌───────────────────────┐   ┌────────────────┐ │
   │  │ 12 Attack Categories  │──▶│ 15 Core Invariants    │──▶│ 10 Golden      │ │
   │  │ • Duplicate Events    │   │ • INV-01 to INV-15    │   │ Metamorphic    │ │
   │  │ • Reordered Delivery  │   │ • Temporal Exclusion  │   │ Reference      │ │
   │  │ • Clock Skew / Delay  │   │ • Provenance Bounding │   │ Cases          │ │
   │  │ • Terminal Conflicts  │   │ • Identity Isolation  │   │ • Pass: Safe   │ │
   │  │ • Source Clustering   │   │ • Tamper Detection    │   │ • Fail: Wrong  │ │
   │  │ • Tampered Payloads   │   └───────────────────────┘   │   Confidence   │ │
   │  └───────────────────────┘                               └────────────────┘ │
   └─────────────────────────────────────────────────────────────────────────────┘
```

> **Fundamental Invariant:**
> A visible `UNKNOWN`, `CONFLICTED`, or `LIMITED` result is a **PASS**.
> A convincing but incorrect answer is considered a **CRITICAL FAILURE**.

---

## 2. The 15 Core Architectural Invariants

| ID | Invariant Name | Formal Specification & Safety Guarantee |
| :--- | :--- | :--- |
| **INV-01** | **Raw Preservation** | Raw observations are never mutated or silently destroyed. Missing attributes produce no observation, preserving original payload fidelity. |
| **INV-02** | **No Duplicate Inflation** | Duplicate provider events sharing the same upstream ID do not multiply distinct sources or generate artificial corroboration. |
| **INV-03** | **Temporal Boundary** | Evidence observed after evaluation anchor `as_of` is strictly excluded from historical assessments. Future data never leaks into past snapshots. |
| **INV-04** | **No Fallback Guesswork** | `UNKNOWN` never resolves into a positive claim through default fallbacks or probabilistic heuristics. |
| **INV-05** | **Absence $\neq$ Proof of Absence** | Missing evidence is recorded as missing or incomplete coverage, never asserted as proof of fraud or non-occurrence. |
| **INV-06** | **Auth $\neq$ Semantic Truth** | Cryptographic HMAC verification confirms channel authenticity only; conflicting claims from authenticated sources remain explicit contradictions. |
| **INV-07** | **Cross-Payment Isolation** | Identical attribute values across distinct payments never merge into shared facts or cross-pollinate coverage profiles. |
| **INV-08** | **Lifecycle Distinction** | Multiple lifecycle events for the same payment (e.g., `authorized`, `captured`, `refunded`) are maintained as separate, distinct facts. |
| **INV-09** | **Trace Reproducibility** | Historical audit traces and canonical serialized payloads produce deterministic, bit-for-bit identical SHA-256 digests on replay. |
| **INV-10** | **No Relationship Invention** | Entity graph edges (e.g., payment-to-order associations) are constructed solely when supported by explicit upstream evidence observations. |
| **INV-11** | **Conflict Persistence** | Contradictions and state inconsistencies remain visible and queryable across evaluations until formally resolved. |
| **INV-12** | **Reliability Bounding** | Adding duplicate observations from the same source or under open contradictions cannot elevate reliability to `HIGH`. |
| **INV-13** | **Coverage Invariance** | Re-sending identical observations does not increase the count of required or expected facts satisfied. |
| **INV-14** | **Methodology Auditing** | Every integrity, coverage, and reliability assessment carries an explicit, versioned methodology string (`EIS-1.0`, `ECM-1.0`, `ERM-1.0`). |
| **INV-15** | **Lineage Safety Bounds** | Graph traversal depth and node retrieval limits are strictly bounded to prevent runaway recursion or resource exhaustion. |

---

## 3. The 10 Golden Metamorphic Reference Cases

| Case ID | Scenario Description | Input Perturbation | Expected Safe Outcome | Invariant |
| :--- | :--- | :--- | :--- | :--- |
| **`GOLDEN_001`** | **Normal Captured Payment** | Standard verified webhook payload with complete lineage | `HIGH` reliability, complete provenance | Baseline |
| **`GOLDEN_002`** | **Duplicate Replay Attack** | Single webhook duplicated 10x with identical ID | Reliability capped $\le$ baseline rank; no source inflation | **INV-02, INV-12** |
| **`GOLDEN_003`** | **Reordered Lifecycle** | `captured` arrives with earlier timestamp than `authorized` | `STATE_CONFLICT` / `TEMPORAL_CONFLICT` generated | **INV-08, INV-11** |
| **`GOLDEN_004`** | **Conflicting Monetary Value** | Conflicting amount claims (`50000` vs `70000`) for same payment | `VALUE_CONFLICT` flagged; reliability degraded | **INV-06, INV-11** |
| **`GOLDEN_005`** | **Omitted Lifecycle Step** | Capture observed without prior authorization | Incomplete coverage; missing requirement noted | **INV-05, INV-13** |
| **`GOLDEN_006`** | **Ambiguous Entity Identity** | Observation with insufficient attributes for reconciliation | Fact remains in `UNRESOLVED` status | **INV-04** |
| **`GOLDEN_007`** | **Clustered Source Dependency** | 10 observations generated from single webhook event | Classified as `SAME_SOURCE_CORROBORATION` | **INV-02** |
| **`GOLDEN_008`** | **Historical Point-in-Time** | `as_of` set to $T_1$ while additional evidence exists at $T_2 > T_1$ | Future evidence excluded; snapshot evaluates only $T \le T_1$ | **INV-03** |
| **`GOLDEN_009`** | **Delayed Network Arrival** | Late webhook arrival where arrival time $\gg$ event time | Chronology ordered by provider `observed_at` | **INV-09** |
| **`GOLDEN_010`** | **Severed Lineage Chain** | Observation persisted with `webhook_event_id = NULL` | Provenance dimension flags `BROKEN`; status $\ne$ `HIGH` | **INV-15** |

---

## 4. Attack Categories & Failure Modes Validated

### A. Duplication & Replay
- Evaluates behavior when upstream providers send repeated webhooks or re-deliver messages.
- Verifies that `CorroborationService` does not elevate single-source duplicates to `MULTI_SOURCE_CORROBORATION`.
- Proves that `CoverageEngine` and `ReliabilityEngine` do not inflate scores under replay conditions.

### B. Reordering & Temporal Inversions
- Simulates out-of-order network arrival and invalid backward state transitions (e.g., `refunded` before `captured`, `captured` before `authorized`).
- Asserts that `PaymentStateMachine` rejects invalid state movements and `ContradictionEngine` raises explicit `STATE_CONFLICT` records.

### C. Contradictions & Value Clashes
- Injects conflicting attributes from authenticated webhooks (different amounts, different order associations, contradictory terminal states).
- Proves that authenticated delivery does not suppress contradiction detection, maintaining visibility of conflicting real-world assertions.

### D. Malformed Payloads & Missing Provenance
- Injects observations with null values, unknown source types, and omitted webhook references.
- Validates that the system safely degrades reliability dimensions (`BROKEN` provenance, `UNKNOWN` source authenticity) without raising unhandled runtime exceptions.

### E. Tampering Simulation & Cryptographic Integrity
- Modifies canonical payload JSON after record creation and executes `TraceVerificationService.verify_trace_integrity`.
- Demonstrates constant-time SHA-256 digest comparison detecting modified fields, returning `status="INVALID"`.

---

## 5. Verification & Test Metrics

- **Total Backend Tests Passing**: **424 / 424** tests (100% pass rate).
- **Adversarial Test Suite (`test_adversarial.py`)**: **41 dedicated test scenarios** covering all 15 core invariants and 10 golden cases.
- **Frontend Production Build**: Clean build with Vite & TypeScript (`tsc -b && vite build`) with zero regressions.
- **Methodology Version**: Governed under **`EAV-1.0`** (Evidence Adversarial Validation v1.0).
