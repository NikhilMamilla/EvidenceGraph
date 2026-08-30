"""
Evidence Historical Reliability Service — Phase 6.

Determines the historical reliability STATUS of an evidence type.

CRITICAL: This service does NOT manufacture numerical reliability scores.
In Phase 6 we have no outcome data — we haven't recorded any chargebacks,
fraud confirmations, or dispute resolutions. Therefore:

  - All evidence types currently return NO_OUTCOME_DATA or INSUFFICIENT_SAMPLE.
  - The service provides the infrastructure for future phases to plug in real
    outcome data without changing the calling API.
  - Returning INSUFFICIENT_SAMPLE(count=0) is PREFERABLE to returning 0.5
    with no empirical basis.

When Phase N eventually implements outcome recording, this service will:
  1. Query the evidence_evaluations table for outcomes matching the evidence type.
  2. Compute meaningful reliability when sample_count ≥ MIN_SAMPLE_THRESHOLD.
  3. Update the status to AVAILABLE with a computed (not assumed) value.
"""

from __future__ import annotations

from typing import NamedTuple

from sqlalchemy.orm import Session

from app.models.quality_types import (
    RELIABILITY_METHODOLOGY_VERSION,
    HistoricalReliabilityStatus,
)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Minimum number of outcomes required before reliability can be computed.
# Below this threshold → INSUFFICIENT_SAMPLE.
# This prevents drawing conclusions from 1–2 observations.
MIN_SAMPLE_THRESHOLD = 30


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------

class ReliabilityResult(NamedTuple):
    """
    Historical reliability assessment for an evidence type.

    Does NOT contain a numerical score in Phase 6.
    Status is the primary output.
    """

    evidence_id: int
    evidence_type: str
    status: str
    """From HistoricalReliabilityStatus: NO_OUTCOME_DATA, INSUFFICIENT_SAMPLE, AVAILABLE."""
    sample_count: int | None
    """How many historical outcomes were found. None if NO_OUTCOME_DATA."""
    explanation: str
    """Plain-language explanation of the status."""
    methodology_version: str


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class EvidenceReliabilityService:
    """
    Assesses the historical reliability status of an evidence observation.

    In Phase 6, always returns NO_OUTCOME_DATA or INSUFFICIENT_SAMPLE.
    Future phases will populate the evidence_evaluations table with real
    outcomes and upgrade the status to AVAILABLE.
    """

    def assess_by_fields(
        self,
        evidence_id: int,
        evidence_type: str,
        db: Session | None = None,
    ) -> ReliabilityResult:
        """
        Assess historical reliability.

        db is optional — when provided, a future implementation will query
        evidence_evaluations for real outcome data. In Phase 6, the result
        is determined without DB access.
        """
        # Phase 6: Query evidence_evaluations for this evidence type.
        # Currently this table has no rows, so the result is NO_OUTCOME_DATA.
        # When outcome recording is implemented, this block will be replaced
        # with a real query.
        sample_count = self._count_outcomes(evidence_type, db)

        if sample_count == 0:
            return ReliabilityResult(
                evidence_id=evidence_id,
                evidence_type=evidence_type,
                status=HistoricalReliabilityStatus.NO_OUTCOME_DATA,
                sample_count=None,
                explanation=(
                    f"No historical outcomes have been recorded for evidence type "
                    f"'{evidence_type}'. Reliability cannot be assessed. "
                    f"This is the honest state in Phase 6 — no outcomes have been "
                    f"linked to this evidence type yet."
                ),
                methodology_version=RELIABILITY_METHODOLOGY_VERSION,
            )

        if sample_count < MIN_SAMPLE_THRESHOLD:
            return ReliabilityResult(
                evidence_id=evidence_id,
                evidence_type=evidence_type,
                status=HistoricalReliabilityStatus.INSUFFICIENT_SAMPLE,
                sample_count=sample_count,
                explanation=(
                    f"{sample_count} outcome(s) recorded for '{evidence_type}', "
                    f"but minimum required is {MIN_SAMPLE_THRESHOLD}. "
                    f"Reliability cannot be meaningfully computed yet."
                ),
                methodology_version=RELIABILITY_METHODOLOGY_VERSION,
            )

        # AVAILABLE path — reserved for future phases
        return ReliabilityResult(
            evidence_id=evidence_id,
            evidence_type=evidence_type,
            status=HistoricalReliabilityStatus.AVAILABLE,
            sample_count=sample_count,
            explanation=(
                f"{sample_count} outcomes available. Reliability computation "
                f"will be implemented in a future phase."
            ),
            methodology_version=RELIABILITY_METHODOLOGY_VERSION,
        )

    def assess(
        self,
        observation: object,
        db: Session | None = None,
    ) -> ReliabilityResult:
        """
        Assess historical reliability for an EvidenceObservation ORM object.
        """
        return self.assess_by_fields(
            evidence_id=observation.internal_id,
            evidence_type=observation.evidence_type,
            db=db,
        )

    def _count_outcomes(self, evidence_type: str, db: Session | None) -> int:
        """
        Count recorded outcomes for the given evidence type.

        In Phase 6: always returns 0 because evidence_evaluations is empty.
        A future phase will replace this with a real DB query.
        """
        if db is None:
            return 0

        # Future implementation will be something like:
        #   return db.execute(
        #       select(func.count())
        #       .select_from(EvidenceEvaluation)
        #       .where(EvidenceEvaluation.availability_status == "AVAILABLE")
        #       .join(EvidenceObservation)
        #       .where(EvidenceObservation.evidence_type == evidence_type)
        #   ).scalar()
        #
        # For now: 0
        return 0


# Module-level singleton
reliability_service = EvidenceReliabilityService()
