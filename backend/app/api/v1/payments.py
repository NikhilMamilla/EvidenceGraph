from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.evidence import EvidenceObservation
from app.models.payment import Payment
from app.models.payment_event import PaymentEvent
from app.models.webhook_event import WebhookEvent
from app.schemas.evidence import (
    EvidenceSchema,
    EvidenceTimelineEntrySchema,
    EvidenceTimelineSchema,
)
from app.schemas.payment import PaymentSchema, PaymentWithEventsSchema
from app.models.evidence_types import SourceType

router = APIRouter()


@router.get("", response_model=list[PaymentSchema])
def list_payments(db: Session = Depends(get_db)):
    payments = db.execute(
        select(Payment).order_by(Payment.created_at.desc())
    ).scalars().all()
    return payments


@router.get("/{razorpay_payment_id}", response_model=PaymentSchema)
def get_payment(razorpay_payment_id: str, db: Session = Depends(get_db)):
    payment = db.execute(
        select(Payment).where(Payment.razorpay_payment_id == razorpay_payment_id)
    ).scalar_one_or_none()

    if not payment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Payment not found"
        )
    return payment


@router.get("/{razorpay_payment_id}/events", response_model=PaymentWithEventsSchema)
def get_payment_with_events(razorpay_payment_id: str, db: Session = Depends(get_db)):
    payment = db.execute(
        select(Payment).where(Payment.razorpay_payment_id == razorpay_payment_id)
    ).scalar_one_or_none()

    if not payment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Payment not found"
        )

    events = db.execute(
        select(PaymentEvent)
        .where(PaymentEvent.payment_id == payment.internal_id)
        .order_by(PaymentEvent.event_timestamp.asc())
    ).scalars().all()

    # Create schema representation
    payment_dict = {
        "razorpay_payment_id": payment.razorpay_payment_id,
        "amount_minor": payment.amount_minor,
        "currency": payment.currency,
        "status": payment.status,
        "payment_method_type": payment.payment_method_type,
        "payment_method_details": payment.payment_method_details,
        "captured": payment.captured,
        "first_observed_at": payment.first_observed_at,
        "last_observed_at": payment.last_observed_at,
        "events": events
    }

    return payment_dict


@router.get("/{razorpay_payment_id}/evidence", response_model=list[EvidenceSchema])
def get_payment_evidence(
    razorpay_payment_id: str,
    db: Session = Depends(get_db),
):
    """
    Retrieve all evidence observations for a payment, ordered by observed_at.

    Returns actual database evidence only. No fabricated records.
    """
    payment = db.execute(
        select(Payment).where(Payment.razorpay_payment_id == razorpay_payment_id)
    ).scalar_one_or_none()

    if not payment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Payment not found",
        )

    observations = db.execute(
        select(EvidenceObservation)
        .where(
            EvidenceObservation.subject_type == "payment",
            EvidenceObservation.subject_id == razorpay_payment_id,
        )
        .order_by(EvidenceObservation.observed_at.asc())
    ).scalars().all()

    return observations


@router.get(
    "/{razorpay_payment_id}/evidence/timeline",
    response_model=EvidenceTimelineSchema,
)
def get_payment_evidence_timeline(
    razorpay_payment_id: str,
    db: Session = Depends(get_db),
):
    """
    Retrieve evidence observations grouped by payment event (timeline view).

    Each timeline entry corresponds to one payment event (e.g. payment.captured)
    and contains all evidence observations extracted from that event.

    Results are ordered by event observed_at ascending.

    Returns actual database evidence only. No fabricated records.
    """
    payment = db.execute(
        select(Payment).where(Payment.razorpay_payment_id == razorpay_payment_id)
    ).scalar_one_or_none()

    if not payment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Payment not found",
        )

    # Fetch all payment events for this payment, ordered by event_timestamp
    payment_events = db.execute(
        select(PaymentEvent)
        .where(PaymentEvent.payment_id == payment.internal_id)
        .order_by(PaymentEvent.event_timestamp.asc())
    ).scalars().all()

    timeline: list[EvidenceTimelineEntrySchema] = []
    total_count = 0

    for pe in payment_events:
        # Fetch all evidence for this payment event
        ev_obs = db.execute(
            select(EvidenceObservation)
            .where(EvidenceObservation.payment_event_id == pe.internal_id)
            .order_by(EvidenceObservation.observed_at.asc())
        ).scalars().all()

        total_count += len(ev_obs)

        timeline.append(
            EvidenceTimelineEntrySchema(
                payment_event_id=pe.internal_id,
                event_type=pe.event_type,
                event_timestamp=pe.event_timestamp,
                source_type=SourceType.RAZORPAY_WEBHOOK,
                evidence=[EvidenceSchema.model_validate(o) for o in ev_obs],
            )
        )

    return EvidenceTimelineSchema(
        payment_id=razorpay_payment_id,
        timeline=timeline,
        total_evidence_count=total_count,
    )
