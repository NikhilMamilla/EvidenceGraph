"""
Phase 21 — Evaluation Label Model.

Stores ground truth labels and predicted labels for each claim within a
defense case. Supports claim-level evaluation with full provenance.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class EvaluationLabel(Base):
    """Ground truth or predicted label for a defense claim evaluation."""

    __tablename__ = "evaluation_labels"

    internal_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    case_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    claim_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    dataset_version: Mapped[str] = mapped_column(String(32), nullable=False)
    label_type: Mapped[str] = mapped_column(String(16), nullable=False)
    """GROUND_TRUTH or PREDICTED"""
    label: Mapped[str] = mapped_column(String(32), nullable=False)
    """SUPPORTED, INSUFFICIENT_EVIDENCE, CONTRADICTED, UNKNOWN"""
    methodology_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    labeler_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    """Human annotator ID, or DETERMINISTIC_REFERENCE for automated labels."""
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    supporting_evidence_ids: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    contradicting_evidence_ids: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    missing_requirement_ids: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    label_confidence: Mapped[float | None] = mapped_column(nullable=True)
    """0.0-1.0 confidence in this label. NULL = unquantified."""
    metadata_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:
        return (
            f"<EvaluationLabel case={self.case_id} claim={self.claim_id} "
            f"label={self.label} type={self.label_type}>"
        )
