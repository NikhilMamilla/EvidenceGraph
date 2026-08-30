"""
Tests for Phase 6 — Evidence Quality Measurement.

All tests are pure unit tests — no live DB required.
The measurement services accept explicit evaluation_time,
making all assertions deterministic.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.models.evidence_types import EvidenceType, SourceType
from app.models.quality_types import (
    FreshnessState,
    HistoricalReliabilityStatus,
    SourceDirectness,
    AuthorityLevel,
    FRESHNESS_METHODOLOGY_VERSION,
    SOURCE_QUALITY_METHODOLOGY_VERSION,
    RELIABILITY_METHODOLOGY_VERSION,
)
from app.services.freshness_service import (
    EvidenceFreshnessService,
    get_policy_for_evidence_type,
)
from app.services.source_service import EvidenceSourceService
from app.services.reliability_service import EvidenceReliabilityService


# -------------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------------

def _utc(year=2026, month=8, day=20, hour=10, minute=0) -> datetime:
    return datetime(year, month, day, hour, minute, 0, tzinfo=timezone.utc)


# -------------------------------------------------------------------------
# FreshnessService — CURRENT
# -------------------------------------------------------------------------

class TestFreshnessServiceCurrent:
    def test_within_current_threshold_is_current(self):
        svc = EvidenceFreshnessService()
        observed = _utc(hour=10)
        # 30 minutes later — well within default 24h current threshold
        evaluation = _utc(hour=10, minute=30)
        result = svc.measure_by_fields(
            evidence_id=1,
            evidence_type=EvidenceType.PAYMENT_EVENT,
            observed_at=observed,
            evaluation_time=evaluation,
        )
        assert result.freshness_state == FreshnessState.CURRENT
        assert result.age_seconds == 30 * 60
        assert result.methodology_version == FRESHNESS_METHODOLOGY_VERSION

    def test_age_exactly_zero_is_current(self):
        svc = EvidenceFreshnessService()
        t = _utc()
        result = svc.measure_by_fields(
            evidence_id=2,
            evidence_type=EvidenceType.PAYMENT_METHOD,
            observed_at=t,
            evaluation_time=t,
        )
        assert result.freshness_state == FreshnessState.CURRENT
        assert result.age_seconds == 0.0


# -------------------------------------------------------------------------
# FreshnessService — AGING
# -------------------------------------------------------------------------

class TestFreshnessServiceAging:
    def test_between_current_and_stale_thresholds_is_aging(self):
        svc = EvidenceFreshnessService()
        observed = _utc(day=1, hour=0)
        # 2 days later — past default 24h current, before default 7d stale
        evaluation = observed + timedelta(days=2)
        result = svc.measure_by_fields(
            evidence_id=3,
            evidence_type=EvidenceType.PAYMENT_EVENT,
            observed_at=observed,
            evaluation_time=evaluation,
        )
        assert result.freshness_state == FreshnessState.AGING

    def test_payment_status_aging_after_4h(self):
        """PAYMENT_STATUS has a narrower policy: CURRENT < 4h, STALE >= 48h."""
        svc = EvidenceFreshnessService()
        observed = _utc(hour=0)
        evaluation = observed + timedelta(hours=5)
        result = svc.measure_by_fields(
            evidence_id=4,
            evidence_type=EvidenceType.PAYMENT_STATUS,
            observed_at=observed,
            evaluation_time=evaluation,
        )
        assert result.freshness_state == FreshnessState.AGING
        assert result.policy_key == "PAYMENT_STATUS"


# -------------------------------------------------------------------------
# FreshnessService — STALE
# -------------------------------------------------------------------------

class TestFreshnessServiceStale:
    def test_past_stale_threshold_is_stale(self):
        svc = EvidenceFreshnessService()
        observed = _utc(day=1)
        # 8 days later — past default 7d stale threshold
        evaluation = observed + timedelta(days=8)
        result = svc.measure_by_fields(
            evidence_id=5,
            evidence_type=EvidenceType.PAYMENT_EVENT,
            observed_at=observed,
            evaluation_time=evaluation,
        )
        assert result.freshness_state == FreshnessState.STALE

    def test_payment_status_stale_after_48h(self):
        svc = EvidenceFreshnessService()
        observed = _utc(hour=0)
        evaluation = observed + timedelta(hours=50)
        result = svc.measure_by_fields(
            evidence_id=6,
            evidence_type=EvidenceType.PAYMENT_STATUS,
            observed_at=observed,
            evaluation_time=evaluation,
        )
        assert result.freshness_state == FreshnessState.STALE

    def test_payment_amount_not_stale_at_10_days(self):
        """PAYMENT_AMOUNT stale threshold is 30d — should be AGING at 10d."""
        svc = EvidenceFreshnessService()
        observed = _utc(day=1)
        evaluation = observed + timedelta(days=10)
        result = svc.measure_by_fields(
            evidence_id=7,
            evidence_type=EvidenceType.PAYMENT_AMOUNT,
            observed_at=observed,
            evaluation_time=evaluation,
        )
        assert result.freshness_state == FreshnessState.AGING


# -------------------------------------------------------------------------
# FreshnessService — UNKNOWN
# -------------------------------------------------------------------------

class TestFreshnessServiceUnknown:
    def test_none_observed_at_is_unknown(self):
        svc = EvidenceFreshnessService()
        result = svc.measure_by_fields(
            evidence_id=8,
            evidence_type=EvidenceType.PAYMENT_STATUS,
            observed_at=None,
            evaluation_time=_utc(),
        )
        assert result.freshness_state == FreshnessState.UNKNOWN
        assert result.age_seconds is None

    def test_future_observed_at_is_unknown(self):
        """observed_at after evaluation_time → UNKNOWN, not negative age."""
        svc = EvidenceFreshnessService()
        evaluation = _utc(hour=10)
        future = _utc(hour=12)  # 2h in the future relative to evaluation
        result = svc.measure_by_fields(
            evidence_id=9,
            evidence_type=EvidenceType.PAYMENT_EVENT,
            observed_at=future,
            evaluation_time=evaluation,
        )
        assert result.freshness_state == FreshnessState.UNKNOWN
        assert result.age_seconds is None


# -------------------------------------------------------------------------
# FreshnessService — Determinism
# -------------------------------------------------------------------------

class TestFreshnessDeterminism:
    def test_same_inputs_same_output(self):
        svc = EvidenceFreshnessService()
        observed = _utc()
        evaluation = observed + timedelta(hours=2)
        r1 = svc.measure_by_fields(1, EvidenceType.PAYMENT_STATUS, observed, evaluation)
        r2 = svc.measure_by_fields(1, EvidenceType.PAYMENT_STATUS, observed, evaluation)
        assert r1.freshness_state == r2.freshness_state
        assert r1.age_seconds == r2.age_seconds
        assert r1.methodology_version == r2.methodology_version

    def test_evaluation_time_must_be_timezone_aware(self):
        svc = EvidenceFreshnessService()
        naive_dt = datetime(2026, 8, 20, 10, 0, 0)  # no tzinfo
        with pytest.raises(ValueError, match="timezone-aware"):
            svc.measure_by_fields(1, EvidenceType.PAYMENT_EVENT, _utc(), naive_dt)


# -------------------------------------------------------------------------
# FreshnessService — Temporal re-evaluation
# -------------------------------------------------------------------------

class TestFreshnessTemporalReeval:
    def test_transitions_from_current_to_stale(self):
        """Same evidence, different evaluation timestamps → different states."""
        svc = EvidenceFreshnessService()
        observed = _utc(day=1, hour=0)

        t1 = observed + timedelta(hours=1)   # CURRENT
        t2 = observed + timedelta(days=10)   # STALE

        r1 = svc.measure_by_fields(10, EvidenceType.PAYMENT_EVENT, observed, t1)
        r2 = svc.measure_by_fields(10, EvidenceType.PAYMENT_EVENT, observed, t2)

        assert r1.freshness_state == FreshnessState.CURRENT
        assert r2.freshness_state == FreshnessState.STALE
        assert r2.age_seconds > r1.age_seconds


# -------------------------------------------------------------------------
# SourceService
# -------------------------------------------------------------------------

class TestSourceService:
    def test_razorpay_webhook_payment_event_is_direct_primary(self):
        svc = EvidenceSourceService()
        result = svc.classify_by_fields(
            evidence_id=1,
            source_type=SourceType.RAZORPAY_WEBHOOK,
            evidence_type=EvidenceType.PAYMENT_EVENT,
        )
        assert result.authority_level == AuthorityLevel.PRIMARY
        assert result.directness == SourceDirectness.DIRECT
        assert result.methodology_version == SOURCE_QUALITY_METHODOLOGY_VERSION

    def test_razorpay_webhook_payment_status_is_derived(self):
        """PAYMENT_STATUS is derived from PAYMENT_EVENT, even from webhook source."""
        svc = EvidenceSourceService()
        result = svc.classify_by_fields(
            evidence_id=2,
            source_type=SourceType.RAZORPAY_WEBHOOK,
            evidence_type=EvidenceType.PAYMENT_STATUS,
        )
        assert result.authority_level == AuthorityLevel.PRIMARY
        assert result.directness == SourceDirectness.DERIVED

    def test_razorpay_webhook_payment_amount_is_derived(self):
        svc = EvidenceSourceService()
        result = svc.classify_by_fields(3, SourceType.RAZORPAY_WEBHOOK, EvidenceType.PAYMENT_AMOUNT)
        assert result.directness == SourceDirectness.DERIVED

    def test_internal_system_is_secondary_derived(self):
        svc = EvidenceSourceService()
        result = svc.classify_by_fields(4, SourceType.INTERNAL_SYSTEM, EvidenceType.PAYMENT_STATUS)
        assert result.authority_level == AuthorityLevel.SECONDARY
        assert result.directness == SourceDirectness.DERIVED

    def test_razorpay_api_is_direct_primary(self):
        svc = EvidenceSourceService()
        result = svc.classify_by_fields(5, SourceType.RAZORPAY_API, EvidenceType.PAYMENT_STATUS)
        assert result.authority_level == AuthorityLevel.PRIMARY
        assert result.directness == SourceDirectness.DIRECT

    def test_deterministic_same_inputs_same_output(self):
        svc = EvidenceSourceService()
        r1 = svc.classify_by_fields(1, SourceType.RAZORPAY_WEBHOOK, EvidenceType.PAYMENT_STATUS)
        r2 = svc.classify_by_fields(1, SourceType.RAZORPAY_WEBHOOK, EvidenceType.PAYMENT_STATUS)
        assert r1.directness == r2.directness
        assert r1.authority_level == r2.authority_level


# -------------------------------------------------------------------------
# ReliabilityService
# -------------------------------------------------------------------------

class TestReliabilityService:
    def test_no_db_returns_no_outcome_data(self):
        svc = EvidenceReliabilityService()
        result = svc.assess_by_fields(
            evidence_id=1,
            evidence_type=EvidenceType.PAYMENT_STATUS,
            db=None,
        )
        assert result.status == HistoricalReliabilityStatus.NO_OUTCOME_DATA
        assert result.sample_count is None
        assert result.methodology_version == RELIABILITY_METHODOLOGY_VERSION

    def test_no_outcome_for_payment_event(self):
        svc = EvidenceReliabilityService()
        result = svc.assess_by_fields(1, EvidenceType.PAYMENT_EVENT, db=None)
        assert result.status == HistoricalReliabilityStatus.NO_OUTCOME_DATA

    def test_explanation_is_honest(self):
        svc = EvidenceReliabilityService()
        result = svc.assess_by_fields(1, EvidenceType.PAYMENT_STATUS, db=None)
        # Explanation must NOT claim a numerical reliability
        assert "%" not in result.explanation
        assert "0." not in result.explanation  # no 0.xx score
        assert "No historical outcomes" in result.explanation or "cannot" in result.explanation.lower()

    def test_methodology_version_present(self):
        svc = EvidenceReliabilityService()
        result = svc.assess_by_fields(1, EvidenceType.PAYMENT_AMOUNT, db=None)
        assert result.methodology_version is not None
        assert len(result.methodology_version) > 0


# -------------------------------------------------------------------------
# Versioning — every measurement carries methodology_version
# -------------------------------------------------------------------------

class TestMethodologyVersioning:
    def test_freshness_result_has_version(self):
        svc = EvidenceFreshnessService()
        result = svc.measure_by_fields(1, EvidenceType.PAYMENT_EVENT, _utc(), _utc())
        assert result.methodology_version == FRESHNESS_METHODOLOGY_VERSION

    def test_source_result_has_version(self):
        svc = EvidenceSourceService()
        result = svc.classify_by_fields(1, SourceType.RAZORPAY_WEBHOOK, EvidenceType.PAYMENT_EVENT)
        assert result.methodology_version == SOURCE_QUALITY_METHODOLOGY_VERSION

    def test_reliability_result_has_version(self):
        svc = EvidenceReliabilityService()
        result = svc.assess_by_fields(1, EvidenceType.PAYMENT_EVENT, db=None)
        assert result.methodology_version == RELIABILITY_METHODOLOGY_VERSION
