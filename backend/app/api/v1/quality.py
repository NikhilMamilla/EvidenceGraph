"""
Evidence Quality API — Phase 6.

Read-only endpoints for querying evidence quality measurements.
No Evidence Integrity Score is returned. Deliberately.

Endpoints:
  GET /api/v1/quality/evidence/{evidence_id}
      Latest quality snapshot for one evidence observation.

  GET /api/v1/quality/payments/{payment_id}
      Latest quality snapshot for each evidence observation in a payment.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.evidence import EvidenceObservation
from app.models.evidence_quality import EvidenceQualitySnapshot
from app.models.evidence_types import SubjectType
from app.models.payment import Payment
from app.schemas.quality import (
    EvidenceQualityResponseSchema,
    PaymentEvidenceQualityResponseSchema,
    QualitySnapshotSchema,
)

router = APIRouter()


def _snapshot_to_schema(snap: EvidenceQualitySnapshot) -> QualitySnapshotSchema:
    return QualitySnapshotSchema(
        snapshot_id=snap.internal_id,
        evidence_id=snap.evidence_id,
        evaluated_at=snap.evaluated_at,
        age_seconds=float(snap.age_seconds) if snap.age_seconds is not None else None,
        freshness_state=snap.freshness_state,
        freshness_policy_key=snap.freshness_policy_key,
        freshness_methodology_version=snap.freshness_methodology_version,
        source_type=snap.source_type,
        source_directness=snap.source_directness,
        source_authority_level=snap.source_authority_level,
        source_methodology_version=snap.source_methodology_version,
        historical_reliability_status=snap.historical_reliability_status,
        reliability_sample_count=snap.reliability_sample_count,
        reliability_methodology_version=snap.reliability_methodology_version,
        snapshot_metadata=snap.snapshot_metadata,
        created_at=snap.created_at,
    )


def _build_evidence_quality_response(
    obs: EvidenceObservation,
    db: Session,
) -> EvidenceQualityResponseSchema:
    """Build the response for one evidence observation."""
    # Count total snapshots
    total = db.execute(
        select(func.count()).select_from(EvidenceQualitySnapshot)
        .where(EvidenceQualitySnapshot.evidence_id == obs.internal_id)
    ).scalar() or 0

    # Latest snapshot
    latest_snap = db.execute(
        select(EvidenceQualitySnapshot)
        .where(EvidenceQualitySnapshot.evidence_id == obs.internal_id)
        .order_by(desc(EvidenceQualitySnapshot.evaluated_at))
        .limit(1)
    ).scalar_one_or_none()

    return EvidenceQualityResponseSchema(
        evidence_id=obs.internal_id,
        evidence_type=obs.evidence_type,
        subject_id=obs.subject_id,
        observed_at=obs.observed_at,
        latest_snapshot=_snapshot_to_schema(latest_snap) if latest_snap else None,
        snapshot_count=total,
    )


@router.get(
    "/evidence/{evidence_id}",
    response_model=EvidenceQualityResponseSchema,
    summary="Quality measurement for one evidence observation",
    description=(
        "Returns the latest quality snapshot for an evidence observation. "
        "Shows freshness, source directness, and historical reliability status. "
        "Does NOT return an Evidence Integrity Score."
    ),
)
def get_evidence_quality(
    evidence_id: int,
    db: Session = Depends(get_db),
) -> EvidenceQualityResponseSchema:
    obs = db.get(EvidenceObservation, evidence_id)
    if not obs:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Evidence observation not found",
        )
    return _build_evidence_quality_response(obs, db)


@router.get(
    "/payments/{razorpay_payment_id}",
    response_model=PaymentEvidenceQualityResponseSchema,
    summary="Quality measurements for all evidence in a payment",
    description=(
        "Returns the latest quality snapshot for each evidence observation "
        "in the given payment. No Evidence Integrity Score."
    ),
)
def get_payment_evidence_quality(
    razorpay_payment_id: str,
    db: Session = Depends(get_db),
) -> PaymentEvidenceQualityResponseSchema:
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
            EvidenceObservation.subject_type == SubjectType.PAYMENT,
            EvidenceObservation.subject_id == razorpay_payment_id,
        )
        .order_by(EvidenceObservation.observed_at.asc())
    ).scalars().all()

    quality_list = [_build_evidence_quality_response(obs, db) for obs in observations]

    total_snapshots = sum(q.snapshot_count for q in quality_list)

    return PaymentEvidenceQualityResponseSchema(
        payment_id=razorpay_payment_id,
        evidence_quality=quality_list,
        total_evidence_count=len(quality_list),
        snapshot_count=total_snapshots,
    )
