"""
Phase 21 — Payment Analytics API.

Endpoints:
  GET /api/v1/analytics/failures           — Failure intelligence dashboard
  GET /api/v1/analytics/failures/{id}      — Single payment failure analysis
  GET /api/v1/analytics/funnel             — Payment funnel visualization
  GET /api/v1/analytics/revenue            — Revenue intelligence
  GET /api/v1/analytics/notifications      — Real-time notification center
  GET /api/v1/analytics/merchant-risk      — Merchant risk profiling
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.payment_analytics import (
    FailureDashboardResponse,
    MerchantRiskDashboardResponse,
    NotificationCenterResponse,
    PaymentFailureAnalysis,
    PaymentFunnelResponse,
    RevenueIntelligenceResponse,
)
from app.services.payment_analytics_engine import PaymentAnalyticsEngine

router = APIRouter()


@router.get(
    "/analytics/failures",
    response_model=FailureDashboardResponse,
    summary="Payment failure intelligence dashboard",
)
def get_failure_dashboard(db: Session = Depends(get_db)) -> FailureDashboardResponse:
    return PaymentAnalyticsEngine.get_failure_dashboard(db)


@router.get(
    "/analytics/failures/{razorpay_payment_id}",
    response_model=PaymentFailureAnalysis,
    summary="Root cause analysis for a single payment",
)
def get_payment_failure_analysis(
    razorpay_payment_id: str,
    db: Session = Depends(get_db),
) -> PaymentFailureAnalysis:
    result = PaymentAnalyticsEngine.get_payment_failure_analysis(db, razorpay_payment_id)
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Payment not found",
        )
    return result


@router.get(
    "/analytics/funnel",
    response_model=PaymentFunnelResponse,
    summary="Payment funnel visualization",
)
def get_payment_funnel(db: Session = Depends(get_db)) -> PaymentFunnelResponse:
    return PaymentAnalyticsEngine.get_payment_funnel(db)


@router.get(
    "/analytics/revenue",
    response_model=RevenueIntelligenceResponse,
    summary="Revenue intelligence dashboard",
)
def get_revenue_intelligence(db: Session = Depends(get_db)) -> RevenueIntelligenceResponse:
    return PaymentAnalyticsEngine.get_revenue_intelligence(db)


@router.get(
    "/analytics/notifications",
    response_model=NotificationCenterResponse,
    summary="Real-time notification center",
)
def get_notifications(db: Session = Depends(get_db)) -> NotificationCenterResponse:
    return PaymentAnalyticsEngine.get_notifications(db)


@router.get(
    "/analytics/merchant-risk",
    response_model=MerchantRiskDashboardResponse,
    summary="Merchant risk profiling dashboard",
)
def get_merchant_risk_dashboard(db: Session = Depends(get_db)) -> MerchantRiskDashboardResponse:
    return PaymentAnalyticsEngine.get_merchant_risk_dashboard(db)
