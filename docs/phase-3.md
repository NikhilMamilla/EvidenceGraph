# Phase 3 — Canonical Payment Domain

## 1. Phase Objective

Phase 3 established the canonical representation of the real payment world from verified
Razorpay webhook events. Where Phase 2 persisted raw, immutable webhook payloads,
Phase 3 translated those payloads into structured, first-class domain entities that the
rest of EvidenceGraph operates on.

The goal was a system that could deterministically answer:

> "Given this verified Razorpay event, what canonical payment, order, and customer
> entities exist, and what is their current state?"

---

## 2. Architecture

```
Razorpay
    ↓
Verified Webhook (HMAC-SHA256)
    ↓
webhook_events (Supabase — immutable raw payload)
    ↓
Redis (transient event ID notification)
    ↓
Webhook Worker (background thread)
    ↓
Canonical Domain
    ├── Order                (orders table)
    ├── Payment              (payments table)
    ├── Payment Event        (payment_events table)
    └── Customer Reference   (customer_references table)
```

The worker is the only component that writes to canonical tables.
The webhook ingestion path writes only to `webhook_events` and Redis, then returns immediately.

---

## 3. Database Changes

All canonical tables were created in Alembic migration
`fe5fd3d3fd6f` (`20260821_0844_fe5fd3d3fd6f_phase_3_canonical_models.py`),
applied against Supabase PostgreSQL.

The migration also dropped the Phase 2 placeholder tables
`payment_references` and `order_references`.

### `customer_references`

| Column                 | Type                   | Constraints                    |
|------------------------|------------------------|--------------------------------|
| `internal_id`          | Integer                | PK, autoincrement              |
| `razorpay_customer_id` | String(64)             | NOT NULL, UNIQUE, indexed      |
| `created_at`           | DateTime (tz)          | NOT NULL, server default now() |
| `updated_at`           | DateTime (tz)          | NOT NULL, server default now() |

### `orders`

| Column              | Type           | Constraints                    |
|---------------------|----------------|--------------------------------|
| `internal_id`       | Integer        | PK, autoincrement              |
| `razorpay_order_id` | String(64)     | NOT NULL, UNIQUE, indexed      |
| `amount_minor`      | Integer        | nullable                       |
| `currency`          | String(3)      | nullable                       |
| `status`            | String(32)     | NOT NULL, default `'unknown'`  |
| `created_at`        | DateTime (tz)  | NOT NULL, server default now() |
| `updated_at`        | DateTime (tz)  | NOT NULL, server default now() |

### `payments`

| Column                   | Type           | Constraints                                   |
|--------------------------|----------------|-----------------------------------------------|
| `internal_id`            | Integer        | PK, autoincrement                             |
| `razorpay_payment_id`    | String(64)     | NOT NULL, UNIQUE, indexed                     |
| `order_id`               | Integer        | FK → `orders.internal_id`, indexed, nullable  |
| `customer_id`            | Integer        | FK → `customer_references.internal_id`, indexed, nullable |
| `amount_minor`           | Integer        | nullable                                      |
| `currency`               | String(3)      | nullable                                      |
| `status`                 | String(32)     | NOT NULL, default `'unknown'`                 |
| `payment_method_type`    | String(32)     | nullable                                      |
| `payment_method_details` | JSONB          | nullable                                      |
| `captured`               | Boolean        | NOT NULL, default false                       |
| `first_observed_at`      | DateTime (tz)  | NOT NULL, server default now()                |
| `last_observed_at`       | DateTime (tz)  | NOT NULL, server default now()                |
| `created_at`             | DateTime (tz)  | NOT NULL, server default now()                |
| `updated_at`             | DateTime (tz)  | NOT NULL, server default now()                |

### `payment_events`

| Column             | Type          | Constraints                                              |
|--------------------|---------------|----------------------------------------------------------|
| `internal_id`      | Integer       | PK, autoincrement                                        |
| `payment_id`       | Integer       | FK → `payments.internal_id`, NOT NULL, indexed           |
| `webhook_event_id` | Integer       | FK → `webhook_events.id`, NOT NULL, UNIQUE, indexed      |
| `event_type`       | String(64)    | NOT NULL                                                 |
| `event_timestamp`  | DateTime (tz) | nullable                                                 |
| `created_at`       | DateTime (tz) | NOT NULL, server default now()                           |

