"""
Phase 16 — Evidence Reliability Calibration & Uncertainty Assessment Database Models.
"""

from datetime import datetime, timezone
from sqlalchemy import (
    Column,
    Integer,
    String,
    DateTime,
    Text,
    JSON,
    UniqueConstraint,
    Index,
    func,
)
from app.db.session import Base


class EvidenceReliabilityAssessment(Base):
    """
    Immutable reliability calibration snapshot for an individual evidence fact or payment context.
    Evaluated deterministically as of a point in time.
    """
    __tablename__ = "evidence_reliability_assessments"

    internal_id = Column(Integer, primary_key=True, autoincrement=True)
    payment_id = Column(String(64), nullable=False, index=True)
    fact_id = Column(Integer, nullable=True, index=True)
    evaluated_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), index=True)
    methodology_version = Column(String(32), nullable=False, default="ERM-1.0")

    # Categorical Dimension States
    overall_state = Column(String(32), nullable=False)
    source_state = Column(String(64), nullable=False)
    provenance_state = Column(String(64), nullable=False)
    temporal_state = Column(String(64), nullable=False)
    identity_state = Column(String(64), nullable=False)
    structural_state = Column(String(64), nullable=False)
    contradiction_state = Column(String(64), nullable=False)
    dependency_state = Column(String(64), nullable=False)

    # Explainability & Uncertainty
    supporting_factors = Column(JSON, nullable=False, default=list)
    degradation_factors = Column(JSON, nullable=False, default=list)
    ceilings_applied = Column(JSON, nullable=False, default=list)
    uncertainty_profile = Column(JSON, nullable=False, default=list)
    explanation = Column(Text, nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "payment_id",
            "fact_id",
            "evaluated_at",
            "methodology_version",
            name="uq_reliability_eval_snapshot",
        ),
        Index("ix_reliability_pay_fact", "payment_id", "fact_id"),
    )
