"""
SQLAlchemy model — EvidenceObservation.

A first-class, immutable record of a single observable fact associated with a
real payment/order/event, together with its provenance, timestamp, and value.

Design principles:
  - Immutable: no updated_at column. Evidence is never modified.
  - Provenance: every record carries a traceable source reference.
  - observed_at vs created_at: strictly separated.
      observed_at  = when the provider says the fact occurred.
      created_at   = when EvidenceGraph created this record.
  - Absence of evidence is NOT stored. Missing fields produce no row.
  - Monetary values stored as integer strings (INTEGER_MINOR_UNITS).
  - extraction_version identifies which logic generated this record.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import ForeignKey

from app.db.session import Base


class EvidenceObservation(Base):
    __tablename__ = "evidence_observations"

    # -------------------------------------------------------------------------
    # Identity
    # -------------------------------------------------------------------------
    internal_id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )

    # -------------------------------------------------------------------------
    # What was observed
    # -------------------------------------------------------------------------
    evidence_type: Mapped[str] = mapped_column(String(64), nullable=False)
    """e.g. PAYMENT_AMOUNT, PAYMENT_STATUS — from EvidenceType constants."""

    # -------------------------------------------------------------------------
    # Subject — which entity this observation describes
    # -------------------------------------------------------------------------
    subject_type: Mapped[str] = mapped_column(String(32), nullable=False)
    """'payment' or 'order' — from SubjectType constants."""

    subject_id: Mapped[str] = mapped_column(String(128), nullable=False)
    """External Razorpay ID (e.g. pay_xxx or order_xxx), NOT the internal PK.
    Using external IDs here avoids mandatory joins when querying evidence."""

    # -------------------------------------------------------------------------
    # Value representation
    # -------------------------------------------------------------------------
    value: Mapped[str | None] = mapped_column(Text, nullable=True)
    """String representation of the observed value.
    Monetary amounts: stored as integer string in minor units (e.g. '49900').
    Enum values: stored as the string (e.g. 'captured').
    Boolean values: stored as 'true' or 'false'."""

    value_type: Mapped[str] = mapped_column(String(32), nullable=False)
    """How to interpret value — from ValueType constants:
    INTEGER_MINOR_UNITS, STRING, ENUM, BOOLEAN."""

    # -------------------------------------------------------------------------
    # Provenance — where the evidence came from
    # -------------------------------------------------------------------------
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    """From SourceType constants: RAZORPAY_WEBHOOK, RAZORPAY_API, INTERNAL_SYSTEM."""

    source_reference: Mapped[str | None] = mapped_column(String(128), nullable=True)
    """Traceable reference to the originating source.
    For RAZORPAY_WEBHOOK: str(webhook_events.id).
    Never contains secrets or credentials."""

    # -------------------------------------------------------------------------
    # Time — observation time vs processing time
    # -------------------------------------------------------------------------
    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    """When the underlying fact/event occurred according to the provider.
    Taken from payment_event.event_timestamp if available,
    otherwise from webhook_event.received_at.
    MUST NOT be confused with created_at."""

    valid_from: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    """If this observation represents a state with a known start time."""

    valid_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    """If this observation is superseded by a later state, set to that time.
    NULL means currently valid (open-ended validity)."""

    # -------------------------------------------------------------------------
    # Lineage — FK references for evidence trace
    # -------------------------------------------------------------------------
    webhook_event_id: Mapped[int | None] = mapped_column(
        ForeignKey("webhook_events.id"), nullable=True
    )
    """FK to the WebhookEvent that produced this observation.
    Evidence → WebhookEvent → raw_payload → Razorpay original event."""

    payment_event_id: Mapped[int | None] = mapped_column(
        ForeignKey("payment_events.internal_id"), nullable=True
    )
    """FK to the PaymentEvent this observation belongs to (where applicable)."""

    # -------------------------------------------------------------------------
    # Extraction metadata
    # -------------------------------------------------------------------------
    extraction_method: Mapped[str] = mapped_column(String(64), nullable=False)
    """From ExtractionMethod constants: WEBHOOK_FIELD_EXTRACTION."""

    extraction_version: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="1.0"
    )
    """Version of the extraction logic that produced this record.
    Allows future audit of which logic generated a historical record."""

    provenance_metadata: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True
    )
    """Structured metadata about how this observation was produced.
    Example: {"provider": "razorpay", "event_type": "payment.captured",
               "extraction_version": "1.0"}
    Does NOT duplicate sensitive raw payload content."""

    # -------------------------------------------------------------------------
    # Record creation time — NOT the observation time
    # -------------------------------------------------------------------------
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    """When EvidenceGraph created this record. NOT when the fact occurred.
    Observation time is stored in observed_at."""

    # No updated_at — evidence records are immutable by design.

    # -------------------------------------------------------------------------
    # Indexes — chosen for actual query patterns
    # -------------------------------------------------------------------------
    __table_args__ = (
        # Primary query: all evidence for a subject (e.g. all evidence for pay_xxx)
        Index("ix_evidence_subject", "subject_type", "subject_id"),
        # Filter by evidence type across subjects
        Index("ix_evidence_type", "evidence_type"),
        # Filter by source
        Index("ix_evidence_source_type", "source_type"),
        Index("ix_evidence_source_reference", "source_reference"),
        # Time-based queries and ordering
        Index("ix_evidence_observed_at", "observed_at"),
        # Lineage traversal
        Index("ix_evidence_webhook_event_id", "webhook_event_id"),
        Index("ix_evidence_payment_event_id", "payment_event_id"),
    )

    def __repr__(self) -> str:
        return (
            f"<EvidenceObservation id={self.internal_id} "
            f"type={self.evidence_type} subject={self.subject_type}:{self.subject_id}>"
        )
