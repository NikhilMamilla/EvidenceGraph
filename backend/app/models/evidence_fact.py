"""
Phase 13 — EvidenceFact model.

An EvidenceFact is the canonical representation of a single, normalized
real-world payment event or attribute observation. It is the identity layer
that sits between raw EvidenceObservations and derived Claims.

Pipeline:
    Raw EvidenceObservation
          ↓ (Phase 13 ReconciliationEngine)
    EvidenceFact
          ↓ (Phase 7 ClaimService)
    Claim
          ↓ (Phase 9 IntegrityEngine)
    EvidenceIntegritySnapshot

Design invariants:
  - EvidenceFact is NEVER created by deleting or mutating observations.
    Both observations and the fact coexist.
  - The unique constraint on (payment_id, fact_type, canonical_value_hash)
    ensures idempotency: two reconciliation runs cannot create duplicate facts.
  - observation_count and distinct_source_count are DERIVED — they must be
    recomputed from ObservationFactLink records, not trusted blindly.
  - All timestamps are timezone-aware UTC.

FACT vs CLAIM distinction:
  - EvidenceFact = WHAT HAPPENED (e.g. "payment was captured at time T")
  - Claim         = WHAT THE SYSTEM ASSERTS (e.g. "PAYMENT_STATUS = captured")
  These are related but semantically separate. A fact may support multiple
  claims; a claim may aggregate multiple facts.
"""

from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Index, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


def _canonical_value_hash(payment_id: str, fact_type: str, canonical_value: str) -> str:
    """
    Deterministic SHA-256 hash of the fact's identity triple.
    Used as the third member of the uniqueness constraint so that
    long canonical_value strings don't exceed index limits.
    """
    raw = f"{payment_id}|{fact_type}|{canonical_value}"
    return hashlib.sha256(raw.encode()).hexdigest()


class EvidenceFact(Base):
    """
    Canonical real-world event or attribute observation for one payment.

    Identity tuple: (payment_id, fact_type, canonical_value_hash)
    At most one EvidenceFact may exist per identity triple — enforced by
    the unique constraint. Idempotent insertion is safe.

    Fact history is preserved:
    - first_observed_at: when the first supporting observation was made
    - last_observed_at: when the most recent supporting observation was made
    - observation_count: total observations linked (may include duplicates from retries)
    - distinct_source_count: distinct source_type values across linked observations

    A fact is NEVER deleted, even if all supporting observations are later
    invalidated. Instead, its status transitions to SUPERSEDED or INVALIDATED.
    """

    __tablename__ = "evidence_facts"

    # -------------------------------------------------------------------------
    # Identity
    # -------------------------------------------------------------------------
    internal_id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )

    # -------------------------------------------------------------------------
    # Subject
    # -------------------------------------------------------------------------
    payment_id: Mapped[str] = mapped_column(String(128), nullable=False)
    """Razorpay payment ID (e.g. pay_xxx). Stored as external ID, not FK,
    consistent with the EvidenceObservation design. Allows evidence queries
    without mandatory joins to the payments table."""

    # -------------------------------------------------------------------------
    # Fact classification
    # -------------------------------------------------------------------------
    fact_type: Mapped[str] = mapped_column(String(64), nullable=False)
    """From FactType constants: PAYMENT_CAPTURED, PAYMENT_AMOUNT_OBSERVED, etc."""

    canonical_value: Mapped[str] = mapped_column(String(512), nullable=False)
    """Normalized string representation of the observed fact value.
    Monetary: integer string in minor units (e.g. '49900').
    Status/enum: lowercased Razorpay status string (e.g. 'captured').
    Event occurrence: ISO-8601 timestamp string of the event.
    Association: the associated entity ID (e.g. 'order_xxx')."""

    canonical_value_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    """SHA-256 of (payment_id + '|' + fact_type + '|' + canonical_value).
    Used in the unique constraint to handle long canonical_value strings safely."""

    # -------------------------------------------------------------------------
    # Status
    # -------------------------------------------------------------------------
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default="ACTIVE"
    )
    """From FactStatus constants: ACTIVE, SUPERSEDED, INVALIDATED, UNRESOLVED."""

    # -------------------------------------------------------------------------
    # Temporal coverage
    # -------------------------------------------------------------------------
    first_observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    """When the first observation supporting this fact was made (observed_at of
    the earliest supporting EvidenceObservation)."""

    last_observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    """When the most recent observation supporting this fact was made."""

    # -------------------------------------------------------------------------
    # Aggregated observation metrics
    # -------------------------------------------------------------------------
    observation_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    """Total number of EvidenceObservation records linked to this fact.
    Includes duplicate provider deliveries. Do NOT use this as an independence count."""

    distinct_source_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    """Number of distinct source_type values across linked observations.
    A source is a distinct observation mechanism (RAZORPAY_WEBHOOK, RAZORPAY_API, etc.)."""

    # -------------------------------------------------------------------------
    # Methodology version
    # -------------------------------------------------------------------------
    methodology_version: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="1.0"
    )
    """Version of the fact creation/reconciliation methodology.
    Allows historical audit of which rules produced this fact."""

    # -------------------------------------------------------------------------
    # Optional structured metadata
    # -------------------------------------------------------------------------
    fact_metadata: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True
    )
    """Non-sensitive structured context for this fact.
    Example: {"event_type": "payment.captured", "provider": "razorpay"}
    Must never contain raw payloads, credentials, or sensitive PII."""

    # -------------------------------------------------------------------------
    # Record timestamps
    # -------------------------------------------------------------------------
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
        onupdate=func.now()
    )

    # -------------------------------------------------------------------------
    # Indexes and constraints
    # -------------------------------------------------------------------------
    __table_args__ = (
        UniqueConstraint(
            "payment_id",
            "fact_type",
            "canonical_value_hash",
            name="uq_evidence_fact_identity",
        ),
        Index("ix_evidence_facts_payment_id", "payment_id"),
        Index("ix_evidence_facts_fact_type", "fact_type"),
        Index("ix_evidence_facts_status", "status"),
        Index("ix_evidence_facts_canonical_value_hash", "canonical_value_hash"),
        Index("ix_evidence_facts_first_observed_at", "first_observed_at"),
    )

    def __repr__(self) -> str:
        return (
            f"<EvidenceFact id={self.internal_id} "
            f"type={self.fact_type} payment={self.payment_id} "
            f"status={self.status}>"
        )
