"""
SQLAlchemy model — PaymentEvent.

Event history mapping for a payment.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class PaymentEvent(Base):
    __tablename__ = "payment_events"

    internal_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    payment_id: Mapped[int] = mapped_column(ForeignKey("payments.internal_id"), nullable=False, index=True)
    webhook_event_id: Mapped[int] = mapped_column(ForeignKey("webhook_events.id"), nullable=False, index=True, unique=True)
    
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    event_timestamp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:
        return f"<PaymentEvent type={self.event_type} payment_id={self.payment_id}>"
