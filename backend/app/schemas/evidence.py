"""
Pydantic schemas for evidence observations — Phase 4.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class EvidenceSchema(BaseModel):
    """Full representation of a single evidence observation."""

    internal_id: int
    evidence_type: str
    subject_type: str
    subject_id: str
    value: str | None
    value_type: str
    source_type: str
    source_reference: str | None
    observed_at: datetime
    valid_from: datetime | None
    valid_until: datetime | None
    webhook_event_id: int | None
    payment_event_id: int | None
    extraction_method: str
    extraction_version: str
    provenance_metadata: dict[str, Any] | None
    created_at: datetime

    class Config:
        from_attributes = True


class EvidenceLineageSchema(BaseModel):
    """
    Evidence with its full provenance chain.

    Answers: Evidence → PaymentEvent → WebhookEvent → Razorpay event ID.
    """

    evidence: EvidenceSchema
    payment_event_id: int | None
    payment_event_type: str | None
    payment_event_timestamp: datetime | None
    webhook_event_id: int | None
    razorpay_event_id: str | None
    razorpay_event_type: str | None


class EvidenceTimelineEntrySchema(BaseModel):
    """
    One event-group in the evidence timeline.

    Groups all evidence observations produced by a single payment event.
    """

    payment_event_id: int
    event_type: str
    event_timestamp: datetime | None
    source_type: str
    evidence: list[EvidenceSchema]


class EvidenceTimelineSchema(BaseModel):
    """Complete evidence timeline for a payment, ordered by observed_at."""

    payment_id: str
    timeline: list[EvidenceTimelineEntrySchema]
    total_evidence_count: int
