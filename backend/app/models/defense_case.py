"""
Phase 21 — Defense Case Model.

Canonical evaluation case representing one dispute-defense scenario.
Links to existing Payment and EvidenceObservation models.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class DefenseCase(Base):
    """One dispute-defense evaluation case."""
    __tablename__ = "defense_cases"

    internal_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    case_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    dispute_category: Mapped[str] = mapped_column(String(64), nullable=False)
    dispute_reason: Mapped[str] = mapped_column(Text, nullable=False)
    case_description: Mapped[str] = mapped_column(Text, nullable=False)
    payment_reference: Mapped[str | None] = mapped_column(String(64), nullable=True)
    order_reference: Mapped[str | None] = mapped_column(String(64), nullable=True)
    dataset_version: Mapped[str] = mapped_column(String(32), nullable=False)
    case_source: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="CREATED")
    evaluation_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:
        return f"<DefenseCase case_id={self.case_id} category={self.dispute_category}>"
