"""
SQLAlchemy model for Phase 9 — Evidence Integrity Snapshot.

One record per (payment_id, evaluated_at, methodology_version) triple.
Historical snapshots are immutable — new evidence creates a new snapshot,
never overwrites an existing one.

Design:
  - JSONB columns store structured dimension results rather than flat columns
    so the schema stays stable as dimension detail evolves without migrations.
  - No numeric overall_score in EIS-1.0 — status-based classification chosen
    over false numerical precision.
  - Unique constraint enforces idempotency and temporal reproducibility.
  - All timestamps are timezone-aware UTC.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    DateTime,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class EvidenceIntegritySnapshot(Base):
    """
    A point-in-time assessment of the evidence integrity for one payment.

    Answers: "Given the evidence available at evaluated_at, how strong,
    diverse, fresh, consistent, and well-supported is the evidence?"

    This is NOT a fraud score. It is NOT a risk decision.
    It is a measurement of evidence quality and internal consistency.

    Immutability contract:
      - Once created, a snapshot is never updated.
      - If evidence changes, a NEW snapshot is computed at the new time.
      - Old snapshots remain queryable for historical comparison.

    Idempotency contract:
      - The unique constraint on (payment_id, evaluated_at, methodology_version)
        guarantees that duplicate computation attempts do not create duplicate rows.
    """

    __tablename__ = "evidence_integrity_snapshots"

    internal_id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )

    # -------------------------------------------------------------------------
    # Identity
    # -------------------------------------------------------------------------
    payment_id: Mapped[str] = mapped_column(String(128), nullable=False)
    """The Razorpay payment ID this snapshot assesses."""

    evaluated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    """
    The explicit temporal anchor for this integrity evaluation.

    Only evidence with observed_at <= evaluated_at is included.
    Future evidence must NOT influence this snapshot.

    This is NOT the same as created_at — a snapshot can be backfilled
    with an explicit historical evaluation_time.
    """

    methodology_version: Mapped[str] = mapped_column(
        String(16), nullable=False
    )
    """
    Identifies the exact methodology used to compute this snapshot.
    Example: 'EIS-1.0'.

    Changing the methodology produces a new version string, not an
    overwrite of existing snapshots.
    """

    # -------------------------------------------------------------------------
    # Overall result
    # -------------------------------------------------------------------------
    overall_status: Mapped[str] = mapped_column(String(32), nullable=False)
    """
    The overall integrity classification from IntegrityStatus:
    VERY_STRONG, STRONG, LIMITED, WEAK, INSUFFICIENT_DATA, UNRESOLVED.

    Determined by rule-based aggregation of the five dimension results.
    """

    # -------------------------------------------------------------------------
    # Evidence scope (for context and debugging)
    # -------------------------------------------------------------------------
    evidence_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    """Number of evidence observations in scope at evaluated_at."""

    source_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    """Number of distinct source types represented in the evidence set."""

    conflict_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    """Total number of detected conflicts (all severities and statuses)."""

    open_conflict_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    """Number of OPEN conflicts with severity > INFO."""

    # -------------------------------------------------------------------------
    # Dimension results (structured JSONB)
    # -------------------------------------------------------------------------
    # Each dimension result has the shape:
    # {
    #   "status": str,               # dimension-specific status constant
    #   "reason": str,               # one-sentence explanation
    #   "inputs": dict[str, Any],    # the actual data values used
    # }

    freshness_result: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True
    )
    """Freshness dimension result. Uses Phase 6 EvidenceQualitySnapshot data."""

    source_result: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True
    )
    """Source quality dimension result. Uses Phase 6 authority and directness data."""

    independence_result: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True
    )
    """Independence dimension result. Uses Phase 7 EvidenceStructureSnapshot data."""

    corroboration_result: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True
    )
    """Corroboration dimension result. Uses Phase 7 EvidenceCorroboration data."""

    consistency_result: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True
    )
    """Consistency dimension result. Uses Phase 8 EvidenceConflict data."""

    # -------------------------------------------------------------------------
    # Explanation and limitations
    # -------------------------------------------------------------------------
    explanation_lines: Mapped[list[str] | None] = mapped_column(
        JSONB, nullable=True
    )
    """
    Deterministic, human-readable explanation of the overall status.

    Generated from actual data values — no LLM, no templates with fake specifics.
    Does NOT claim fraud or innocence. Does NOT overclaim.

    Example:
      ["Evidence was observed recently.",
       "Source is an authoritative primary provider.",
       "No contradiction was detected in the available evidence.",
       "Most observations originate from one provider event, limiting diversity."]
    """

    limitations: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    """
    Explicit limitations of this integrity assessment.

    Missing information is surfaced here, not silently assumed.

    Example:
      ["Historical reliability data unavailable (no outcome records exist).",
       "Source diversity is limited to a single provider type."]
    """

    # -------------------------------------------------------------------------
    # Audit
    # -------------------------------------------------------------------------
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    """When EvidenceGraph created this snapshot record.
    Distinct from evaluated_at."""

    __table_args__ = (
        UniqueConstraint(
            "payment_id",
            "evaluated_at",
            "methodology_version",
            name="uq_integrity_snapshot",
        ),
        Index("ix_integrity_snapshot_payment_id", "payment_id"),
        Index("ix_integrity_snapshot_evaluated_at", "evaluated_at"),
        Index("ix_integrity_snapshot_overall_status", "overall_status"),
    )

    def __repr__(self) -> str:
        return (
            f"<EvidenceIntegritySnapshot payment_id={self.payment_id} "
            f"status={self.overall_status} evaluated_at={self.evaluated_at}>"
        )
