"""
Phase 16 — Evidence Reliability Calibration & Uncertainty Boundaries API Router.
"""

from datetime import datetime
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.evidence_fact import EvidenceFact
from app.schemas.reliability import (
    FactReliabilityResponse,
    PaymentReliabilityResponse,
    ReliabilityHistoryResponse,
    UncertaintyItemSchema,
)
from app.services.reliability_engine import (
    evaluate_fact_reliability,
    evaluate_payment_reliability,
    get_payment_uncertainty,
    get_reliability_history,
)

router = APIRouter(tags=["Evidence Reliability & Uncertainty (Phase 16)"])


@router.get(
    "/facts/{fact_id}/reliability",
    response_model=FactReliabilityResponse,
    summary="Get Fact Reliability Assessment",
    description="Deterministically evaluates reliability dimensions, ceilings, and uncertainty for a specific evidence fact.",
)
def get_fact_reliability_endpoint(
    fact_id: int,
    as_of: Optional[datetime] = Query(None, description="Historical point-in-time boundary (ISO-8601 UTC)"),
    db: Session = Depends(get_db),
):
    fact = db.query(EvidenceFact).filter(EvidenceFact.internal_id == fact_id).first()
    if not fact:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"EvidenceFact with ID {fact_id} was not found.",
        )
    return evaluate_fact_reliability(db, fact, as_of=as_of)


@router.get(
    "/payments/{payment_id}/reliability",
    response_model=PaymentReliabilityResponse,
    summary="Get Payment Evidence Reliability Assessment",
    description="Evaluates categorical reliability states across all facts of a payment at a point in time.",
)
def get_payment_reliability_endpoint(
    payment_id: str,
    as_of: Optional[datetime] = Query(None, description="Historical point-in-time boundary (ISO-8601 UTC)"),
    persist: bool = Query(False, description="Persist evaluation snapshot to database"),
    db: Session = Depends(get_db),
):
    return evaluate_payment_reliability(db, payment_id, as_of=as_of, persist=persist)


@router.get(
    "/payments/{payment_id}/reliability/history",
    response_model=ReliabilityHistoryResponse,
    summary="Get Payment Reliability History",
    description="Returns chronological history of persisted reliability evaluation snapshots.",
)
def get_payment_reliability_history_endpoint(
    payment_id: str,
    db: Session = Depends(get_db),
):
    return get_reliability_history(db, payment_id)


@router.get(
    "/payments/{payment_id}/uncertainty",
    response_model=List[UncertaintyItemSchema],
    summary="Get Payment Uncertainty Boundaries",
    description="Returns structured uncertainty boundaries (what is established vs uncertain vs unobserved).",
)
def get_payment_uncertainty_endpoint(
    payment_id: str,
    as_of: Optional[datetime] = Query(None, description="Historical point-in-time boundary (ISO-8601 UTC)"),
    db: Session = Depends(get_db),
):
    return get_payment_uncertainty(db, payment_id, as_of=as_of)
