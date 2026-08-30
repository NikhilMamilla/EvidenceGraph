"""
Evidence API — GET /api/v1/evidence/{evidence_id}

Returns a single evidence observation with its full provenance chain.
Read-only. No evidence is created or modified via this endpoint.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.evidence import EvidenceObservation
from app.models.payment_event import PaymentEvent
from app.models.webhook_event import WebhookEvent
from app.schemas.evidence import EvidenceLineageSchema, EvidenceSchema

router = APIRouter()


@router.get("/{evidence_id}", response_model=EvidenceLineageSchema)
def get_evidence_with_lineage(
    evidence_id: int,
    db: Session = Depends(get_db),
) -> EvidenceLineageSchema:
    """
    Retrieve a single evidence observation with its full provenance chain.

    Returns:
        Evidence → PaymentEvent → WebhookEvent → Razorpay event ID

    This demonstrates the complete lineage from an observation back to
    the original Razorpay provider event.
    """
    obs = db.get(EvidenceObservation, evidence_id)
    if obs is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Evidence observation not found",
        )

    # Resolve PaymentEvent
    payment_event: PaymentEvent | None = None
    if obs.payment_event_id is not None:
        payment_event = db.get(PaymentEvent, obs.payment_event_id)

    # Resolve WebhookEvent
    webhook_event: WebhookEvent | None = None
    if obs.webhook_event_id is not None:
        webhook_event = db.get(WebhookEvent, obs.webhook_event_id)

    return EvidenceLineageSchema(
        evidence=EvidenceSchema.model_validate(obs),
        payment_event_id=payment_event.internal_id if payment_event else None,
        payment_event_type=payment_event.event_type if payment_event else None,
        payment_event_timestamp=payment_event.event_timestamp if payment_event else None,
        webhook_event_id=webhook_event.id if webhook_event else None,
        razorpay_event_id=webhook_event.razorpay_event_id if webhook_event else None,
        razorpay_event_type=webhook_event.event_type if webhook_event else None,
    )
