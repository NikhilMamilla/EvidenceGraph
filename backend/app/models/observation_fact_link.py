"""
Phase 13 — ObservationFactLink model.

Associates an EvidenceObservation with the EvidenceFact it supports.

Design:
  - Many-to-one: many observations may support one fact.
  - One observation supports at most one fact (one-to-one in practice,
    but the schema allows extension if a single observation is later
    determined to support multiple facts).
  - Unique constraint on (observation_id, fact_id) ensures idempotency.
  - No mutation of the originating EvidenceObservation.

Provenance invariant:
  EvidenceObservations are NEVER deleted when they are linked to a fact.
  Both the raw observation and the fact coexist, independently queryable.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class ObservationFactLink(Base):
    """
    Join record between an EvidenceObservation and the EvidenceFact it supports.

    Identity: (observation_id, fact_id) — unique.

    This link is the provenance bridge: given a fact, you can find every
    raw observation that supports it; given an observation, you can find
    which fact it has been reconciled into.
    """

    __tablename__ = "observation_fact_links"

    # -------------------------------------------------------------------------
    # Identity
    # -------------------------------------------------------------------------
    internal_id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )

    # -------------------------------------------------------------------------
    # Linked records
    # -------------------------------------------------------------------------
    observation_id: Mapped[int] = mapped_column(
        ForeignKey("evidence_observations.internal_id", ondelete="CASCADE"),
        nullable=False,
    )
    """FK to the EvidenceObservation. Cascade delete: if an observation is
    ever removed (which should not happen in normal operation), the link is
    removed but the EvidenceFact itself is preserved."""

    fact_id: Mapped[int] = mapped_column(
        ForeignKey("evidence_facts.internal_id", ondelete="CASCADE"),
        nullable=False,
    )
    """FK to the EvidenceFact this observation supports."""

    # -------------------------------------------------------------------------
    # Record creation time
    # -------------------------------------------------------------------------
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # -------------------------------------------------------------------------
    # Relationships (lazy-loaded to avoid circular imports)
    # -------------------------------------------------------------------------
    observation = relationship("EvidenceObservation", lazy="select")
    fact = relationship("EvidenceFact", lazy="select")

    # -------------------------------------------------------------------------
    # Constraints and indexes
    # -------------------------------------------------------------------------
    __table_args__ = (
        UniqueConstraint(
            "observation_id",
            "fact_id",
            name="uq_observation_fact_link",
        ),
        Index("ix_observation_fact_links_observation_id", "observation_id"),
        Index("ix_observation_fact_links_fact_id", "fact_id"),
    )

    def __repr__(self) -> str:
        return (
            f"<ObservationFactLink obs={self.observation_id} → fact={self.fact_id}>"
        )
