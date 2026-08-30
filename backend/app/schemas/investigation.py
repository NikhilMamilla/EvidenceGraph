"""
Phase 20 — Investigation Command Center.

Provides search, filtering, and guided investigation workflows for
operators exploring payment evidence across the platform.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class InvestigationSearchResult(BaseModel):
    """A single search result from the investigation engine."""
    result_type: str  # PAYMENT, EVIDENCE, CONFLICT, FACT, TRACE
    entity_id: str
    title: str
    subtitle: str
    relevance_score: float = Field(ge=0.0, le=1.0)
    metadata: dict[str, Any] = {}
    payment_id: Optional[str] = None
    timestamp: Optional[datetime] = None


class InvestigationSearchResponse(BaseModel):
    """Search results from the investigation command center."""
    query: str
    results: list[InvestigationSearchResult]
    total_results: int
    search_time_ms: float
    suggestions: list[str] = []


class PaymentInvestigationProfile(BaseModel):
    """Complete investigation profile for a single payment."""
    payment_id: str
    payment_status: str
    amount_minor: Optional[int] = None
    currency: Optional[str] = None

    # Evidence summary
    total_evidence: int
    distinct_sources: int
    distinct_events: int
    evidence_types: list[str]

    # Risk summary
    risk_score: Optional[float] = None
    risk_level: Optional[str] = None

    # Conflict summary
    total_conflicts: int
    open_conflicts: int

    # Coverage summary
    coverage_status: Optional[str] = None

    # Key facts
    key_facts: list[dict[str, Any]]

    # Timeline highlights
    timeline_highlights: list[dict[str, Any]]

    # Investigation recommendations
    investigation_steps: list[str]
    anomaly_flags: list[str]

    evaluated_at: datetime
    methodology_version: str


class InvestigationTimelineEvent(BaseModel):
    """A chronological event in the investigation timeline."""
    timestamp: datetime
    event_type: str
    category: str  # EVIDENCE, CONFLICT, INTEGRITY, FRAUD, SYSTEM
    severity: str  # INFO, WARNING, ALERT
    title: str
    description: str
    entity_id: Optional[str] = None
    metadata: dict[str, Any] = {}


class InvestigationTimelineResponse(BaseModel):
    """Full investigation timeline for a payment."""
    payment_id: str
    events: list[InvestigationTimelineEvent]
    total_events: int
    time_range_start: Optional[datetime] = None
    time_range_end: Optional[datetime] = None
    methodology_version: str


class InvestigationRecommendation(BaseModel):
    """An actionable investigation recommendation."""
    recommendation_id: str
    priority: str  # LOW, MEDIUM, HIGH, URGENT
    category: str
    title: str
    description: str
    action_url: Optional[str] = None
    payment_id: Optional[str] = None
    generated_at: datetime
    methodology_version: str


class InvestigationRecommendationsResponse(BaseModel):
    """Investigation recommendations for a payment or the system."""
    recommendations: list[InvestigationRecommendation]
    total_count: int
    evaluated_at: datetime
    methodology_version: str


# ── Phase 12 Investigation Engine Schemas ──
# These schemas are required by app/api/v1/investigation.py

class InvestigationGraphNode(BaseModel):
    """A node in the investigation graph."""
    node_id: str
    node_type: str
    label: str
    entity_id: Optional[str] = None
    metadata: dict[str, Any] = {}


class InvestigationGraphEdge(BaseModel):
    """An edge in the investigation graph."""
    source_node_id: str
    target_node_id: str
    edge_type: str
    label: str = ""
    metadata: dict[str, Any] = {}


class InvestigationGraphResponse(BaseModel):
    """Full investigation graph for a payment."""
    payment_id: str
    nodes: list[InvestigationGraphNode]
    edges: list[InvestigationGraphEdge]
    node_count: int
    edge_count: int
    traversal_depth: int
    traversal_status: str
    methodology_version: str
    evaluated_at: datetime


class InvestigationPathNode(BaseModel):
    """A node in a path between two entities."""
    node_id: str
    node_type: str
    label: str


class InvestigationPathEdge(BaseModel):
    """An edge in a path between two entities."""
    source_node_id: str
    target_node_id: str
    edge_type: str


class InvestigationPathResponse(BaseModel):
    """Shortest path between two graph nodes."""
    source: str
    target: str
    path_nodes: list[InvestigationPathNode]
    path_edges: list[InvestigationPathEdge]
    path_length: int
    found: bool
    methodology_version: str
    evaluated_at: datetime


class EvidenceProvenanceStep(BaseModel):
    """A single step in the evidence provenance chain."""
    entity_type: str
    entity_id: str
    label: str
    timestamp: Optional[datetime] = None
    metadata: dict[str, Any] = {}


class EvidenceProvenanceResponse(BaseModel):
    """Full provenance chain for an evidence observation."""
    evidence_id: int
    provenance_chain: list[EvidenceProvenanceStep]
    chain_length: int
    methodology_version: str
    evaluated_at: datetime


class ClaimSupportEvidence(BaseModel):
    """An evidence observation supporting a claim."""
    evidence_id: int
    evidence_type: str
    source_type: str
    value: Optional[str] = None
    is_independent: bool
    observed_at: Optional[datetime] = None


class ClaimSupportResponse(BaseModel):
    """Supporting evidence and corroboration for a claim."""
    claim_id: int
    claim_type: str
    canonical_value: str
    supporting_evidence: list[ClaimSupportEvidence]
    total_support_count: int
    independent_support_count: int
    dependency_count: int
    methodology_version: str
    evaluated_at: datetime


class EvidenceDependency(BaseModel):
    """A dependency relationship between evidence observations."""
    source_evidence_id: int
    target_evidence_id: int
    dependency_type: str
    description: str


class EvidenceDependenciesResponse(BaseModel):
    """Dependencies for an evidence observation."""
    evidence_id: int
    direct_dependencies: list[EvidenceDependency]
    indirect_dependencies: list[EvidenceDependency]
    total_dependency_count: int
    methodology_version: str
    evaluated_at: datetime


class ConflictPathStep(BaseModel):
    """A step in a conflict contradiction path."""
    entity_type: str
    entity_id: str
    label: str
    role: str  # CLAIM_A, CLAIM_B, EVIDENCE, CONFLICT
    metadata: dict[str, Any] = {}


class ConflictPathResponse(BaseModel):
    """Conflict structure and contradiction path."""
    conflict_id: int
    conflict_type: str
    severity: str
    status: str
    path_steps: list[ConflictPathStep]
    path_length: int
    methodology_version: str
    evaluated_at: datetime


class SearchEntityResult(BaseModel):
    """A single search result entity."""
    entity_type: str
    entity_id: str
    label: str
    matched_field: str
    matched_value: str


class SearchResponse(BaseModel):
    """Search results from entity lookup."""
    query: str
    results: list[SearchEntityResult]
    total_results: int
    methodology_version: str
    evaluated_at: datetime
