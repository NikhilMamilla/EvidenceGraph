"""
Phase 7 Evidence Structure, Claim, Group, Corroboration and Snapshot Models.
"""
from datetime import datetime, timezone
from sqlalchemy import (
    Column,
    BigInteger,
    String,
    DateTime,
    ForeignKey,
    UniqueConstraint,
    Index,
    Integer,
    Float,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from app.db.session import Base


class Claim(Base):
    """
    Canonical proposition about an entity (e.g. PAYMENT_STATUS = captured).
    An abstract claim supported by one or more EvidenceObservation instances.
    """
    __tablename__ = "claims"

    internal_id = Column(Integer, primary_key=True, autoincrement=True)
    subject_type = Column(String(64), nullable=False)
    subject_id = Column(String(128), nullable=False)
    claim_type = Column(String(64), nullable=False)
    claim_key = Column(String(128), nullable=False)
    canonical_value = Column(String(512), nullable=False)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    links = relationship("EvidenceClaimLink", back_populates="claim", cascade="all, delete-orphan")
    corroboration = relationship("EvidenceCorroboration", back_populates="claim", uselist=False)

    __table_args__ = (
        UniqueConstraint(
            "subject_type",
            "subject_id",
            "claim_type",
            "claim_key",
            "canonical_value",
            name="uq_claim_proposition",
        ),
        Index("ix_claims_subject", "subject_type", "subject_id"),
        Index("ix_claims_type", "claim_type"),
    )


class EvidenceClaimLink(Base):
    """
    Associates an immutable EvidenceObservation with a canonical Claim it supports.
    """
    __tablename__ = "evidence_claim_links"

    internal_id = Column(Integer, primary_key=True, autoincrement=True)
    claim_id = Column(BigInteger, ForeignKey("claims.internal_id", ondelete="CASCADE"), nullable=False)
    evidence_id = Column(BigInteger, ForeignKey("evidence_observations.internal_id", ondelete="CASCADE"), nullable=False)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    claim = relationship("Claim", back_populates="links")
    evidence = relationship("EvidenceObservation")

    __table_args__ = (
        UniqueConstraint("claim_id", "evidence_id", name="uq_evidence_claim_link"),
        Index("ix_evidence_claim_links_claim_id", "claim_id"),
        Index("ix_evidence_claim_links_evidence_id", "evidence_id"),
    )


class EvidenceGroup(Base):
    """
    Represents a cluster of observations sharing a structural origin context
    (e.g., all observations extracted from the exact same webhook delivery or provider event).
    """
    __tablename__ = "evidence_groups"

    internal_id = Column(Integer, primary_key=True, autoincrement=True)
    payment_id = Column(String(128), nullable=False)
    group_type = Column(String(64), nullable=False)
    grouping_key = Column(String(128), nullable=False)
    rule_version = Column(String(32), nullable=False, default="1.0")
    metadata_ = Column("metadata", JSONB, nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    members = relationship("EvidenceGroupMember", back_populates="group", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("payment_id", "group_type", "grouping_key", name="uq_evidence_group_key"),
        Index("ix_evidence_groups_payment_id", "payment_id"),
        Index("ix_evidence_groups_type", "group_type"),
    )


class EvidenceGroupMember(Base):
    """
    Membership association between an EvidenceGroup and an EvidenceObservation.
    """
    __tablename__ = "evidence_group_members"

    internal_id = Column(Integer, primary_key=True, autoincrement=True)
    group_id = Column(BigInteger, ForeignKey("evidence_groups.internal_id", ondelete="CASCADE"), nullable=False)
    evidence_id = Column(BigInteger, ForeignKey("evidence_observations.internal_id", ondelete="CASCADE"), nullable=False)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    group = relationship("EvidenceGroup", back_populates="members")
    evidence = relationship("EvidenceObservation")

    __table_args__ = (
        UniqueConstraint("group_id", "evidence_id", name="uq_evidence_group_member"),
        Index("ix_evidence_group_members_group_id", "group_id"),
        Index("ix_evidence_group_members_evidence_id", "evidence_id"),
    )


class EvidenceCorroboration(Base):
    """
    Captures corroboration analysis for a canonical claim supported across evidence observations.
    """
    __tablename__ = "evidence_corroborations"

    internal_id = Column(Integer, primary_key=True, autoincrement=True)
    claim_id = Column(BigInteger, ForeignKey("claims.internal_id", ondelete="CASCADE"), nullable=False)
    payment_id = Column(String(128), nullable=False)
    corroboration_type = Column(String(64), nullable=False)
    independence_status = Column(String(64), nullable=False)
    observation_count = Column(Integer, nullable=False, default=1)
    distinct_sources_count = Column(Integer, nullable=False, default=1)
    distinct_events_count = Column(Integer, nullable=False, default=1)
    methodology_version = Column(String(32), nullable=False, default="1.0")
    details = Column(JSONB, nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    claim = relationship("Claim", back_populates="corroboration")

    __table_args__ = (
        Index("ix_evidence_corroborations_claim_id", "claim_id"),
        Index("ix_evidence_corroborations_payment_id", "payment_id"),
    )


class EvidenceStructureSnapshot(Base):
    """
    Structural snapshot measuring evidence concentration, corroboration, and grouping for a payment.
    """
    __tablename__ = "evidence_structure_snapshots"

    internal_id = Column(Integer, primary_key=True, autoincrement=True)
    payment_id = Column(String(128), nullable=False)
    evaluated_at = Column(DateTime(timezone=True), nullable=False)
    total_observations = Column(Integer, nullable=False)
    distinct_claims = Column(Integer, nullable=False)
    distinct_sources = Column(Integer, nullable=False)
    distinct_events = Column(Integer, nullable=False)
    distinct_groups = Column(Integer, nullable=False)
    largest_group_size = Column(Integer, nullable=False)
    group_hhi = Column(Float, nullable=False)
    corroborated_claim_count = Column(Integer, nullable=False, default=0)
    multi_source_claim_count = Column(Integer, nullable=False, default=0)
    methodology_version = Column(String(32), nullable=False, default="1.0")
    structural_summary = Column(JSONB, nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        Index("ix_structure_snapshots_payment_id", "payment_id"),
        Index("ix_structure_snapshots_evaluated_at", "evaluated_at"),
    )
