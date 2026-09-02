"""
Phase 21 — Payment Failure Intelligence, Funnel Analytics, Revenue Intelligence,
Real-Time Notifications, and Merchant Risk Profiling.

Addresses real-world Razorpay problems:
- Why do payments fail? Root cause analysis
- What's the payment success funnel?
- Revenue metrics and trends
- Real-time alerting for operators
- Merchant-level risk assessment
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


# ── Payment Failure Intelligence ──

class FailureCategory(BaseModel):
    """A categorized failure type with count and explanation."""
    category: str  # INSUFFICIENT_FUNDS, AUTH_DECLINED, TIMEOUT, etc.
    display_name: str
    count: int
    percentage: float
    severity: str  # LOW, MEDIUM, HIGH
    explanation: str
    recommendation: str


class PaymentFailureAnalysis(BaseModel):
    """Root cause analysis for payment failures."""
    payment_id: str
    status: str
    failure_reason: Optional[str] = None
    failure_category: Optional[str] = None
    failure_timestamp: Optional[datetime] = None
    time_to_failure_seconds: Optional[float] = None
    evidence_signals: list[str] = []
    root_cause: str
    recommendation: str
    methodology_version: str


class FailureDashboardResponse(BaseModel):
    """Global payment failure analytics."""
    evaluated_at: datetime
    total_payments: int
    total_captured: int
    total_failed: int
    total_pending: int
    success_rate: float
    failure_rate: float
    failure_categories: list[FailureCategory]
    recent_failures: list[PaymentFailureAnalysis]
    hourly_failure_trend: list[dict[str, Any]]
    trend_window: str = "Last 24 hours"    # what span the trend actually covers
    methodology_version: str


# ── Payment Funnel Analytics ──

class FunnelStage(BaseModel):
    """A stage in the payment funnel."""
    stage_name: str
    stage_order: int
    count: int
    percentage: float
    drop_off_count: int
    drop_off_percentage: float
    avg_time_in_stage_seconds: Optional[float] = None


class PaymentFunnelResponse(BaseModel):
    """Payment funnel visualization data."""
    evaluated_at: datetime
    total_initiated: int
    stages: list[FunnelStage]
    overall_conversion_rate: float
    biggest_drop_off_stage: str
    avg_total_time_seconds: Optional[float] = None
    methodology_version: str


# ── Revenue Intelligence ──

class RevenueMetric(BaseModel):
    """A single revenue metric."""
    label: str
    value: float
    unit: str  # INR, PERCENT, COUNT
    change_pct: Optional[float] = None
    trend: str  # UP, DOWN, STABLE


class RevenueTimeSeries(BaseModel):
    """Revenue data point over time."""
    timestamp: datetime
    label: str = ""          # human tick label for the bucket ("14h" / "Aug 24")
    gmv: float
    success_count: int
    failure_count: int
    success_rate: float


class RevenueIntelligenceResponse(BaseModel):
    """Revenue intelligence dashboard."""
    evaluated_at: datetime
    metrics: list[RevenueMetric]
    time_series: list[RevenueTimeSeries]
    series_window: str = "Last 24 hours"   # what span the series actually covers
    total_gmv: float
    avg_transaction_value: float
    success_rate: float
    peak_hour: Optional[str] = None
    methodology_version: str


# ── Real-Time Notifications ──

class NotificationItem(BaseModel):
    """A single notification/alert."""
    notification_id: str
    category: str  # FRAUD, FAILURE, SYSTEM, ANOMALY, MILESTONE
    severity: str  # INFO, WARNING, CRITICAL
    title: str
    description: str
    payment_id: Optional[str] = None
    created_at: datetime
    read: bool = False
    metadata: dict[str, Any] = {}


class NotificationCenterResponse(BaseModel):
    """Notification center with alerts."""
    notifications: list[NotificationItem]
    total_count: int
    unread_count: int
    critical_count: int
    evaluated_at: datetime


# ── Merchant Risk Profiling ──

class MerchantRiskProfile(BaseModel):
    """Risk profile for a payment pattern/entity."""
    entity_id: str
    entity_type: str  # PAYMENT_METHOD, SOURCE, CURRENCY
    risk_score: float = Field(ge=0.0, le=100.0)
    risk_level: str
    total_transactions: int
    success_rate: float
    avg_amount: float
    failure_rate: float
    conflict_rate: float
    fraud_signal_count: int
    key_risks: list[str]
    recommendations: list[str]
    evaluated_at: datetime
    methodology_version: str


class MerchantRiskDashboardResponse(BaseModel):
    """Dashboard showing risk profiles across entities."""
    evaluated_at: datetime
    profiles: list[MerchantRiskProfile]
    total_entities: int
    high_risk_count: int
    methodology_version: str
