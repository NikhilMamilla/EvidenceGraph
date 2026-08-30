"""
Phase 20 — Composite Evidence Integrity Risk Score API.

Endpoints:
  GET /api/v1/payments/{id}/risk-score  — Full risk score with dimensional breakdown
  GET /api/v1/risk-scores               — Risk summaries for all payments
  GET /api/v1/payments/{id}/risk-trend  — Risk score trend over time
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.risk_score import RiskScoreResponse, RiskTrendResponse
from app.services.risk_score_engine import RiskScoreEngine

router = APIRouter()


@router.get(
    "/payments/{razorpay_payment_id}/risk-score",
    response_model=RiskScoreResponse,
    summary="Composite evidence integrity risk score",
    description=(
        "Computes a multi-dimensional risk score (0–100) from evidence quality, "
        "coverage, reliability, consistency, and freshness signals."
    ),
)
def get_payment_risk_score(
    razorpay_payment_id: str,
    db: Session = Depends(get_db),
) -> RiskScoreResponse:
    result = RiskScoreEngine.compute_risk_score(db, razorpay_payment_id)
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Payment not found",
        )
    return result


@router.get(
    "/risk-scores",
    response_model=list,
    summary="Risk summaries for all payments",
)
def get_all_risk_summaries(
    db: Session = Depends(get_db),
):
    return RiskScoreEngine.get_all_payment_risk_summaries(db)


@router.get(
    "/payments/{razorpay_payment_id}/risk-trend",
    response_model=RiskTrendResponse,
    summary="Risk score trend over time",
)
def get_risk_trend(
    razorpay_payment_id: str,
    db: Session = Depends(get_db),
) -> RiskTrendResponse:
    result = RiskScoreEngine.get_risk_trend(db, razorpay_payment_id)
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Payment not found",
        )
    return result
