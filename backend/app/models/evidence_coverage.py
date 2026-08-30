"""
Phase 15 — Evidence Completeness & Coverage Analysis SQLAlchemy models.

Two tables:
1. evidence_coverage_snapshots:
   One immutable record per point-in-time coverage evaluation.
2. evidence_coverage_results:
   Requirement-level evaluations linked to the parent snapshot.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, List, Optional

from sqlalchemy import (
    Column,
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
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.models.coverage_types import (
    COVERAGE_METHODOLOGY_VERSION,
    PROFILE_VERSION_1,
    STANDARD_PAYMENT_PROFILE_ID,
    CoverageStatus,
)


class EvidenceCoverageSnapshot(Base):
    """
    Point-in-time snapshot of evidence completeness and coverage for a payment.
    Immutability contract: Once written, snapshots are never updated.
    """
    __tablename__ = "evidence_coverage_snapshots"

    internal_id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    payment_id: Mapped[str] = mapped_column(String(128), nullable=False)
    evaluated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    profile_id: Mapped[str] = mapped_column(
        String(64), nullable=False, default=STANDARD_PAYMENT_PROFILE_ID
    )
    profile_version: Mapped[str] = mapped_column(
        String(32), nullable=False, default=PROFILE_VERSION_1
    )
    methodology_version: Mapped[str] = mapped_column(
        String(32), nullable=False, default=COVERAGE_METHODOLOGY_VERSION
    )
    overall_coverage_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=CoverageStatus.UNKNOWN
    )

    # Metrics
    total_applicable_requirements: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    required_present_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    required_missing_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    expected_present_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    expected_missing_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    optional_present_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    conflicted_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    unknown_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    not_applicable_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    summary_explanation: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    results: Mapped[List["EvidenceCoverageResult"]] = relationship(
        "EvidenceCoverageResult",
        back_populates="snapshot",
        cascade="all, delete-orphan",
        order_by="EvidenceCoverageResult.internal_id",
    )

    __table_args__ = (
        UniqueConstraint(
            "payment_id",
            "evaluated_at",
            "profile_version",
            "methodology_version",
            name="uq_evidence_coverage_snapshot",
        ),
        Index("ix_evidence_coverage_snapshots_payment_id", "payment_id"),
        Index("ix_evidence_coverage_snapshots_evaluated_at", "evaluated_at"),
    )


class EvidenceCoverageResult(Base):
    """
    Evaluation of a single evidence requirement within a coverage snapshot.
    """
    __tablename__ = "evidence_coverage_results"

    internal_id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    snapshot_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("evidence_coverage_snapshots.internal_id", ondelete="CASCADE"),
        nullable=False,
    )
    payment_id: Mapped[str] = mapped_column(String(128), nullable=False)
    requirement_id: Mapped[str] = mapped_column(String(64), nullable=False)
    requirement_type: Mapped[str] = mapped_column(String(32), nullable=False)
    evidence_type: Mapped[str] = mapped_column(String(64), nullable=False)
    fact_type: Mapped[str] = mapped_column(String(64), nullable=False)
    expected_state: Mapped[str] = mapped_column(String(32), nullable=False)
    observed_state: Mapped[str] = mapped_column(String(32), nullable=False)

    matched_fact_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    matched_observation_ids: Mapped[list[int] | None] = mapped_column(JSONB, nullable=True)
    search_scope_summary: Mapped[str] = mapped_column(String(256), nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    snapshot: Mapped["EvidenceCoverageSnapshot"] = relationship(
        "EvidenceCoverageSnapshot", back_populates="results"
    )

    __table_args__ = (
        Index("ix_evidence_coverage_results_snapshot_id", "snapshot_id"),
        Index("ix_evidence_coverage_results_payment_id", "payment_id"),
        Index("ix_evidence_coverage_results_requirement_id", "requirement_id"),
    )
