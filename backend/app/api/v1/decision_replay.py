"""
Phase 18 — Decision Replay & Differential Analysis API Endpoints.

Exposes REST endpoints for deterministic historical decision replay,
trace-based replay verification, pairwise differential analysis, and
change explanation generation.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.payment import Payment
from app.schemas.decision_replay import (
    DecisionChangeExplanationResponse,
    DecisionReplayRequest,
    DecisionReplayResponse,
    EvidenceDecisionDiffResponse,
    ReplayVerificationResponse,
)
from app.services.decision_diff_engine import DecisionDiffEngine
from app.services.decision_replay_engine import DecisionReplayEngine

router = APIRouter(tags=["Decision Replay & Differential Analysis"])


@router.post(
    "/payments/{payment_id}/replay",
    response_model=DecisionReplayResponse,
    summary="Reconstruct historical decision state at timestamp T",
)
def replay_payment_decision(
    payment_id: str,
    request: DecisionReplayRequest,
    db: Session = Depends(get_db),
) -> DecisionReplayResponse:
    """
    Executes a deterministic, read-only replay of a payment's evidence decision
    at evaluation_time. Enforces methodology and profile pinning, point-in-time
    evidence exclusion, and trace verification.
    """
    payment = db.query(Payment).filter(Payment.razorpay_payment_id == payment_id).first()
    if payment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Payment '{payment_id}' not found.",
        )

    return DecisionReplayEngine.reconstruct_decision_state(
        db=db,
        payment_id=payment_id,
        evaluation_time=request.evaluation_time,
        methodology_version=request.methodology_version or "EIS-1.0",
        profile_version=request.profile_version or "STANDARD_PAYMENT_PROFILE_V1",
        verify_trace=request.verify_trace if request.verify_trace is not None else True,
    )


@router.post(
    "/integrity/{trace_id}/verify-replay",
    response_model=ReplayVerificationResponse,
    summary="Verify historical trace reproducibility via replayed execution",
)
def verify_trace_replay(
    trace_id: str,
    db: Session = Depends(get_db),
) -> ReplayVerificationResponse:
    """
    Reconstructs the evaluation recorded in trace_id and performs a bit-for-bit
    and semantic comparison against the stored trace.
    """
    result = DecisionReplayEngine.verify_trace_replay(db, trace_id)
    if not result.payment_id and result.verification_status == "INCOMPLETE":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Decision trace '{trace_id}' not found.",
        )
    return result


def _parse_query_datetime(val: str | datetime) -> datetime:
    if isinstance(val, datetime):
        return val if val.tzinfo is not None else val.replace(tzinfo=timezone.utc)
    # Replace space with + if URL-decoded + became space
    s = val.strip()
    if " " in s and ("+" not in s[10:] and "-" not in s[10:]):
        s = s.replace(" ", "+")
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    dt = datetime.fromisoformat(s)
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


@router.get(
    "/payments/{payment_id}/diff",
    response_model=EvidenceDecisionDiffResponse,
    summary="Compute differential evidence and decision comparison between T1 and T2",
)
def get_decision_diff(
    payment_id: str,
    from_time: str = Query(..., alias="from", description="Historical start timestamp T1"),
    to_time: str = Query(..., alias="to", description="Historical end timestamp T2"),
    methodology_version: Optional[str] = Query(default="EIS-1.0"),
    profile_version: Optional[str] = Query(default="STANDARD_PAYMENT_PROFILE_V1"),
    db: Session = Depends(get_db),
) -> EvidenceDecisionDiffResponse:
    """
    Computes a comprehensive point-to-point differential analysis between T1 and T2,
    including fact lifecycle changes, source transitions, conflict additions/resolutions,
    coverage changes, reliability dimension shifts, and overall integrity changes.
    """
    payment = db.query(Payment).filter(Payment.razorpay_payment_id == payment_id).first()
    if payment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Payment '{payment_id}' not found.",
        )

    t1 = _parse_query_datetime(from_time)
    t2 = _parse_query_datetime(to_time)

    return DecisionDiffEngine.compare_decision_states(
        db=db,
        payment_id=payment_id,
        from_time=t1,
        to_time=t2,
        methodology_version=methodology_version or "EIS-1.0",
        profile_version=profile_version or "STANDARD_PAYMENT_PROFILE_V1",
    )


@router.get(
    "/payments/{payment_id}/diff/explanation",
    response_model=DecisionChangeExplanationResponse,
    summary="Generate deterministic change explanation between T1 and T2",
)
def get_decision_change_explanation(
    payment_id: str,
    from_time: str = Query(..., alias="from", description="Historical start timestamp T1"),
    to_time: str = Query(..., alias="to", description="Historical end timestamp T2"),
    methodology_version: Optional[str] = Query(default="EIS-1.0"),
    profile_version: Optional[str] = Query(default="STANDARD_PAYMENT_PROFILE_V1"),
    db: Session = Depends(get_db),
) -> DecisionChangeExplanationResponse:
    """
    Generates an auditable, deterministic change explanation answering 'What Changed?',
    'Why It Mattered?', and 'What Remains Uncertain?', with strict causal bounding.
    """
    payment = db.query(Payment).filter(Payment.razorpay_payment_id == payment_id).first()
    if payment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Payment '{payment_id}' not found.",
        )

    t1 = _parse_query_datetime(from_time)
    t2 = _parse_query_datetime(to_time)

    return DecisionDiffEngine.generate_change_explanation(
        db=db,
        payment_id=payment_id,
        from_time=t1,
        to_time=t2,
        methodology_version=methodology_version or "EIS-1.0",
        profile_version=profile_version or "STANDARD_PAYMENT_PROFILE_V1",
    )
