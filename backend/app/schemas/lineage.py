"""
Phase 14 — Evidence Lineage & Causal Explanation Engine: Pydantic Schemas.

Sanitized response models for the lineage API.

Security invariants:
  - No raw webhook payloads.
  - No webhook signatures or secrets.
  - No CVV, PIN, OTP, or authentication tokens.
  - No raw provider response bodies.
  - All monetary values as integer strings in minor units only.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Building blocks
# ---------------------------------------------------------------------------

class LineageNode(BaseModel):
    """
    One node in the lineage graph — a reference to an authoritative database record.

    entity_id is the external string ID (payment_id, trace_id, etc.) or
    internal integer ID formatted as string, depending on node_type.
    """

    node_id: str = Field(..., description="Unique node identifier within this lineage response (e.g. 'OBS:42')")
    node_type: str = Field(..., description="LineageNodeType constant")
    entity_id: str = Field(..., description="The authoritative identifier of the entity (external or internal ID)")
    label: str = Field(..., description="Short human-readable label for display")
    timestamp: Optional[datetime] = Field(None, description="Primary timestamp for this node (observed_at, evaluated_at, etc.)")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Safe structured metadata — no raw payloads or secrets")


class LineageEdge(BaseModel):
    """
    Directed relationship between two lineage nodes.

    source_node_id and target_node_id reference node_id values in the nodes list.
    """

    source_node_id: str
    target_node_id: str
    edge_type: str = Field(..., description="LineageEdgeType constant")
    causal_role: str = Field(..., description="CausalRole constant")
    linkage_type: str = Field(..., description="LinkageType — FOREIGN_KEY, DERIVED_TEMPORAL, or SAME_PAYMENT")
    explanation: str = Field(..., description="One-sentence deterministic explanation of this relationship")


class LineageGap(BaseModel):
    """
    An explicit record of a missing or unestablishable lineage link.

    Gaps are a first-class feature — they document where the chain is incomplete
    rather than silently hiding the absence of data.
    """

    location: str = Field(..., description="Human-readable location in the lineage where the gap occurs")
    expected_edge_type: str = Field(..., description="The LineageEdgeType that was expected but could not be established")
    reason: str = Field(..., description="Why this link could not be established")
    detected_at: datetime = Field(..., description="When this gap was detected (evaluation time)")


class LineageSummary(BaseModel):
    """
    Concise summary of the assembled lineage — all values from real data."""

    fact_count: int = Field(0, description="Number of EvidenceFact nodes")
    observation_count: int = Field(0, description="Number of EvidenceObservation nodes")
    source_count: int = Field(0, description="Number of distinct source_type values")
    conflict_count: int = Field(0, description="Number of EvidenceConflict nodes")
    claim_count: int = Field(0, description="Number of Claim nodes")
    dimension_count: int = Field(0, description="Number of integrity dimensions with results")
    affected_dimensions: List[str] = Field(default_factory=list)
    has_integrity_trace: bool = False
    has_state_changes: bool = False


class LineageExplanation(BaseModel):
    """
    Deterministic textual explanation of the lineage.

    Generated from real record values. No LLM. No templates with invented specifics.
    """

    summary: str = Field(..., description="One-paragraph summary of the evidence chain")
    detail_lines: List[str] = Field(default_factory=list, description="One line per significant lineage step or gap")


class EvaluationContext(BaseModel):
    """Temporal and methodology context for a lineage evaluation."""

    as_of: Optional[datetime] = None
    methodology_version: str = "LIN-1.0"
    truncated: bool = False
    node_count: int = 0
    edge_count: int = 0
    gap_count: int = 0


# ---------------------------------------------------------------------------
# API Response models
# ---------------------------------------------------------------------------

class PaymentLineageResponse(BaseModel):
    """
    Complete lineage for a payment, assembled forward from provider events
    to the final integrity result.
    """

    payment_id: str
    nodes: List[LineageNode]
    edges: List[LineageEdge]
    gaps: List[LineageGap]
    completeness: str = Field(..., description="LineageCompleteness: COMPLETE, PARTIAL, or BROKEN")
    summary: LineageSummary
    explanation: LineageExplanation
    evaluation_context: EvaluationContext


class TraceLineageResponse(BaseModel):
    """
    Reverse lineage starting from an EvidenceIntegrityTrace, walking backward
    to the original provider events.
    """

    trace_id: str
    payment_id: str
    nodes: List[LineageNode]
    edges: List[LineageEdge]
    gaps: List[LineageGap]
    completeness: str
    summary: LineageSummary
    explanation: LineageExplanation
    evaluation_context: EvaluationContext


class FactLineageResponse(BaseModel):
    """
    Lineage for a single EvidenceFact — showing its supporting observations,
    provider events, associated claims, and integrity references.
    """

    fact_id: int
    payment_id: str
    nodes: List[LineageNode]
    edges: List[LineageEdge]
    gaps: List[LineageGap]
    completeness: str
    summary: LineageSummary
    explanation: LineageExplanation
    evaluation_context: EvaluationContext


class LineagePathNode(BaseModel):
    """One step in a found path between two lineage entities."""

    node: LineageNode
    edge_to_next: Optional[LineageEdge] = None


class LineagePathResponse(BaseModel):
    """
    Result of a bounded path search between two lineage entities.
    """

    found: bool
    source_type: str
    source_id: str
    target_type: str
    target_id: str
    path: List[LineageNode]
    edges: List[LineageEdge]
    depth: int
    truncated: bool
    explanation: str
