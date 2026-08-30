"""
Pydantic schemas for Evidence Quality — Phase 6.

Read-only response schemas for the quality measurement API.
No Evidence Integrity Score is included — deliberately.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class QualitySnapshotSchema(BaseModel):
    """
    A single point-in-time quality measurement for one evidence observation.

    Contains:
      - Freshness: age, state, policy
      - Source: type, directness, authority
      - Historical reliability: status only (no score)
    """

    snapshot_id: int
    evidence_id: int
    evaluated_at: datetime

    # Freshness
    age_seconds: float | None
    freshness_state: str
    freshness_policy_key: str
    freshness_methodology_version: str

    # Source
    source_type: str
    source_directness: str
    source_authority_level: str
    source_methodology_version: str

    # Historical reliability — status label only, no number
    historical_reliability_status: str
    reliability_sample_count: int | None
    reliability_methodology_version: str

    # Provenance
    snapshot_metadata: dict[str, Any] | None
    created_at: datetime

    class Config:
        from_attributes = True


class EvidenceQualityResponseSchema(BaseModel):
    """
    Quality information for one evidence observation.
    Returns all snapshots (history preserved) and the latest snapshot.
    """

    evidence_id: int
    evidence_type: str
    subject_id: str
    observed_at: datetime

    latest_snapshot: QualitySnapshotSchema | None
    """Most recent measurement. None if no snapshot exists yet."""

    snapshot_count: int
    """Total number of quality snapshots for this evidence."""

    class Config:
        from_attributes = True


class PaymentEvidenceQualityResponseSchema(BaseModel):
    """
    Quality information for all evidence in a payment.
    One entry per evidence observation.
    """

    payment_id: str
    evidence_quality: list[EvidenceQualityResponseSchema]
    total_evidence_count: int
    snapshot_count: int

    class Config:
        from_attributes = True
