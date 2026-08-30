"""
Phase 15 — Evidence Completeness & Coverage Analysis API endpoints.

Routes:
  GET /api/v1/payments/{payment_id}/coverage
  GET /api/v1/payments/{payment_id}/coverage/history
  GET /api/v1/coverage/requirements/{requirement_id}
  POST /api/v1/payments/{payment_id}/coverage/recompute
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.coverage import (
    CoverageHistoryResponse,
    CoverageRecomputeResponse,
    EvidenceRequirementSchema,
    PaymentCoverageResponse,
)
from app.services.coverage_engine import (
    STANDARD_REQUIREMENTS,
    evaluate_coverage,
    get_coverage_history,
)

router = APIRouter(tags=["coverage"])


@router.get(
    "/payments/{payment_id}/coverage",
    response_model=PaymentCoverageResponse,
    summary="Evidence completeness and coverage for a payment",
    description=(
        "Evaluates what evidence was expected under the applicable evidence profile, "
        "what evidence has actually been observed, what is missing, and provides safe, "
        "deterministic explanations without negative fact assertions or fraud scoring."
    ),
)
def get_payment_coverage(
    payment_id: str,
    as_of: Optional[datetime] = Query(
        None,
        description="Evaluate coverage as of this timestamp (ISO-8601). Future evidence is excluded.",
    ),
    profile_id: Optional[str] = Query(
        None,
        description="Optional profile override (default: deterministically selected profile).",
    ),
    db: Session = Depends(get_db),
) -> PaymentCoverageResponse:
    return evaluate_coverage(
        db=db,
        payment_id=payment_id,
        as_of=as_of,
        profile_id=profile_id,
        persist=True,
    )


@router.get(
    "/payments/{payment_id}/coverage/history",
    response_model=CoverageHistoryResponse,
    summary="Historical evidence coverage snapshots for a payment",
    description="Returns an immutable chronological timeline of past coverage evaluations.",
)
def get_payment_coverage_history(
    payment_id: str,
    db: Session = Depends(get_db),
) -> CoverageHistoryResponse:
    return get_coverage_history(db=db, payment_id=payment_id)


@router.get(
    "/coverage/requirements/{requirement_id}",
    response_model=EvidenceRequirementSchema,
    summary="Requirement specification definition",
    description="Returns specification metadata for a specific evidence requirement.",
)
def get_requirement_detail(
    requirement_id: str,
) -> EvidenceRequirementSchema:
    for req in STANDARD_REQUIREMENTS:
        if req.requirement_id == requirement_id:
            return EvidenceRequirementSchema(
                requirement_id=req.requirement_id,
                requirement_type=req.base_requirement_type,
                evidence_type=req.evidence_type,
                fact_type=req.fact_type,
                description=req.description,
                applicability_reason="Configured in standard payment profile definition.",
            )
    raise HTTPException(status_code=404, detail=f"Requirement '{requirement_id}' not found.")


@router.post(
    "/payments/{payment_id}/coverage/recompute",
    response_model=CoverageRecomputeResponse,
    summary="Idempotent coverage evaluation recomputation",
    description="Recomputes evidence coverage for a payment at the current or specified time.",
)
def recompute_coverage(
    payment_id: str,
    as_of: Optional[datetime] = Query(None, description="Evaluation timestamp cutoff."),
    db: Session = Depends(get_db),
) -> CoverageRecomputeResponse:
    resp = evaluate_coverage(
        db=db,
        payment_id=payment_id,
        as_of=as_of,
        persist=True,
    )
    return CoverageRecomputeResponse(
        payment_id=payment_id,
        evaluated_at=resp.evaluated_at,
        overall_coverage_status=resp.overall_coverage_status,
        profile_id=resp.profile_id,
        profile_version=resp.profile_version,
        total_applicable=resp.metrics.total_applicable,
        snapshot_internal_id=0,
        recomputed=True,
        explanation=resp.explanation,
    )
