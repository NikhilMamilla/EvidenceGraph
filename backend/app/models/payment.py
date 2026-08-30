"""
SQLAlchemy model — Payment.

Canonical representation of a Payment.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from sqlalchemy import func

class Payment(Base):
    __tablename__ = "payments"

    internal_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    razorpay_payment_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    order_id: Mapped[int | None] = mapped_column(ForeignKey("orders.internal_id"), nullable=True, index=True)
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customer_references.internal_id"), nullable=True, index=True)
    
    amount_minor: Mapped[int | None] = mapped_column(Integer, nullable=True)
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="unknown")
    payment_method_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    payment_method_details: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    
    captured: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    
    first_observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    last_observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:
        return (
            f"<Payment payment_id={self.razorpay_payment_id} "
            f"status={self.status}>"
        )
