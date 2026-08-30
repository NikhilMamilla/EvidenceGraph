"""
Phase 21 — Defense Evidence Link Model.

Links a defense claim to specific EvidenceObservation records from the
existing EvidenceGraph evidence layer. This preserves lineage without
duplicating evidence content.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class DefenseEvidenceLink(Base):
    """Links a defense claim to evidence that supports or contradicts it."""

    __tablename__ = "defense_evidence_links"

    internal_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    claim_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    evidence_observation_id: Mapped[int] = mapped_column(
        Integer, nullable=False, index=True
    )
    """FK to evidence_observations.internal_id — reused, not duplicated."""
    link_type: Mapped[str] = mapped_column(String(32), nullable=False)
    """SUPPORTING, CONTRADICTING, REQUIRED_MISSING"""
    relevance_score: Mapped[float | None] = mapped_column(nullable=True)
    """0.0-1.0 relevance of this evidence to the claim. NULL = unranked."""
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:
        return (
            f"<DefenseEvidenceLink claim={self.claim_id} "
            f"evidence_id={self.evidence_observation_id} type={self.link_type}>"
        )
