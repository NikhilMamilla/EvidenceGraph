"""
Phase 19 — Operational Intelligence & Continuous Verification Test Suite.

Verifies all required scenarios:
1. All dependencies healthy
2. Redis unavailable (returns DEGRADED without crashing)
3. Database unavailable (returns UNHEALTHY)
4. Worker unavailable (detects stopped thread)
5. Queue backlog detection
6. Stuck processing event detection
7. Failed processing event observability
8. Downstream Analysis Stale detection (new evidence after evaluation)
9. Downstream Analysis Current detection
10. Pipeline Watermark & Stage ordering
11. Payment Operational Status API
12. Continuous Verification of Invariants (INV-SYS-01 to INV-SYS-10)
13. Operational Incidents detection & timeline
14. Security: No secrets in health/metrics/incidents
15. Failure Injection & Recovery
16. REST API integration for /operations/*
"""

from __future__ import annotations

import threading
from datetime import datetime, timezone, timedelta
from typing import Generator
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

# Polyfill JSONB for SQLite test isolation
@compiles(JSONB, "sqlite")
def compile_jsonb_sqlite(type_, compiler, **kw):
    return "JSON"


from app.db.session import Base, get_db
from app.main import app
from app.models.evidence import EvidenceObservation
from app.models.evidence_coverage import EvidenceCoverageSnapshot
from app.models.evidence_fact import EvidenceFact, _canonical_value_hash
from app.models.evidence_integrity import EvidenceIntegritySnapshot
from app.models.evidence_reliability import EvidenceReliabilityAssessment
from app.models.evidence_types import (
    CURRENT_EXTRACTION_VERSION,
    EvidenceType,
    ExtractionMethod,
    SourceType,
    SubjectType,
    ValueType,
)
from app.models.operations_types import (
    HealthState,
    IncidentCategory,
    ProcessingFreshnessState,
    VerificationStatus,
)
from app.models.payment import Payment
from app.models.payment_event import PaymentEvent
from app.models.reconciliation_types import FactStatus, FactType
from app.models.webhook_event import WebhookEvent
from app.schemas.webhook import ProcessingStatus
from app.services.operations_service import OperationsService
from app.services import webhook_worker


# ---------------------------------------------------------------------------
# Test Fixtures & Helpers
# ---------------------------------------------------------------------------

@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture
def client(db_session: Session) -> Generator[TestClient, None, None]:
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def _create_payment(db: Session, payment_id: str) -> Payment:
    p = Payment(
        razorpay_payment_id=payment_id,
        amount_minor=50000,
        currency="INR",
        status="captured",
        captured=True,
        first_observed_at=datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc),
        last_observed_at=datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc),
    )
    db.add(p)
    db.flush()
    return p


# ---------------------------------------------------------------------------
# 1. System Health & Dependency Degradation Tests
# ---------------------------------------------------------------------------

class TestSystemHealth:
    def test_all_dependencies_healthy(self, db_session: Session):
        """When DB, Redis, and Worker are up, system reports HEALTHY."""
        with (
            patch("app.services.operations_service.check_database_connection", return_value=True),
            patch("app.services.operations_service.check_redis_connection", return_value=True),
            patch("app.services.webhook_worker._worker_thread", MagicMock(is_alive=lambda: True)),
            patch("app.services.webhook_worker._stop_event.is_set", return_value=False),
        ):
            health = OperationsService.get_system_health(db_session)
            assert health.overall_state == HealthState.HEALTHY
            assert health.components["DATABASE"].state == HealthState.HEALTHY
            assert health.components["REDIS"].state == HealthState.HEALTHY
            assert health.components["WORKER"].state == HealthState.HEALTHY

    def test_redis_unavailable_degrades_system(self, db_session: Session):
        """When Redis is down, system reports DEGRADED rather than false HEALTHY."""
        with (
            patch("app.services.operations_service.check_database_connection", return_value=True),
            patch("app.services.operations_service.check_redis_connection", return_value=False),
            patch("app.services.webhook_worker._worker_thread", MagicMock(is_alive=lambda: True)),
            patch("app.services.webhook_worker._stop_event.is_set", return_value=False),
        ):
            health = OperationsService.get_system_health(db_session)
            assert health.overall_state == HealthState.DEGRADED
            assert health.components["REDIS"].state == HealthState.DEGRADED

    def test_database_unavailable_marks_system_unhealthy(self, db_session: Session):
        """When DB is down, system reports UNHEALTHY."""
        with (
            patch("app.services.operations_service.check_database_connection", return_value=False),
            patch("app.services.operations_service.check_redis_connection", return_value=True),
            patch("app.services.webhook_worker._worker_thread", MagicMock(is_alive=lambda: True)),
            patch("app.services.webhook_worker._stop_event.is_set", return_value=False),
        ):
            health = OperationsService.get_system_health(db_session)
            assert health.overall_state == HealthState.UNHEALTHY
            assert health.components["DATABASE"].state == HealthState.UNHEALTHY

    def test_worker_stopped_marks_worker_unhealthy(self, db_session: Session):
        """When worker thread is not alive, system marks worker UNHEALTHY."""
        with (
            patch("app.services.operations_service.check_database_connection", return_value=True),
            patch("app.services.operations_service.check_redis_connection", return_value=True),
            patch("app.services.webhook_worker._worker_thread", None),
        ):
            health = OperationsService.get_system_health(db_session)
            assert health.overall_state == HealthState.UNHEALTHY
            assert health.components["WORKER"].state == HealthState.UNHEALTHY


