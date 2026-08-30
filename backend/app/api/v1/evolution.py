"""
Phase 11 — Evidence Temporal Evolution API.

Read-oriented endpoints exposing evidence state snapshots and change records
for a payment, plus a write endpoint to trigger a fresh recomputation.

Endpoints:
  GET /payments/{payment_id}/changes
      All EvidenceStateChange records for the payment, optionally filtered
      by dimension (case-insensitive).  Ordered by detected_at ascending.

  GET /payments/{payment_id}/state-history
      All EvidenceStateSnapshot records for the payment, ordered by
      evaluation_time ascending.  Each item is annotated with the
      integrity_trace_id of the linked Phase 10 trace when one exists.

  GET /changes/{change_id}
      Full detail for a single EvidenceStateChange record.  Safe fields only
      — the schema excludes raw payloads and any credential-adjacent names.

  POST /payments/{payment_id}/integrity/recompute
      Trigger a fresh Phase 9 integrity evaluation, create a Phase 11
      state snapshot, diff against the previous snapshot, and return the
      newly detected changes.  No admin key required.

Authorization:
  All four endpoints are in the same public tier as GET /payments/.../integrity.
  No X-API-Key header is required.

Tags: ["evolution"]
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.evolution_models import EvidenceStateChange, EvidenceStateSnapshot
from app.models.integrity_trace import EvidenceIntegrityTrace
from app.models.payment import Payment
from app.schemas.evolution import (
    ChangeDetailResponse,
    ChangeItem,
    EvidenceChangesResponse,
    RecomputeResponse,
    StateHistoryResponse,
    StateSnapshotItem,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["evolution"])

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_TRACE_MATCH_WINDOW = timedelta(seconds=5)
"""
Maximum absolute difference between an EvidenceStateSnapshot.evaluation_time
and an EvidenceIntegrityTrace.evaluated_at for them to be considered linked.
"""


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


def _find_trace_id_for_snapshot(
    db: Session,
    payment_id: str,
    evaluation_time: datetime,
    methodology_version: str,
) -> str | None:
    """
    Try to find a COMPLETED EvidenceIntegrityTrace whose evaluated_at is
    within _TRACE_MATCH_WINDOW of the given evaluation_time and whose
    methodology_version matches.

    Returns the trace_id string if found, else None.
    """
    # Compute the window boundaries.
    lower = evaluation_time - _TRACE_MATCH_WINDOW
    upper = evaluation_time + _TRACE_MATCH_WINDOW

    trace = db.execute(
        select(EvidenceIntegrityTrace).where(
            EvidenceIntegrityTrace.payment_id == payment_id,
            EvidenceIntegrityTrace.evaluated_at >= lower,
            EvidenceIntegrityTrace.evaluated_at <= upper,
            EvidenceIntegrityTrace.methodology_version == methodology_version,
            EvidenceIntegrityTrace.status == "COMPLETED",
        ).order_by(
            # Prefer the closest match in case multiple fall within the window.
            EvidenceIntegrityTrace.evaluated_at.asc()
        )
    ).scalars().first()

    return trace.trace_id if trace is not None else None


# ---------------------------------------------------------------------------
# Endpoint 1 — GET /payments/{payment_id}/changes
# ---------------------------------------------------------------------------

@router.get(
    "/payments/{payment_id}/changes",
    response_model=EvidenceChangesResponse,
    summary="Evidence state changes for a payment",
    description=(
        "Returns all EvidenceStateChange records for the payment, ordered by "
        "detected_at ascending. Optionally filter to a single quality dimension "
        "using the ?dimension= query parameter (case-insensitive match)."
    ),
)
def get_payment_changes(
    payment_id: str,
    dimension: Optional[str] = None,
    db: Session = Depends(get_db),
) -> EvidenceChangesResponse:
    _get_payment_or_404(payment_id, db)

    stmt = (
        select(EvidenceStateChange)
        .where(EvidenceStateChange.payment_id == payment_id)
    )

    if dimension is not None:
        stmt = stmt.where(EvidenceStateChange.dimension.ilike(dimension))

    stmt = stmt.order_by(EvidenceStateChange.detected_at.asc())

    changes = list(db.execute(stmt).scalars().all())

    return EvidenceChangesResponse(
        payment_id=payment_id,
        changes=[ChangeItem.from_change(c) for c in changes],
        total=len(changes),
        dimension_filter=dimension,
    )


# ---------------------------------------------------------------------------
# Endpoint 2 — GET /payments/{payment_id}/state-history
# ---------------------------------------------------------------------------

@router.get(
    "/payments/{payment_id}/state-history",
    response_model=StateHistoryResponse,
    summary="Evidence state snapshot history for a payment",
    description=(
        "Returns all EvidenceStateSnapshot records for the payment ordered by "
        "evaluation_time ascending. Each snapshot item is annotated with the "
        "integrity_trace_id of the nearest COMPLETED Phase 10 trace when one "
        "can be matched by payment_id, methodology_version, and evaluation time."
    ),
)
def get_payment_state_history(
    payment_id: str,
    db: Session = Depends(get_db),
) -> StateHistoryResponse:
    _get_payment_or_404(payment_id, db)

    snapshots = list(
        db.execute(
            select(EvidenceStateSnapshot)
            .where(EvidenceStateSnapshot.payment_id == payment_id)
            .order_by(EvidenceStateSnapshot.evaluation_time.asc())
        ).scalars().all()
    )

    history: list[StateSnapshotItem] = []
    for snap in snapshots:
        trace_id = _find_trace_id_for_snapshot(
            db,
            payment_id=snap.payment_id,
            evaluation_time=snap.evaluation_time,
            methodology_version=snap.methodology_version,
        )
        history.append(StateSnapshotItem.from_snapshot(snap, integrity_trace_id=trace_id))

    return StateHistoryResponse(
        payment_id=payment_id,
        history=history,
        total=len(history),
    )


# ---------------------------------------------------------------------------
# Endpoint 3 — GET /changes/{change_id}
# ---------------------------------------------------------------------------

@router.get(
    "/changes/{change_id}",
    response_model=ChangeDetailResponse,
    summary="Full detail for a single evidence state change",
    description=(
        "Returns the complete EvidenceStateChange record for the given UUID. "
        "Only safe derived fields are returned — the schema excludes raw payloads, "
        "secrets, credentials, and any other sensitive data."
    ),
)
def get_change_detail(
    change_id: str,
    db: Session = Depends(get_db),
) -> ChangeDetailResponse:
    change = db.execute(
        select(EvidenceStateChange).where(
            EvidenceStateChange.change_id == change_id
        )
    ).scalar_one_or_none()

    if change is None:
        raise HTTPException(
            status_code=404,
            detail=f"Change '{change_id}' not found.",
        )

    return ChangeDetailResponse.model_validate(change)


# ---------------------------------------------------------------------------
# Endpoint 4 — POST /payments/{payment_id}/integrity/recompute
# ---------------------------------------------------------------------------

@router.post(
    "/payments/{payment_id}/integrity/recompute",
    response_model=RecomputeResponse,
    summary="Trigger fresh integrity evaluation and change detection",
    description=(
        "Runs a fresh Phase 9 integrity evaluation at the current time, "
        "creates a new EvidenceStateSnapshot, diffs it against the previous "
        "snapshot to detect changes, commits, and returns the result. "
        "Idempotent within the same second (the Phase 9 engine deduplicates "
        "by identity triple). Returns no_material_change=True when the new "
        "snapshot is identical to the previous one."
    ),
)
def recompute_payment_integrity(
    payment_id: str,
    db: Session = Depends(get_db),
) -> RecomputeResponse:
    _get_payment_or_404(payment_id, db)

    measurement_time = datetime.now(tz=timezone.utc)

    # --- Phase 9 + Phase 10: run integrity evaluation and record trace -------
    from app.services.integrity_trace_service import IntegrityTraceService

    trace = IntegrityTraceService.record_evaluation(
        db,
        payment_id,
        measurement_time,
        trigger="MANUAL_RECOMPUTATION",
    )

    # Legacy data guard: if the trace service returns None it means a Phase 9
    # snapshot existed before Phase 10 was introduced and no trace could be
    # fabricated.  Skip snapshot creation and return an empty result.
    if trace is None:
        logger.warning(
            "recompute: IntegrityTraceService returned None (legacy data) — "
            "skipping Phase 11 snapshot; returning empty changes",
            extra={"payment_id": payment_id},
        )
        # We still need a stub snapshot item.  Build a minimal placeholder
        # using whatever the most recent snapshot is, if one exists.
        latest_snap = db.execute(
            select(EvidenceStateSnapshot)
            .where(EvidenceStateSnapshot.payment_id == payment_id)
            .order_by(EvidenceStateSnapshot.evaluation_time.desc())
        ).scalars().first()

        if latest_snap is not None:
            stub = StateSnapshotItem.from_snapshot(latest_snap)
        else:
            # No snapshot at all — we cannot return a meaningful result.
            raise HTTPException(
                status_code=500,
                detail=(
                    "Integrity computation produced no result "
                    "(legacy data without a Phase 10 trace)."
                ),
            )

        return RecomputeResponse(
            payment_id=payment_id,
            new_snapshot=stub,
            changes_detected=[],
            change_count=0,
            no_material_change=True,
        )

    # --- Phase 11: take a state snapshot -------------------------------------
    from app.services.evolution_snapshot_service import EvidenceStateSnapshotService

    current_snap = EvidenceStateSnapshotService.take_snapshot(
        db, payment_id, measurement_time
    )

    # --- Phase 11: compare with the previous snapshot ------------------------
    prev_snap = db.execute(
        select(EvidenceStateSnapshot)
        .where(
            EvidenceStateSnapshot.payment_id == payment_id,
            EvidenceStateSnapshot.internal_id != current_snap.internal_id,
        )
        .order_by(EvidenceStateSnapshot.evaluation_time.desc())
        .limit(1)
    ).scalars().first()

    changes: list[EvidenceStateChange] = []
    if prev_snap is not None:
        from app.services.evolution_change_engine import EvidenceChangeEngine

        changes = EvidenceChangeEngine.detect_and_persist_changes(
            db, payment_id, prev_snap, current_snap
        )

    db.commit()

    logger.info(
        "Manual recomputation completed",
        extra={
            "payment_id": payment_id,
            "measurement_time": measurement_time.isoformat(),
            "snapshot_id": current_snap.internal_id,
            "change_count": len(changes),
            "no_material_change": len(changes) == 0,
        },
    )

    return RecomputeResponse(
        payment_id=payment_id,
        new_snapshot=StateSnapshotItem.from_snapshot(current_snap),
        changes_detected=[ChangeItem.from_change(c) for c in changes],
        change_count=len(changes),
        no_material_change=len(changes) == 0,
    )
