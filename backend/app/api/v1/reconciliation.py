"""
Phase 13 — Reconciliation API Router.

Exposes REST endpoints for:
- GET /api/v1/facts/{fact_id}
- GET /api/v1/payments/{payment_id}/facts
- GET /api/v1/observations/{observation_id}/reconciliation
- POST /api/v1/payments/{payment_id}/reconcile
- POST /api/v1/reconciliation/backfill

Security:
- Never exposes sensitive webhook raw_payload or secrets.
- Uses sanitized Pydantic response schemas.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.reconciliation import (
    BackfillReportResponse,
    FactDetailResponse,
    ObservationReconciliationResponse,
    PaymentFactsResponse,
)
from app.services.fact_service import FactService
from app.services.reconciliation_engine import ReconciliationEngine

router = APIRouter(tags=["reconciliation"])


@router.get(
    "/facts/{fact_id}",
    response_model=FactDetailResponse,
    summary="Retrieve canonical EvidenceFact details and provenance",
    description="Returns an EvidenceFact, its supporting observations, source diversity breakdown, and associated claims/conflicts.",
)
def get_fact_detail(
    fact_id: int,
    db: Session = Depends(get_db),
) -> FactDetailResponse:
    try:
        return FactService.get_fact_detail(db=db, fact_id=fact_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )


@router.get(
    "/payments/{payment_id}/facts",
    response_model=PaymentFactsResponse,
    summary="List canonical EvidenceFacts for a payment",
    description="Returns all canonical EvidenceFacts for the specified payment with optional filtering by fact_type and status.",
)
def get_payment_facts(
    payment_id: str,
    fact_type: Optional[str] = Query(None, description="Filter by FactType constant"),
    status_filter: Optional[str] = Query(None, alias="status", description="Filter by FactStatus constant"),
    from_time: Optional[datetime] = Query(None, description="Earliest first_observed_at filter"),
    to_time: Optional[datetime] = Query(None, description="Latest last_observed_at filter"),
    db: Session = Depends(get_db),
) -> PaymentFactsResponse:
    return FactService.get_payment_facts(
        db=db,
        payment_id=payment_id,
        fact_type=fact_type,
        status=status_filter,
        from_time=from_time,
        to_time=to_time,
    )


@router.get(
    "/observations/{observation_id}/reconciliation",
    response_model=ObservationReconciliationResponse,
    summary="Retrieve reconciliation history for an observation",
    description="Returns the matched EvidenceFact and all pairwise reconciliation decisions involving this observation.",
)
def get_observation_reconciliation(
    observation_id: int,
    db: Session = Depends(get_db),
) -> ObservationReconciliationResponse:
    try:
        return FactService.get_observation_reconciliation(db=db, observation_id=observation_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )


@router.post(
    "/payments/{payment_id}/reconcile",
    response_model=PaymentFactsResponse,
    summary="Run deterministic reconciliation on payment observations",
    description="Evaluates all observations for a payment, links them to canonical EvidenceFacts, and records pairwise decisions.",
)
def reconcile_payment(
    payment_id: str,
    db: Session = Depends(get_db),
) -> PaymentFactsResponse:
    facts = ReconciliationEngine.reconcile_payment(db=db, payment_id=payment_id)
    return FactService.get_payment_facts(db=db, payment_id=payment_id)


@router.post(
    "/reconciliation/backfill",
    response_model=BackfillReportResponse,
    summary="Run historical reconciliation backfill across all payments",
    description="Safe and idempotent historical backfill of evidence facts and reconciliation records.",
)
def run_backfill(
    db: Session = Depends(get_db),
) -> BackfillReportResponse:
    report = ReconciliationEngine.backfill_all_payments(db=db)
    return BackfillReportResponse(
        payments_processed=report.payments_processed,
        observations_processed=report.observations_processed,
        facts_created=report.facts_created,
        facts_matched_existing=report.facts_matched_existing,
        same_fact_decisions=report.same_fact_decisions,
        different_fact_decisions=report.different_fact_decisions,
        related_fact_decisions=report.related_fact_decisions,
        conflicting_fact_decisions=report.conflicting_fact_decisions,
        unknown_decisions=report.unknown_decisions,
        failures=report.failures,
    )
