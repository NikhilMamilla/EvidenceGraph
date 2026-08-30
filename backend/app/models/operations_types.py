"""
Phase 19 — Operational Intelligence & Continuous Verification Types.

Defines deterministic health states, component definitions, invariant rules,
operational metrics data structures, and incident classifications.
"""

from __future__ import annotations

from enum import Enum


OPERATIONS_METHODOLOGY_VERSION = "EOI-1.0"


class HealthState(str, Enum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    UNHEALTHY = "UNHEALTHY"
    UNKNOWN = "UNKNOWN"


class ComponentType(str, Enum):
    DATABASE = "DATABASE"
    REDIS = "REDIS"
    WORKER = "WORKER"
    INGESTION = "INGESTION"
    NORMALIZATION = "NORMALIZATION"
    EVIDENCE_PROCESSING = "EVIDENCE_PROCESSING"
    RECONCILIATION = "RECONCILIATION"
    COVERAGE = "COVERAGE"
    RELIABILITY = "RELIABILITY"
    INTEGRITY = "INTEGRITY"
    REPLAY = "REPLAY"


class ProcessingFreshnessState(str, Enum):
    CURRENT = "CURRENT"
    STALE = "STALE"
    PROCESSING = "PROCESSING"
    UNKNOWN = "UNKNOWN"


class VerificationStatus(str, Enum):
    PASS = "PASS"
    WARN = "WARN"
    FAIL = "FAIL"
    UNKNOWN = "UNKNOWN"


class IncidentSeverity(str, Enum):
    CRITICAL = "CRITICAL"
    MAJOR = "MAJOR"
    WARNING = "WARNING"
    INFO = "INFO"


class IncidentCategory(str, Enum):
    INGESTION_FAILURE = "INGESTION_FAILURE"
    QUEUE_BACKLOG = "QUEUE_BACKLOG"
    WORKER_FAILURE = "WORKER_FAILURE"
    DATABASE_FAILURE = "DATABASE_FAILURE"
    ANALYSIS_STALE = "ANALYSIS_STALE"
    PROCESSING_FAILURE = "PROCESSING_FAILURE"
    RECONCILIATION_BACKLOG = "RECONCILIATION_BACKLOG"
    UNKNOWN_OPERATIONAL_STATE = "UNKNOWN_OPERATIONAL_STATE"


# ---------------------------------------------------------------------------
# Default Operational Thresholds (Configurable & Documented)
# ---------------------------------------------------------------------------
DEFAULT_QUEUE_BACKLOG_WARN_THRESHOLD = 50
DEFAULT_QUEUE_BACKLOG_CRITICAL_THRESHOLD = 200
DEFAULT_STUCK_EVENT_AGE_SECONDS_WARN = 60.0  # Events pending > 60s
DEFAULT_STUCK_EVENT_AGE_SECONDS_CRITICAL = 300.0  # Events pending > 5m
DEFAULT_LAG_SECONDS_WARN = 10.0
DEFAULT_MAX_PROCESSING_FAILURES_WINDOW = 5
