"""
Phase 8 — Evidence Conflict and Resolution Models.
"""
from datetime import datetime, timezone
from sqlalchemy import (
    Column,
    Integer,
    String,
    DateTime,
    ForeignKey,
    UniqueConstraint,
    Index,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from app.db.session import Base


class EvidenceConflict(Base):
    """
    Represents an observed contradiction or temporal inconsistency between two claims.
    Immutably recorded and versioned.
    """
    __tablename__ = "evidence_conflicts"

    internal_id = Column(Integer, primary_key=True, autoincrement=True)
    payment_id = Column(String(128), nullable=False)
    claim_a_id = Column(Integer, ForeignKey("claims.internal_id", ondelete="CASCADE"), nullable=False)
    claim_b_id = Column(Integer, ForeignKey("claims.internal_id", ondelete="CASCADE"), nullable=False)
    conflict_type = Column(String(64), nullable=False)
    severity = Column(String(32), nullable=False)
    status = Column(String(32), nullable=False, default="OPEN")
    detected_at = Column(DateTime(timezone=True), nullable=False)
    rule_version = Column(String(32), nullable=False, default="1.0")
    explanation = Column(JSONB, nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    claim_a = relationship("Claim", foreign_keys=[claim_a_id])
    claim_b = relationship("Claim", foreign_keys=[claim_b_id])
    resolutions = relationship("ConflictResolution", back_populates="conflict", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint(
            "payment_id",
            "claim_a_id",
            "claim_b_id",
            "conflict_type",
            "rule_version",
            name="uq_evidence_conflict_pair",
        ),
        Index("ix_evidence_conflicts_payment_id", "payment_id"),
        Index("ix_evidence_conflicts_type", "conflict_type"),
        Index("ix_evidence_conflicts_status", "status"),
    )


class ConflictResolution(Base):
    """
    Captures how an existing contradiction was resolved by subsequent authoritative evidence.
    Preserves historical conflict observations without mutating them.
    """
    __tablename__ = "conflict_resolutions"

    internal_id = Column(Integer, primary_key=True, autoincrement=True)
    conflict_id = Column(Integer, ForeignKey("evidence_conflicts.internal_id", ondelete="CASCADE"), nullable=False)
    resolving_evidence_id = Column(Integer, ForeignKey("evidence_observations.internal_id", ondelete="SET NULL"), nullable=True)
    resolution_type = Column(String(64), nullable=False)
    explanation = Column(String(512), nullable=False)
    resolved_at = Column(DateTime(timezone=True), nullable=False)
    rule_version = Column(String(32), nullable=False, default="1.0")
    metadata_ = Column("metadata", JSONB, nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    conflict = relationship("EvidenceConflict", back_populates="resolutions")
    resolving_evidence = relationship("EvidenceObservation")

    __table_args__ = (
        Index("ix_conflict_resolutions_conflict_id", "conflict_id"),
    )
