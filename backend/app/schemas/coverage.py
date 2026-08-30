"""
Phase 15 — Evidence Completeness & Coverage Analysis Pydantic Schemas.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, List, Optional
from pydantic import BaseModel, Field


class EvidenceRequirementSchema(BaseModel):
    requirement_id: str = Field(..., description="Unique identifier of requirement in profile")
    requirement_type: str = Field(..., description="REQUIRED, EXPECTED, OPTIONAL, CONDITIONAL, NOT_APPLICABLE")
    evidence_type: str = Field(..., description="Evidence type expected (e.g. PAYMENT_STATUS, AMOUNT)")
    fact_type: str = Field(..., description="FactType expected from Phase 13")
    description: str = Field(..., description="Human-readable description of requirement")
    applicability_reason: str = Field(..., description="Why this requirement applies or does not apply")


class CoverageResultSchema(BaseModel):
    requirement_id: str
    requirement_type: str
    evidence_type: str
    fact_type: str
    expected_state: str
    observed_state: str
    matched_fact_id: Optional[int] = None
    matched_observation_ids: Optional[List[int]] = None
    search_scope_summary: str
    explanation: str


class MissingEvidenceDetail(BaseModel):
    requirement_id: str
    requirement_type: str
    evidence_type: str
    fact_type: str
    why_expected: str
    search_scope: str
    search_result: str
    explanation: str


class CoverageSummaryMetrics(BaseModel):
    total_applicable: int
    required_present: int
    required_missing: int
    expected_present: int
    expected_missing: int
    optional_present: int
    conflicted: int
    unknown: int
    not_applicable: int


class PaymentCoverageResponse(BaseModel):
    payment_id: str
    profile_id: str
    profile_version: str
    methodology_version: str
    overall_coverage_status: str
    evaluated_at: datetime
    metrics: CoverageSummaryMetrics
    results: List[CoverageResultSchema]
    missing_evidence: List[MissingEvidenceDetail]
    explanation: str
    evaluation_context: dict[str, Any] = Field(default_factory=dict)


class CoverageSnapshotSummary(BaseModel):
    internal_id: int
    payment_id: str
    evaluated_at: datetime
    profile_id: str
    profile_version: str
    methodology_version: str
    overall_coverage_status: str
    total_applicable_requirements: int
    required_present_count: int
    required_missing_count: int
    expected_present_count: int
    expected_missing_count: int
    conflicted_count: int


class CoverageHistoryResponse(BaseModel):
    payment_id: str
    history: List[CoverageSnapshotSummary]
    total: int


class CoverageRecomputeResponse(BaseModel):
    payment_id: str
    evaluated_at: datetime
    overall_coverage_status: str
    profile_id: str
    profile_version: str
    total_applicable: int
    snapshot_internal_id: int
    recomputed: bool
    explanation: str
