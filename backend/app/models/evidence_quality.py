"""
SQLAlchemy models for Phase 6 — Evidence Quality Measurement.

Three models:

1. EvidenceSourceProfile
   Metadata about where evidence came from — authority, directness.
   Shared across evidence with the same source_type.

2. EvidenceQualitySnapshot
   Point-in-time measurement of an evidence observation's quality.
   Created when evidence is produced, and again when re-evaluated later.
   NEVER mutates the original evidence.

3. EvidenceEvaluation
   Infrastructure for future outcome recording.
   Currently stores NO_OUTCOME_DATA / INSUFFICIENT_SAMPLE statuses.
   Will be populated when actual payment outcomes are known.

Design principles:
  - Quality measurements are SNAPSHOTS, not mutations.
  - All measurements carry methodology_version for auditability.
  - No evidence integrity score is computed or stored here.
  - No fake outcomes are recorded.
  - All timestamps are timezone-aware UTC.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


# ---------------------------------------------------------------------------
# EvidenceSourceProfile
# ---------------------------------------------------------------------------

class EvidenceSourceProfile(Base):
    """
    Metadata describing the authority and directness of an evidence source type.

    One row per source_type — shared profile, not per-observation.
    For example, all RAZORPAY_WEBHOOK evidence shares one profile.

    This is NOT a trust score. It is structured provenance metadata.
    """

    __tablename__ = "evidence_source_profiles"

    internal_id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )

    source_type: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True
    )
    """The source type this profile describes (e.g. RAZORPAY_WEBHOOK).
    Must match SourceType constants from evidence_types.py."""

    authority_level: Mapped[str] = mapped_column(String(32), nullable=False)
    """How authoritative this source is — from AuthorityLevel constants:
    PRIMARY, SECONDARY, TERTIARY."""

    default_directness: Mapped[str] = mapped_column(String(32), nullable=False)
    """The default directness for evidence from this source — from SourceDirectness:
    DIRECT, DERIVED, INFERRED.
    Individual evidence observations may override this."""

    description: Mapped[str | None] = mapped_column(String(512), nullable=True)
    """Human-readable description of this source type's authority."""

    methodology_version: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="1.0"
    )

    profile_metadata: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True
    )
    """Additional structured metadata about this source profile."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:
        return (
            f"<EvidenceSourceProfile source_type={self.source_type} "
            f"authority={self.authority_level} directness={self.default_directness}>"
        )


# ---------------------------------------------------------------------------
# EvidenceQualitySnapshot
# ---------------------------------------------------------------------------

class EvidenceQualitySnapshot(Base):
    """
    A point-in-time measurement of evidence quality dimensions.

    Created when:
      1. Evidence is first extracted (evaluated at creation time).
      2. Evidence is re-evaluated later (e.g. to track freshness decay).

    NEVER modifies the original EvidenceObservation.
    Snapshots accumulate — multiple snapshots per evidence observation are expected.

    Does NOT contain an Evidence Integrity Score.
    The individual measurement dimensions are kept separate deliberately.
    """

    __tablename__ = "evidence_quality_snapshots"

    internal_id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )

    # -------------------------------------------------------------------------
    # Which evidence observation this snapshot measures
    # -------------------------------------------------------------------------
    evidence_id: Mapped[int] = mapped_column(
        ForeignKey("evidence_observations.internal_id", ondelete="RESTRICT"),
        nullable=False,
    )

    # -------------------------------------------------------------------------
    # When this measurement was taken
    # -------------------------------------------------------------------------
    evaluated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    """The explicit evaluation timestamp used for this measurement.
    NOT necessarily the same as created_at — snapshots can be created
    retroactively or with an explicit future/past evaluation time."""

    # -------------------------------------------------------------------------
    # Freshness dimension
    # -------------------------------------------------------------------------
    age_seconds: Mapped[float | None] = mapped_column(
        Numeric(precision=18, scale=3), nullable=True
    )
    """Age of the evidence in seconds at evaluation_time.
    Computed as: (evaluated_at - observed_at).total_seconds()
    NULL if observed_at is missing or observed_at > evaluated_at (UNKNOWN state)."""

    freshness_state: Mapped[str] = mapped_column(String(16), nullable=False)
    """From FreshnessState constants: CURRENT, AGING, STALE, UNKNOWN."""

    freshness_policy_key: Mapped[str] = mapped_column(String(64), nullable=False)
    """Which freshness policy was used (e.g. 'DEFAULT', 'PAYMENT_STATUS').
    Allows future per-type policy differentiation."""

    freshness_methodology_version: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="1.0"
    )

    # -------------------------------------------------------------------------
    # Source quality dimension
    # -------------------------------------------------------------------------
    source_type: Mapped[str] = mapped_column(String(64), nullable=False)
    """Copied from the evidence observation for query convenience."""

    source_directness: Mapped[str] = mapped_column(String(32), nullable=False)
    """From SourceDirectness: DIRECT, DERIVED, INFERRED."""

    source_authority_level: Mapped[str] = mapped_column(String(32), nullable=False)
    """From AuthorityLevel: PRIMARY, SECONDARY, TERTIARY."""

    source_methodology_version: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="1.0"
    )

    # -------------------------------------------------------------------------
    # Historical reliability dimension
    # -------------------------------------------------------------------------
    historical_reliability_status: Mapped[str] = mapped_column(
        String(32), nullable=False
    )
    """From HistoricalReliabilityStatus: NO_OUTCOME_DATA, INSUFFICIENT_SAMPLE, AVAILABLE.
    In Phase 6 this will always be NO_OUTCOME_DATA or INSUFFICIENT_SAMPLE.
    A numeric reliability score is deliberately NOT stored here."""

    reliability_sample_count: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    """How many historical outcomes were available for this evidence type.
    NULL when status is NO_OUTCOME_DATA."""

    reliability_methodology_version: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="1.0"
    )

    # -------------------------------------------------------------------------
    # Snapshot provenance
    # -------------------------------------------------------------------------
    snapshot_metadata: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True
    )
    """Additional structured context about this measurement snapshot."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    """When EvidenceGraph created this snapshot record.
    Distinct from evaluated_at — a snapshot can be created at T2 but
    report measurements as of evaluation_time=T1."""

    __table_args__ = (
        Index("ix_quality_snapshot_evidence_id", "evidence_id"),
        Index("ix_quality_snapshot_evaluated_at", "evaluated_at"),
        Index("ix_quality_snapshot_freshness_state", "freshness_state"),
    )

    def __repr__(self) -> str:
        return (
            f"<EvidenceQualitySnapshot evidence_id={self.evidence_id} "
            f"freshness={self.freshness_state} evaluated_at={self.evaluated_at}>"
        )


# ---------------------------------------------------------------------------
# EvidenceEvaluation  (outcome infrastructure — Phase 6 skeleton)
# ---------------------------------------------------------------------------

class EvidenceEvaluation(Base):
    """
    Infrastructure for future outcome recording.

    Currently stores readiness status only (NO_OUTCOME_DATA / INSUFFICIENT_SAMPLE).
    A future phase will populate actual outcomes when Razorpay chargebacks,
    disputes, or manual verifications occur.

    CRITICAL: Do NOT insert fake outcomes. If there is no real authoritative
    event confirming fraud/chargeback/success, this row must not be created
    or must carry result=NULL with a clear status.
    """

    __tablename__ = "evidence_evaluations"

    internal_id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )

    evidence_id: Mapped[int] = mapped_column(
        ForeignKey("evidence_observations.internal_id", ondelete="RESTRICT"),
        nullable=False,
    )

    evaluation_type: Mapped[str] = mapped_column(String(64), nullable=False)
    """Type of evaluation: e.g. CHARGEBACK_OUTCOME, FRAUD_CONFIRMED, PAYMENT_VERIFIED."""

    evaluation_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    """When this evaluation was conducted."""

    outcome_reference: Mapped[str | None] = mapped_column(
        String(256), nullable=True
    )
    """Reference to the authoritative event that produced this outcome
    (e.g. a Razorpay dispute ID, chargeback ID, or review ticket ID).
    NULL means no authoritative outcome reference exists."""

    result: Mapped[str | None] = mapped_column(String(64), nullable=True)
    """The evaluation result (e.g. FRAUD_CONFIRMED, LEGITIMATE, NULL if unknown).
    NULL is explicit: we do not manufacture outcomes."""

    availability_status: Mapped[str] = mapped_column(String(32), nullable=False)
    """From HistoricalReliabilityStatus: NO_OUTCOME_DATA, INSUFFICIENT_SAMPLE, AVAILABLE."""

    methodology_version: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="1.0"
    )

    evaluation_metadata: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        Index("ix_evidence_evaluation_evidence_id", "evidence_id"),
        Index("ix_evidence_evaluation_type", "evaluation_type"),
    )

    def __repr__(self) -> str:
        return (
            f"<EvidenceEvaluation id={self.internal_id} "
            f"evidence_id={self.evidence_id} status={self.availability_status}>"
        )