The `UNIQUE` constraint on `webhook_event_id` ensures one `PaymentEvent` per
`WebhookEvent` — a core idempotency guarantee.

---

## 4. Event History

Payment event history is preserved through the `payment_events` table.
Every time the worker processes a webhook event that involves a known payment,
a `PaymentEvent` row is inserted linking:

- the canonical `Payment` (`payment_id`)
- the originating `WebhookEvent` (`webhook_event_id`)
- the event type (e.g. `payment.authorized`, `payment.captured`)
- the provider-reported event timestamp

This creates a complete, append-only history of every webhook event
that affected a payment. The `Payment` table itself stores only the
**current summarized state** (via `status`, `last_observed_at`), while
`payment_events` preserves the full chronological record.

---

## 5. Data Lineage

Canonical data can be traced back to the original verified Razorpay webhook:

```
Payment (razorpay_payment_id)
    ↑
PaymentEvent (payment_id FK)
    ↑
WebhookEvent (webhook_event_id FK, raw_payload, signature_verified=True)
    ↑
Razorpay (razorpay_event_id, original JSON body)
```

The `WebhookEvent.raw_payload` is never mutated after insertion.
The `WebhookEvent.payload_hash` (SHA-256 of the raw body) allows
integrity verification at any time.

---

## 6. Entity Resolution

Razorpay IDs are deterministically mapped to canonical entities using
`SELECT … WHERE razorpay_*_id = ?` lookups before inserting:

- `CustomerReference` — resolved by `razorpay_customer_id`
- `Order` — resolved by `razorpay_order_id`
- `Payment` — resolved by `razorpay_payment_id`

If an entity does not yet exist, it is created.
If it already exists, only fields that were previously absent (null) or
whose status has been superseded are updated.

This means the same Razorpay ID will never produce two database rows for
the same entity type.

---

## 7. Idempotency

Duplicate events are handled at two levels:

1. **WebhookEvent level** (Phase 2): the partial unique index on
   `razorpay_event_id` in `webhook_events` prevents the same Razorpay
   event from being inserted twice. An `IntegrityError` is caught and
   returned as `duplicate` to the caller.

2. **PaymentEvent level** (Phase 3): the UNIQUE constraint on
   `payment_events.webhook_event_id` ensures that even if the same
   `WebhookEvent` row is re-queued to Redis (e.g. after a crash recovery),
   the worker will not create a second `PaymentEvent` for it.

---

## 8. Replay

There is no public replay endpoint.

Replay is implemented as an internal worker capability: if a
`WebhookEvent` that has already been persisted but is in a non-`PROCESSED`
state is re-queued to Redis (by ID), the worker will reprocess it.
The idempotency constraints at both the `webhook_events` and `payment_events`
levels prevent double-processing from creating duplicate canonical entities.

To trigger a replay, an operator would push the `webhook_events.id` integer
back into the `evidencegraph:webhook_events` Redis list directly:

```bash
redis-cli LPUSH evidencegraph:webhook_events <webhook_event_db_id>
```

No CLI tool or internal service method was implemented for replay in Phase 3
beyond the worker's existing re-entrant processing logic.

---

## 9. Monetary Representation

All monetary amounts are stored as:

```
amount_minor   INTEGER
currency       String(3)
```

`amount_minor` is the amount in the smallest denomination of the currency
(e.g. paise for INR). A payment of ₹499 is stored as `49900`.

This representation is taken directly from the Razorpay API, which already
returns amounts in minor units. No division, multiplication, or floating-point
conversion is performed. This avoids IEEE 754 floating-point rounding errors
entirely.

The `currency` field is the ISO 4217 currency code (e.g. `INR`, `USD`).

---

## 10. Security

The following sensitive data is intentionally **not** stored in canonical tables:

- CVV / CVC
- Card PINs
- OTPs
- Bank account numbers (only masked or tokenised identifiers where present in the webhook payload)
- `RAZORPAY_WEBHOOK_SECRET` — never persisted to the database
- `RAZORPAY_KEY_SECRET` — never persisted to the database

The `payment_method_details` JSONB column stores only non-secret fields
selected explicitly by the normalizer:
`card_id`, `card` (masked card object if present), `bank`, `wallet`,
`vpa`, `email`, `contact`.

---

## 11. API Endpoints

The following read-only endpoints were implemented in Phase 3:

