"""
Phase 19 — Operational Intelligence & Verification REST Endpoints.
"""

from __future__ import annotations

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.auth import require_admin_api_key
from app.db.session import get_db
from app.schemas.operations import (
    IncidentTimelineResponse,
    PaymentOperationalStatusResponse,
    PipelineWatermarkResponse,
    SystemHealthResponse,
    SystemOperationalMetricsResponse,
    VerificationRunResponse,
)
from app.services.operations_service import OperationsService

router = APIRouter(prefix="/operations", tags=["operations"])


@router.get(
    "/health",
    response_model=SystemHealthResponse,
    summary="Get unified system operational health",
    description="Returns real-time operational health state across all dependencies and pipeline components.",
)
def get_operational_health(db: Session = Depends(get_db)) -> SystemHealthResponse:
    return OperationsService.get_system_health(db)


@router.get(
    "/metrics",
    response_model=SystemOperationalMetricsResponse,
    summary="Get real-time operational metrics",
    description="Returns actual queue depth, processing lag, event counts, throughput, and error rates.",
)
def get_operational_metrics(db: Session = Depends(get_db)) -> SystemOperationalMetricsResponse:
    return OperationsService.get_operational_metrics(db)


@router.get(
    "/pipeline",
    response_model=PipelineWatermarkResponse,
    summary="Get end-to-end pipeline status and watermark",
    description="Returns status of all 8 pipeline processing stages along with latest pipeline watermark.",
)
def get_pipeline_status(db: Session = Depends(get_db)) -> PipelineWatermarkResponse:
    return OperationsService.get_pipeline_status(db)


@router.get(
    "/verification",
    response_model=VerificationRunResponse,
    summary="Get or run continuous verification of system invariants",
    description="Executes deterministic system invariant checks (INV-SYS-01 to INV-SYS-10). Read-only; never mutates evidence.",
)
@router.post(
    "/verification",
    response_model=VerificationRunResponse,
    summary="Run continuous verification of system invariants",
)
@router.post(
    "/verify",
    response_model=VerificationRunResponse,
    summary="Run continuous verification of system invariants (legacy alias)",
)
def run_system_verification(db: Session = Depends(get_db)) -> VerificationRunResponse:
    return OperationsService.run_continuous_verification(db)


@router.get(
    "/incidents",
    response_model=IncidentTimelineResponse,
    summary="Get operational incidents and timeline",
    description="Returns actual operational incidents detected across dependencies, queues, and workers.",
)
def get_operational_incidents(
    window_hours: int = Query(default=24, ge=1, le=168),
    db: Session = Depends(get_db),
) -> IncidentTimelineResponse:
    return OperationsService.detect_operational_incidents(db, time_window_hours=window_hours)


# Payment-scoped operational status endpoint (also exposed under payments router)
payment_ops_router = APIRouter(tags=["operations"])


@payment_ops_router.get(
    "/payments/{payment_id}/operational-status",
    response_model=PaymentOperationalStatusResponse,
    summary="Get payment processing freshness and downstream layer status",
    description="Evaluates whether canonical facts, coverage, reliability, and integrity are CURRENT or STALE relative to observed evidence.",
)
def get_payment_operational_status(
    payment_id: str,
    db: Session = Depends(get_db),
) -> PaymentOperationalStatusResponse:
    result = OperationsService.get_payment_operational_status(db, payment_id)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Payment '{payment_id}' not found.",
        )
    return result
