# Phase 24 — Hardening, Verifier Test Suite & Real-LLM Wiring

**Status**: COMPLETE
**Scope**: security + robustness pass on the Track-02 defense verifier; no new
product surface.

---

## 1. Objective

Phases 21–23 built the defense verifier but shipped it with **zero dedicated
tests** and a stubbed-only AI layer. Phase 24 closes both gaps and hardens the
deterministic core against the failure modes in the evaluation-gate catalog.

---

## 2. Real-LLM providers (Phase 23 completion)

| Change | File |
|---|---|
| Native Claude provider (Anthropic SDK), interface-compatible with the OpenAI-compatible one | `app/services/ai_anthropic_provider.py` (new) |
| Provider factory — selects `test` / `openai` / `anthropic` by `AI_PROVIDER`; `is_real_llm_configured()` | `app/services/ai_config.py` |
| Fixed: `DefenseVerifier._init_provider()` always fell back to the test stub | `app/services/defense_verifier.py` |
| Track C uses whichever real provider is configured | `app/services/three_way_evaluation.py` |
| `/defense/ai/status` reports `provider_name`, `model`, `real_llm_ready` (never the key) | `app/api/v1/defense_verification.py` |
| `anthropic>=1.0.0`, `openai>=1.54.0`; every `AI_*` var documented | `requirements.txt`, `.env.example` |

Keyless behaviour is unchanged: no key → `AI_UNAVAILABLE` → the deterministic
evaluator still returns a verdict. Nothing fabricated is ever substituted.

---

## 3. Deterministic reference evaluator — REF_EVAL_V2

`app/services/defense_reference_evaluator.py`

| Fix | Effect |
|---|---|
| Timezone coercion in `_is_valid_for_evaluation` | naive timestamps (SQLite, some drivers) no longer raise on temporal comparison |
| **Provenance filter runs before coverage** | a fabricated document can no longer "cover" a required evidence type |
| **Entity-value match** (`_entity_value_matches`) | a `PAYMENT_ID_MATCH` / `ORDER_ID_MATCH` item must actually name this case's payment/order |
| **Delivery-status semantics** (`_delivery_value_status`) | a supporting delivery proof only counts if its value is a conclusive completed delivery; `in_transit` / `pending` / `failed` → not support (present-but-inconclusive → `UNKNOWN`, not `INSUFFICIENT`) |

### Measured on the 20-case golden set

| | REF_EVAL_V1 | REF_EVAL_V2 |
|---|---|---|
| Accuracy | 0.80 | **0.90** |
| Macro-F1 | 0.747 | **0.885** |
| False-SUPPORTED | 4 | **0** |
| Contradiction recall | 1.00 | **1.00** |
| Majority-class baseline (B1) | 0.33 | 0.33 |

Residual errors (2): `GOLDEN_010`, `GOLDEN_020` — a provenance-invalid delivery
proof is scored `INSUFFICIENT` where the human label is `UNKNOWN`. Both are on
the safe side of the confusion matrix.

---

## 4. Defense verifier test suite

`backend/tests/test_defense_verifier.py` — 26 tests, 4 groups:

1. **Golden baseline** — seed the 20 cases, run the evaluation engine, assert
   accuracy / macro-F1 floors, that it beats B1, total contradiction recall,
   zero false-SUPPORTED, stable dataset fingerprint.
2. **Metamorphic M1–M10** — duplicate / reorder / irrelevant evidence leave the
   verdict unchanged; remove-required → `INSUFFICIENT`; inject-contradiction →
   `CONTRADICTED`; future evidence excluded from a historical verdict; expired
   `valid_until`; empty set → `UNKNOWN`.
3. **Adversarial A1–A8** — evidence flooding, contradiction hiding, timestamp
   manipulation, wrong-entity evidence, fabricated source, empty provenance,
   duplicate inflation, and prompt-injection strings inside evidence text. Every
   one must fail *safe* (`INSUFFICIENT` / `CONTRADICTED` / `UNKNOWN`), never a
   confident wrong `SUPPORTED`.
4. **AI override policy** — test-provider determinism, hallucinated-ID rejection,
   AI cannot override a deterministic `CONTRADICTED`, AI failure still yields a
   deterministic verdict.

Full suite: **471 passing, 0 failing.**

---

## 5. Security notes

Published in [`docs/security-notes.md`](security-notes.md): secret rotation
(the DB password is currently reused as the webhook secret), `ADMIN_API_KEY`,
prompt-injection isolation, AI output validation, and the pre-public checklist.

---

## 6. Not done (needs a key / annotators / live Razorpay)

- Real three-way evaluation run with a live LLM key → the actual AI-vs-baseline
  metrics table.
- Golden set expansion 20 → 50–100 from real Test Mode base events.
- Two-annotator protocol + Cohen's kappa.

These are the Phase 25 plan.
