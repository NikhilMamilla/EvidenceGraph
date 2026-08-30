"""
Evidence Graph API endpoints — Phase 5.

Read-only endpoints for querying the evidence graph.
No scoring, no risk labels, no fraud signals.

Registered at /api/v1/graph (prefix-less sub-paths):
  GET /api/v1/graph/payments/{payment_id}  → payment evidence graph
  GET /api/v1/graph/evidence/{evidence_id}/relationships → per-observation edges
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.evidence import EvidenceObservation
from app.models.payment import Payment
from app.schemas.graph import GraphEdgeSchema, PaymentGraphSchema
from app.services.graph_service import get_evidence_relationships, get_payment_graph

router = APIRouter()


@router.get(
    "/payments/{razorpay_payment_id}",
    response_model=PaymentGraphSchema,
    summary="Evidence graph for a payment",
    description=(
        "Returns all evidence nodes and directed relationship edges "
        "for the given payment. Bounded to the payment's own evidence set. "
        "No scores, no risk labels, no interpretation."
    ),
)
def get_payment_evidence_graph(
    razorpay_payment_id: str,
    db: Session = Depends(get_db),
) -> PaymentGraphSchema:
    payment = db.execute(
        select(Payment).where(Payment.razorpay_payment_id == razorpay_payment_id)
    ).scalar_one_or_none()

    if not payment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Payment not found",
        )

    return get_payment_graph(razorpay_payment_id, db)


@router.get(
    "/evidence/{evidence_id}/relationships",
    response_model=list[GraphEdgeSchema],
    summary="Relationships for a single evidence observation",
    description=(
        "Returns all directed edges where this evidence observation is "
        "the source or the target. No scores, no interpretation."
    ),
)
def get_evidence_relationship_edges(
    evidence_id: int,
    db: Session = Depends(get_db),
) -> list[GraphEdgeSchema]:
    obs = db.get(EvidenceObservation, evidence_id)
    if not obs:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Evidence observation not found",
        )

    return get_evidence_relationships(evidence_id, db)
