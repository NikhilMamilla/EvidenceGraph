"""
Phase 13 — Pydantic schemas for Evidence Reconciliation & Evidence Identity.

Defines schemas for:
- EvidenceFact summary and detail responses
- Observation-pair reconciliation decisions
- Payment facts listing
- Observation reconciliation history
- Safe, non-sensitive observation summaries (no raw payloads)
- Backfill execution report
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict


class ObservationSummary(BaseModel):
    """
    Sanitized summary of an EvidenceObservation.
    Never exposes raw_payload, credentials, or sensitive PII.
    """
    model_config = ConfigDict(from_attributes=True)

    internal_id: int
    evidence_type: str
    subject_type: str
    subject_id: str
    value: Optional[str] = None
    value_type: str
    source_type: str
    source_reference: Optional[str] = None
    observed_at: datetime
    webhook_event_id: Optional[int] = None
    payment_event_id: Optional[int] = None
    extraction_version: str
    created_at: datetime


class EvidenceFactResponse(BaseModel):
    """
    Summary of an EvidenceFact.
    """
    model_config = ConfigDict(from_attributes=True)

    internal_id: int
    payment_id: str
    fact_type: str
    canonical_value: str
    canonical_value_hash: str
    status: str
    first_observed_at: datetime
    last_observed_at: datetime
    observation_count: int
    distinct_source_count: int
    methodology_version: str
    fact_metadata: Optional[Dict[str, Any]] = None
    created_at: datetime
    updated_at: datetime


class ReconciliationDecisionResponse(BaseModel):
    """
    Pairwise reconciliation decision between two observations.
    """
    model_config = ConfigDict(from_attributes=True)

    internal_id: int
    observation_a_id: int
    observation_b_id: int
    result: str
    rule_id: str
    rule_version: str
    explanation: str
    fact_id: Optional[int] = None
    evaluated_at: datetime
    created_at: datetime


class SourceDiversityDetail(BaseModel):
    """Breakdown of observation mechanisms supporting a fact."""
    source_types: List[str]
    distinct_source_count: int
    observation_count: int
    is_multi_source: bool


class RelatedFactSummary(BaseModel):
    """Summary of a related or preceding/succeeding fact."""
    fact_id: int
    fact_type: str
    canonical_value: str
    status: str
    relationship: str  # e.g., "PRECEDES", "SUCCEEDS", "RELATED_LIFECYCLE"


class FactConflictSummary(BaseModel):
    """Conflict associated with this fact."""
    conflict_id: int
    conflict_type: str
    severity: str
    status: str
    opposing_fact_id: Optional[int] = None
    opposing_value: Optional[str] = None


class FactClaimSummary(BaseModel):
    """Claim supported by or related to this fact."""
    claim_id: int
    claim_type: str
    canonical_value: str


class FactDetailResponse(BaseModel):
    """
    Full detail of an EvidenceFact including provenance, source diversity,
    supporting observations, related facts, conflicts, and claims.
    """
    fact: EvidenceFactResponse
    supporting_observations: List[ObservationSummary]
    source_diversity: SourceDiversityDetail
    related_facts: List[RelatedFactSummary] = []
    conflicts: List[FactConflictSummary] = []
    claims: List[FactClaimSummary] = []


class PaymentFactsResponse(BaseModel):
    """
    All canonical EvidenceFacts for a payment.
    """
    payment_id: str
    total_facts: int
    active_facts_count: int
    facts: List[EvidenceFactResponse]


class ObservationReconciliationResponse(BaseModel):
    """
    Reconciliation history and matched fact for a single observation.
    """
    observation: ObservationSummary
    matched_fact: Optional[EvidenceFactResponse] = None
    decisions: List[ReconciliationDecisionResponse] = []
    related_observations: List[ObservationSummary] = []


class BackfillReportResponse(BaseModel):
    """
    Report returned after executing historical reconciliation backfill.
    """
    payments_processed: int
    observations_processed: int
    facts_created: int
    facts_matched_existing: int
    same_fact_decisions: int
    different_fact_decisions: int
    related_fact_decisions: int
    conflicting_fact_decisions: int
    unknown_decisions: int
    failures: int = 0