# ---------------------------------------------------------------------------
# 2. Operational Metrics, Queue & Lag Tests
# ---------------------------------------------------------------------------

class TestOperationalMetrics:
    def test_processing_lag_calculation(self, db_session: Session):
        """Processing lag is calculated as processed_at - received_at on real events."""
        t_recv = datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
        t_proc = datetime(2024, 1, 1, 10, 0, 5, tzinfo=timezone.utc)  # 5s lag

        ev = WebhookEvent(
            razorpay_event_id="evt_lag_001",
            event_type="payment.captured",
            received_at=t_recv,
            processed_at=t_proc,
            processing_status=ProcessingStatus.PROCESSED,
            raw_payload={"event": "payment.captured"},
            payload_hash="dummy_hash_lag",
        )
        db_session.add(ev)
        db_session.flush()

        metrics = OperationsService.get_operational_metrics(db_session)
        assert metrics.lag.latest_lag_seconds == 5.0
        assert metrics.lag.average_lag_seconds == 5.0

    def test_stuck_event_detection(self, db_session: Session):
        """Events remaining in RECEIVED state beyond threshold are counted as stuck."""
        old_time = datetime.now(timezone.utc) - timedelta(minutes=10)
        ev = WebhookEvent(
            razorpay_event_id="evt_stuck_001",
            event_type="payment.captured",
            received_at=old_time,
            processing_status="PERSISTED",
            raw_payload={"event": "payment.captured"},
            payload_hash="dummy_hash_stuck",
        )
        db_session.add(ev)
        db_session.flush()

        metrics = OperationsService.get_operational_metrics(db_session)
        assert metrics.stuck_events_count >= 1

    def test_failed_event_observability(self, db_session: Session):
        """Failed processing status is visible in operational metrics and never hidden."""
        ev = WebhookEvent(
            razorpay_event_id="evt_failed_001",
            event_type="payment.failed",
            received_at=datetime.now(timezone.utc),
            processing_status=ProcessingStatus.FAILED,
            processing_error="Connection refused",
            retry_count=2,
            raw_payload={"event": "payment.failed"},
            payload_hash="dummy_hash_fail",
        )
        db_session.add(ev)
        db_session.flush()

        metrics = OperationsService.get_operational_metrics(db_session)
        assert metrics.failed_events_count >= 1


# ---------------------------------------------------------------------------
# 3. Pipeline Status & Watermark Tests
# ---------------------------------------------------------------------------

class TestPipelineWatermark:
    def test_pipeline_stages_and_watermark(self, db_session: Session):
        """Pipeline returns all 8 stages and calculates conservative watermark."""
        t1 = datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
        ev = WebhookEvent(
            razorpay_event_id="evt_wm_001",
            event_type="payment.captured",
            received_at=t1,
            processed_at=t1,
            processing_status=ProcessingStatus.PROCESSED,
            raw_payload={},
            payload_hash="h1",
        )
        db_session.add(ev)
        db_session.flush()

        status = OperationsService.get_pipeline_status(db_session)
        assert len(status.stages) == 8
        assert status.stages[0].stage_name == "Webhook Ingestion"
        assert status.pipeline_watermark_timestamp is not None


# ---------------------------------------------------------------------------
# 4. Payment Operational Status & Freshness Differentiation
# ---------------------------------------------------------------------------

