"""
Webhook ingestion service.

Responsibilities:
1. Verify signature (using raw body bytes)
2. Check idempotency (duplicate event detection)
3. Persist verified event to Supabase
4. Publish event reference to Redis
5. Return quickly — heavy processing is async

Source of truth: PostgreSQL.
Redis: transient event notification only.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.integrations.razorpay.signature import verify_webhook_signature
from app.models.webhook_event import WebhookEvent
from app.schemas.webhook import ProcessingStatus
from app.services.metrics import get_metrics
from app.services.redis_client import get_redis_client

logger = logging.getLogger(__name__)

REDIS_WEBHOOK_QUEUE = "evidencegraph:webhook_events"


def ingest_webhook(
    raw_body: bytes,
    signature_header: str,
    webhook_secret: str,
    db: Session,
    request_id: str,
) -> tuple[bool, str, str | None]:
    """
    Process an incoming Razorpay webhook.

    Returns:
        (success, status_message, webhook_event_id_or_none)

    success=True  → event verified and persisted (or duplicate)
    success=False → signature invalid or persistence error
    """
    metrics = get_metrics()
    metrics.inc_received()
    received_at = datetime.now(tz=timezone.utc)

    # ------------------------------------------------------------------
    # 1. Verify signature using raw bytes
    # ------------------------------------------------------------------
    sig_ok = verify_webhook_signature(raw_body, signature_header, webhook_secret)
    if not sig_ok:
        metrics.inc_rejected()
        logger.warning(
            "Webhook signature verification failed",
            extra={"request_id": request_id, "sig_header_prefix": signature_header[:8]},
        )
        return False, "invalid_signature", None

    metrics.inc_verified()

    # ------------------------------------------------------------------
    # 2. Parse payload (only after signature is verified)
    # ------------------------------------------------------------------
    try:
        payload: dict[str, Any] = json.loads(raw_body)
    except json.JSONDecodeError:
        logger.error("Failed to parse webhook payload JSON", extra={"request_id": request_id})
        metrics.inc_failed()
        return False, "invalid_json", None

    event_type: str = payload.get("event", "unknown")
    razorpay_event_id: str | None = payload.get("id")
    account_id: str | None = payload.get("account_id")
    created_at_ts = payload.get("created_at")
    event_timestamp: datetime | None = None
    if created_at_ts:
        try:
            event_timestamp = datetime.fromtimestamp(int(created_at_ts), tz=timezone.utc)
        except (ValueError, TypeError):
            pass

    # Extract payment/order IDs for convenience indexing
    inner_payload = payload.get("payload", {})
    payment_id: str | None = None
    order_id: str | None = None

    payment_entity = inner_payload.get("payment", {}).get("entity", {})
    if payment_entity:
        payment_id = payment_entity.get("id")
        order_id = payment_entity.get("order_id")

    order_entity = inner_payload.get("order", {}).get("entity", {})
    if order_entity and not order_id:
        order_id = order_entity.get("id")

    # Payload hash for integrity
    payload_hash = hashlib.sha256(raw_body).hexdigest()

    logger.info(
        "Webhook verified",
        extra={
            "request_id": request_id,
            "event_type": event_type,
            "event_id": razorpay_event_id,
            "payment_id": payment_id,
            "order_id": order_id,
        },
    )

    # ------------------------------------------------------------------
    # 3. Persist — with idempotency via unique constraint on event_id
    # ------------------------------------------------------------------
    event = WebhookEvent(
        razorpay_event_id=razorpay_event_id,
        event_type=event_type,
        received_at=received_at,
        event_timestamp=event_timestamp,
        signature_verified=True,
        processing_status=ProcessingStatus.PERSISTED,
        raw_payload=payload,
        payload_hash=payload_hash,
        payment_id=payment_id,
        order_id=order_id,
        account_id=account_id,
    )

    try:
        db.add(event)
        db.commit()
        db.refresh(event)
    except IntegrityError:
        db.rollback()
        metrics.inc_duplicate()
        logger.info(
            "Duplicate webhook event detected",
            extra={"request_id": request_id, "razorpay_event_id": razorpay_event_id},
        )
        return True, "duplicate", razorpay_event_id
    except Exception as exc:
        db.rollback()
        metrics.inc_failed()
        logger.error(
            "Failed to persist webhook event: %s",
            type(exc).__name__,
            extra={"request_id": request_id},
        )
        return False, "persistence_error", None

    # ------------------------------------------------------------------
    # 4. Publish event reference to Redis (non-blocking)
    # ------------------------------------------------------------------
    try:
        redis = get_redis_client()
        redis.lpush(REDIS_WEBHOOK_QUEUE, str(event.id))
        logger.info(
            "Webhook event queued for processing",
            extra={"request_id": request_id, "webhook_event_db_id": event.id},
        )
    except Exception as exc:
        # Redis failure must NOT fail the webhook acknowledgement
        logger.warning(
            "Redis publish failed (event still persisted): %s",
            type(exc).__name__,
            extra={"request_id": request_id},
        )

    return True, "accepted", razorpay_event_id
