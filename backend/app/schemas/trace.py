"""
Phase 10 — Decision Trace Pydantic response schemas.

Three exposure tiers:
  - TraceSummaryItem / TraceListResponse   → normal authorization
    (identity, lifecycle, result, hash presence; NO full audit content)
  - TraceDetailResponse                    → admin authorization
    (complete canonical payload + audit event timeline)
  - TraceVerificationResponse / TraceReplayResponse → admin authorization

No secrets, raw webhook payloads, or credentials can appear in these
responses: the canonical payload only ever contains safe derived references.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class TraceSummaryItem(BaseModel):
    """List-view representation of a decision trace (no full content)."""

    trace_id: str
    trace_type: str
    original_trace_id: str | None = None
    payment_id: str
    evaluated_at: datetime
    methodology_version: str
    methodology_snapshot_hash: str | None = None
    status: str = Field(
        description="EVALUATION_STARTED, COMPLETED, or FAILED."
    )
    overall_status: str | None = Field(
        default=None,
        description="Final integrity classification (COMPLETED traces only).",
    )
    failure_stage: str | None = None
    failure_category: str | None = None
    trace_hash: str | None = Field(
        default=None,
        description="SHA-256 hex digest of the canonical payload (finalized traces).",
    )
    hash_algorithm: str | None = None
    canonicalization_version: str | None = None
    previous_trace_id: str | None = None
    previous_trace_hash: str | None = None
    integrity_snapshot_internal_id: int | None = None
    trigger: str | None = None
    created_at: datetime
    finalized_at: datetime | None = None

    model_config = {"from_attributes": True}

    @classmethod
    def from_trace(cls, trace) -> "TraceSummaryItem":
        return cls(
            trace_id=trace.trace_id,
            trace_type=trace.trace_type,
            original_trace_id=trace.original_trace_id,
            payment_id=trace.payment_id,
            evaluated_at=trace.evaluated_at,
            methodology_version=trace.methodology_version,
            methodology_snapshot_hash=trace.methodology_snapshot_hash,
            status=trace.status,
            overall_status=trace.overall_status,
            failure_stage=trace.failure_stage,
            failure_category=trace.failure_category,
            trace_hash=trace.trace_hash,
            hash_algorithm=trace.hash_algorithm,
            canonicalization_version=trace.canonicalization_version,
            previous_trace_id=trace.previous_trace_id,
            previous_trace_hash=trace.previous_trace_hash,
            integrity_snapshot_internal_id=trace.integrity_snapshot_internal_id,
            trigger=trace.trigger,
            created_at=trace.created_at,
            finalized_at=trace.finalized_at,
        )


class AuditEventItem(BaseModel):
    """One ordered audit event from a trace's lifecycle."""

    event_id: str
    trace_id: str
    sequence_number: int = Field(description="Explicit logical execution order.")
    event_type: str
    occurred_at: datetime
    actor_type: str
    metadata: dict[str, Any] | None = Field(default=None)

    model_config = {"from_attributes": True}

    @classmethod
    def from_event(cls, event) -> "AuditEventItem":
        return cls(
            event_id=event.event_id,
            trace_id=event.trace_id,
            sequence_number=event.sequence_number,
            event_type=event.event_type,
            occurred_at=event.occurred_at,
            actor_type=event.actor_type,
            metadata=event.event_metadata,
        )


class TraceDetailResponse(BaseModel):
    """Complete decision trace: envelope + canonical payload + event timeline."""

    # Envelope
    trace_id: str
    trace_type: str
    original_trace_id: str | None = None
    payment_id: str
    evaluated_at: datetime
    methodology_version: str
    methodology_snapshot_hash: str | None = None
    status: str
    overall_status: str | None = None
    failure_stage: str | None = None
    failure_category: str | None = None
    failure_detail: str | None = None

    # Cryptography
    trace_hash: str | None = None
    hash_algorithm: str | None = None
    canonicalization_version: str | None = None
    previous_trace_id: str | None = None
    previous_trace_hash: str | None = None

    # Content
    canonical_payload: dict[str, Any] | None = Field(
        description=(
            "The exact canonical auditable content covered by trace_hash: "
            "hash_domain, schema, envelope, and content sections."
        )
    )

    # Lineage references for drill-down
    integrity_snapshot_internal_id: int | None = None

    # Timeline
    events: list[AuditEventItem] = Field(default_factory=list)

    created_at: datetime
    finalized_at: datetime | None = None

    @classmethod
    def from_trace(cls, trace, events: list) -> "TraceDetailResponse":
        return cls(
            trace_id=trace.trace_id,
            trace_type=trace.trace_type,
            original_trace_id=trace.original_trace_id,
            payment_id=trace.payment_id,
            evaluated_at=trace.evaluated_at,
            methodology_version=trace.methodology_version,
            methodology_snapshot_hash=trace.methodology_snapshot_hash,
            status=trace.status,
            overall_status=trace.overall_status,
            failure_stage=trace.failure_stage,
            failure_category=trace.failure_category,
            failure_detail=trace.failure_detail,
            trace_hash=trace.trace_hash,
            hash_algorithm=trace.hash_algorithm,
            canonicalization_version=trace.canonicalization_version,
            previous_trace_id=trace.previous_trace_id,
            previous_trace_hash=trace.previous_trace_hash,
            canonical_payload=trace.canonical_payload,
            integrity_snapshot_internal_id=trace.integrity_snapshot_internal_id,
            events=[AuditEventItem.from_event(e) for e in events],
            created_at=trace.created_at,
            finalized_at=trace.finalized_at,
        )


class TraceListResponse(BaseModel):
    """Historical decision traces for one payment."""

    payment_id: str
    traces: list[TraceSummaryItem]
    total: int


class TraceVerificationResponse(BaseModel):
    """Result of cryptographic verification of a single trace."""

    trace_id: str
    status: str = Field(description="VALID, INVALID, VERIFICATION_UNAVAILABLE, NOT_FOUND.")
    trace_status: str | None = Field(
        default=None, description="Lifecycle state of the verified trace."
    )
    hash_algorithm: str | None = None
    canonicalization_version: str | None = None
    message: str
    reason: str | None = None


class TraceChainVerificationResponse(BaseModel):
    """Result of per-payment hash-chain verification."""

    payment_id: str
    status: str = Field(
        description="CHAIN_VALID, CHAIN_INVALID, CHAIN_START, or NO_TRACES."
    )
    verified_count: int
    chain_start_trace_id: str | None = None
    problems: list[dict[str, Any]] = Field(default_factory=list)
    message: str


class TraceReplayResponse(BaseModel):
    """Result of replaying a decision trace."""

    original_trace_id: str
    original_payment_id: str
    evaluated_at: datetime
    methodology_version: str
    replay_trace_id: str
    original_result: str | None
    replay_result: str | None
    comparison_result: str = Field(description="MATCH or MISMATCH.")
    first_difference: dict[str, Any] | None = None
    differences: list[dict[str, Any]] = Field(default_factory=list)