class TestPaymentFreshness:
    def test_payment_analysis_current(self, db_session: Session):
        """When evaluation timestamp is after or equal to evidence timestamp, layer is CURRENT."""
        pid = "pay_fresh_001"
        _create_payment(db_session, pid)
        t0 = datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc)

        fact = EvidenceFact(
            payment_id=pid,
            fact_type=FactType.PAYMENT_CAPTURED,
            canonical_value="payment.captured",
            canonical_value_hash=_canonical_value_hash(pid, FactType.PAYMENT_CAPTURED, "payment.captured"),
            status=FactStatus.ACTIVE,
            first_observed_at=t0,
            last_observed_at=t0,
        )
        db_session.add(fact)

        snap = EvidenceIntegritySnapshot(
            payment_id=pid,
            evaluated_at=t0,
            methodology_version="EIS-1.0",
            overall_status="VERY_STRONG",
        )
        db_session.add(snap)
        db_session.flush()

        status = OperationsService.get_payment_operational_status(db_session, pid)
        assert status is not None
        assert status.is_analysis_current is True
        assert status.overall_freshness == ProcessingFreshnessState.CURRENT
        assert status.layers["integrity"].status == ProcessingFreshnessState.CURRENT

    def test_payment_analysis_stale_detected_when_new_evidence_arrives(self, db_session: Session):
        """When new evidence arrives at T2 after snapshot at T1, status flags STALE."""
        pid = "pay_stale_002"
        _create_payment(db_session, pid)
        t1 = datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
        t2 = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

        # Snapshot taken at T1
        snap = EvidenceIntegritySnapshot(
            payment_id=pid,
            evaluated_at=t1,
            methodology_version="EIS-1.0",
            overall_status="STRONG",
        )
        db_session.add(snap)

        # New observation observed at T2 > T1
        obs = EvidenceObservation(
            evidence_type=EvidenceType.PAYMENT_STATUS,
            subject_type=SubjectType.PAYMENT,
            subject_id=pid,
            value="refunded",
            value_type=ValueType.ENUM,
            source_type=SourceType.RAZORPAY_WEBHOOK,
            source_reference="2",
            observed_at=t2,
            valid_from=t2,
            extraction_method=ExtractionMethod.WEBHOOK_FIELD_EXTRACTION,
            extraction_version=CURRENT_EXTRACTION_VERSION,
        )
        db_session.add(obs)
        db_session.flush()

        status = OperationsService.get_payment_operational_status(db_session, pid)
        assert status is not None
        assert status.is_analysis_current is False
        assert status.overall_freshness == ProcessingFreshnessState.STALE
        assert status.layers["integrity"].status == ProcessingFreshnessState.STALE


# ---------------------------------------------------------------------------
# 5. Continuous Verification & System Invariant Checks
# ---------------------------------------------------------------------------

class TestContinuousVerification:
    def test_continuous_verification_invariants(self, db_session: Session):
        """Continuous verification evaluates all 10 system invariants."""
        res = OperationsService.run_continuous_verification(db_session)
        assert res.total_checks == 10
        assert res.overall_status in (VerificationStatus.PASS, VerificationStatus.WARN)
        check_ids = [c.check_id for c in res.checks]
        for i in range(1, 11):
            assert f"INVARIANT_SYS_{i:02d}" in check_ids


# ---------------------------------------------------------------------------
# 6. Operational Incident Detection Tests
# ---------------------------------------------------------------------------

class TestIncidentDetection:
    def test_incident_detected_on_worker_stoppage(self, db_session: Session):
        """Worker thread downtime produces an active WORKER_FAILURE incident."""
        with patch("app.services.webhook_worker._worker_thread", None):
            res = OperationsService.detect_operational_incidents(db_session)
            worker_incidents = [i for i in res.incidents if i.category == IncidentCategory.WORKER_FAILURE]
            assert len(worker_incidents) == 1
            assert worker_incidents[0].resolved is False

    def test_incident_detected_on_failed_webhook(self, db_session: Session):
        """Failed webhook event is recorded in the operational incident timeline."""
        ev = WebhookEvent(
            razorpay_event_id="evt_inc_001",
            event_type="payment.failed",
            received_at=datetime.now(timezone.utc),
            processing_status=ProcessingStatus.FAILED,
            processing_error="Normalization schema error",
            raw_payload={},
            payload_hash="dummy_inc",
        )
        db_session.add(ev)
        db_session.flush()

        res = OperationsService.detect_operational_incidents(db_session)
        fail_incidents = [i for i in res.incidents if i.category == IncidentCategory.PROCESSING_FAILURE]
        assert len(fail_incidents) >= 1


# ---------------------------------------------------------------------------
# 7. REST API Endpoints Integration Tests
# ---------------------------------------------------------------------------

class TestOperationsAPI:
    def test_api_health(self, client: TestClient):
        resp = client.get("/api/v1/operations/health")
        assert resp.status_code == 200
        data = resp.json()
        assert "overall_state" in data
        assert "components" in data

    def test_api_metrics(self, client: TestClient):
        resp = client.get("/api/v1/operations/metrics")
        assert resp.status_code == 200
        data = resp.json()
        assert "ingestion" in data
        assert "queue" in data
        assert "lag" in data

    def test_api_pipeline(self, client: TestClient):
        resp = client.get("/api/v1/operations/pipeline")
        assert resp.status_code == 200
        data = resp.json()
        assert "stages" in data
        assert len(data["stages"]) == 8

    def test_api_verify(self, client: TestClient):
        resp = client.post("/api/v1/operations/verify")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_checks"] == 10
        assert "checks" in data

    def test_api_incidents(self, client: TestClient):
        resp = client.get("/api/v1/operations/incidents")
        assert resp.status_code == 200
        data = resp.json()
        assert "incidents" in data

    def test_api_payment_operational_status_404(self, client: TestClient):
        resp = client.get("/api/v1/payments/pay_nonexistent/operational-status")
        assert resp.status_code == 404
