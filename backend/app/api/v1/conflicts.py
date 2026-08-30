"""
Phase 8 — Conflict & Consistency API Endpoints.

Read-only endpoints for inspecting contradiction observations.
Does NOT expose fraud scores, risk scores, or trust scores.

Route structure:
  GET /api/v1/payments/{payment_id}/conflicts
  GET /api/v1/payments/{payment_id}/consistency
  GET /api/v1/conflicts/{conflict_id}
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.evidence_conflict import EvidenceConflict, ConflictResolution
from app.models.conflict_types import ConflictStatus
from app.schemas.conflict import ConflictDetailResponse, PaymentConsistencyResponse

router = APIRouter(tags=["Contradiction & Consistency"])


@router.get(
    "/payments/{payment_id}/conflicts",
    response_model=list[ConflictDetailResponse],
    summary="List all contradiction observations for a payment",
    description=(
        "Returns all detected evidence inconsistencies and temporal conflicts for the "
        "given payment. Conflicts are structural observations, not fraud judgments."
    ),
)
def list_payment_conflicts(
    payment_id: str,
    db: Session = Depends(get_db),
) -> list[ConflictDetailResponse]:
    conflicts = (
        db.query(EvidenceConflict)
        .filter(EvidenceConflict.payment_id == payment_id)
        .order_by(EvidenceConflict.detected_at.asc())
        .all()
    )
    return [_enrich(c, db) for c in conflicts]


@router.get(
    "/conflicts/{conflict_id}",
    response_model=ConflictDetailResponse,
    summary="Get a specific contradiction observation",
)
def get_conflict(
    conflict_id: int,
    db: Session = Depends(get_db),
) -> ConflictDetailResponse:
    conflict = db.query(EvidenceConflict).filter(EvidenceConflict.internal_id == conflict_id).first()
    if not conflict:
        raise HTTPException(status_code=404, detail="Conflict not found")
    return _enrich(conflict, db)


@router.get(
    "/payments/{payment_id}/consistency",
    response_model=PaymentConsistencyResponse,
    summary="Get temporal consistency summary for a payment",
    description=(
        "Returns a structured summary of evidence consistency for the given payment. "
        "is_consistent=True means no semantic conflicts were detected. "
        "Ordering ambiguities (INFO severity) do not make a payment inconsistent."
    ),
)
def get_payment_consistency(
    payment_id: str,
    db: Session = Depends(get_db),
) -> PaymentConsistencyResponse:
    conflicts = (
        db.query(EvidenceConflict)
        .filter(EvidenceConflict.payment_id == payment_id)
        .order_by(EvidenceConflict.detected_at.asc())
        .all()
    )

    # is_consistent: no OPEN conflicts with severity > INFO
    open_conflicts = [
        c for c in conflicts
        if c.status == ConflictStatus.OPEN.value and c.severity != "INFO"
    ]
    resolved_count = sum(1 for c in conflicts if c.status == ConflictStatus.RESOLVED.value)

    return PaymentConsistencyResponse(
        payment_id=payment_id,
        is_consistent=len(open_conflicts) == 0,
        total_conflicts=len(conflicts),
        open_conflicts=len(open_conflicts),
        resolved_conflicts=resolved_count,
        conflicts=[_enrich(c, db) for c in conflicts],
    )


def _enrich(conflict: EvidenceConflict, db: Session) -> ConflictDetailResponse:
    resolutions = (
        db.query(ConflictResolution)
        .filter(ConflictResolution.conflict_id == conflict.internal_id)
        .all()
    )
    return ConflictDetailResponse(
        internal_id=conflict.internal_id,
        payment_id=conflict.payment_id,
        claim_a_id=conflict.claim_a_id,
        claim_b_id=conflict.claim_b_id,
        conflict_type=conflict.conflict_type,
        severity=conflict.severity,
        status=conflict.status,
        detected_at=conflict.detected_at,
        rule_version=conflict.rule_version,
        explanation=conflict.explanation,
        created_at=conflict.created_at,
        resolutions=[
            {
                "internal_id": r.internal_id,
                "conflict_id": r.conflict_id,
                "resolving_evidence_id": r.resolving_evidence_id,
                "resolution_type": r.resolution_type,
                "explanation": r.explanation,
                "resolved_at": r.resolved_at,
                "rule_version": r.rule_version,
                "metadata": r.metadata_,
                "created_at": r.created_at,
            }
            for r in resolutions
        ],
    )
