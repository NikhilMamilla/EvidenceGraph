"""
Evidence extraction service — Phase 4.

Converts a canonical PaymentEvent + its originating WebhookEvent into
a list of EvidenceObservation records.

Design rules enforced here:
  1. Deterministic: same input → same evidence observations.
  2. No fabrication: absent fields produce no evidence record.
  3. Absence ≠ negative: a missing field is simply not extracted.
  4. Monetary values: stored as integer strings in minor units.
  5. observed_at = provider event time (not processing time).
  6. created_at = system clock at extraction time.
  7. extraction_version = CURRENT_EXTRACTION_VERSION.
  8. No LLM, no probabilistic logic, no scoring.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.models.evidence import EvidenceObservation
from app.models.evidence_types import (
    CURRENT_EXTRACTION_VERSION,
    EvidenceType,
    ExtractionMethod,
    SourceType,
    SubjectType,
    ValueType,
)
from app.models.payment_event import PaymentEvent
from app.models.webhook_event import WebhookEvent

logger = logging.getLogger(__name__)


def _make_evidence(
    *,
    evidence_type: str,
    subject_type: str,
    subject_id: str,
    value: str,
    value_type: str,
    source_type: str,
    source_reference: str | None,
    observed_at: datetime,
    webhook_event_id: int | None,
    payment_event_id: int | None,
    event_type: str,
) -> EvidenceObservation:
    """Construct a single EvidenceObservation. Does NOT add to session."""
    return EvidenceObservation(
        evidence_type=evidence_type,
        subject_type=subject_type,
        subject_id=subject_id,
        value=value,
        value_type=value_type,
        source_type=source_type,
        source_reference=source_reference,
        observed_at=observed_at,
        valid_from=observed_at,
        valid_until=None,  # open-ended validity
        webhook_event_id=webhook_event_id,
        payment_event_id=payment_event_id,
        extraction_method=ExtractionMethod.WEBHOOK_FIELD_EXTRACTION,
        extraction_version=CURRENT_EXTRACTION_VERSION,
        provenance_metadata={
            "provider": "razorpay",
            "event_type": event_type,
            "extraction_version": CURRENT_EXTRACTION_VERSION,
        },
        # created_at is set by server_default=func.now() — not set here
    )


def extract_evidence_from_payment_event(
    payment_event: PaymentEvent,
    webhook_event: WebhookEvent,
) -> list[EvidenceObservation]:
    """
    Extract evidence observations from a canonical PaymentEvent.

    Returns a list of EvidenceObservation objects ready to be added to the session.
    Does NOT flush or commit.

    Rules:
    - Only extracts fields actually present in the raw_payload.
    - Missing fields produce no record.
    - observed_at is taken from payment_event.event_timestamp if available,
      falling back to webhook_event.received_at.
    - No record is created if the field value is None.
    """
    raw: dict[str, Any] = webhook_event.raw_payload or {}
    event_type: str = raw.get("event", "unknown")
    inner_payload: dict[str, Any] = raw.get("payload", {})

    # Determine observed_at
    observed_at: datetime = (
        payment_event.event_timestamp
        if payment_event.event_timestamp is not None
        else (webhook_event.received_at or datetime.now(tz=timezone.utc))
    )

    source_reference = str(webhook_event.id)
    common_kwargs = dict(
        source_type=SourceType.RAZORPAY_WEBHOOK,
        source_reference=source_reference,
        observed_at=observed_at,
        webhook_event_id=webhook_event.id,
        payment_event_id=payment_event.internal_id,
        event_type=event_type,
    )

    observations: list[EvidenceObservation] = []

    # ------------------------------------------------------------------
    # Extract from payment entity
    # ------------------------------------------------------------------
    payment_entity: dict[str, Any] = (
        inner_payload.get("payment", {}).get("entity", {})
    )
    payment_id: str | None = payment_entity.get("id")

    if payment_id:
        # PAYMENT_EVENT — the occurrence of this event type
        observations.append(
            _make_evidence(
                evidence_type=EvidenceType.PAYMENT_EVENT,
                subject_type=SubjectType.PAYMENT,
                subject_id=payment_id,
                value=event_type,
                value_type=ValueType.ENUM,
                **common_kwargs,
            )
        )

        # PAYMENT_STATUS
        payment_status: str | None = _derive_payment_status(event_type)
        if payment_status is not None:
            observations.append(
                _make_evidence(
                    evidence_type=EvidenceType.PAYMENT_STATUS,
                    subject_type=SubjectType.PAYMENT,
                    subject_id=payment_id,
                    value=payment_status,
                    value_type=ValueType.ENUM,
                    **common_kwargs,
                )
            )

        # PAYMENT_AMOUNT
        amount: int | None = payment_entity.get("amount")
        if amount is not None:
            observations.append(
                _make_evidence(
                    evidence_type=EvidenceType.PAYMENT_AMOUNT,
                    subject_type=SubjectType.PAYMENT,
                    subject_id=payment_id,
                    value=str(int(amount)),  # always integer, never float
                    value_type=ValueType.INTEGER_MINOR_UNITS,
                    **common_kwargs,
                )
            )

        # PAYMENT_CURRENCY
        currency: str | None = payment_entity.get("currency")
        if currency is not None:
            observations.append(
                _make_evidence(
                    evidence_type=EvidenceType.PAYMENT_CURRENCY,
                    subject_type=SubjectType.PAYMENT,
                    subject_id=payment_id,
                    value=str(currency),
                    value_type=ValueType.STRING,
                    **common_kwargs,
                )
            )

        # PAYMENT_METHOD
        method: str | None = payment_entity.get("method")
        if method is not None:
            observations.append(
                _make_evidence(
                    evidence_type=EvidenceType.PAYMENT_METHOD,
                    subject_type=SubjectType.PAYMENT,
                    subject_id=payment_id,
                    value=str(method),
                    value_type=ValueType.ENUM,
                    **common_kwargs,
                )
            )

        # PAYMENT_ORDER_RELATIONSHIP
        order_id_from_payment: str | None = payment_entity.get("order_id")
        if order_id_from_payment:
            observations.append(
                _make_evidence(
                    evidence_type=EvidenceType.PAYMENT_ORDER_RELATIONSHIP,
                    subject_type=SubjectType.PAYMENT,
                    subject_id=payment_id,
                    value=order_id_from_payment,
                    value_type=ValueType.STRING,
                    **common_kwargs,
                )
            )

    # ------------------------------------------------------------------
    # Extract from order entity (present for order.paid events)
    # ------------------------------------------------------------------
    order_entity: dict[str, Any] = (
        inner_payload.get("order", {}).get("entity", {})
    )
    order_id: str | None = order_entity.get("id")

    if order_id:
        # ORDER_STATUS
        order_status: str | None = order_entity.get("status")
        if order_status is not None:
            observations.append(
                _make_evidence(
                    evidence_type=EvidenceType.ORDER_STATUS,
                    subject_type=SubjectType.ORDER,
                    subject_id=order_id,
                    value=str(order_status),
                    value_type=ValueType.ENUM,
                    **common_kwargs,
                )
            )

        # ORDER_AMOUNT
        order_amount: int | None = order_entity.get("amount")
        if order_amount is not None:
            observations.append(
                _make_evidence(
                    evidence_type=EvidenceType.ORDER_AMOUNT,
                    subject_type=SubjectType.ORDER,
                    subject_id=order_id,
                    value=str(int(order_amount)),
                    value_type=ValueType.INTEGER_MINOR_UNITS,
                    **common_kwargs,
                )
            )

        # ORDER_CURRENCY
        order_currency: str | None = order_entity.get("currency")
        if order_currency is not None:
            observations.append(
                _make_evidence(
                    evidence_type=EvidenceType.ORDER_CURRENCY,
                    subject_type=SubjectType.ORDER,
                    subject_id=order_id,
                    value=str(order_currency),
                    value_type=ValueType.STRING,
                    **common_kwargs,
                )
            )

    return observations


def _derive_payment_status(event_type: str) -> str | None:
    """Map a Razorpay event type to a payment status string.

    Returns None for event types that do not carry a clear payment status.
    This avoids inserting a fabricated status when the event type is unexpected.
    """
    _map = {
        "payment.authorized": "authorized",
        "payment.captured": "captured",
        "payment.failed": "failed",
        "order.paid": "paid",
    }
    return _map.get(event_type)


def extract_and_persist_evidence(
    payment_event: PaymentEvent,
    webhook_event: WebhookEvent,
    db: Session,
) -> int:
    """
    Extract evidence from a canonical PaymentEvent and persist all observations.

    Called by the webhook worker within the same DB transaction that created
    the PaymentEvent.

    Returns the count of evidence records created.
    """
    start = time.perf_counter()

    try:
        observations = extract_evidence_from_payment_event(payment_event, webhook_event)

        for obs in observations:
            db.add(obs)

        # Flush to assign IDs without committing — the caller (worker) commits.
        db.flush()

        duration_ms = round((time.perf_counter() - start) * 1000, 2)
        logger.info(
            "Evidence extracted",
            extra={
                "webhook_event_id": webhook_event.id,
                "payment_event_id": payment_event.internal_id,
                "evidence_count": len(observations),
                "extraction_version": CURRENT_EXTRACTION_VERSION,
                "evidence_extraction_duration_ms": duration_ms,
            },
        )
        return len(observations)

    except Exception as exc:
        logger.error(
            "Evidence extraction failed: %s",
            type(exc).__name__,
            extra={
                "webhook_event_id": webhook_event.id,
                "payment_event_id": payment_event.internal_id,
            },
            exc_info=True,
        )
        raise
