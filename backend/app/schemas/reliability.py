"""
Phase 16 — Evidence Reliability Calibration & Uncertainty Boundaries API Schemas.
"""

from datetime import datetime
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, ConfigDict
from app.models.reliability_types import (
    ReliabilityState,
    UncertaintyBoundaryType,
)


class DimensionAssessmentSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    dimension_name: str
    state: str
    description: str
    is_degraded: bool
    supporting_evidence: List[str] = []


class UncertaintyItemSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    boundary_type: UncertaintyBoundaryType
    topic: str
    statement: str
    scope: str


class FactReliabilityResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    fact_id: int
    payment_id: str
    fact_type: str
    canonical_value: str
    evaluated_at: datetime
    methodology_version: str
    overall_state: ReliabilityState
    dimensions: Dict[str, DimensionAssessmentSchema]
    supporting_factors: List[str]
    degradation_factors: List[str]
    ceilings_applied: List[str]
    uncertainty_profile: List[UncertaintyItemSchema]
    explanation: str


class PaymentReliabilityResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    payment_id: str
    overall_state: ReliabilityState
    evaluated_at: datetime
    methodology_version: str
    facts_assessed: int
    fact_assessments: List[FactReliabilityResponse]
    uncertainty_summary: List[UncertaintyItemSchema]
    coverage_summary: Optional[Dict[str, Any]] = None
    conflicts_summary: Optional[Dict[str, Any]] = None
    explanation: str


class ReliabilityHistoryItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    internal_id: int
    payment_id: str
    fact_id: Optional[int] = None
    evaluated_at: datetime
    overall_state: ReliabilityState
    methodology_version: str
    explanation: str


class ReliabilityHistoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    payment_id: str
    total: int
    history: List[ReliabilityHistoryItem]
