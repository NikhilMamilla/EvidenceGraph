"""
Phase 19 — Operational Intelligence & Verification Pydantic Schemas.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field

from app.models.operations_types import (
    ComponentType,
    HealthState,
    IncidentCategory,
    IncidentSeverity,
    ProcessingFreshnessState,
    VerificationStatus,
)


class ComponentHealth(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    component: ComponentType
    state: HealthState
    reason: str
    checked_at: datetime
    metrics: Dict[str, Any] = Field(default_factory=dict)
    methodology_version: Optional[str] = None


class SystemHealthResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    overall_state: HealthState
    summary: str
    checked_at: datetime
    components: Dict[str, ComponentHealth]
    methodology_version: str


class QueueMetrics(BaseModel):
    queue_name: str
    queue_depth: int
    oldest_event_age_seconds: Optional[float]
    is_backlogged: bool


class ProcessingLagMetrics(BaseModel):
    average_lag_seconds: Optional[float]
    latest_lag_seconds: Optional[float]
    max_recent_lag_seconds: Optional[float]


class IngestionOperationalMetrics(BaseModel):
    total_received: int
    total_verified: int
    total_rejected: int
    total_duplicates: int
    total_processed: int
    total_failed: int
    last_received_at: Optional[datetime]
    last_verified_at: Optional[datetime]
    last_processed_at: Optional[datetime]
    recent_events_count_1h: int


class SystemOperationalMetricsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    timestamp: datetime
    ingestion: IngestionOperationalMetrics
    queue: QueueMetrics
    lag: ProcessingLagMetrics
    stuck_events_count: int
    failed_events_count: int
    active_payments_count: int
    active_facts_count: int


class PipelineStageStatus(BaseModel):
    stage_name: str
    component: ComponentType
    state: HealthState
    freshness: ProcessingFreshnessState
    last_processed_at: Optional[datetime]
    details: Dict[str, Any] = Field(default_factory=dict)


class PipelineWatermarkResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    timestamp: datetime
    pipeline_watermark_timestamp: Optional[datetime]
    stages: List[PipelineStageStatus]
    is_pipeline_caught_up: bool
    summary: str


class DownstreamLayerStatus(BaseModel):
    layer_name: str
    status: ProcessingFreshnessState
    latest_evaluation_at: Optional[datetime]
    is_current: bool
    details: Dict[str, Any] = Field(default_factory=dict)


class PaymentOperationalStatusResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    payment_id: str
    latest_evidence_at: Optional[datetime]
    latest_canonical_at: Optional[datetime]
    overall_freshness: ProcessingFreshnessState
    is_analysis_current: bool
    pipeline_lag_seconds: Optional[float]
    layers: Dict[str, DownstreamLayerStatus]
    summary: str


class VerificationCheckResult(BaseModel):
    check_id: str
    invariant_name: str
    status: VerificationStatus
    reason: str
    checked_at: datetime
    affected_scope: str
    metrics: Dict[str, Any] = Field(default_factory=dict)


class VerificationRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    timestamp: datetime
    overall_status: VerificationStatus
    total_checks: int
    passed_count: int
    warn_count: int
    failed_count: int
    checks: List[VerificationCheckResult]


class OperationalIncident(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    incident_id: str
    category: IncidentCategory
    severity: IncidentSeverity
    component: ComponentType
    detected_at: datetime
    description: str
    evidence: Dict[str, Any] = Field(default_factory=dict)
    resolved: bool = False
    resolved_at: Optional[datetime] = None


class IncidentTimelineResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    timestamp: datetime
    active_incidents_count: int
    incidents: List[OperationalIncident]
