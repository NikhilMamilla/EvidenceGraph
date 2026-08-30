"""
Phase 20 — Investigation Command Center API.

Endpoints:
  GET /api/v1/investigate/search?q=...          — Full-text search
  GET /api/v1/investigate/payments/{id}/profile — Payment investigation profile
  GET /api/v1/investigate/payments/{id}/timeline — Investigation timeline
  GET /api/v1/investigate/recommendations        — Investigation recommendations
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.investigation import (
    InvestigationRecommendationsResponse,
    InvestigationSearchResponse,
    InvestigationTimelineResponse,
    PaymentInvestigationProfile,
)
from app.services.investigation_service import InvestigationService

router = APIRouter()


@router.get(
    "/investigate/search",
    response_model=InvestigationSearchResponse,
    summary="Full-text search across all entities",
)
def search_investigation(
    q: str = Query(..., min_length=1, description="Search query"),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> InvestigationSearchResponse:
    return InvestigationService.search(db, q, limit=limit)


@router.get(
    "/investigate/payments/{razorpay_payment_id}/profile",
    response_model=PaymentInvestigationProfile,
    summary="Payment investigation profile",
)
def get_investigation_profile(
    razorpay_payment_id: str,
    db: Session = Depends(get_db),
) -> PaymentInvestigationProfile:
    result = InvestigationService.get_payment_profile(db, razorpay_payment_id)
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Payment not found",
        )
    return result


@router.get(
    "/investigate/payments/{razorpay_payment_id}/timeline",
    response_model=InvestigationTimelineResponse,
    summary="Unified investigation timeline",
)
def get_investigation_timeline(
    razorpay_payment_id: str,
    db: Session = Depends(get_db),
) -> InvestigationTimelineResponse:
    result = InvestigationService.get_investigation_timeline(db, razorpay_payment_id)
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Payment not found",
        )
    return result


@router.get(
    "/investigate/recommendations",
    response_model=InvestigationRecommendationsResponse,
    summary="Investigation recommendations",
)
def get_investigation_recommendations(
    payment_id: str | None = Query(None, description="Optional payment ID"),
    db: Session = Depends(get_db),
) -> InvestigationRecommendationsResponse:
    return InvestigationService.get_recommendations(db, payment_id)
