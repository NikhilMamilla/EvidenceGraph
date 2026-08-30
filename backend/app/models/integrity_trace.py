"""
Phase 10 — Evidence Integrity Decision Trace models.

Two tables:

1. evidence_integrity_traces
   ONE immutable, tamper-evident record per specific integrity evaluation
   (or replay of one). A trace answers: WHAT was evaluated, WHEN, with WHICH
   inputs, WHICH rules, and WHY the result was produced.

2. integrity_trace_events
   Ordered audit event log for a trace's lifecycle. Events carry an explicit
   per-trace sequence number so logical execution order never depends on
   database insertion order.

Immutability contract
---------------------
A trace that reaches COMPLETED or FAILED is finalized: its auditable contents
(canonical_payload), digest (trace_hash), and chain linkage are never updated
by application code. There is deliberately NO update path exposed through
services or APIs. New evaluations create NEW traces; history is never rewritten.

Hash-chain contract
-------------------
EVALUATION traces of one payment are chained:
    trace_n.previous_trace_hash == trace_{n-1}.trace_hash
The chain is an AUDIT mechanism providing tamper-EVIDENCE for ordering.
It does NOT make the database immutable, and it is not a blockchain.

Transactional finalization contract
-----------------------------------
Database CHECK constraints guarantee that no trace can claim COMPLETED/FAILED
without a canonical payload, a hash, an algorithm, and (for COMPLETED) a final
integrity result. Finalization happens inside the caller's transaction.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.trace_types import TraceStatus


class EvidenceIntegrityTrace(Base):
    """
    Tamper-evident decision trace for one Evidence Integrity evaluation.

    Identity tuple (requirement: historical reproducibility):
        (payment_id, evaluated_at, methodology_version)

    At most ONE COMPLETED EVALUATION trace may exist per identity tuple —
    enforced by a partial unique index. FAILED traces do not consume the
    identity slot, so a failed attempt can be retried without rewriting
    the failure record.
    """

    __tablename__ = "evidence_integrity_traces"

    internal_id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )

    # -------------------------------------------------------------------------
    # Identity
    # -------------------------------------------------------------------------
    trace_id: Mapped[str] = mapped_column(String(36), nullable=False)
    """Globally unique trace identifier (UUID4). Never reused."""

    trace_type: Mapped[str] = mapped_column(String(16), nullable=False)
    """TraceType: EVALUATION or REPLAY."""

    original_trace_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    """For REPLAY traces: the trace_id of the original evaluation being replayed."""

    payment_id: Mapped[str] = mapped_column(String(128), nullable=False)
    """The Razorpay payment ID this evaluation assesses."""

    evaluated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    """
    The explicit temporal anchor of the evaluation (evaluation_time).

    The trace represents the world AS KNOWN at this instant. Candidate
    evidence observed after this instant is recorded as EXCLUDED, never
    silently included or discarded.
    """

    methodology_version: Mapped[str] = mapped_column(String(16), nullable=False)
    """Phase 9 methodology version used (e.g. 'EIS-1.0')."""

    methodology_snapshot_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    """SHA-256 of the canonical methodology snapshot stored in the payload."""

    trigger: Mapped[str | None] = mapped_column(String(64), nullable=True)
    """What caused this evaluation (safe metadata only): WEBHOOK_PROCESSING,
    ON_DEMAND_API, REPLAY_REQUEST. Not part of the audit content hash."""

    # -------------------------------------------------------------------------
    # Lifecycle
    # -------------------------------------------------------------------------
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    """TraceStatus: EVALUATION_STARTED, COMPLETED, FAILED."""

    failure_stage: Mapped[str | None] = mapped_column(String(64), nullable=True)
    """For FAILED traces: pipeline stage where evaluation failed.
    Never contains stack traces."""

    failure_category: Mapped[str | None] = mapped_column(String(64), nullable=True)
    """For FAILED traces: safe exception category (exception class name)."""

    failure_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    """For FAILED traces: short human-safe failure description."""

    # -------------------------------------------------------------------------
    # Result (present only on COMPLETED traces)
    # -------------------------------------------------------------------------
    integrity_snapshot_internal_id: Mapped[int | None] = mapped_column(
        ForeignKey("evidence_integrity_snapshots.internal_id"), nullable=True
    )
    """Reference to the authoritative Phase 9 snapshot produced by this
    evaluation. The trace REFERENCES it; it never duplicates or replaces it."""

    overall_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    """Final IntegrityStatus value (mirrored from the snapshot for query convenience;
    the hashed copy lives inside the canonical payload)."""

    # -------------------------------------------------------------------------
    # Cryptographic integrity
    # -------------------------------------------------------------------------
    canonical_payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    """The exact canonical, auditable content that was hashed.
    Structure documented in docs/phase-10.md and trace_canonicalization.py."""

    trace_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    """SHA-256 hex digest of the canonical serialization of canonical_payload."""

    hash_algorithm: Mapped[str | None] = mapped_column(String(32), nullable=True)
    """Hash algorithm identifier (HASH_ALGORITHM constant, 'SHA-256')."""

    canonicalization_version: Mapped[str | None] = mapped_column(String(16), nullable=True)
    """Canonical serialization rules version used for hashing ('CG-1.0')."""

    # -------------------------------------------------------------------------
    # Hash chain (per-payment, EVALUATION traces only)
    # -------------------------------------------------------------------------
    previous_trace_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    """trace_id of the immediately preceding finalized EVALUATION trace
    for this payment (ordered by evaluated_at, internal_id)."""

    previous_trace_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    """trace_hash of that preceding trace. NULL for the first trace."""

    # -------------------------------------------------------------------------
    # Audit
    # -------------------------------------------------------------------------
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    """When EvidenceGraph created this trace record. Distinct from evaluated_at.
    Deliberately EXCLUDED from the canonical hash (mutable DB-generated metadata
    that is not part of trace identity)."""

    finalized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    """When the trace reached a terminal state (COMPLETED or FAILED)."""

    __table_args__ = (
        UniqueConstraint("trace_id", name="uq_integrity_trace_trace_id"),
        # Idempotency: at most one COMPLETED EVALUATION trace per identity tuple.
        # Implemented as partial unique indexes for PostgreSQL and SQLite.
        Index(
            "uq_integrity_trace_evaluation_identity",
            "payment_id",
            "evaluated_at",
            "methodology_version",
            unique=True,
            postgresql_where=(
                (trace_type == "EVALUATION") & (status == TraceStatus.COMPLETED)
            ),
            sqlite_where=(
                (trace_type == "EVALUATION") & (status == TraceStatus.COMPLETED)
            ),
        ),
        CheckConstraint(
            "status IN ('EVALUATION_STARTED', 'COMPLETED', 'FAILED')",
            name="ck_integrity_trace_status",
        ),
        CheckConstraint(
            "trace_type IN ('EVALUATION', 'REPLAY')", name="ck_integrity_trace_type"
        ),
        # Transactional finalization safety: a terminal trace must be complete.
        CheckConstraint(
            "(status NOT IN ('COMPLETED', 'FAILED')) OR "
            "(canonical_payload IS NOT NULL AND trace_hash IS NOT NULL "
            "AND hash_algorithm IS NOT NULL AND canonicalization_version IS NOT NULL)",
            name="ck_integrity_trace_finalized_complete",
        ),
        CheckConstraint(
            "(status <> 'COMPLETED') OR "
            "((trace_type = 'EVALUATION') AND integrity_snapshot_internal_id IS NOT NULL "
            "AND overall_status IS NOT NULL) OR "
            "((trace_type = 'REPLAY') AND overall_status IS NOT NULL)",
            name="ck_integrity_trace_completed_has_result",
        ),
        CheckConstraint(
            "(status <> 'FAILED') OR "
            "(failure_stage IS NOT NULL AND failure_category IS NOT NULL)",
            name="ck_integrity_trace_failed_has_failure_info",
        ),
        CheckConstraint(
            "(trace_type <> 'REPLAY') OR (original_trace_id IS NOT NULL)",
            name="ck_integrity_trace_replay_has_original",
        ),
        Index("ix_integrity_trace_payment_id", "payment_id"),
        Index("ix_integrity_trace_evaluated_at", "evaluated_at"),
        Index("ix_integrity_trace_status", "status"),
        Index("ix_integrity_trace_original_trace_id", "original_trace_id"),
    )

    def __repr__(self) -> str:
        return (
            f"<EvidenceIntegrityTrace trace_id={self.trace_id} "
            f"payment_id={self.payment_id} status={self.status} "
            f"hash={str(self.trace_hash)[:12]}>"
        )


class IntegrityTraceEvent(Base):
    """
    One ordered audit event within a trace lifecycle.

    Ordering: (sequence_number) is explicit and monotonic per trace.
    Database insertion order is NEVER relied upon for logical ordering.
    """

    __tablename__ = "integrity_trace_events"

    internal_id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )

    event_id: Mapped[str] = mapped_column(String(36), nullable=False)
    """Globally unique event identifier (UUID4)."""

    trace_id: Mapped[str] = mapped_column(String(36), nullable=False)
    """The trace this event belongs to (logical reference; traces are append-only)."""

    sequence_number: Mapped[int] = mapped_column(Integer, nullable=False)
    """Monotonic per-trace execution order starting at 1."""

    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    """TraceEventType constant."""

    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    """When the event occurred (wall clock). Ordering authority is sequence_number."""

    actor_type: Mapped[str] = mapped_column(String(16), nullable=False)
    """ActorType: SYSTEM or USER. No invented user identities are stored."""

    event_metadata: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    """Safe structured metadata. Never contains raw webhook payloads or secrets."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint("event_id", name="uq_integrity_trace_event_event_id"),
        UniqueConstraint(
            "trace_id", "sequence_number", name="uq_integrity_trace_event_order"
        ),
        CheckConstraint(
            "actor_type IN ('SYSTEM', 'USER')", name="ck_integrity_trace_event_actor"
        ),
        Index("ix_integrity_trace_events_trace_id", "trace_id"),
        Index("ix_integrity_trace_events_type", "event_type"),
    )

    def __repr__(self) -> str:
        return (
            f"<IntegrityTraceEvent trace_id={self.trace_id} "
            f"seq={self.sequence_number} type={self.event_type}>"
        )
