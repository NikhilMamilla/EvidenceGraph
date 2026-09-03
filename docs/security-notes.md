# Security notes

Defensive-security posture for the EvidenceGraph chargeback defense verifier.
Track 02 is **defense-only** — nothing in this system is offense-capable.

---

## Secrets

| Item | State | Action |
|---|---|---|
| `.env` | Gitignored; never committed. Verified clean before the first commit. | Keep it out of git. `git status` should never list it. |
| Supabase DB password | Independent value. **No longer reused** as the webhook secret. The old shared string still exists in git history from earlier commits. | Rotate the Supabase password (Project Settings → Database → Reset password) so the history copy is dead. |
| `RAZORPAY_WEBHOOK_SECRET` | Now a distinct `whsec_...` value in `.env`, generated with `secrets.token_urlsafe(32)`. | Set the **same value** in the Razorpay dashboard (Settings → Webhooks) so signature checks pass. |
| `RAZORPAY_KEY_SECRET` | Test-mode key in `.env`. | Fine for the demo. Never commit a live-mode key. |
| `ADMIN_API_KEY` | Set in `.env` (`secrets.token_urlsafe(36)`). Restricted trace / replay / chain-verify endpoints require it via `X-API-Key`; they **fail closed (503)** if it is ever unset. | Keep it in `.env` only. Rotate if shared. |
| `ANTHROPIC_API_KEY` / `AI_API_KEY` | Unset. The verifier runs the deterministic stub until a key is present. | Add to `.env` only; the code reads it from the environment and never logs it. |

Rotate anything that has been pasted into a chat, screen-shared, or committed
in history — treat it as burned.

---

## Transport & middleware hardening

Wired in `app.main.create_app()` (order: security headers outermost, then rate
limiter, then correlation ID):

- **Security headers on every API response** (`SecurityHeadersMiddleware`):
  `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`,
  `Referrer-Policy: no-referrer`, a restrictive `Permissions-Policy`,
  `Cross-Origin-Opener-Policy: same-origin`, `Cross-Origin-Resource-Policy:
  same-site`, and `Cache-Control: no-store` on `/api/` paths. nginx sets its own
  headers for the SPA; this covers direct access to `:8000`.
- **In-process rate limiting** (`RateLimitMiddleware`, `RATE_LIMIT_PER_MINUTE`,
  default 120/min per client IP): fixed-window limiter on the mutating /
  expensive routes only — `/webhooks/*`, `/defense/evaluation/{run,seed,freeze}`,
  `/defense/verify`, `/defense/ai/evaluate`. `GET` and health probes are never
  limited. Over the limit → `429` with `Retry-After`. Set to `0` to disable
  (the test suite does). A real deployment puts this at the edge.
- **Tighter CORS.** `allow_headers` is an explicit list
  (`Content-Type, Authorization, X-API-Key, X-Request-ID`), not `*`.
- **Docs surface.** `/docs`, `/redoc` and `/openapi.json` are served only when
  `APP_ENV != production`.

Covered by `tests/test_security_middleware.py`.

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

1. **Rotate the Supabase DB password.** The old value was reused as the webhook
   secret in earlier commits and still lives in git history — rotating is the
   only way to kill that copy. Supabase → Project Settings → Database → Reset
   password, then update `DATABASE_URL` in `.env`.
2. **Webhook secret** is already a distinct `whsec_...` value (done). Set the
   same value in the Razorpay dashboard so signature verification keeps working.
3. **`ADMIN_API_KEY`** is already set in `.env` (done). Confirm it is present.
4. `git log -p -- .env` → confirm `.env` itself never appears in history.
5. Scan history for the old shared string. Read it from the untracked `.env`
   backup or your password manager — do not paste it here:

   ```bash
   git grep -I -- "<old-password>" $(git rev-list --all)   # any hit → rotate
   ```
6. Confirm `docs/`, `README.md`, and screenshots contain no real key material
   (`git grep -nE 'rzp_live_|sk-ant-[A-Za-z0-9]|BEGIN (RSA|PRIVATE)'`).
