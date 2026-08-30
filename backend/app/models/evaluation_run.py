"""
Phase 21 — Evaluation Run Model.

Tracks each evaluation run with its results, metrics, and fingerprints.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class EvaluationRun(Base):
    """One evaluation run against a frozen dataset version."""

    __tablename__ = "evaluation_runs"

    internal_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    dataset_version: Mapped[str] = mapped_column(String(32), nullable=False)
    methodology_version: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="RUNNING")
    """RUNNING, COMPLETED, FAILED"""
    total_cases: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    evaluated_cases: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    correct_predictions: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    confusion_matrix: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    metrics: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    """{accuracy, macro_precision, macro_recall, macro_f1, per_class: {...}}"""
    error_cases: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    results_fingerprint: Mapped[str | None] = mapped_column(String(128), nullable=True)
    dataset_fingerprint: Mapped[str | None] = mapped_column(String(128), nullable=True)
    run_metadata: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:
        return (
            f"<EvaluationRun run_id={self.run_id} "
            f"dataset={self.dataset_version} status={self.status}>"
        )
