"""
Phase 21 — Evaluation Dataset Model.

Tracks dataset versions, composition, fingerprints, and freeze status.
Every evaluation run references a specific dataset version.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class EvaluationDataset(Base):
    """A versioned, immutable evaluation dataset."""

    __tablename__ = "evaluation_datasets"

    internal_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    dataset_version: Mapped[str] = mapped_column(String(32), nullable=False, unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    total_cases: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    source_counts: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    """{REAL_RAZORPAY_TEST_DATA: 5, CONTROLLED_TEST_CASE: 15}"""
    label_counts: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    """{SUPPORTED: 8, CONTRADICTED: 5, INSUFFICIENT_EVIDENCE: 4, UNKNOWN: 3}"""
    split_counts: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    """{TRAIN: 14, VALIDATION: 3, TEST: 3}"""
    dataset_fingerprint: Mapped[str | None] = mapped_column(String(128), nullable=True)
    """SHA-256 hash of dataset content for reproducibility."""
    is_frozen: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    frozen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    methodology_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    def __repr__(self) -> str:
        return (
            f"<EvaluationDataset version={self.dataset_version} "
            f"cases={self.total_cases} frozen={self.is_frozen}>"
        )
