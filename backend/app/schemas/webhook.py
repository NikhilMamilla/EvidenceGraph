"""
Pydantic schemas for webhook ingestion — Phase 2.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel


class ProcessingStatus(str, Enum):
    RECEIVED = "RECEIVED"
    VALIDATED = "VALIDATED"
    PERSISTED = "PERSISTED"
    PROCESSED = "PROCESSED"
    FAILED = "FAILED"
    DUPLICATE = "DUPLICATE"


class SupportedEventType(str, Enum):
    PAYMENT_AUTHORIZED = "payment.authorized"
    PAYMENT_CAPTURED = "payment.captured"
    PAYMENT_FAILED = "payment.failed"
    ORDER_PAID = "order.paid"


class NormalizedPaymentEvent(BaseModel):
    """Internal normalized representation of a Razorpay payment/order event."""

    event_id: str | None
    event_type: str
    entity_type: str          # "payment" or "order"
    entity_id: str | None     # payment_id or order_id
    order_id: str | None
    payment_id: str | None
    customer_id: str | None = None
    amount_minor: int | None = None
    currency: str | None = None
    payment_method_type: str | None = None
    payment_method_details: dict[str, Any] | None = None
    event_timestamp: datetime | None
    received_timestamp: datetime
    processing_status: ProcessingStatus
    raw_event_type: str       # original Razorpay event type string


class WebhookIngestionResponse(BaseModel):
    """Response returned to Razorpay after webhook receipt."""

    status: str
    event_id: str | None = None
    message: str = ""


class RazorpayStatusResponse(BaseModel):
    """Response for GET /api/v1/integrations/razorpay/status."""

    configured: bool
    mode: str
    key_id_prefix: str        # first 8 chars of key ID only
    last_verified_event_at: datetime | None
    events_received: int
    events_processed: int
    events_rejected: int
    events_duplicate: int
