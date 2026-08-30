"""
Phase 14 — Evidence Lineage & Causal Explanation Engine: API endpoints.

Routes:
  GET /api/v1/payments/{payment_id}/lineage
  GET /api/v1/integrity/{trace_id}/lineage
  GET /api/v1/facts/{fact_id}/lineage
  GET /api/v1/lineage/path
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.lineage_types import (
    LINEAGE_MAX_DEPTH_HARD_LIMIT,
    LINEAGE_MAX_NODES_HARD_LIMIT,
)
from app.schemas.lineage import (
    FactLineageResponse,
    LineagePathResponse,
    PaymentLineageResponse,
    TraceLineageResponse,
)
from app.services.lineage_engine import (
    build_fact_lineage,
    build_payment_lineage,
    build_trace_lineage,
    find_lineage_path,
)

router = APIRouter(tags=["lineage"])


@router.get(
    "/payments/{payment_id}/lineage",
    response_model=PaymentLineageResponse,
    summary="Full evidence lineage for a payment",
    description=(
        "Assembles the complete, forward evidence lineage for a payment — from the "
        "original Razorpay provider event (WebhookEvent) to the final EvidenceIntegrityTrace. "
        "All edges are backed by actual FK relationships or explicitly documented as "
        "DERIVED_TEMPORAL where no FK exists. Gaps are recorded as explicit LineageGap objects."
    ),
)
def get_payment_lineage(
    payment_id: str,
    as_of: Optional[datetime] = Query(
        None,
        description=(
            "Return lineage as known at this timestamp. Evidence observed after "
            "this time is excluded. ISO-8601 format with timezone (e.g. 2026-08-23T10:00:00Z)."
        ),
    ),
    max_nodes: int = Query(
        200,
        ge=1,
        le=LINEAGE_MAX_NODES_HARD_LIMIT,
        description="Maximum number of lineage nodes to include. Default 200, maximum 500.",
    ),
    max_depth: int = Query(
        8,
        ge=1,
        le=LINEAGE_MAX_DEPTH_HARD_LIMIT,
        description="Maximum traversal depth. Default 8, maximum 10.",
    ),
    db: Session = Depends(get_db),
) -> PaymentLineageResponse:
    return build_payment_lineage(
        db=db,
        payment_id=payment_id,
        as_of=as_of,
        max_nodes=max_nodes,
        max_depth=max_depth,
    )


@router.get(
    "/integrity/{trace_id}/lineage",
    response_model=TraceLineageResponse,
    summary="Reverse lineage from an integrity trace to provider events",
    description=(
        "Assembles evidence lineage in reverse — starting from an EvidenceIntegrityTrace "
        "and walking backward to the original Razorpay WebhookEvents. "
        "Uses the trace's evaluated_at timestamp as the implicit as_of boundary."
    ),
)
def get_trace_lineage(
    trace_id: str,
    max_nodes: int = Query(
        200,
        ge=1,
        le=LINEAGE_MAX_NODES_HARD_LIMIT,
        description="Maximum number of lineage nodes to include.",
    ),
    db: Session = Depends(get_db),
) -> TraceLineageResponse:
    return build_trace_lineage(db=db, trace_id=trace_id, max_nodes=max_nodes)


@router.get(
    "/facts/{fact_id}/lineage",
    response_model=FactLineageResponse,
    summary="Lineage for a single evidence fact",
    description=(
        "Assembles the lineage for one EvidenceFact — its supporting observations, "
        "originating WebhookEvents, associated Claims, and integrity reference. "
        "Traversal is bounded to the fact's payment context."
    ),
)
def get_fact_lineage(
    fact_id: int,
    as_of: Optional[datetime] = Query(
        None,
        description="Return lineage as known at this timestamp.",
    ),
    db: Session = Depends(get_db),
) -> FactLineageResponse:
    result = build_fact_lineage(db=db, fact_id=fact_id, as_of=as_of)
    if result.payment_id == "" and not result.nodes:
        raise HTTPException(status_code=404, detail=f"EvidenceFact #{fact_id} not found.")
    return result


@router.get(
    "/lineage/path",
    response_model=LineagePathResponse,
    summary="Find the shortest path between two lineage entities",
    description=(
        "Performs a bounded BFS across the evidence lineage graph to find the shortest "
        "path between two entities. Both entities must belong to the same payment's lineage. "
        "Returns found=False if no path exists within max_depth steps."
    ),
)
def get_lineage_path(
    source_type: str = Query(..., description="LineageNodeType of the source entity (e.g. 'WEBHOOK_EVENT')"),
    source_id: str = Query(..., description="ID of the source entity"),
    target_type: str = Query(..., description="LineageNodeType of the target entity (e.g. 'INTEGRITY_TRACE')"),
    target_id: str = Query(..., description="ID of the target entity"),
    max_depth: int = Query(
        8,
        ge=1,
        le=LINEAGE_MAX_DEPTH_HARD_LIMIT,
        description="Maximum path depth (default 8, maximum 10).",
    ),
    as_of: Optional[datetime] = Query(None, description="Optional temporal cutoff."),
    db: Session = Depends(get_db),
) -> LineagePathResponse:
    return find_lineage_path(
        db=db,
        source_type=source_type,
        source_id=source_id,
        target_type=target_type,
        target_id=target_id,
        max_depth=max_depth,
        as_of=as_of,
    )
