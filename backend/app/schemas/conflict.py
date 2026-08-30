"""
Phase 8 — Pydantic schemas for Evidence Conflicts and Resolutions.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict


class ConflictResolutionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    internal_id: int
    conflict_id: int
    resolving_evidence_id: Optional[int] = None
    resolution_type: str
    explanation: str
    resolved_at: datetime
    rule_version: str
    metadata: Optional[Dict[str, Any]] = None
    created_at: datetime


class ConflictDetailResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    internal_id: int
    payment_id: str
    claim_a_id: int
    claim_b_id: int
    conflict_type: str
    severity: str
    status: str
    detected_at: datetime
    rule_version: str
    explanation: Optional[Dict[str, Any]] = None
    created_at: datetime
    resolutions: List[ConflictResolutionResponse] = []


class PaymentConsistencyResponse(BaseModel):
    payment_id: str
    is_consistent: bool
    total_conflicts: int
    open_conflicts: int
    resolved_conflicts: int
    conflicts: List[ConflictDetailResponse] = []
