# Phase 4 — Evidence Observation & Provenance Layer

## 1. Phase Objective

Phase 4 introduced the **Evidence Observation** layer. While Phase 3 built the
canonical domain entities (the "what is"), Phase 4 built the immutable evidentiary
record (the "how do we know it").

Instead of overwriting state blindly, every field update from Razorpay is now
extracted into an immutable `EvidenceObservation` record, tied to a specific
entity and linked directly back to the `WebhookEvent` that proved it.

This layer guarantees that every fact the system believes about a payment can be
traced directly to an origin event, completely separating the *act of observation*
from the *act of interpretation*.

---

## 2. Architecture

```
Razorpay
    ↓
Verified Webhook (HMAC-SHA256)
    ↓
webhook_events (immutable raw payload)
    ↓
Webhook Worker (background thread)
    ↓
Canonical Domain                  Evidence Layer (New in Phase 4)
    ├── Order                       │
    ├── Payment                     ├── EvidenceObservation
    ├── PaymentEvent ───────────────┘   (Extraction Service)
    └── CustomerReference
```

Evidence extraction happens deterministically inside the worker, in the same
database transaction that creates the `PaymentEvent`.

---

## 3. Database Changes

The `evidence_observations` table was created via Alembic migration
`0003_phase4` (`20260822_0003_phase4_evidence.py`).

| Column                 | Type           | Constraints                               |
|------------------------|----------------|-------------------------------------------|
| `internal_id`          | Integer        | PK, autoincrement                         |
| `evidence_type`        | String(64)     | NOT NULL (e.g. `PAYMENT_AMOUNT`)          |
| `subject_type`         | String(32)     | NOT NULL (e.g. `payment`)                 |
| `subject_id`           | String(128)    | NOT NULL (External ID, e.g. `pay_xxx`)    |
| `value`                | Text           | nullable                                  |
| `value_type`           | String(32)     | NOT NULL (e.g. `INTEGER_MINOR_UNITS`)     |
| `source_type`          | String(32)     | NOT NULL (e.g. `RAZORPAY_WEBHOOK`)        |
| `source_reference`     | String(128)    | nullable (WebhookEvent ID)                |
| `observed_at`          | DateTime (tz)  | NOT NULL (Provider time)                  |
| `valid_from`           | DateTime (tz)  | nullable                                  |
| `valid_until`          | DateTime (tz)  | nullable                                  |
| `webhook_event_id`     | Integer        | FK → `webhook_events.id`, nullable        |
| `payment_event_id`     | Integer        | FK → `payment_events.internal_id`         |
| `extraction_method`    | String(64)     | NOT NULL (`WEBHOOK_FIELD_EXTRACTION`)     |
| `extraction_version`   | String(16)     | NOT NULL, default `1.0`                   |
| `provenance_metadata`  | JSONB          | nullable                                  |
| `created_at`           | DateTime (tz)  | NOT NULL, server default `now()`          |

**Crucial Constraints & Design Choices:**
- **No `updated_at` column:** Evidence records are immutable by design.
- **External IDs:** `subject_id` stores Razorpay's `pay_xxx` ID, avoiding mandatory joins with canonical tables when querying evidence.
- **Integer Amounts:** `value` for monetary amounts is stored as an integer string in minor units (e.g. `"49900"`), never a float.

---

## 4. Evidence Taxonomy

To avoid painful Alembic database migrations when new types are added, the taxonomy
is defined purely in application code as Python string constants in
`app/models/evidence_types.py`:

- **EvidenceType**: `PAYMENT_AMOUNT`, `PAYMENT_CURRENCY`, `PAYMENT_STATUS`, `PAYMENT_METHOD`, `ORDER_AMOUNT`, `ORDER_CURRENCY`, `ORDER_STATUS`, `PAYMENT_ORDER_RELATIONSHIP`, `PAYMENT_EVENT`
- **SourceType**: `RAZORPAY_WEBHOOK`, `RAZORPAY_API`, `INTERNAL_SYSTEM`
- **ValueType**: `INTEGER_MINOR_UNITS`, `STRING`, `ENUM`, `BOOLEAN`
- **SubjectType**: `payment`, `order`
- **ExtractionMethod**: `WEBHOOK_FIELD_EXTRACTION`

---

## 5. Extraction Service

The extraction service (`app/services/evidence_service.py`) operates under strict deterministic rules:
1. **No ML/AI:** It uses hardcoded, predictable dictionary lookups to pull fields from the verified Razorpay payload.
2. **No Scoring:** It does not assign trust, risk, or confidence scores to the evidence.
3. **Absence ≠ Negative:** If a field is missing from a webhook payload, it simply produces no evidence record for that field. It does not fabricate a `null` or `false` record.
4. **Time Separation:** The `observed_at` timestamp is taken from the provider's event time (`payment_event.event_timestamp`), while `created_at` is set by the database clock at insertion time.

---

## 6. API Updates

The following read-only endpoints were added:

| Method | Path                                                  | Description                                                |
|--------|-------------------------------------------------------|------------------------------------------------------------|
| `GET`  | `/api/v1/payments/{id}/evidence`                      | Returns a flat list of all evidence for a payment          |
| `GET`  | `/api/v1/payments/{id}/evidence/timeline`             | Returns evidence grouped chronologically by payment event  |
| `GET`  | `/api/v1/evidence/{evidence_id}`                      | Returns a single evidence record with its full provenance chain back to the Razorpay event ID |

---

## 7. Frontend Updates

The `PaymentInspector` component (`frontend/src/components/PaymentInspector.tsx`)
was updated to visualize the new evidence layer:

- Replaced the simple "Event Lineage" UI with a detailed **Evidence Timeline**.
- When a payment is selected, it fetches the `/evidence/timeline` endpoint.
- Displays each event (e.g., `payment.captured`) with its timestamp.
- Within each event block, it lists all deterministic observations extracted from that event payload (e.g., `PAYMENT_STATUS: captured`, `PAYMENT_AMOUNT: 49900`).
- Displays the total count of evidence observations for the payment.

---

## 8. Verification

1. **Test Suite:** The comprehensive unit test suite in `tests/test_evidence.py` passed entirely (32/32 tests), ensuring deterministic extraction, proper FK lineage mapping, correct fallback for missing timestamps, and that absent fields produce no records.
2. **Live Integration:** Event ID `11` (a previously processed real Razorpay Test Mode event in the Supabase DB) was manually re-triggered through the worker pipeline.
3. The worker output log confirmed: `INFO:app.services.evidence_service:Evidence extracted`, demonstrating that evidence is successfully extracted and written to the database for real-world Razorpay events.

---

## 9. Known Limitations

- **Open-ended Validity:** Currently, the `valid_until` column is always `NULL` (open-ended). Future phases involving the timeline reconciler will need to close these validity windows when newer state supersedes older state.
- **No Timeline Reconciliation:** We now have the evidence, but the worker still updates the canonical `Payment.status` using a basic priority map. Phase 5+ will move to evaluating the entire Evidence timeline to determine canonical state dynamically.
- **No API fallback:** If a webhook is missed, we do not currently poll the Razorpay API to generate `RAZORPAY_API` source evidence.
