"""
Investigation Engine API Router — Phase 12.

Deterministic graph querying, bounded traversal, provenance tracking,
claim support & corroboration analysis, conflict inspection, and exact search.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.investigation_types import (
    DEFAULT_MAX_EDGES,
    DEFAULT_MAX_NODES,
    DEFAULT_TRAVERSAL_DEPTH,
    HARD_MAX_EDGES,
    HARD_MAX_NODES,
    MAX_TRAVERSAL_DEPTH,
    InvestigationEdgeType,
    InvestigationNodeType,
)
from app.schemas.investigation import (
    ClaimSupportResponse,
    ConflictPathResponse,
    EvidenceDependenciesResponse,
    EvidenceProvenanceResponse,
    InvestigationGraphResponse,
    InvestigationPathResponse,
    SearchResponse,
)
from app.services.investigation_service import InvestigationService

router = APIRouter(prefix="/investigation", tags=["investigation"])


@router.get(
    "/payments/{payment_id}/graph",
    response_model=InvestigationGraphResponse,
    summary="Retrieve bounded investigation graph for a payment",
    description=(
        "Returns the deterministic evidence graph centered on a payment. "
        "Supports depth bounding, as_of historical filtering, and node/edge limits. "
        "Sensitive fields and credentials are never exposed."
    ),
)
def get_payment_investigation_graph(
    payment_id: str,
    depth: int = Query(
        DEFAULT_TRAVERSAL_DEPTH,
        ge=1,
        le=MAX_TRAVERSAL_DEPTH,
        description="Traversal depth (hops from root payment)",
    ),
    as_of: Optional[datetime] = Query(
        None,
        description="Point-in-time timestamp (ISO 8601). Excludes evidence observed after this time.",
    ),
    node_types: Optional[list[InvestigationNodeType]] = Query(
        None,
        description="Optional filter for specific node types",
    ),
    relationship_types: Optional[list[InvestigationEdgeType]] = Query(
        None,
        description="Optional filter for specific relationship edge types",
    ),
    max_nodes: int = Query(
        DEFAULT_MAX_NODES,
        ge=1,
        le=HARD_MAX_NODES,
        description="Maximum number of nodes to return before bounding",
    ),
    max_edges: int = Query(
        DEFAULT_MAX_EDGES,
        ge=1,
        le=HARD_MAX_EDGES,
        description="Maximum number of edges to return before bounding",
    ),
    db: Session = Depends(get_db),
) -> InvestigationGraphResponse:
    try:
        return InvestigationService.build_payment_graph(
            db=db,
            payment_id=payment_id,
            depth=depth,
            as_of=as_of,
            node_types=node_types,
            relationship_types=relationship_types,
            max_nodes=max_nodes,
            max_edges=max_edges,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )


@router.get(
    "/path",
    response_model=InvestigationPathResponse,
    summary="Find shortest path between two graph nodes",
    description="Traverses persisted relationships between source and target nodes.",
)
def get_investigation_path(
    source: str = Query(..., description="Source node ID (e.g. pay:pay_123, ev:45)"),
    target: str = Query(..., description="Target node ID (e.g. claim:67, wh:89)"),
    max_depth: int = Query(5, ge=1, le=10, description="Maximum search hops"),
    as_of: Optional[datetime] = Query(None, description="Historical timestamp filter"),
    db: Session = Depends(get_db),
) -> InvestigationPathResponse:
    return InvestigationService.find_path(
        db=db,
        source=source,
        target=target,
        max_depth=max_depth,
        as_of=as_of,
    )


@router.get(
    "/evidence/{evidence_id}/provenance",
    response_model=EvidenceProvenanceResponse,
    summary="Retrieve provenance chain for an evidence observation",
    description="Returns the full upstream lineage: Evidence -> PaymentEvent -> WebhookEvent -> Payment.",
)
def get_evidence_provenance(
    evidence_id: int,
    db: Session = Depends(get_db),
) -> EvidenceProvenanceResponse:
    try:
        return InvestigationService.get_evidence_provenance(db=db, evidence_id=evidence_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )


@router.get(
    "/claims/{claim_id}/support",
    response_model=ClaimSupportResponse,
    summary="Query supporting evidence and corroboration for a claim",
    description=(
        "Explains which observations independently corroborate this claim vs "
        "which are duplicate representations of the same underlying event."
    ),
)
def get_claim_support(
    claim_id: int,
    db: Session = Depends(get_db),
) -> ClaimSupportResponse:
    try:
        return InvestigationService.get_claim_support(db=db, claim_id=claim_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )


@router.get(
    "/evidence/{evidence_id}/dependencies",
    response_model=EvidenceDependenciesResponse,
    summary="Query dependencies for an evidence observation",
    description="Returns direct and indirect dependency graph for an evidence observation.",
)
def get_evidence_dependencies(
    evidence_id: int,
    db: Session = Depends(get_db),
) -> EvidenceDependenciesResponse:
    try:
        return InvestigationService.get_evidence_dependencies(db=db, evidence_id=evidence_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )


@router.get(
    "/conflicts/{conflict_id}/path",
    response_model=ConflictPathResponse,
    summary="Inspect conflict structure, opposing claims, and supporting evidence",
    description="Traverses the contradiction path between opposing claims and their evidence bases.",
)
def get_conflict_path(
    conflict_id: int,
    db: Session = Depends(get_db),
) -> ConflictPathResponse:
    try:
        return InvestigationService.get_conflict_path(db=db, conflict_id=conflict_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )


@router.get(
    "/search",
    response_model=SearchResponse,
    summary="Exact and prefix lookup for entity identifiers",
    description="Indexed search across payments, orders, customers, webhooks, evidence, claims, and traces.",
)
def search_investigation_entities(
    q: str = Query(..., min_length=1, max_length=128, description="Identifier query string"),
    limit: int = Query(20, ge=1, le=50, description="Max results"),
    db: Session = Depends(get_db),
) -> SearchResponse:
    return InvestigationService.search_entities(db=db, query=q, limit=limit)
