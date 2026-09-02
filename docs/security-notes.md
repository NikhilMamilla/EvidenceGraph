# Security notes

Defensive-security posture for the EvidenceGraph chargeback defense verifier.
Track 02 is **defense-only** — nothing in this system is offense-capable.

---

## Secrets

| Item | State | Action |
|---|---|---|
| `.env` | Gitignored; never committed. Verified clean before the first commit. | Keep it out of git. `git status` should never list it. |
| Supabase DB password | Currently **reused** as `RAZORPAY_WEBHOOK_SECRET` (same string). | **Rotate both** to independent high-entropy values before the repo is made public or shared. Supabase → Project Settings → Database → Reset password. Razorpay → Dashboard → Webhooks → regenerate secret. |
| `RAZORPAY_KEY_SECRET` | Test-mode key in `.env`. | Fine for the demo. Never commit a live-mode key. |
| `ADMIN_API_KEY` | Empty. Restricted trace / replay / chain-verify endpoints **fail closed (503)** when unset. | Set a random 32+ char value before demoing the cryptographic-trace endpoints. |
| `ANTHROPIC_API_KEY` / `AI_API_KEY` | Unset. The verifier runs the deterministic stub until a key is present. | Add to `.env` only; the code reads it from the environment and never logs it. |

Rotate anything that has been pasted into a chat, screen-shared, or committed
in history — treat it as burned.

---

## Request handling

- **Webhook signature is verified against the raw body before any parsing.**
  `POST /api/v1/webhooks/razorpay` reads `await request.body()` and runs
  HMAC-SHA256 verification before the payload is deserialized. Unverified
  payloads get `400`; a missing secret gets `503` (fail closed).
- **No secrets in responses, logs, or errors.** The global exception handler
  returns a typed envelope with no stack trace, DB URL, or Redis URL. API
  responses bound `payment_method_details` to non-sensitive fields.
- **Append-only evidence.** Observations and decision traces cannot be mutated
  or deleted in place — tamper-evidence for the audit trail.

---

## AI semantic layer

The AI layer (`AI_ENABLED=true`) is **advisory only** and is treated as an
untrusted component:

- **Prompt-injection isolation.** Merchant defense text and evidence values are
  passed as *data*, never concatenated into system instructions. The system
  prompt explicitly tells the model to ignore instructions embedded in the
  input. Covered by `test_defense_verifier.py::TestAdversarial::test_a8_*`.
- **Output is validated, not trusted.** Extracted claim types are checked
  against an allowlist; evidence IDs the model returns that are not in the
  candidate set are dropped (`DefenseVerifier._validate_references`); confidence
  is clamped to `[0,1]`.
- **The AI can never override the deterministic verdict.** A deterministic
  `CONTRADICTED` / `INSUFFICIENT` / `UNKNOWN` always wins. The AI can only move
  `UNKNOWN → SUPPORTED` when deterministic coverage is already complete.
  Covered by `TestAIOverridePolicy`.
- **Graceful degradation.** Any provider error → `AI_UNAVAILABLE`, and the
  deterministic evaluator still produces a verdict. No fabricated result is ever
  substituted for a failed AI call.
- **Data minimization.** Only the fields needed for claim matching are sent
  (evidence type, value, source type, id) — no raw webhook payloads, no PII
  beyond what the dispute requires.

---

## Known info-disclosure (accepted for the demo)

- `GET /api/v1/defense/ai/status` is unauthenticated and reveals whether a real
  LLM key is configured and which model id is set (not the key). Consistent with
  the rest of the read-only API surface; gate behind `ADMIN_API_KEY` if this is
  ever exposed beyond a demo.
- Most read endpoints are unauthenticated by design (inspection tool). Only the
  full cryptographic-trace / replay / chain-verify endpoints require
  `X-API-Key`.

---

## Before making the repo public

1. Rotate the reused DB / webhook secret.
2. `git log -p -- .env` → confirm it never appears in history (it does not in
   the current branch; check `main` if you merge).
3. Scan history for the reused string. Do **not** paste the secret into this
   file — read it from the untracked `.env` so the check never becomes its own
   match:

   ```bash
   SECRET=$(grep -oP '(?<=^RAZORPAY_WEBHOOK_SECRET=).*' .env)
   git grep -I -- "$SECRET" $(git rev-list --all)   # must return nothing
   ```
4. Set `ADMIN_API_KEY`.
5. Confirm `docs/`, `README.md`, and screenshots contain no real key material.
