"""
Phase 9 — Evidence Integrity API.

Read-only endpoints exposing evidence integrity assessments for payments.

Endpoints:
  GET /payments/{payment_id}/integrity
      Returns the current integrity snapshot, computing one on-demand if
      none exists for the most recent evaluation time.

  GET /payments/{payment_id}/integrity/history
      Returns all historical snapshots ordered by evaluated_at ascending.

These endpoints expose derived, safe metadata only.
No sensitive payment credentials, CVV, OTP, or secrets are exposed.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.evidence_integrity import EvidenceIntegritySnapshot
from app.models.payment import Payment
from app.models.trace_types import ActorType, TraceStatus
from app.schemas.integrity import (
    IntegrityHistoryItem,
    IntegrityHistoryResponse,
    IntegritySnapshotResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["integrity"])


def _get_payment_or_404(payment_id: str, db: Session) -> Payment:
    payment = db.execute(
        select(Payment).where(Payment.razorpay_payment_id == payment_id)
    ).scalar_one_or_none()
    if payment is None:
        raise HTTPException(
            status_code=404,
            detail=f"Payment '{payment_id}' not found.",
        )
    return payment


@router.get(
    "/payments/{payment_id}/integrity",
    response_model=IntegritySnapshotResponse,
    summary="Current evidence integrity for a payment",
    description=(
        "Returns the most recent Evidence Integrity Snapshot for the payment. "
        "If no snapshot exists, one is computed on-demand at the current time "
        "together with its Phase 10 decision trace. "
        "This assessment reflects the quality and internal consistency of evidence "
        "observed so far — it is NOT a fraud or risk score."
    ),
)
def get_payment_integrity(
    payment_id: str,
    db: Session = Depends(get_db),
) -> IntegritySnapshotResponse:
    _get_payment_or_404(payment_id, db)

    # Try to find the most recent existing snapshot
    latest = db.execute(
        select(EvidenceIntegritySnapshot)
        .where(EvidenceIntegritySnapshot.payment_id == payment_id)
        .order_by(EvidenceIntegritySnapshot.evaluated_at.desc())
    ).scalars().first()

    if latest is not None:
        return IntegritySnapshotResponse.from_snapshot(latest)

    # No snapshot exists — compute one on-demand at current time, recording
    # the decision trace for the evaluation (Phase 10).
    evaluation_time = datetime.now(tz=timezone.utc)
    from app.services.integrity_trace_service import IntegrityTraceService

    trace = IntegrityTraceService.record_evaluation(
        db,
        payment_id,
        evaluation_time,
        trigger="ON_DEMAND_API",
        actor_type=ActorType.USER,
    )
    db.commit()

    if trace is None or trace.status != TraceStatus.COMPLETED:
        logger.error(
            "On-demand integrity computation did not complete",
            extra={
                "payment_id": payment_id,
                "trace_id": trace.trace_id if trace is not None else None,
            },
        )
        raise HTTPException(
            status_code=500,
            detail=(
                "Integrity computation failed; no result is available. "
                "A failure record was created for audit."
            ),
        )

    snapshot = db.get(EvidenceIntegritySnapshot, trace.integrity_snapshot_internal_id)
    logger.info(
        "On-demand integrity computation completed",
        extra={
            "payment_id": payment_id,
            "evaluated_at": evaluation_time.isoformat(),
            "trace_id": trace.trace_id,
            "overall_status": snapshot.overall_status if snapshot else None,
        },
    )

    return IntegritySnapshotResponse.from_snapshot(snapshot)


@router.get(
    "/payments/{payment_id}/integrity/history",
    response_model=IntegrityHistoryResponse,
    summary="Historical evidence integrity snapshots for a payment",
    description=(
        "Returns all Evidence Integrity Snapshots for the payment ordered by "
        "evaluated_at ascending. Historical snapshots are immutable — "
        "new evidence creates a new snapshot, never overwrites an old one. "
        "This allows observing how evidence quality changed over time."
    ),
)
def get_payment_integrity_history(
    payment_id: str,
    db: Session = Depends(get_db),
) -> IntegrityHistoryResponse:
    _get_payment_or_404(payment_id, db)

    snapshots = db.execute(
        select(EvidenceIntegritySnapshot)
        .where(EvidenceIntegritySnapshot.payment_id == payment_id)
        .order_by(EvidenceIntegritySnapshot.evaluated_at.asc())
    ).scalars().all()

    history = [IntegrityHistoryItem.from_snapshot(s) for s in snapshots]

    return IntegrityHistoryResponse(
        payment_id=payment_id,
        history=history,
        total=len(history),
    )
