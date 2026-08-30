"""
Phase 21 — Defense Claim Model.

A defense claim represents a specific factual assertion made by a merchant
in response to a payment dispute. Each claim is independently evaluated
against available evidence.

Claim types are intentionally narrow for Phase 21 (delivery disputes only).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class DefenseClaim(Base):
    """One factual claim within a defense case."""

    __tablename__ = "defense_claims"

    internal_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    claim_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    case_id: Mapped[str] = mapped_column(
        String(64), nullable=False, index=True
    )
    claim_text: Mapped[str] = mapped_column(Text, nullable=False)
    claim_type: Mapped[str] = mapped_column(String(64), nullable=False)
    """From ClaimType constants: DELIVERY_COMPLETED, CUSTOMER_RECEIVED_GOODS, etc."""
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:
        return f"<DefenseClaim claim_id={self.claim_id} type={self.claim_type}>"
