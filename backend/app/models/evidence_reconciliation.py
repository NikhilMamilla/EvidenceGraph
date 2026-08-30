"""
Phase 13 — EvidenceReconciliation model.

A first-class, immutable record of every identity decision made between
a pair of EvidenceObservations.

Design invariants:
  - One record per (observation_a_id, observation_b_id, rule_id, rule_version).
  - observation_a_id < observation_b_id always (deterministic pair ordering)
    so that (A, B) and (B, A) map to the same row.
  - Immutable: no updated_at column. Once created, never overwritten.
  - Every result includes: rule_id, rule_version, explanation.
  - Uncertainty is first-class: UNKNOWN is a valid and important result.
  - Re-running reconciliation on existing pairs is idempotent (unique constraint).

Integration with Phase 8 (Contradiction Engine):
  CONFLICTING_FACT results feed EvidenceConflict creation through the
  ContradictionEngine bridge — no duplicate contradiction system is created.

Integration with Phase 7 (Corroboration):
  SAME_FACT results inform the CorroborationService that observations
  from the same provider event should not be counted as independent.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class EvidenceReconciliation(Base):
    """
    Immutable record of an identity decision between two EvidenceObservations.

    Identity tuple: (observation_a_id, observation_b_id, rule_id, rule_version)
    observation_a_id is always min(a, b) for deterministic ordering.

    Result taxonomy:
        SAME_FACT       — both observations represent the same real-world event.
        DIFFERENT_FACT  — observations represent distinct real-world facts.
        RELATED_FACT    — causally linked but separate events (different lifecycle).
        CONFLICTING_FACT — same attribute, incompatible values.
        UNKNOWN         — insufficient information to determine identity.
    """

    __tablename__ = "evidence_reconciliations"

    # -------------------------------------------------------------------------
    # Identity
    # -------------------------------------------------------------------------
    internal_id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )

    # -------------------------------------------------------------------------
    # The observation pair (always min_id, max_id for deterministic ordering)
    # -------------------------------------------------------------------------
    observation_a_id: Mapped[int] = mapped_column(
        ForeignKey("evidence_observations.internal_id", ondelete="CASCADE"),
        nullable=False,
    )
    """Always the observation with the smaller internal_id."""

    observation_b_id: Mapped[int] = mapped_column(
        ForeignKey("evidence_observations.internal_id", ondelete="CASCADE"),
        nullable=False,
    )
    """Always the observation with the larger internal_id."""

    # -------------------------------------------------------------------------
    # Decision
    # -------------------------------------------------------------------------
    result: Mapped[str] = mapped_column(String(32), nullable=False)
    """From ReconciliationResult: SAME_FACT, DIFFERENT_FACT, RELATED_FACT,
    CONFLICTING_FACT, UNKNOWN."""

    rule_id: Mapped[str] = mapped_column(String(64), nullable=False)
    """From ReconciliationRule — which rule produced this decision."""

    rule_version: Mapped[str] = mapped_column(String(16), nullable=False)
    """Version string of the rule set (e.g. '1.0')."""

    explanation: Mapped[str] = mapped_column(String(1024), nullable=False)
    """Human-readable, deterministic explanation of this decision.
    Never contains speculation. Uses explicit categorized language.
    Example: 'Both observations originate from the same Razorpay provider
    event (webhook_event_id=42).'"""

    # -------------------------------------------------------------------------
    # Linked fact (set when result is SAME_FACT)
    # -------------------------------------------------------------------------
    fact_id: Mapped[int | None] = mapped_column(
        ForeignKey("evidence_facts.internal_id", ondelete="SET NULL"),
        nullable=True,
    )
    """FK to the EvidenceFact that both observations were reconciled into.
    Only populated when result == SAME_FACT."""

    # -------------------------------------------------------------------------
    # Temporal
    # -------------------------------------------------------------------------
    evaluated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    """When this reconciliation decision was made."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # -------------------------------------------------------------------------
    # Relationships
    # -------------------------------------------------------------------------
    observation_a = relationship(
        "EvidenceObservation",
        foreign_keys=[observation_a_id],
        lazy="select",
    )
    observation_b = relationship(
        "EvidenceObservation",
        foreign_keys=[observation_b_id],
        lazy="select",
    )
    fact = relationship("EvidenceFact", lazy="select")

    # -------------------------------------------------------------------------
    # Constraints and indexes
    # -------------------------------------------------------------------------
    __table_args__ = (
        UniqueConstraint(
            "observation_a_id",
            "observation_b_id",
            "rule_id",
            "rule_version",
            name="uq_evidence_reconciliation_pair",
        ),
        Index("ix_evidence_reconciliations_obs_a", "observation_a_id"),
        Index("ix_evidence_reconciliations_obs_b", "observation_b_id"),
        Index("ix_evidence_reconciliations_result", "result"),
        Index("ix_evidence_reconciliations_fact_id", "fact_id"),
        Index("ix_evidence_reconciliations_evaluated_at", "evaluated_at"),
    )

    def __repr__(self) -> str:
        return (
            f"<EvidenceReconciliation "
            f"obs_a={self.observation_a_id} obs_b={self.observation_b_id} "
            f"result={self.result} rule={self.rule_id}>"
        )
