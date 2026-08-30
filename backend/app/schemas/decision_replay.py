"""
Phase 18 — Decision Replay & Differential Analysis Pydantic Schemas.

Defines request/response data contracts for deterministic decision replay,
verification against historical traces, and differential change analysis.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from app.models.replay_types import (
    ChangeCategory,
    ConflictDiffType,
    CorroborationDiffType,
    FactDiffCategory,
    ReplayVerificationStatus,
    SourceDiffType,
)


class DecisionReplayRequest(BaseModel):
    """Parameters for executing a read-only historical decision replay."""
    evaluation_time: datetime = Field(
        ...,
        description="Explicit point-in-time timestamp at which to replay the analytical decision state.",
    )
    methodology_version: Optional[str] = Field(
        default="EIS-1.0",
        description="Integrity methodology version to pin during replay.",
    )
    profile_version: Optional[str] = Field(
        default="STANDARD_PAYMENT_PROFILE_V1",
        description="Evidence profile version to pin during replay.",
    )
    verify_trace: Optional[bool] = Field(
        default=True,
        description="Whether to compare the replayed state against existing historical traces.",
    )


class ReplayEvidenceStateSchema(BaseModel):
    """Summary of active evidence entities available at the evaluation timestamp."""
    observation_count: int
    fact_count: int
    claim_count: int
    active_conflicts_count: int
    distinct_sources_count: int
    sources: List[str]


class DecisionReplayResponse(BaseModel):
    """Complete analytical reconstruction of a payment's evidence decision at time T."""
    payment_id: str
    evaluation_time: datetime
    methodology_version: str
    profile_version: str
    input_fingerprint: str
    result_fingerprint: str
    reproducibility_status: str
    evidence_state: ReplayEvidenceStateSchema
    coverage_state: str
    reliability_state: str
    integrity_status: str
    coverage_metrics: Dict[str, Any]
    reliability_dimensions: Dict[str, Any]
    integrity_dimensions: Dict[str, Any]
    active_conflicts: List[Dict[str, Any]]
    verified_against_trace_id: Optional[str] = None
    verification_status: Optional[ReplayVerificationStatus] = None
    mismatch_details: Optional[Dict[str, Any]] = None


class ReplayVerificationResponse(BaseModel):
    """Result of verifying a historical decision trace against a reconstructed replay."""
    trace_id: str
    payment_id: str
    verification_status: ReplayVerificationStatus
    historical_fingerprint: str
    replay_fingerprint: str
    methodology_version: str
    profile_version: str
    differences: Dict[str, Any]
    explanation: str


class FactDiffItemSchema(BaseModel):
    """Detailed diff for an individual EvidenceFact identity."""
    fact_id: Optional[int] = None
    fact_type: str
    canonical_value: str
    category: FactDiffCategory
    observations_t1_count: int
    observations_t2_count: int
    detail: str


class SourceDiffSchema(BaseModel):
    """Differential analysis of evidence sources between T1 and T2."""
    sources_t1: List[str]
    sources_t2: List[str]
    added_sources: List[str]
    removed_sources: List[str]
    diversity_change: SourceDiffType


class CorroborationDiffSchema(BaseModel):
    """Differential analysis of corroboration and independence between T1 and T2."""
    corroboration_t1: Optional[str] = None
    corroboration_t2: Optional[str] = None
    independence_t1: Optional[str] = None
    independence_t2: Optional[str] = None
    change_type: CorroborationDiffType


class ConflictDiffItemSchema(BaseModel):
    """Differential comparison of contradictions between T1 and T2."""
    conflict_id: Optional[int] = None
    conflict_type: str
    status_t1: Optional[str] = None
    status_t2: Optional[str] = None
    change_type: ConflictDiffType
    detail: str


class CoverageDiffSchema(BaseModel):
    """Differential comparison of requirement coverage between T1 and T2."""
    status_t1: str
    status_t2: str
    required_present_t1: int
    required_present_t2: int
    required_missing_t1: int
    required_missing_t2: int
    transitions: List[Dict[str, Any]]


class ReliabilityDiffSchema(BaseModel):
    """Differential comparison of reliability dimensions between T1 and T2."""
    overall_t1: str
    overall_t2: str
    dimension_changes: Dict[str, Dict[str, Any]]
    reasons: List[str]


class IntegrityDiffSchema(BaseModel):
    """Differential comparison of integrity dimensions and final status between T1 and T2."""
    overall_t1: str
    overall_t2: str
    dimension_changes: Dict[str, Dict[str, Any]]


class EvidenceDecisionDiffResponse(BaseModel):
    """Complete differential analysis comparing decision states between T1 and T2."""
    payment_id: str
    from_time: datetime
    to_time: datetime
    diff_methodology_version: str
    methodology_t1: str
    methodology_t2: str
    methodology_changed: bool
    profile_t1: str
    profile_t2: str
    profile_changed: bool
    change_categories: List[ChangeCategory]
    fact_diffs: List[FactDiffItemSchema]
    source_diff: SourceDiffSchema
    corroboration_diff: CorroborationDiffSchema
    conflict_diffs: List[ConflictDiffItemSchema]
    coverage_diff: CoverageDiffSchema
    reliability_diff: ReliabilityDiffSchema
    integrity_diff: IntegrityDiffSchema
    input_fingerprint_t1: str
    input_fingerprint_t2: str
    result_fingerprint_t1: str
    result_fingerprint_t2: str


class DecisionChangeExplanationResponse(BaseModel):
    """Deterministic, auditable explanation of what changed between T1 and T2 and why."""
    payment_id: str
    from_time: datetime
    to_time: datetime
    what_changed: List[str]
    why_it_mattered: List[str]
    what_remains_uncertain: List[str]
    causal_summary: str
    explanation_chain: List[str]
