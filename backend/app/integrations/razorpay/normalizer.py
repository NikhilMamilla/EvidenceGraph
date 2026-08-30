"""
Razorpay event normalizer.

Converts raw verified Razorpay webhook payloads into NormalizedPaymentEvent.
Supports: payment.authorized, payment.captured, payment.failed, order.paid

Razorpay webhook payload structure (documented):
{
  "entity": "event",
  "account_id": "...",
  "event": "payment.captured",
  "contains": ["payment"],
  "payload": {
    "payment": {
      "entity": { ...payment fields... }
    }
  },
  "created_at": 1234567890
}
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from app.schemas.webhook import NormalizedPaymentEvent, ProcessingStatus, SupportedEventType

logger = logging.getLogger(__name__)


def normalize_event(
    raw_payload: dict[str, Any],
    received_at: datetime,
) -> NormalizedPaymentEvent | None:
    """
    Parse a verified Razorpay webhook payload into a NormalizedPaymentEvent.
    Returns None if the event type is not supported.
    """
    event_type = raw_payload.get("event", "")
    event_id = raw_payload.get("id")  # Razorpay event ID if present
    account_id = raw_payload.get("account_id")
    created_at_ts = raw_payload.get("created_at")
    event_timestamp: datetime | None = None
    if created_at_ts:
        try:
            event_timestamp = datetime.fromtimestamp(int(created_at_ts), tz=timezone.utc)
        except (ValueError, TypeError):
            pass

    payload = raw_payload.get("payload", {})
    payment_id: str | None = None
    order_id: str | None = None
    entity_type = "unknown"
    entity_id: str | None = None

    customer_id: str | None = None
    amount_minor: int | None = None
    currency: str | None = None
    payment_method_type: str | None = None
    payment_method_details: dict[str, Any] | None = None

    if event_type in (
        SupportedEventType.PAYMENT_AUTHORIZED,
        SupportedEventType.PAYMENT_CAPTURED,
        SupportedEventType.PAYMENT_FAILED,
    ):
        entity_type = "payment"
        payment_entity = payload.get("payment", {}).get("entity", {})
        payment_id = payment_entity.get("id")
        order_id = payment_entity.get("order_id")
        entity_id = payment_id
        customer_id = payment_entity.get("customer_id")
        amount_minor = payment_entity.get("amount")
        currency = payment_entity.get("currency")
        payment_method_type = payment_entity.get("method")
        
        # Build payment method details by selecting relevant fields
        details = {}
        for key in ["card_id", "card", "bank", "wallet", "vpa", "email", "contact"]:
            if key in payment_entity:
                details[key] = payment_entity[key]
        payment_method_details = details if details else None

    elif event_type == SupportedEventType.ORDER_PAID:
        entity_type = "order"
        order_entity = payload.get("order", {}).get("entity", {})
        order_id = order_entity.get("id")
        # order.paid also contains payment
        payment_entity = payload.get("payment", {}).get("entity", {})
        payment_id = payment_entity.get("id")
        entity_id = order_id
        customer_id = payment_entity.get("customer_id") or order_entity.get("customer_id")
        amount_minor = payment_entity.get("amount") or order_entity.get("amount")
        currency = payment_entity.get("currency") or order_entity.get("currency")
        payment_method_type = payment_entity.get("method")
        
        details = {}
        for key in ["card_id", "card", "bank", "wallet", "vpa", "email", "contact"]:
            if key in payment_entity:
                details[key] = payment_entity[key]
        payment_method_details = details if details else None

    else:
        logger.info("Unsupported event type received: %s", event_type)
        return None

    return NormalizedPaymentEvent(
        event_id=event_id,
        event_type=event_type,
        entity_type=entity_type,
        entity_id=entity_id,
        order_id=order_id,
        payment_id=payment_id,
        customer_id=customer_id,
        amount_minor=amount_minor,
        currency=currency,
        payment_method_type=payment_method_type,
        payment_method_details=payment_method_details,
        event_timestamp=event_timestamp,
        received_timestamp=received_at,
        processing_status=ProcessingStatus.VALIDATED,
        raw_event_type=event_type,
    )


def extract_payment_status(event_type: str) -> str:
    """Map Razorpay event type to a payment status string."""
    mapping = {
        SupportedEventType.PAYMENT_AUTHORIZED: "authorized",
        SupportedEventType.PAYMENT_CAPTURED: "captured",
        SupportedEventType.PAYMENT_FAILED: "failed",
        SupportedEventType.ORDER_PAID: "paid",
    }
    return mapping.get(event_type, "unknown")  # type: ignore[arg-type]
