"""
Phase 20 — Composite Evidence Integrity Risk Score Engine.

Computes a multi-dimensional risk score (0–100) from evidence quality,
coverage, reliability, consistency, and freshness signals.

Score semantics:
  0–25:   CRITICAL_RISK  — Evidence is severely deficient or contradictory
  26–50:  HIGH_RISK      — Significant evidence gaps or quality concerns
  51–75:  MEDIUM_RISK    — Adequate evidence with some areas of concern
  76–100: LOW_RISK       — Strong, consistent, multi-source evidence

ZERO fabricated data — all scores derived from real database evidence.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import func, select, desc
from sqlalchemy.orm import Session

from app.models.evidence import EvidenceObservation
from app.models.evidence_conflict import EvidenceConflict
from app.models.evidence_coverage import EvidenceCoverageSnapshot
from app.models.evidence_fact import EvidenceFact
from app.models.evidence_integrity import EvidenceIntegritySnapshot
from app.models.evidence_reliability import EvidenceReliabilityAssessment
from app.models.evidence_structure import EvidenceStructureSnapshot
from app.models.payment import Payment
from app.models.payment_event import PaymentEvent
from app.schemas.risk_score import (
    DimensionScore,
    PaymentRiskSummary,
    RiskScoreResponse,
    RiskTrendPoint,
    RiskTrendResponse,
)

logger = logging.getLogger(__name__)

METHODOLOGY_VERSION = "2.0.0"

# Dimension weights — sum to 1.0
DIMENSION_WEIGHTS = {
    "evidence_volume": 0.15,
    "source_diversity": 0.15,
    "consistency": 0.20,
    "coverage": 0.15,
    "freshness": 0.10,
    "corroboration": 0.15,
    "conflict_resolution": 0.10,
}

RISK_THRESHOLDS = {
    "LOW_RISK": (76, 100),
    "MEDIUM_RISK": (51, 75),
    "HIGH_RISK": (26, 50),
    "CRITICAL_RISK": (0, 25),
}


def _classify_risk(score: float) -> str:
    for level, (lo, hi) in RISK_THRESHOLDS.items():
        if lo <= score <= hi:
            return level
    return "CRITICAL_RISK"


def _classify_dimension(score: float) -> str:
    if score >= 76:
        return "STRONG"
    if score >= 51:
        return "ADEQUATE"
    if score >= 26:
        return "WEAK"
    return "CRITICAL"


class RiskScoreEngine:
    """Computes composite evidence integrity risk scores."""

    @classmethod
    def compute_risk_score(
        cls, db: Session, payment_id: str
    ) -> Optional[RiskScoreResponse]:
        """Compute the composite risk score for a single payment."""
        now = datetime.now(timezone.utc)

        payment = db.execute(
            select(Payment).where(Payment.razorpay_payment_id == payment_id)
        ).scalar_one_or_none()

        if not payment:
            return None

        # Gather all evidence signals
        evidence_count = db.execute(
            select(func.count(EvidenceObservation.internal_id)).where(
                EvidenceObservation.subject_id == payment_id
            )
        ).scalar() or 0

        # Distinct sources
        source_rows = db.execute(
            select(func.count(func.distinct(EvidenceObservation.source_type))).where(
                EvidenceObservation.subject_id == payment_id
            )
        ).scalar() or 0

        # Distinct events
        event_rows = db.execute(
            select(func.count(func.distinct(EvidenceObservation.payment_event_id))).where(
                EvidenceObservation.subject_id == payment_id,
                EvidenceObservation.payment_event_id.isnot(None),
            )
        ).scalar() or 0

        # Conflicts
        total_conflicts = db.execute(
            select(func.count(EvidenceConflict.internal_id)).where(
                EvidenceConflict.payment_id == payment_id
            )
        ).scalar() or 0

        open_conflicts = db.execute(
            select(func.count(EvidenceConflict.internal_id)).where(
                EvidenceConflict.payment_id == payment_id,
                EvidenceConflict.status == "ACTIVE",
            )
        ).scalar() or 0

        # Facts
        total_facts = db.execute(
            select(func.count(EvidenceFact.internal_id)).where(
                EvidenceFact.payment_id == payment_id
            )
        ).scalar() or 0

        active_facts = db.execute(
            select(func.count(EvidenceFact.internal_id)).where(
                EvidenceFact.payment_id == payment_id,
                EvidenceFact.status == "ACTIVE",
            )
        ).scalar() or 0

        # Coverage
        latest_coverage = db.execute(
            select(EvidenceCoverageSnapshot)
            .where(EvidenceCoverageSnapshot.payment_id == payment_id)
            .order_by(desc(EvidenceCoverageSnapshot.evaluated_at))
            .limit(1)
        ).scalars().first()

        coverage_status = latest_coverage.overall_coverage_status if latest_coverage else "UNKNOWN"

        # Latest integrity snapshot
        latest_integrity = db.execute(
            select(EvidenceIntegritySnapshot)
            .where(EvidenceIntegritySnapshot.payment_id == payment_id)
            .order_by(desc(EvidenceIntegritySnapshot.evaluated_at))
            .limit(1)
        ).scalars().first()

        # Latest reliability
        latest_reliability = db.execute(
            select(EvidenceReliabilityAssessment)
            .where(EvidenceReliabilityAssessment.payment_id == payment_id)
            .order_by(desc(EvidenceReliabilityAssessment.evaluated_at))
            .limit(1)
        ).scalars().first()

        # Structure snapshot
        latest_structure = db.execute(
            select(EvidenceStructureSnapshot)
            .where(EvidenceStructureSnapshot.payment_id == payment_id)
            .order_by(desc(EvidenceStructureSnapshot.evaluated_at))
            .limit(1)
        ).scalars().first()

        # ── Compute Dimensions ──

        dimensions: List[DimensionScore] = []

        # 1. Evidence Volume Score
        vol_score = min(100.0, evidence_count * 10.0)  # 10 evidence = 100
        vol_score = max(0.0, vol_score)
        dimensions.append(DimensionScore(
            dimension="evidence_volume",
            score=round(vol_score, 1),
            weight=DIMENSION_WEIGHTS["evidence_volume"],
            status=_classify_dimension(vol_score),
            explanation=f"{evidence_count} evidence observations recorded for this payment",
            evidence_count=evidence_count,
        ))

        # 2. Source Diversity Score
        src_score = min(100.0, source_rows * 33.3)  # 3 sources = 100
        src_score = max(0.0, src_score)
        dimensions.append(DimensionScore(
            dimension="source_diversity",
            score=round(src_score, 1),
            weight=DIMENSION_WEIGHTS["source_diversity"],
            status=_classify_dimension(src_score),
            explanation=f"{source_rows} distinct evidence sources observed",
            evidence_count=source_rows,
        ))

        # 3. Consistency Score (based on conflicts)
        if total_conflicts == 0:
            con_score = 100.0
        elif open_conflicts == 0:
            con_score = 70.0  # All resolved
        else:
            con_score = max(0.0, 100.0 - (open_conflicts * 25.0))
        dimensions.append(DimensionScore(
            dimension="consistency",
            score=round(con_score, 1),
            weight=DIMENSION_WEIGHTS["consistency"],
            status=_classify_dimension(con_score),
            explanation=f"{total_conflicts} total conflicts, {open_conflicts} currently active",
        ))

        # 4. Coverage Score
        coverage_map = {
            "COMPLETE": 100.0,
            "SUFFICIENT": 75.0,
            "PARTIAL": 45.0,
            "INSUFFICIENT": 15.0,
        }
        cov_score = coverage_map.get(coverage_status, 30.0)
        dimensions.append(DimensionScore(
            dimension="coverage",
            score=round(cov_score, 1),
            weight=DIMENSION_WEIGHTS["coverage"],
            status=_classify_dimension(cov_score),
            explanation=f"Evidence coverage status: {coverage_status}",
        ))

        # 5. Freshness Score (based on how recent the last evidence is)
        latest_obs = db.execute(
            select(EvidenceObservation)
            .where(EvidenceObservation.subject_id == payment_id)
            .order_by(desc(EvidenceObservation.observed_at))
            .limit(1)
        ).scalars().first()

        if latest_obs and latest_obs.observed_at:
            obs_time = latest_obs.observed_at
            if not obs_time.tzinfo:
                obs_time = obs_time.replace(tzinfo=timezone.utc)
            age_seconds = (now - obs_time).total_seconds()
            if age_seconds < 300:
                fresh_score = 100.0
            elif age_seconds < 3600:
                fresh_score = 75.0
            elif age_seconds < 86400:
                fresh_score = 50.0
            else:
                fresh_score = 20.0
        else:
            fresh_score = 0.0

        dimensions.append(DimensionScore(
            dimension="freshness",
            score=round(fresh_score, 1),
            weight=DIMENSION_WEIGHTS["freshness"],
            status=_classify_dimension(fresh_score),
            explanation=f"Latest evidence observed {age_seconds:.0f}s ago" if latest_obs else "No evidence observations found",
        ))

        # 6. Corroboration Score
        if latest_structure:
            corr_count = latest_structure.corroborated_claim_count or 0
            multi_src = latest_structure.multi_source_claim_count or 0
            total_claims = latest_structure.distinct_claims or 1
            if total_claims > 0:
                corroboration_ratio = (corr_count + multi_src) / (total_claims * 2)
                corr_score = min(100.0, corroboration_ratio * 100.0)
            else:
                corr_score = 0.0
        else:
            corr_score = 25.0  # Default if no structure snapshot

        dimensions.append(DimensionScore(
            dimension="corroboration",
            score=round(corr_score, 1),
            weight=DIMENSION_WEIGHTS["corroboration"],
            status=_classify_dimension(corr_score),
            explanation=f"Corroboration analysis based on structure evaluation",
        ))

        # 7. Conflict Resolution Score
        if total_conflicts == 0:
            res_score = 100.0
        else:
            resolved = total_conflicts - open_conflicts
            res_score = (resolved / total_conflicts) * 100.0 if total_conflicts > 0 else 100.0

        dimensions.append(DimensionScore(
            dimension="conflict_resolution",
            score=round(res_score, 1),
            weight=DIMENSION_WEIGHTS["conflict_resolution"],
            status=_classify_dimension(res_score),
            explanation=f"{total_conflicts - open_conflicts} of {total_conflicts} conflicts resolved",
        ))

        # ── Composite Score ──
        composite = sum(d.score * d.weight for d in dimensions)
        composite = round(max(0.0, min(100.0, composite)), 1)
        risk_level = _classify_risk(composite)

        # ── Generate Explanation ──
        explanation_lines = []
        recommendations = []

        weakest = min(dimensions, key=lambda d: d.score)
        strongest = max(dimensions, key=lambda d: d.score)

        explanation_lines.append(
            f"Composite evidence integrity score: {composite}/100 ({risk_level})"
        )
        explanation_lines.append(
            f"Strongest dimension: {strongest.dimension} ({strongest.score}/100)"
        )
        explanation_lines.append(
            f"Weakest dimension: {weakest.dimension} ({weakest.score}/100)"
        )

        if open_conflicts > 0:
            explanation_lines.append(
                f"⚠ {open_conflicts} unresolved evidence conflict(s) impacting consistency"
            )
            recommendations.append("Review and resolve active evidence conflicts")

        if source_rows < 2:
            recommendations.append(
                "Gather evidence from additional independent sources"
            )

        if fresh_score < 50:
            recommendations.append(
                "Request updated evidence to improve temporal freshness"
            )

        if coverage_status in ("INSUFFICIENT", "PARTIAL"):
            recommendations.append(
                f"Evidence coverage is {coverage_status} — collect missing required evidence"
            )

        if composite < 50:
            recommendations.append(
                "This payment has significant evidence deficiencies — manual review recommended"
            )

        if not recommendations:
            recommendations.append("Evidence profile is healthy — no immediate action required")

        return RiskScoreResponse(
            payment_id=payment_id,
            evaluated_at=now,
            methodology_version=METHODOLOGY_VERSION,
            composite_score=composite,
            risk_level=risk_level,
            dimensions=dimensions,
            evidence_count=evidence_count,
            source_count=source_rows,
            conflict_count=total_conflicts,
            open_conflict_count=open_conflicts,
            coverage_status=coverage_status,
            freshness_status="FRESH" if fresh_score >= 75 else ("AGING" if fresh_score >= 50 else "STALE"),
            explanation_lines=explanation_lines,
            recommendations=recommendations,
        )

    @classmethod
    def get_all_payment_risk_summaries(
        cls, db: Session
    ) -> List[PaymentRiskSummary]:
        """Get lightweight risk summaries for all payments."""
        payments = db.execute(
            select(Payment).order_by(desc(Payment.created_at))
        ).scalars().all()

        summaries = []
        for p in payments:
            risk = cls.compute_risk_score(db, p.razorpay_payment_id)
            if risk:
                summaries.append(PaymentRiskSummary(
                    payment_id=risk.payment_id,
                    composite_score=risk.composite_score,
                    risk_level=risk.risk_level,
                    evidence_count=risk.evidence_count,
                    conflict_count=risk.conflict_count,
                    evaluated_at=risk.evaluated_at,
                ))
        return summaries

    @classmethod
    def get_risk_trend(
        cls, db: Session, payment_id: str
    ) -> Optional[RiskTrendResponse]:
        """
        Compute risk score trend from integrity snapshots over time.
        Each snapshot becomes a trend point.
        """
        payment = db.execute(
            select(Payment).where(Payment.razorpay_payment_id == payment_id)
        ).scalar_one_or_none()

        if not payment:
            return None

        snapshots = db.execute(
            select(EvidenceIntegritySnapshot)
            .where(EvidenceIntegritySnapshot.payment_id == payment_id)
            .order_by(desc(EvidenceIntegritySnapshot.evaluated_at))
            .limit(50)
        ).scalars().all()

        trend_points = []
        for snap in snapshots:
            # Compute a rough score from snapshot data
            has_conflicts = (snap.open_conflict_count or 0) > 0
            has_freshness = snap.freshness_result is not None
            has_independence = snap.independence_result is not None

            base_score = 50.0
            if snap.overall_status == "PASS":
                base_score = 85.0
            elif snap.overall_status == "WARN":
                base_score = 60.0
            elif snap.overall_status == "FAIL":
                base_score = 25.0

            if has_conflicts:
                base_score -= 15.0
            if has_freshness:
                base_score += 5.0
            if has_independence:
                base_score += 5.0

            base_score = max(0.0, min(100.0, base_score))

            trend_points.append(RiskTrendPoint(
                timestamp=snap.evaluated_at,
                composite_score=round(base_score, 1),
                risk_level=_classify_risk(base_score),
                evidence_count=snap.evidence_count or 0,
                conflict_count=snap.conflict_count or 0,
            ))

        return RiskTrendResponse(
            payment_id=payment_id,
            trend=list(reversed(trend_points)),
            methodology_version=METHODOLOGY_VERSION,
        )
