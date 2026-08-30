"""
Phase 10 — Evidence Integrity Decision Trace API.

Endpoints and authorization tiers:

  GET /payments/{payment_id}/integrity/traces          normal authorization
        Historical trace summaries for a payment (identity, lifecycle,
        result, hash presence). No full audit content.

  GET /integrity/{trace_id}                            X-API-Key (admin)
        Full decision trace: canonical payload + audit event timeline.

  GET /integrity/{trace_id}/verify                     X-API-Key (admin)
        Cryptographic verification status (VALID / INVALID / ...).

  GET /payments/{payment_id}/integrity/chain-verify    X-API-Key (admin)
        Per-payment hash-chain verification.

  POST /integrity/{trace_id}/replay                    X-API-Key (admin)
        Re-execute the evaluation and compare. Never mutates the original.

There is deliberately NO endpoint that creates, updates, or deletes traces:
completed traces are immutable and history is never rewritten through the API.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.auth import require_admin_api_key
from app.db.session import get_db
from app.models.integrity_trace import IntegrityTraceEvent
from app.models.payment import Payment
from app.schemas.trace import (
    TraceChainVerificationResponse,
    TraceDetailResponse,
    TraceListResponse,
    TraceReplayResponse,
    TraceSummaryItem,
    TraceVerificationResponse,
)
from app.services.replay_service import ReplayNotPossibleError, ReplayService
from app.services.trace_verification import TraceVerificationService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["integrity-traces"])


def _payment_exists_or_404(payment_id: str, db: Session) -> None:
    payment = db.execute(
        select(Payment).where(Payment.razorpay_payment_id == payment_id)
    ).scalar_one_or_none()
    if payment is None:
        raise HTTPException(
            status_code=404, detail=f"Payment '{payment_id}' not found."
        )


# ---------------------------------------------------------------------------
# Tier 1 — normal authorization: trace summaries
# ---------------------------------------------------------------------------

@router.get(
    "/payments/{payment_id}/integrity/traces",
    response_model=TraceListResponse,
    summary="Historical decision traces for a payment",
    description=(
        "Returns all Evidence Integrity Decision Traces for the payment, "
        "ordered by evaluation time ascending. Summaries include lifecycle "
        "status, result, and cryptographic hash metadata — not full audit "
        "content. New evaluations create new traces; history is never mutated."
    ),
)
def list_payment_traces(
    payment_id: str,
    db: Session = Depends(get_db),
) -> TraceListResponse:
    _payment_exists_or_404(payment_id, db)

    from app.services.integrity_trace_service import IntegrityTraceService

    traces = IntegrityTraceService.list_payment_traces(db, payment_id)
    return TraceListResponse(
        payment_id=payment_id,
        traces=[TraceSummaryItem.from_trace(t) for t in traces],
        total=len(traces),
    )


# ---------------------------------------------------------------------------
# Tier 2 — admin authorization: full trace content
# ---------------------------------------------------------------------------

@router.get(
    "/integrity/{trace_id}",
    response_model=TraceDetailResponse,
    summary="Full decision trace (restricted)",
    description=(
        "Returns the complete audit trace: evaluation context, evidence "
        "inputs and exclusions, measurements, structure, corroboration, "
        "conflicts, rule executions, intermediate results, final result, "
        "limitations, canonical payload, and the ordered audit event timeline. "
        "Requires administrative API-key authorization."
    ),
    dependencies=[Depends(require_admin_api_key)],
)
def get_trace_detail(
    trace_id: str,
    db: Session = Depends(get_db),
) -> TraceDetailResponse:
    from app.services.integrity_trace_service import IntegrityTraceService

    trace = IntegrityTraceService.get_by_trace_id(db, trace_id)
    if trace is None:
        raise HTTPException(status_code=404, detail=f"Trace '{trace_id}' not found.")

    events = list(
        db.execute(
            select(IntegrityTraceEvent)
            .where(IntegrityTraceEvent.trace_id == trace_id)
            .order_by(IntegrityTraceEvent.sequence_number.asc())
        ).scalars().all()
    )
    return TraceDetailResponse.from_trace(trace, events)


# ---------------------------------------------------------------------------
# Tier 3 — admin authorization: cryptographic verification
# ---------------------------------------------------------------------------

@router.get(
    "/integrity/{trace_id}/verify",
    response_model=TraceVerificationResponse,
    summary="Verify one trace's cryptographic integrity (restricted)",
    description=(
        "Reconstructs the canonical payload, recomputes SHA-256, and compares "
        "against the stored hash. Returns VALID, INVALID, or "
        "VERIFICATION_UNAVAILABLE (never a false VALID). Requires "
        "administrative API-key authorization."
    ),
    dependencies=[Depends(require_admin_api_key)],
)
def verify_trace(
    trace_id: str,
    db: Session = Depends(get_db),
) -> TraceVerificationResponse:
    result = TraceVerificationService.verify_trace_integrity(db, trace_id)
    if result["status"] == "NOT_FOUND":
        raise HTTPException(status_code=404, detail=result["message"])
    return TraceVerificationResponse(**result)


@router.get(
    "/payments/{payment_id}/integrity/chain-verify",
    response_model=TraceChainVerificationResponse,
    summary="Verify the payment's trace hash chain (restricted)",
    description=(
        "Independently recomputes every finalized evaluation trace hash for "
        "the payment and validates the previous-hash linkage. Returns "
        "CHAIN_VALID, CHAIN_INVALID, CHAIN_START, or NO_TRACES. The chain is "
        "a tamper-EVIDENCE audit mechanism, not immutability."
    ),
    dependencies=[Depends(require_admin_api_key)],
)
def verify_trace_chain(
    payment_id: str,
    db: Session = Depends(get_db),
) -> TraceChainVerificationResponse:
    _payment_exists_or_404(payment_id, db)
    result = TraceVerificationService.verify_trace_chain(db, payment_id)
    return TraceChainVerificationResponse(**result)


# ---------------------------------------------------------------------------
# Tier 4 — admin authorization: replay
# ---------------------------------------------------------------------------

@router.post(
    "/integrity/{trace_id}/replay",
    response_model=TraceReplayResponse,
    summary="Replay a decision trace (restricted)",
    description=(
        "Re-executes the authoritative integrity computation for the "
        "original evaluation context and compares results. The original "
        "trace is never modified; a separate REPLAY trace records the "
        "comparison. Requires administrative API-key authorization."
    ),
    dependencies=[Depends(require_admin_api_key)],
)
def replay_trace(
    trace_id: str,
    db: Session = Depends(get_db),
) -> TraceReplayResponse:
    try:
        result = ReplayService.replay_trace(db, trace_id)
    except ReplayNotPossibleError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    db.commit()
    return TraceReplayResponse(**result)
