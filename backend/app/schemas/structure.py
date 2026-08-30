"""
Phase 7 — Pydantic schemas for Evidence Structure, Claims, Groups, and Corroboration.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict


class ClaimResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    internal_id: int
    subject_type: str
    subject_id: str
    claim_type: str
    claim_key: str
    canonical_value: str
    created_at: datetime
    supporting_evidence_count: int = 1


class EvidenceGroupResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    internal_id: int
    payment_id: str
    group_type: str
    grouping_key: str
    rule_version: str
    metadata: Optional[Dict[str, Any]] = None
    created_at: datetime
    member_count: int = 0


class CorroborationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    internal_id: int
    claim_id: int
    payment_id: str
    corroboration_type: str
    independence_status: str
    observation_count: int
    distinct_sources_count: int
    distinct_events_count: int
    methodology_version: str
    details: Optional[Dict[str, Any]] = None
    created_at: datetime


class StructureSnapshotResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    internal_id: int
    payment_id: str
    evaluated_at: datetime
    total_observations: int
    distinct_claims: int
    distinct_sources: int
    distinct_events: int
    distinct_groups: int
    largest_group_size: int
    group_hhi: float
    corroborated_claim_count: int
    multi_source_claim_count: int
    methodology_version: str
    structural_summary: Optional[Dict[str, Any]] = None
    created_at: datetime


class PaymentStructureResponse(BaseModel):
    payment_id: str
    snapshot: Optional[StructureSnapshotResponse] = None
    claims: List[ClaimResponse] = []
    groups: List[EvidenceGroupResponse] = []
    corroborations: List[CorroborationResponse] = []


class ClaimEvidenceItem(BaseModel):
    evidence_id: int
    evidence_type: str
    subject_type: str
    subject_id: str
    value: Optional[str]
    value_type: str
    source_type: str
    observed_at: Optional[datetime]
    payment_event_id: Optional[int]
    webhook_event_id: Optional[int]


class ClaimEvidenceDetailResponse(BaseModel):
    claim: ClaimResponse
    evidence: List[ClaimEvidenceItem]
