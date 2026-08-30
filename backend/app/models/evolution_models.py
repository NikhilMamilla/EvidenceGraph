"""
Phase 11 — Evidence Temporal Evolution & Change Intelligence SQLAlchemy models.

Two tables:

1. evidence_state_snapshots
   A denormalised, point-in-time summary of the evidence quality dimensions for
   one payment at one specific evaluation time and methodology version.  Each row
   mirrors the key scalar fields from the corresponding Phase 9
   EvidenceIntegritySnapshot so that the evolution service can compare successive
   snapshots without re-joining Phase 6–9 tables.

   Immutability contract
   ---------------------
   Once written, a snapshot row is NEVER updated.  If a new integrity evaluation
   is performed, a NEW EvidenceStateSnapshot is created.  History is preserved as
   an append-only log.  The unique constraint on
   (payment_id, evaluation_time, methodology_version) enforces idempotency and
   prevents duplicate snapshots for the same logical instant.

2. evidence_state_changes
   One row per observable dimension change detected between two consecutive
   EvidenceStateSnapshot records.  Each row names the dimension that changed, the
   previous and current values, the change type, and optional causality
   information derived from Phase 4–8 data.

   Change rows reference the predecessor and successor snapshot via FK so that the
   full before/after context is always recoverable.  They also carry optional
   foreign keys into evidence_observations and evidence_conflicts so that a change
   can be traced directly to a single originating record when causality is DIRECT.

Design notes
------------
- Plain string constants (from evolution_types.py) are used for all status and
  type columns.  No database ENUMs — adding new values requires no migration.
- All timestamps are timezone-aware UTC DateTimes.
- No numeric scores or probabilities are stored.  Status-based classification is
  used throughout, consistent with the Phase 9 methodology.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class EvidenceStateSnapshot(Base):
    """
    Denormalised point-in-time summary of evidence quality for one payment.

    Identity tuple:
        (payment_id, evaluation_time, methodology_version)

    The unique constraint on this triple guarantees that only one snapshot
    exists per logical evaluation instant.  Subsequent evaluations at the same
    instant and methodology version are idempotent no-ops.

    Immutability contract:
        A snapshot that has been written is NEVER updated by application code.
        Temporal comparisons always read two existing immutable rows and write a
        NEW EvidenceStateChange record — they never mutate a snapshot.
    """

    __tablename__ = "evidence_state_snapshots"

    internal_id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )

    # -------------------------------------------------------------------------
    # Identity
    # -------------------------------------------------------------------------
    payment_id: Mapped[str] = mapped_column(String(128), nullable=False)
    """The Razorpay payment ID this snapshot describes."""

    evaluation_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    """
    The explicit temporal anchor for this snapshot.

    Only evidence with observed_at <= evaluation_time is reflected.
    Future evidence MUST NOT influence this snapshot.  This is NOT the same
    as created_at — a snapshot can be backfilled with a historical time.
    """

    # -------------------------------------------------------------------------
    # Phase 9 linkage
    # -------------------------------------------------------------------------
    integrity_snapshot_id: Mapped[int] = mapped_column(
        ForeignKey("evidence_integrity_snapshots.internal_id"), nullable=False
    )
    """
    FK to the authoritative Phase 9 EvidenceIntegritySnapshot that this
    evolution snapshot summarises.  The Phase 9 row is the source of truth;
    this row is a denormalised projection created for efficient temporal diff.
    """

    # -------------------------------------------------------------------------
    # Overall result
    # -------------------------------------------------------------------------
    overall_integrity_status: Mapped[str] = mapped_column(String(32), nullable=False)
    """Overall IntegrityStatus value, mirrored from the Phase 9 snapshot."""

    # -------------------------------------------------------------------------
    # Evidence scope counters
    # -------------------------------------------------------------------------
    evidence_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    """Number of evidence observations in scope at evaluation_time."""

    source_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    """Number of distinct source types present in the evidence set."""

    claim_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    """Number of canonical claims supported by the in-scope evidence."""

    conflict_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    """Total number of detected conflicts (all severities and statuses)."""

    open_conflict_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    """Number of OPEN conflicts with severity above INFO."""

    # -------------------------------------------------------------------------
    # Dimension status fields (scalar projections from Phase 9 dimension results)
    # -------------------------------------------------------------------------
    corroboration_status: Mapped[str] = mapped_column(
        String(64), nullable=False, default="UNKNOWN"
    )
    """CorroborationStatus value from the Phase 7 / Phase 9 corroboration result."""

    independence_status: Mapped[str] = mapped_column(
        String(64), nullable=False, default="UNKNOWN"
    )
    """IndependenceStatus value from the Phase 7 / Phase 9 independence result."""

    freshness_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="UNKNOWN"
    )
    """FreshnessStatus value from the Phase 6 / Phase 9 freshness result."""

    consistency_status: Mapped[str] = mapped_column(
        String(64), nullable=False, default="NO_DETECTED_CONFLICT"
    )
    """ConsistencyStatus value from the Phase 8 / Phase 9 consistency result."""

    # -------------------------------------------------------------------------
    # Methodology
    # -------------------------------------------------------------------------
    methodology_version: Mapped[str] = mapped_column(String(16), nullable=False)
    """Phase 9 methodology version used for this evaluation (e.g. 'EIS-1.0')."""

    # -------------------------------------------------------------------------
    # Audit
    # -------------------------------------------------------------------------
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    """When EvidenceGraph created this snapshot record.  Distinct from evaluation_time."""

    __table_args__ = (
        UniqueConstraint(
            "payment_id",
            "evaluation_time",
            "methodology_version",
            name="uq_evidence_state_snapshot",
        ),
        Index("ix_evidence_state_snapshot_payment_id", "payment_id"),
        Index("ix_evidence_state_snapshot_evaluation_time", "evaluation_time"),
    )

    def __repr__(self) -> str:
        return (
            f"<EvidenceStateSnapshot payment_id={self.payment_id} "
            f"status={self.overall_integrity_status} "
            f"evaluation_time={self.evaluation_time}>"
        )


class EvidenceStateChange(Base):
    """
    One observable dimension change detected between two consecutive snapshots.

    A change record answers:
        "Between snapshot A and snapshot B for this payment, dimension D
        moved from value X to value Y, apparently caused by C."

    Causality notes
    ---------------
    - ``direct_cause`` is populated only when a specific Phase 4–8 record can
      be identified as the proximate cause.
    - ``causality`` (CausalityLevel) distinguishes DIRECT (pinpoint) from
      INFERRED (most-likely) from UNKNOWN.
    - No probabilities or scores are stored.  Causality is rule-based only.

    Immutability contract
    ---------------------
    Change rows are append-only.  Once written, they are never updated.
    The unique constraint on (previous_snapshot_id, current_snapshot_id,
    change_type, dimension) prevents duplicate change records for the same
    transition.
    """

    __tablename__ = "evidence_state_changes"

    internal_id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )

    # -------------------------------------------------------------------------
    # Identity
    # -------------------------------------------------------------------------
    change_id: Mapped[str] = mapped_column(String(36), nullable=False)
    """Globally unique change identifier (UUID4).  Never reused."""

    payment_id: Mapped[str] = mapped_column(String(128), nullable=False)
    """The Razorpay payment ID this change pertains to.  Denormalised for query efficiency."""

    # -------------------------------------------------------------------------
    # Snapshot references
    # -------------------------------------------------------------------------
    previous_snapshot_id: Mapped[int] = mapped_column(
        ForeignKey("evidence_state_snapshots.internal_id"), nullable=False
    )
    """FK to the earlier EvidenceStateSnapshot (the 'before' state)."""

    current_snapshot_id: Mapped[int] = mapped_column(
        ForeignKey("evidence_state_snapshots.internal_id"), nullable=False
    )
    """FK to the later EvidenceStateSnapshot (the 'after' state)."""

    # -------------------------------------------------------------------------
    # Change description
    # -------------------------------------------------------------------------
    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    """Wall-clock time when the change was detected by the evolution service."""

    change_type: Mapped[str] = mapped_column(String(64), nullable=False)
    """ChangeType constant (e.g. 'CORROBORATION_INCREASED', 'NEW_EVIDENCE')."""

    dimension: Mapped[str] = mapped_column(String(64), nullable=False)
    """ChangeDimension constant identifying the quality dimension that changed."""

    previous_value: Mapped[str | None] = mapped_column(String(256), nullable=True)
    """String representation of the dimension value in the previous snapshot."""

    current_value: Mapped[str | None] = mapped_column(String(256), nullable=True)
    """String representation of the dimension value in the current snapshot."""

    # -------------------------------------------------------------------------
    # Causality
    # -------------------------------------------------------------------------
    direct_cause: Mapped[str | None] = mapped_column(String(64), nullable=True)
    """DirectCause constant.  NULL when causality cannot be established."""

    causality: Mapped[str | None] = mapped_column(String(16), nullable=True)
    """CausalityLevel constant: DIRECT, INFERRED, or UNKNOWN."""

    explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    """
    Human-readable explanation of the change.

    Generated deterministically from actual data values.  No LLM, no templates
    with invented specifics.  Does NOT claim fraud or risk.
    """

    magnitude: Mapped[str | None] = mapped_column(String(16), nullable=True)
    """ChangeMagnitude constant: MINOR, MODERATE, or MAJOR.  NULL when undetermined."""

    # -------------------------------------------------------------------------
    # Optional Phase 4–8 record linkage
    # -------------------------------------------------------------------------
    linked_evidence_id: Mapped[int | None] = mapped_column(
        ForeignKey("evidence_observations.internal_id"), nullable=True
    )
    """
    FK to the specific EvidenceObservation that caused this change, when
    causality is DIRECT and traceable to a single observation.
    """

    linked_conflict_id: Mapped[int | None] = mapped_column(
        ForeignKey("evidence_conflicts.internal_id"), nullable=True
    )
    """
    FK to the specific EvidenceConflict that caused this change, when
    causality is DIRECT and traceable to a single conflict record.
    """

    # -------------------------------------------------------------------------
    # Methodology
    # -------------------------------------------------------------------------
    methodology_version: Mapped[str | None] = mapped_column(String(16), nullable=True)
    """Methodology version active when this change was detected."""

    # -------------------------------------------------------------------------
    # Audit
    # -------------------------------------------------------------------------
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    """When EvidenceGraph created this change record."""

    __table_args__ = (
        UniqueConstraint("change_id", name="uq_evidence_state_change_id"),
        UniqueConstraint(
            "previous_snapshot_id",
            "current_snapshot_id",
            "change_type",
            "dimension",
            name="uq_evidence_state_change_pair",
        ),
        Index("ix_evidence_state_change_payment_id", "payment_id"),
        Index("ix_evidence_state_change_detected_at", "detected_at"),
        Index("ix_evidence_state_change_dimension", "dimension"),
    )

    def __repr__(self) -> str:
        return (
            f"<EvidenceStateChange change_id={self.change_id} "
            f"payment_id={self.payment_id} dimension={self.dimension} "
            f"type={self.change_type}>"
        )
