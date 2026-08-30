"""
Phase 20 — Fraud Pattern Detection Engine.

Detects suspicious patterns in payment evidence using deterministic
rule-based analysis. Signals include:

1. AMOUNT_ANOMALY — Unusually large amounts relative to payment history
2. VELOCITY_BURST — Multiple events in rapid succession
3. SOURCE_CONCENTRATION — Evidence from single source only
4. STATUS_CONTRADICTION — Conflicting status evidence
5. TIMESTAMP_INVERSION — Evidence timestamps out of order
6. MISSING_EVIDENCE_GAPS — Critical evidence observations absent
7. CONFLICT_CLUSTER — Multiple unresolved conflicts on one payment
8. CROSS_PAYMENT_PATTERN — Suspicious patterns across payment set

ZERO fabricated signals — all detections from real database evidence.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import func, select, desc, and_, text
from sqlalchemy.orm import Session

from app.models.evidence import EvidenceObservation
from app.models.evidence_conflict import EvidenceConflict
from app.models.evidence_fact import EvidenceFact
from app.models.payment import Payment
from app.models.payment_event import PaymentEvent
from app.schemas.fraud_detection import (
    FraudAlertResponse,
    FraudDashboardResponse,
    FraudPatternItem,
    FraudPatternsResponse,
    FraudSignal,
)

logger = logging.getLogger(__name__)

METHODOLOGY_VERSION = "1.0.0"

# Thresholds
AMOUNT_ANOMALY_MULTIPLIER = 10.0  # 10x average is anomalous
VELOCITY_BURST_WINDOW_SECONDS = 30  # Events within 30s
VELOCITY_BURST_THRESHOLD = 3  # 3+ events in burst window
CONFLICT_CLUSTER_THRESHOLD = 2  # 2+ active conflicts
HIGH_AMOUNT_MINOR = 10000000  # 1,00,000 INR in minor units


def _generate_signal_id(payment_id: str, signal_type: str, timestamp: datetime) -> str:
    raw = f"{payment_id}:{signal_type}:{timestamp.isoformat()}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


class FraudDetectionEngine:
    """Detects suspicious patterns in payment evidence."""

    @classmethod
    def analyze_payment(
        cls, db: Session, payment_id: str
    ) -> Optional[FraudAlertResponse]:
        """Run all fraud detection rules on a single payment."""
        now = datetime.now(timezone.utc)

        payment = db.execute(
            select(Payment).where(Payment.razorpay_payment_id == payment_id)
        ).scalar_one_or_none()

        if not payment:
            return None

        signals: List[FraudSignal] = []

        # 1. Amount Anomaly Detection
        cls._check_amount_anomaly(db, payment, signals, now)

        # 2. Velocity Burst Detection
        cls._check_velocity_burst(db, payment_id, signals, now)

        # 3. Source Concentration
        cls._check_source_concentration(db, payment_id, signals, now)

        # 4. Status Contradiction via Conflicts
        cls._check_status_contradiction(db, payment_id, signals, now)

        # 5. Timestamp Inversion
        cls._check_timestamp_inversion(db, payment_id, signals, now)

        # 6. Missing Critical Evidence
        cls._check_missing_evidence(db, payment_id, signals, now)

        # 7. Conflict Cluster
        cls._check_conflict_cluster(db, payment_id, signals, now)

        # 8. High Amount Risk
        cls._check_high_amount(payment, signals, now)

        # Classify overall risk
        critical_count = sum(1 for s in signals if s.severity == "CRITICAL")
        high_count = sum(1 for s in signals if s.severity == "HIGH")

        if critical_count > 0:
            overall_risk = "HIGHLY_SUSPICIOUS"
        elif high_count >= 2:
            overall_risk = "SUSPICIOUS"
        elif high_count == 1 or len(signals) >= 2:
            overall_risk = "ELEVATED"
        else:
            overall_risk = "CLEAR"

        return FraudAlertResponse(
            payment_id=payment_id,
            signals=signals,
            overall_risk=overall_risk,
            signal_count=len(signals),
            critical_count=critical_count,
            high_count=high_count,
            evaluated_at=now,
            methodology_version=METHODOLOGY_VERSION,
        )

    @classmethod
    def get_dashboard(cls, db: Session) -> FraudDashboardResponse:
        """Global fraud detection dashboard summary."""
        now = datetime.now(timezone.utc)

        payments = db.execute(
            select(Payment).order_by(desc(Payment.created_at)).limit(100)
        ).scalars().all()

        all_signals: List[FraudSignal] = []
        signals_by_severity: Dict[str, int] = {}
        signals_by_type: Dict[str, int] = {}

        for p in payments:
            result = cls.analyze_payment(db, p.razorpay_payment_id)
            if result:
                for sig in result.signals:
                    all_signals.append(sig)
                    signals_by_severity[sig.severity] = signals_by_severity.get(sig.severity, 0) + 1
                    signals_by_type[sig.signal_type] = signals_by_type.get(sig.signal_type, 0) + 1

        # Sort by most recent
        all_signals.sort(key=lambda s: s.detected_at, reverse=True)

        return FraudDashboardResponse(
            evaluated_at=now,
            total_payments_analyzed=len(payments),
            total_signals=len(all_signals),
            signals_by_severity=signals_by_severity,
            signals_by_type=signals_by_type,
            recent_signals=all_signals[:20],
            methodology_version=METHODOLOGY_VERSION,
        )

    @classmethod
    def detect_cross_payment_patterns(
        cls, db: Session
    ) -> FraudPatternsResponse:
        """Detect fraud patterns across multiple payments."""
        now = datetime.now(timezone.utc)
        patterns: List[FraudPatternItem] = []

        # Pattern 1: High-value payment cluster
        high_payments = db.execute(
            select(Payment).where(Payment.amount_minor >= HIGH_AMOUNT_MINOR)
        ).scalars().all()

        if len(high_payments) >= 2:
            patterns.append(FraudPatternItem(
                pattern_id="PAT-HIGH-VALUE-CLUSTER",
                pattern_type="HIGH_VALUE_CLUSTER",
                severity="MEDIUM",
                affected_payment_count=len(high_payments),
                affected_payment_ids=[p.razorpay_payment_id for p in high_payments],
                description=f"{len(high_payments)} payments exceeding ₹1,00,000 detected in the system",
                detected_at=now,
                methodology_version=METHODOLOGY_VERSION,
            ))

        # Pattern 2: Single-source evidence across payments
        payments_with_single_source = []
        payments_all = db.execute(
            select(Payment).order_by(desc(Payment.created_at)).limit(50)
        ).scalars().all()

        for p in payments_all:
            src_count = db.execute(
                select(func.count(func.distinct(EvidenceObservation.source_type))).where(
                    EvidenceObservation.subject_id == p.razorpay_payment_id
                )
            ).scalar() or 0
            if src_count == 1:
                payments_with_single_source.append(p.razorpay_payment_id)

        if len(payments_with_single_source) >= 3:
            patterns.append(FraudPatternItem(
                pattern_id="PAT-SINGLE-SOURCE-CLUSTER",
                pattern_type="SINGLE_SOURCE_EVIDENCE",
                severity="MEDIUM",
                affected_payment_count=len(payments_with_single_source),
                affected_payment_ids=payments_with_single_source,
                description=f"{len(payments_with_single_source)} payments rely on evidence from only a single source",
                detected_at=now,
                methodology_version=METHODOLOGY_VERSION,
            ))

        # Pattern 3: High conflict rate
        total_payments = db.execute(select(func.count(Payment.internal_id))).scalar() or 0
        payments_with_conflicts = db.execute(
            select(func.count(func.distinct(EvidenceConflict.payment_id))).where(
                EvidenceConflict.status == "ACTIVE"
            )
        ).scalar() or 0

        if total_payments > 0 and payments_with_conflicts > 0:
            conflict_rate = payments_with_conflicts / total_payments
            if conflict_rate > 0.3:
                patterns.append(FraudPatternItem(
                    pattern_id="PAT-HIGH-CONFLICT-RATE",
                    pattern_type="HIGH_CONFLICT_RATE",
                    severity="HIGH",
                    affected_payment_count=payments_with_conflicts,
                    affected_payment_ids=[],
                    description=f"System-wide conflict rate is {conflict_rate:.0%} ({payments_with_conflicts}/{total_payments} payments have active conflicts)",
                    detected_at=now,
                    methodology_version=METHODOLOGY_VERSION,
                ))

        return FraudPatternsResponse(
            patterns=patterns,
            total_patterns=len(patterns),
            evaluated_at=now,
            methodology_version=METHODOLOGY_VERSION,
        )

    # ── Private Detection Rules ──

    @classmethod
    def _check_amount_anomaly(
        cls, db: Session, payment: Payment, signals: List[FraudSignal], now: datetime
    ):
        """Detect if this payment amount is anomalously large."""
        if payment.amount_minor is None:
            return

        # Get average amount across all payments
        avg_amount = db.execute(
            select(func.avg(Payment.amount_minor)).where(
                Payment.amount_minor.isnot(None),
                Payment.internal_id != payment.internal_id,
            )
        ).scalar()

        if avg_amount and avg_amount > 0:
            ratio = payment.amount_minor / avg_amount
            if ratio >= AMOUNT_ANOMALY_MULTIPLIER:
                signals.append(FraudSignal(
                    signal_id=_generate_signal_id(payment.razorpay_payment_id, "AMOUNT_ANOMALY", now),
                    signal_type="AMOUNT_ANOMALY",
                    severity="HIGH",
                    confidence=min(1.0, ratio / 50.0),
                    payment_id=payment.razorpay_payment_id,
                    detected_at=now,
                    description=f"Payment amount ({payment.amount_minor} minor units) is {ratio:.1f}x the average ({avg_amount:.0f})",
                    evidence={"amount_minor": payment.amount_minor, "avg_amount": round(avg_amount, 0), "ratio": round(ratio, 2)},
                    recommendation="Verify this transaction with the customer",
                    methodology_version=METHODOLOGY_VERSION,
                ))

    @classmethod
    def _check_velocity_burst(
        cls, db: Session, payment_id: str, signals: List[FraudSignal], now: datetime
    ):
        """Detect rapid-fire evidence events for a payment."""
        cutoff = now - timedelta(seconds=VELOCITY_BURST_WINDOW_SECONDS)
        recent_events = db.execute(
            select(func.count(PaymentEvent.internal_id)).join(
                Payment, Payment.internal_id == PaymentEvent.payment_id
            ).where(
                Payment.razorpay_payment_id == payment_id,
                PaymentEvent.event_timestamp >= cutoff,
            )
        ).scalar() or 0

        if recent_events >= VELOCITY_BURST_THRESHOLD:
            signals.append(FraudSignal(
                signal_id=_generate_signal_id(payment_id, "VELOCITY_BURST", now),
                signal_type="VELOCITY_BURST",
                severity="HIGH",
                confidence=min(1.0, recent_events / 10.0),
                payment_id=payment_id,
                detected_at=now,
                description=f"{recent_events} payment events within {VELOCITY_BURST_WINDOW_SECONDS}s window",
                evidence={"event_count": recent_events, "window_seconds": VELOCITY_BURST_WINDOW_SECONDS},
                recommendation="Investigate whether rapid state transitions indicate manipulation",
                methodology_version=METHODOLOGY_VERSION,
            ))

    @classmethod
    def _check_source_concentration(
        cls, db: Session, payment_id: str, signals: List[FraudSignal], now: datetime
    ):
        """Detect payments with evidence from only one source."""
        source_count = db.execute(
            select(func.count(func.distinct(EvidenceObservation.source_type))).where(
                EvidenceObservation.subject_id == payment_id
            )
        ).scalar() or 0

        evidence_count = db.execute(
            select(func.count(EvidenceObservation.internal_id)).where(
                EvidenceObservation.subject_id == payment_id
            )
        ).scalar() or 0

        if evidence_count > 0 and source_count <= 1:
            signals.append(FraudSignal(
                signal_id=_generate_signal_id(payment_id, "SOURCE_CONCENTRATION", now),
                signal_type="SOURCE_CONCENTRATION",
                severity="MEDIUM",
                confidence=0.6,
                payment_id=payment_id,
                detected_at=now,
                description=f"All {evidence_count} evidence observations come from a single source",
                evidence={"source_count": source_count, "evidence_count": evidence_count},
                recommendation="Cross-reference with independent evidence sources",
                methodology_version=METHODOLOGY_VERSION,
            ))

    @classmethod
    def _check_status_contradiction(
        cls, db: Session, payment_id: str, signals: List[FraudSignal], now: datetime
    ):
        """Detect active status contradictions."""
        active_conflicts = db.execute(
            select(func.count(EvidenceConflict.internal_id)).where(
                EvidenceConflict.payment_id == payment_id,
                EvidenceConflict.status == "ACTIVE",
                EvidenceConflict.conflict_type == "STATUS_CONTRADICTION",
            )
        ).scalar() or 0

        if active_conflicts > 0:
            signals.append(FraudSignal(
                signal_id=_generate_signal_id(payment_id, "STATUS_CONTRADICTION", now),
                signal_type="STATUS_CONTRADICTION",
                severity="HIGH",
                confidence=0.8,
                payment_id=payment_id,
                detected_at=now,
                description=f"{active_conflicts} active status contradiction conflict(s) detected",
                evidence={"active_conflicts": active_conflicts},
                recommendation="Manually verify the true status of this payment with Razorpay",
                methodology_version=METHODOLOGY_VERSION,
            ))

    @classmethod
    def _check_timestamp_inversion(
        cls, db: Session, payment_id: str, signals: List[FraudSignal], now: datetime
    ):
        """Detect evidence with inverted timestamps."""
        conflicts = db.execute(
            select(func.count(EvidenceConflict.internal_id)).where(
                EvidenceConflict.payment_id == payment_id,
                EvidenceConflict.status == "ACTIVE",
                EvidenceConflict.conflict_type == "TIMESTAMP_INVERSION",
            )
        ).scalar() or 0

        if conflicts > 0:
            signals.append(FraudSignal(
                signal_id=_generate_signal_id(payment_id, "TIMESTAMP_INVERSION", now),
                signal_type="TIMESTAMP_INVERSION",
                severity="MEDIUM",
                confidence=0.7,
                payment_id=payment_id,
                detected_at=now,
                description=f"{conflicts} evidence timestamp inversion(s) detected — events out of chronological order",
                evidence={"inversion_count": conflicts},
                recommendation="Investigate possible clock skew or event replay",
                methodology_version=METHODOLOGY_VERSION,
            ))

    @classmethod
    def _check_missing_evidence(
        cls, db: Session, payment_id: str, signals: List[FraudSignal], now: datetime
    ):
        """Detect payments with critical evidence gaps."""
        evidence_count = db.execute(
            select(func.count(EvidenceObservation.internal_id)).where(
                EvidenceObservation.subject_id == payment_id
            )
        ).scalar() or 0

        event_count = db.execute(
            select(func.count(PaymentEvent.internal_id)).join(
                Payment, Payment.internal_id == PaymentEvent.payment_id
            ).where(
                Payment.razorpay_payment_id == payment_id
            )
        ).scalar() or 0

        if event_count > 0 and evidence_count == 0:
            signals.append(FraudSignal(
                signal_id=_generate_signal_id(payment_id, "MISSING_EVIDENCE_GAPS", now),
                signal_type="MISSING_EVIDENCE_GAPS",
                severity="CRITICAL",
                confidence=0.95,
                payment_id=payment_id,
                detected_at=now,
                description=f"Payment has {event_count} events but zero extracted evidence observations",
                evidence={"event_count": event_count, "evidence_count": evidence_count},
                recommendation="Critical: Investigate evidence extraction pipeline for this payment",
                methodology_version=METHODOLOGY_VERSION,
            ))

    @classmethod
    def _check_conflict_cluster(
        cls, db: Session, payment_id: str, signals: List[FraudSignal], now: datetime
    ):
        """Detect payments with multiple active conflicts."""
        active_count = db.execute(
            select(func.count(EvidenceConflict.internal_id)).where(
                EvidenceConflict.payment_id == payment_id,
                EvidenceConflict.status == "ACTIVE",
            )
        ).scalar() or 0

        if active_count >= CONFLICT_CLUSTER_THRESHOLD:
            signals.append(FraudSignal(
                signal_id=_generate_signal_id(payment_id, "CONFLICT_CLUSTER", now),
                signal_type="CONFLICT_CLUSTER",
                severity="HIGH",
                confidence=min(1.0, active_count / 5.0),
                payment_id=payment_id,
                detected_at=now,
                description=f"Cluster of {active_count} unresolved conflicts on a single payment",
                evidence={"active_conflict_count": active_count},
                recommendation="Prioritize conflict resolution — multiple contradictions suggest unreliable evidence",
                methodology_version=METHODOLOGY_VERSION,
            ))

    @classmethod
    def _check_high_amount(
        cls, payment: Payment, signals: List[FraudSignal], now: datetime
    ):
        """Flag high-value transactions for review."""
        if payment.amount_minor and payment.amount_minor >= HIGH_AMOUNT_MINOR:
            signals.append(FraudSignal(
                signal_id=_generate_signal_id(payment.razorpay_payment_id, "HIGH_AMOUNT", now),
                signal_type="HIGH_AMOUNT",
                severity="LOW",
                confidence=0.5,
                payment_id=payment.razorpay_payment_id,
                detected_at=now,
                description=f"High-value transaction: ₹{payment.amount_minor / 100:,.2f}",
                evidence={"amount_minor": payment.amount_minor, "threshold": HIGH_AMOUNT_MINOR},
                recommendation="Standard high-value review protocol",
                methodology_version=METHODOLOGY_VERSION,
            ))
