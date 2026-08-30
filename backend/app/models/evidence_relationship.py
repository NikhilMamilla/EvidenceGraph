"""
SQLAlchemy model — EvidenceRelationship.

A directed edge in the evidence graph. Connects two EvidenceObservation nodes
with a typed, versioned, and provenance-bearing relationship.

Design principles:
  - Immutable: no updated_at column. Relationships are never modified.
  - Provenance: every edge carries a relationship_source and rule_version.
  - Idempotent: UNIQUE constraint on (source, target, type) prevents duplicates.
  - No self-loops: CHECK constraint enforces source_evidence_id != target_evidence_id.
  - Directed: source → target. The direction carries semantic meaning
    (e.g. DERIVED_FROM: source is the derived observation, target is the basis).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import ForeignKey

from app.db.session import Base


class EvidenceRelationship(Base):
    __tablename__ = "evidence_relationships"

    # -------------------------------------------------------------------------
    # Identity
    # -------------------------------------------------------------------------
    internal_id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )

    # -------------------------------------------------------------------------
    # Graph edge — directed: source → target
    # -------------------------------------------------------------------------
    source_evidence_id: Mapped[int] = mapped_column(
        ForeignKey("evidence_observations.internal_id", ondelete="RESTRICT"),
        nullable=False,
    )
    """The originating evidence node. For DERIVED_FROM, this is the derived observation."""

    target_evidence_id: Mapped[int] = mapped_column(
        ForeignKey("evidence_observations.internal_id", ondelete="RESTRICT"),
        nullable=False,
    )
    """The target evidence node. For DERIVED_FROM, this is the basis observation."""

    # -------------------------------------------------------------------------
    # Relationship classification
    # -------------------------------------------------------------------------
    relationship_type: Mapped[str] = mapped_column(String(64), nullable=False)
    """From RelationshipType constants: SAME_EVENT, SAME_SOURCE, DERIVED_FROM, etc."""

    relationship_source: Mapped[str] = mapped_column(String(64), nullable=False)
    """From RelationshipSource constants: DETERMINISTIC_RULE, PROVIDER_REFERENCE, etc."""

    rule_version: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="1.0"
    )
    """Version of the rule logic that generated this edge.
    Allows future audit of which rule version created a historical relationship.
    Increment CURRENT_RELATIONSHIP_RULE_VERSION when rules change."""

    # -------------------------------------------------------------------------
    # Provenance metadata — explains WHY this edge was created
    # -------------------------------------------------------------------------
    provenance_metadata: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True
    )
    """Structured justification for this relationship.
    Example: {
        "reason": "Both observations share payment_event_id=7",
        "method": "deterministic_rule_v1",
        "shared_field": "payment_event_id",
        "shared_value": 7
    }
    Must not contain secrets, CVV, PINs, or raw sensitive provider payloads."""

    # -------------------------------------------------------------------------
    # Record creation time
    # -------------------------------------------------------------------------
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    """When EvidenceGraph created this relationship record.
    Relationships are immutable — no updated_at column."""

    # No updated_at — relationship records are immutable by design.

    # -------------------------------------------------------------------------
    # Constraints & indexes
    # -------------------------------------------------------------------------
    __table_args__ = (
        # Idempotency: the same logical relationship cannot be duplicated.
        # INSERT ... ON CONFLICT DO NOTHING relies on this.
        UniqueConstraint(
            "source_evidence_id",
            "target_evidence_id",
            "relationship_type",
            name="uq_evidence_relationship",
        ),
        # No self-loops: an evidence observation cannot relate to itself.
        CheckConstraint(
            "source_evidence_id != target_evidence_id",
            name="ck_evidence_relationship_no_self_loop",
        ),
        # Traversal: find all edges from a source node
        Index("ix_relationship_source_id", "source_evidence_id"),
        # Traversal: find all edges to a target node
        Index("ix_relationship_target_id", "target_evidence_id"),
        # Filter by relationship type (e.g. all SAME_SOURCE edges)
        Index("ix_relationship_type", "relationship_type"),
    )

    def __repr__(self) -> str:
        return (
            f"<EvidenceRelationship id={self.internal_id} "
            f"{self.source_evidence_id} --{self.relationship_type}--> "
            f"{self.target_evidence_id}>"
        )
