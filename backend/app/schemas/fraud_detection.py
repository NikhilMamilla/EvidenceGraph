"""
Phase 20 — Fraud Pattern Detection & Alerting.

Detects suspicious patterns in payment evidence signals using deterministic
rule-based analysis. No ML models — pure signal-based pattern detection.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class FraudSignal(BaseModel):
    """A single detected fraud signal."""
    signal_id: str
    signal_type: str  # AMOUNT_ANOMALY, VELOCITY_BURST, SOURCE_CONCENTRATION, etc.
    severity: str  # LOW, MEDIUM, HIGH, CRITICAL
    confidence: float = Field(ge=0.0, le=1.0)
    payment_id: str
    detected_at: datetime
    description: str
    evidence: dict[str, Any] = {}
    recommendation: str
    methodology_version: str


class FraudAlertResponse(BaseModel):
    """Collection of fraud alerts for a payment."""
    payment_id: str
    signals: list[FraudSignal]
    overall_risk: str  # CLEAR, ELEVATED, SUSPICIOUS, HIGHLY_SUSPICIOUS
    signal_count: int
    critical_count: int
    high_count: int
    evaluated_at: datetime
    methodology_version: str


class FraudDashboardResponse(BaseModel):
    """Global fraud detection dashboard summary."""
    evaluated_at: datetime
    total_payments_analyzed: int
    total_signals: int
    signals_by_severity: dict[str, int]
    signals_by_type: dict[str, int]
    recent_signals: list[FraudSignal]
    methodology_version: str


class FraudPatternItem(BaseModel):
    """A detected fraud pattern across multiple payments."""
    pattern_id: str
    pattern_type: str
    severity: str
    affected_payment_count: int
    affected_payment_ids: list[str]
    description: str
    detected_at: datetime
    methodology_version: str


class FraudPatternsResponse(BaseModel):
    """Cross-payment fraud pattern analysis."""
    patterns: list[FraudPatternItem]
    total_patterns: int
    evaluated_at: datetime
    methodology_version: str
