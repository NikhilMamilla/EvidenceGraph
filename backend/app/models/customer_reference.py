"""
SQLAlchemy model — CustomerReference.

Canonical representation of a Customer reference from Razorpay.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class CustomerReference(Base):
    __tablename__ = "customer_references"

    internal_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    razorpay_customer_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:
        return f"<CustomerReference customer_id={self.razorpay_customer_id}>"
