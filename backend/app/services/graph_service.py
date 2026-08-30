"""
Graph service — Phase 5.

Provides bounded graph query functions.

Bounded means: only evidence belonging to the requested payment is loaded.
No recursive traversal of the entire database.
"""

from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.evidence import EvidenceObservation
from app.models.evidence_relationship import EvidenceRelationship
from app.models.evidence_types import SubjectType
from app.schemas.graph import GraphEdgeSchema, GraphNodeSchema, PaymentGraphSchema


def get_payment_graph(payment_subject_id: str, db: Session) -> PaymentGraphSchema:
    """
    Return the evidence graph for a payment.

    Loads all evidence nodes for the given Razorpay payment_id,
    then loads all relationships that connect them.

    Bounded: only reads from evidence_observations and evidence_relationships
    for this specific payment. Does not traverse the entire graph database.

    Returns a PaymentGraphSchema with nodes and edges.
    No scores, no risk labels, no fraud signals.
    """
    # 1. Load all evidence observations for this payment
    observations = db.execute(
        select(EvidenceObservation)
        .where(
            EvidenceObservation.subject_type == SubjectType.PAYMENT,
            EvidenceObservation.subject_id == payment_subject_id,
        )
        .order_by(EvidenceObservation.observed_at.asc())
    ).scalars().all()

    if not observations:
        return PaymentGraphSchema(
            payment_id=payment_subject_id,
            nodes=[],
            edges=[],
            node_count=0,
            edge_count=0,
        )

    evidence_ids = [o.internal_id for o in observations]

    # 2. Load all relationships whose source OR target is in this evidence set.
    #    This gives us all edges within the payment's own evidence sub-graph.
    relationships = db.execute(
        select(EvidenceRelationship)
        .where(
            or_(
                EvidenceRelationship.source_evidence_id.in_(evidence_ids),
                EvidenceRelationship.target_evidence_id.in_(evidence_ids),
            )
        )
    ).scalars().all()

    # 3. Build node schemas
    nodes = [_obs_to_node(o) for o in observations]

    # 4. Build edge schemas
    edges = [_rel_to_edge(r) for r in relationships]

    return PaymentGraphSchema(
        payment_id=payment_subject_id,
        nodes=nodes,
        edges=edges,
        node_count=len(nodes),
        edge_count=len(edges),
    )


def get_evidence_relationships(evidence_id: int, db: Session) -> list[GraphEdgeSchema]:
    """
    Return all relationships where this evidence observation is source or target.
    """
    relationships = db.execute(
        select(EvidenceRelationship)
        .where(
            or_(
                EvidenceRelationship.source_evidence_id == evidence_id,
                EvidenceRelationship.target_evidence_id == evidence_id,
            )
        )
    ).scalars().all()

    return [_rel_to_edge(r) for r in relationships]


def _obs_to_node(obs: EvidenceObservation) -> GraphNodeSchema:
    return GraphNodeSchema(
        evidence_id=obs.internal_id,
        evidence_type=obs.evidence_type,
        subject_type=obs.subject_type,
        subject_id=obs.subject_id,
        value=obs.value,
        value_type=obs.value_type,
        source_type=obs.source_type,
        observed_at=obs.observed_at,
        payment_event_id=obs.payment_event_id,
        webhook_event_id=obs.webhook_event_id,
        extraction_version=obs.extraction_version,
    )


def _rel_to_edge(rel: EvidenceRelationship) -> GraphEdgeSchema:
    return GraphEdgeSchema(
        edge_id=rel.internal_id,
        source_evidence_id=rel.source_evidence_id,
        target_evidence_id=rel.target_evidence_id,
        relationship_type=rel.relationship_type,
        relationship_source=rel.relationship_source,
        rule_version=rel.rule_version,
        provenance_metadata=rel.provenance_metadata,
        created_at=rel.created_at,
    )