| Method | Path                                        | Description                                    |
|--------|---------------------------------------------|------------------------------------------------|
| `GET`  | `/api/v1/payments`                          | List all canonical payments, newest first      |
| `GET`  | `/api/v1/payments/{razorpay_payment_id}`    | Retrieve a single canonical payment            |
| `GET`  | `/api/v1/payments/{razorpay_payment_id}/events` | Retrieve a payment with its full event history |
| `GET`  | `/api/v1/orders/{razorpay_order_id}`        | Retrieve a single canonical order              |

All endpoints return actual database data. No mock or fabricated records.

---

## 12. Frontend

The `PaymentInspector` React component (`frontend/src/components/PaymentInspector.tsx`)
was implemented in Phase 3 with the following functionality:

- **Payment list panel** — fetches `GET /api/v1/payments`, displays each payment's
  Razorpay ID, formatted amount (INR-aware via `Intl.NumberFormat`), status badge,
  and first-observed timestamp
- **Payment detail panel** — on selecting a payment, fetches
  `GET /api/v1/payments/{id}/events` and displays:
  - Amount and status
  - Payment method and method details
  - Lifecycle timestamps (`first_observed_at`, `last_observed_at`)
  - **Event Lineage timeline** — a chronological vertical timeline showing each
    `PaymentEvent` with its `event_type` and `event_timestamp`
- **Empty states** — "No payments captured yet." and "Select a payment to view..."
- **Refresh button** — re-fetches the payment list on demand
- **Status badges** — colour-coded (green = captured/paid, red = failed, blue = authorized)

No evidence inspection or scoring UI was implemented in Phase 3.

---

## 13. Testing

The following automated test classes passed in Phase 3:

### `TestSignatureVerification` (`tests/test_webhook.py`)
- `test_valid_signature_accepted` — valid HMAC-SHA256 is not rejected
- `test_invalid_signature_rejected` — bad signature returns HTTP 400
- `test_missing_signature_header_returns_422` — missing header returns HTTP 422

### `TestSignatureUnit`
- `test_correct_secret_returns_true` — verify_webhook_signature returns True for correct secret
- `test_wrong_secret_returns_false` — returns False for wrong secret
- `test_tampered_body_returns_false` — returns False when body is modified

### `TestNormalizer`
- `test_payment_captured_normalized` — normalizer extracts payment_id, order_id, entity_type
- `test_unsupported_event_returns_none` — `refund.created` returns None
- `test_order_paid_normalized` — order.paid event correctly parsed

All tests run against mocked DB sessions — no live database connection is required.

---

## 14. Real Razorpay Verification

A real Razorpay Test Mode payment was processed during Phase 2 validation and
continued to be the live integration target during Phase 3.

The Phase 2 engineering record documents:

> A test payment was successfully created via the Razorpay Test Dashboard using
> the UPI method (`success@razorpay`). The resulting `payment.failed` webhook
> triggered the following chain perfectly: Handled by Cloudflare proxy →
> Signature verified by FastAPI → Event persisted into Supabase → Row published
> to Redis → Normalized by background worker in <200ms.

During Phase 3, the worker was extended to also create canonical `Payment`,
`Order`, and `PaymentEvent` rows from that same pipeline. The Phase 3 migration
was applied against the live Supabase instance.

Specific Razorpay Test Mode transaction IDs from Phase 3 are not recorded in
this document to avoid confusion with live credentials. The Supabase
`webhook_events` table retains the immutable raw payloads from all verified events.

---

## 15. Known Limitations

- **No order-creation events**: Razorpay's `order.created` event is not in the
  supported event type list. Orders are created in the canonical DB only when a
  payment event referencing that order_id is received.
- **No replay CLI**: The replay mechanism is internal only. There is no
  `make replay` or script-based replay tool.
- **Status transition policy**: The worker uses a rank-based policy to decide
  whether to update `payment.status`. This means a `payment.authorized` event
  arriving after `payment.captured` will not overwrite the captured status.
  However, the `PaymentEvent` history row is always written regardless.
- **No customer data beyond ID**: `CustomerReference` stores only
  `razorpay_customer_id`. No name, email, or contact fields are stored.
- **Tests are unit-only**: No integration tests that run against a real Supabase
  or Redis instance were implemented in Phase 3.
- **No pagination**: The `GET /api/v1/payments` endpoint returns all payments
  with no pagination, which will not scale.
