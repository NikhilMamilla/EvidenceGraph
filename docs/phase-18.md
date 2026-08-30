# Phase 18 — Deterministic Decision Replay & Differential Analysis

## 1. Executive Summary & Core Purpose

In production evidence processing systems, regulatory and operational integrity demands answering two critical historical questions:
1. **Decision Replay**: *"Can the system reproduce the exact same decision state and integrity verdict at historical timestamp $T$, bit-for-bit, excluding subsequent real-world evidence?"*
2. **Differential Analysis**: *"Between historical point $T_1$ and $T_2$, exactly what evidence, facts, corroborations, contradictions, coverage requirements, or reliability boundaries changed, and what caused the integrity status shift?"*

Phase 18 implements the **Deterministic Decision Replay Engine** and **Pairwise Decision Diff Engine** (`EDR-1.0` / `EDD-1.0` / `DCE-1.0`).

---

## 2. Core Architecture & Services

### A. Decision Replay Engine (`DecisionReplayEngine`)
- Reconstructs point-in-time state strictly bounded by `observed_at <= evaluation_time`.
- Pinned to exact methodology (`EIS-1.0`) and requirement profile versions.
- Generates deterministic SHA-256 fingerprints:
  - `input_fingerprint`: Canonical digest of input facts, observations, and conflict states.
  - `result_fingerprint`: Canonical digest of the derived integrity snapshot.
- Verifies stored historical decision traces (`EvidenceIntegrityTrace`) against replayed execution, returning `MATCH`, `REPLAY_MISMATCH`, or `TRACE_NOT_FOUND`.

### B. Decision Diff Engine (`DecisionDiffEngine`)
- Performs pairwise differential analysis between two timestamps $(T_1, T_2)$ for a given payment.
- Normalizes order automatically if $T_1 > T_2$.
- Categorizes fact transitions (`ADDED`, `REMOVED`, `MODIFIED`, `SUPERSEDED`, `UNRESOLVED`).
- Computes shifts across all 5 integrity dimensions (Freshness, Source Authority, Independence, Corroboration, Consistency) plus Coverage and Conflicts.
- Generates structured, deterministic change explanations (`what_changed`, `why_it_mattered`, `what_remains_uncertain`, `causal_summary`) without ungrounded heuristics or LLM hallucinations.

---

## 3. API Surface

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `POST` | `/api/v1/payments/{payment_id}/replay` | Deterministically reconstruct decision state and verify trace replay |
| `GET` | `/api/v1/payments/{payment_id}/diff?from={t1}&to={t2}` | Pairwise differential comparison between two timestamps |
| `GET` | `/api/v1/payments/{payment_id}/diff/explanation?from={t1}&to={t2}` | Structured explanation of decision divergence |

---

## 4. Verification & Invariance Guarantees

- **Metamorphic Invariance**: Multiple re-runs at the same timestamp yield identical SHA-256 fingerprints.
- **Strict Temporal Isolation**: Future observations arriving at $T > T_1$ never leak into replays at $T_1$.
- **Test Suite**: Fully verified under `backend/tests/test_decision_replay.py` with 100% test pass rate across unit, differential, metamorphic, and API integration scenarios.
