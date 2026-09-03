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
| Mistral provider — Mistral's OpenAI-compatible endpoint, subclasses `RealLLMProvider` (reuses the prompt/parse pipeline), reads `MISTRAL_API_KEY` / `AI_MISTRAL_MODEL` | `app/services/ai_mistral_provider.py` (new) |
| Provider factory — selects `test` / `openai` / `anthropic` / `mistral` by `AI_PROVIDER`; `is_real_llm_configured()` | `app/services/ai_config.py` |
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

### Measured on the golden set

`EG-DEFENSE-1.0` was expanded from 20 to **50 cases** (12 `SUPPORTED` / 14
`INSUFFICIENT` / 12 `CONTRADICTED` / 12 `UNKNOWN`) and frozen.

| | 20 cases | **50 cases** |
|---|---|---|
| Accuracy | 0.90 | **0.92** |
| Macro-F1 | 0.885 | **0.92** |
| False-SUPPORTED | 0 | **0** |
| Contradiction recall | 1.00 | **1.00** |
| Majority-class baseline (B1) | 0.33 | 0.32 |
| Cohen's κ (primary vs adjudication) | — | **0.87** |

Residual errors (4): `GOLDEN_010/020/036/037` — a provenance-invalid or
near-miss entity match scored `INSUFFICIENT` where the label is `UNKNOWN`. All
on the safe side; zero false-SUPPORTED, zero missed contradictions.

**Label reliability.** Each case carries a primary label and an independent
second-pass adjudication (`compute_inter_annotator_agreement()`,
`GET /defense/evaluation/agreement`). κ = 0.87 ("almost perfect"), 5
disagreements, all on the `INSUFFICIENT` ↔ `UNKNOWN` boundary. This is
single-annotator + self-adjudication — documented as such. `POST
/defense/evaluation/freeze` makes the set immutable; the Docker image freezes
on first boot (`SEED_FREEZE_DATASET=true`).

---

## 4. Defense verifier test suite

`backend/tests/test_defense_verifier.py` — 26 tests, 4 groups:

1. **Golden baseline** — seed the 50 cases, run the evaluation engine, assert
   accuracy ≥ 0.88 / macro-F1 ≥ 0.85, beats B1, total contradiction recall,
   zero false-SUPPORTED, stable fingerprint. Plus `TestDatasetIntegrity`:
   50-case / four-label spread, κ ≥ 0.75, adjudication labels seeded, freeze
   makes re-seed a no-op.
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

Full suite: see `python -m pytest -q` (all green).

---

## 5. Security notes

Published in [`docs/security-notes.md`](security-notes.md): the webhook
secret is now distinct from the DB password; `ADMIN_API_KEY` is set; a
`SecurityHeadersMiddleware` + `RateLimitMiddleware` were added (headers on every
API response, a 120/min per-IP fixed-window limiter on the write / expensive
routes); CORS `allow_headers` is an explicit list. Covered by
`tests/test_security_middleware.py`.

---

## 6. Done in this pass

- Golden set expanded 20 → **50**, frozen, with a second label pass and Cohen's κ.
- `SecurityHeadersMiddleware`, `RateLimitMiddleware`, tighter CORS, distinct
  webhook secret, `ADMIN_API_KEY` set.

## 7. Still open (needs a key / live Razorpay / recruits)

- Real three-way evaluation run with a live LLM key → the actual AI-vs-baseline
  metrics table (`AI_ENABLED=true` + a provider key).
- Golden set drawn from real Test Mode base events (currently template-built).
- A true two-annotator protocol with independent recruits (current κ is
  self-adjudication).
