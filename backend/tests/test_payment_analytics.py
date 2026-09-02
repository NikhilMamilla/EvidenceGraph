"""
Payment analytics engine — trend windows and status accounting.

These two behaviours were wrong and shipped to the UI as empty charts and an
inflated failure count, so they are pinned here:

1. Trend windows adapt to the data. Bucketing strictly over the last 24 hours
   renders 24 zeros whenever the newest payment is older than a day, which is
   the normal case for a test-mode dataset.
2. "Failed payments" counts real failures only. Reporting `total - captured`
   labelled every authorized / pending / paid row a loss, contradicting the
   project's "absence of capture is not evidence of failure" axiom.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(type_, compiler, **kw):  # noqa: ANN001
    return "JSON"


from app.db.session import Base
from app.models.payment import Payment
from app.services.payment_analytics_engine import PaymentAnalyticsEngine as Engine


NOW = datetime(2026, 9, 2, 12, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()


def _payment(db, pid: str, status: str, observed: datetime, amount: int = 50000):
    db.add(Payment(
        razorpay_payment_id=pid,
        amount_minor=amount,
        currency="INR",
        status=status,
        captured=status == "captured",
        first_observed_at=observed,
        last_observed_at=observed,
    ))
    db.commit()


class TestActivityWindow:
    def test_recent_activity_keeps_the_hourly_view(self, db):
        _payment(db, "pay_recent", "captured", NOW - timedelta(hours=2))
        buckets, label = Engine._activity_window(db, NOW)
        assert label == "Last 24 hours"
        assert len(buckets) == 24

    def test_stale_data_widens_to_daily_buckets(self, db):
        _payment(db, "pay_old", "captured", NOW - timedelta(days=9))
        buckets, label = Engine._activity_window(db, NOW)
        assert "day" in label
        assert len(buckets) == 10          # 9 days back, inclusive of today
        assert len(buckets) == int(label.split()[1])

    def test_empty_database_still_returns_a_stable_grid(self, db):
        buckets, label = Engine._activity_window(db, NOW)
        assert label == "Last 24 hours"
        assert len(buckets) == 24

    def test_buckets_are_ordered_oldest_first_and_contiguous(self, db):
        _payment(db, "pay_old", "captured", NOW - timedelta(days=4))
        buckets, _ = Engine._activity_window(db, NOW)
        starts = [b[0] for b in buckets]
        assert starts == sorted(starts)
        for (_, end, _), (nxt_start, _, _) in zip(buckets, buckets[1:]):
            assert end == nxt_start


class TestTrendsSurfaceRealData:
    def test_stale_payment_still_appears_in_the_revenue_series(self, db):
        """The bug: a 9-day-old payment produced an all-zero 24h chart."""
        _payment(db, "pay_old", "captured", NOW - timedelta(days=6), amount=50000)
        result = Engine.get_revenue_intelligence(db)
        assert result.series_window != "Last 24 hours"
        assert any(p.gmv > 0 for p in result.time_series), "series is all zeros"
        assert all(p.label for p in result.time_series), "every bucket needs a tick label"

    def test_failure_trend_reports_its_window(self, db):
        _payment(db, "pay_f", "failed", NOW - timedelta(days=3))
        result = Engine.get_failure_dashboard(db)
        assert result.trend_window
        assert sum(p["failure_count"] for p in result.hourly_failure_trend) >= 1


class TestFailureAccounting:
    def test_non_captured_is_not_counted_as_failed(self, db):
        """authorized / pending / paid are not losses."""
        _payment(db, "pay_cap", "captured", NOW - timedelta(hours=1))
        _payment(db, "pay_paid", "paid", NOW - timedelta(hours=1))
        _payment(db, "pay_auth", "authorized", NOW - timedelta(hours=1))

        failed = next(m for m in Engine.get_revenue_intelligence(db).metrics
                      if m.label == "Failed Payments")
        assert failed.value == 0.0

    def test_real_failures_are_counted(self, db):
        _payment(db, "pay_cap", "captured", NOW - timedelta(hours=1))
        _payment(db, "pay_bad", "failed", NOW - timedelta(hours=1))

        failed = next(m for m in Engine.get_revenue_intelligence(db).metrics
                      if m.label == "Failed Payments")
        assert failed.value == 1.0
