"""
Phase 20 — Composite Evidence Integrity Risk Score.

Computes a multi-dimensional risk score from evidence quality, coverage,
reliability, consistency, and freshness signals. Provides a single 0–100
score with dimensional breakdowns for operators.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class DimensionScore(BaseModel):
    """Score for a single risk dimension."""
    dimension: str
    score: float = Field(ge=0.0, le=100.0)
    weight: float = Field(ge=0.0, le=1.0)
    status: str  # STRONG, ADEQUATE, WEAK, CRITICAL
    explanation: str
    evidence_count: int = 0


class RiskScoreResponse(BaseModel):
    """Composite evidence integrity risk score for a payment."""
    payment_id: str
    evaluated_at: datetime
    methodology_version: str

    # Composite score 0–100 (higher = more trustworthy, lower = riskier)
    composite_score: float = Field(ge=0.0, le=100.0)
    risk_level: str  # LOW_RISK, MEDIUM_RISK, HIGH_RISK, CRITICAL_RISK

    # Dimensional breakdown
    dimensions: list[DimensionScore]

    # Signal summary
    evidence_count: int
    source_count: int
    conflict_count: int
    open_conflict_count: int
    coverage_status: str
    freshness_status: str

    # Explanation for operators
    explanation_lines: list[str]
    recommendations: list[str]


class PaymentRiskSummary(BaseModel):
    """Lightweight risk summary for payment list views."""
    payment_id: str
    composite_score: float
    risk_level: str
    evidence_count: int
    conflict_count: int
    evaluated_at: Optional[datetime] = None


class RiskTrendPoint(BaseModel):
    """A single point in a payment's risk score history."""
    timestamp: datetime
    composite_score: float
    risk_level: str
    evidence_count: int
    conflict_count: int


class RiskTrendResponse(BaseModel):
    """Risk score trend over time for a payment."""
    payment_id: str
    trend: list[RiskTrendPoint]
    methodology_version: str
