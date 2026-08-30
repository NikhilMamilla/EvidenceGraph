"""
Phase 20 — Fraud Pattern Detection API.

Endpoints:
  GET /api/v1/payments/{id}/fraud-check     — Fraud analysis for a payment
  GET /api/v1/fraud/dashboard               — Global fraud detection dashboard
  GET /api/v1/fraud/patterns                — Cross-payment fraud patterns
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.fraud_detection import (
    FraudAlertResponse,
    FraudDashboardResponse,
    FraudPatternsResponse,
)
from app.services.fraud_detection_engine import FraudDetectionEngine

router = APIRouter()


@router.get(
    "/payments/{razorpay_payment_id}/fraud-check",
    response_model=FraudAlertResponse,
    summary="Fraud analysis for a payment",
    description=(
        "Runs all fraud detection rules on a payment and returns signals, "
        "severity levels, and recommendations."
    ),
)
def check_payment_fraud(
    razorpay_payment_id: str,
    db: Session = Depends(get_db),
) -> FraudAlertResponse:
    result = FraudDetectionEngine.analyze_payment(db, razorpay_payment_id)
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Payment not found",
        )
    return result


@router.get(
    "/fraud/dashboard",
    response_model=FraudDashboardResponse,
    summary="Global fraud detection dashboard",
)
def get_fraud_dashboard(
    db: Session = Depends(get_db),
) -> FraudDashboardResponse:
    return FraudDetectionEngine.get_dashboard(db)


@router.get(
    "/fraud/patterns",
    response_model=FraudPatternsResponse,
    summary="Cross-payment fraud patterns",
)
def get_fraud_patterns(
    db: Session = Depends(get_db),
) -> FraudPatternsResponse:
    return FraudDetectionEngine.detect_cross_payment_patterns(db)
