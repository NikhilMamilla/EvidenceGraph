# Phase 2 — Razorpay Integration & Event Ingestion

## Scope

Phase 2 focuses on establishing the public ingestion layer, securely accepting webhooks from Razorpay, and reliably pushing them into our background worker pipeline for future processing.

## What was built during Phase 2

1. **Supabase PostgreSQL Migration**: Moved from a local Docker Postgres instance to an external, hosted Supabase PostgreSQL database via a secure SSL connection string. Patched Alembic to handle password special characters properly.
2. **Database Schema**: Created `WebhookEvent`, `PaymentReference`, and `OrderReference` models with robust SQLAlchemy types and indexing.
3. **Webhook Ingestion Endpoint (`/api/v1/webhooks/razorpay`)**: Created the FastAPI route to receive raw JSON payloads.
4. **Signature Verification**: Implemented strict HMAC-SHA256 signature verification using the `X-Razorpay-Signature` header and the raw payload body. Invalid signatures are rejected with a 400 Bad Request.
5. **Idempotency & Persistence**: Stored all valid events in the `webhook_events` table using the unique `event_id` provided by Razorpay to guarantee idempotent processing. Duplicate deliveries are safely prevented from creating duplicate logical events.
6. **Redis Queue**: Emitted successfully persisted events into a Redis list (`evidencegraph:webhook_events`) via RPUSH for immediate asynchronous processing.
7. **Background Worker Thread**: Spawned an async worker thread during the FastAPI app lifespan that continuously drains the Redis list via BRPOP, normalizing the events into reference tables.
8. **Cloudflare Tunneling**: Utilized `cloudflared` to expose the local development backend directly to the public internet, bypassing strict antivirus blockers for tools like `ngrok`.

## Real-world Validation

A test payment was successfully created via the Razorpay Test Dashboard using the UPI method (`success@razorpay`). 
The resulting `payment.failed` webhook triggered the following chain perfectly:
* Handled by Cloudflare proxy
* Signature verified by FastAPI
* Event persisted into Supabase
* Row published to Redis
* Normalized by background worker in <200ms

## Next Steps (Phase 3 Prep)

* **Evidence Graph Construction**: Now that events are successfully normalized, we will need to stitch these atomic pieces of data (payments, orders, customers) together into a queryable graph to start applying our risk engine.
