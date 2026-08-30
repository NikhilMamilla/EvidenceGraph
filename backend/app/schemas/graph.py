"""
Pydantic schemas for the Evidence Graph — Phase 5.

A graph consists of:
  - Nodes: safe evidence observation metadata (no raw payloads, no secrets)
  - Edges: typed, versioned, provenance-bearing relationships between nodes

These schemas are read-only representations used for API responses only.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class GraphNodeSchema(BaseModel):
    """
    A single node in the evidence graph.

    Represents one EvidenceObservation as a graph node.
    Contains only safe metadata — no raw Razorpay payloads, no secrets.
    """

    evidence_id: int
    """Internal ID of the EvidenceObservation (graph node identifier)."""

    evidence_type: str
    """e.g. PAYMENT_STATUS, PAYMENT_AMOUNT — from EvidenceType constants."""

    subject_type: str
    """'payment' or 'order'."""

    subject_id: str
    """External Razorpay ID (e.g. pay_xxx)."""

    value: str | None
    """Observed value (e.g. 'captured', '49900')."""

    value_type: str
    """How to interpret the value (e.g. ENUM, INTEGER_MINOR_UNITS)."""

    source_type: str
    """Where this evidence came from (e.g. RAZORPAY_WEBHOOK)."""

    observed_at: datetime
    """When the provider says this fact occurred."""

    payment_event_id: int | None
    """FK to the PaymentEvent this observation belongs to."""

    webhook_event_id: int | None
    """FK to the originating WebhookEvent (the raw Razorpay event)."""

    extraction_version: str
    """Version of the extraction logic that produced this node."""

    class Config:
        from_attributes = True


class GraphEdgeSchema(BaseModel):
    """
    A directed edge in the evidence graph.

    Connects source_evidence_id → target_evidence_id with a typed,
    versioned, provenance-bearing relationship.
    """

    edge_id: int
    """Internal ID of the EvidenceRelationship record."""

    source_evidence_id: int
    """Graph node the edge originates from."""

    target_evidence_id: int
    """Graph node the edge points to."""

    relationship_type: str
    """e.g. SAME_SOURCE, DERIVED_FROM, INDEPENDENCE_CANDIDATE."""

    relationship_source: str
    """How the edge was produced (e.g. DETERMINISTIC_RULE)."""

    rule_version: str
    """Version of the rule that generated this edge."""

    provenance_metadata: dict[str, Any] | None
    """Structured justification: reason, method, shared_field, shared_value."""

    created_at: datetime

    class Config:
        from_attributes = True


class PaymentGraphSchema(BaseModel):
    """
    Complete evidence graph for a single payment.

    Contains all evidence nodes and all relationships between them,
    bounded to the payment's own evidence set.

    This schema does NOT include fraud scores, risk scores, independence
    scores, or any interpretation. It is a structural representation only.
    """

    payment_id: str
    """The Razorpay payment ID this graph belongs to."""

    nodes: list[GraphNodeSchema]
    """Evidence observation nodes."""

    edges: list[GraphEdgeSchema]
    """Directed relationship edges between nodes."""

    node_count: int
    edge_count: int

    class Config:
        from_attributes = True
