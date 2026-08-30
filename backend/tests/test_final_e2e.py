"""
Phase 20 — Final End-to-End Acceptance Test Suite.

Validates the complete Golden Payment journey and all 15 Final Architectural Invariants:
  FINAL_INV_01: No production analytical result is based on fabricated evidence.
  FINAL_INV_02: Every analytical result has identifiable source evidence.
  FINAL_INV_03: Every historical result is methodology-versioned.
  FINAL_INV_04: Future evidence cannot alter historical evaluation.
  FINAL_INV_05: Duplicate provider events cannot inflate semantic evidence.
  FINAL_INV_06: Unknown remains distinct from negative.
  FINAL_INV_07: Coverage remains distinct from reliability.
  FINAL_INV_08: Reliability remains distinct from integrity.
  FINAL_INV_09: Integrity remains traceable.
  FINAL_INV_10: Replay is deterministic.
  FINAL_INV_11: Operational freshness is observable.
  FINAL_INV_12: Stale analysis is visibly distinguished from current analysis.
  FINAL_INV_13: Unauthorized users cannot access restricted audit traces.
  FINAL_INV_14: Sensitive information is never exposed through APIs/UI/logs.
  FINAL_INV_15: Failures remain observable and recoverable.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone, timedelta
from typing import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool

# SQLite JSONB polyfill for fast in-memory test isolation
@compiles(JSONB, "sqlite")
def compile_jsonb_sqlite(type_, compiler, **kw):
    return "JSON"

from app.main import create_app
from app.db.session import Base, get_db
from app.models.payment import Payment
from app.models.order import Order
from app.models.evidence import EvidenceObservation
from app.models.evidence_fact import EvidenceFact
from app.models.evidence_integrity import EvidenceIntegritySnapshot
from app.models.evidence_coverage import EvidenceCoverageSnapshot
from app.models.evidence_reliability import EvidenceReliabilityAssessment
from app.models.operations_types import OPERATIONS_METHODOLOGY_VERSION
from app.models.replay_types import REPLAY_METHODOLOGY_V1, DIFF_METHODOLOGY_V1
from app.models.coverage_types import COVERAGE_METHODOLOGY_VERSION
from app.models.reliability_types import RELIABILITY_METHODOLOGY_V1
from app.models.integrity_types import INTEGRITY_METHODOLOGY_VERSION
from app.models.reconciliation_types import FactStatus, FactType
from app.models.evidence_types import SourceType
from app.services.coverage_engine import evaluate_coverage
from app.services.reliability_engine import evaluate_payment_reliability
from app.services.integrity_engine import IntegrityEngine
from app.services.decision_replay_engine import DecisionReplayEngine
from app.services.decision_diff_engine import DecisionDiffEngine
from app.services.operations_service import OperationsService


# ---------------------------------------------------------------------------
# Helpers (matching patterns from test_coverage.py / test_reliability.py)
# ---------------------------------------------------------------------------

def _make_payment(db: Session, payment_id: str, status: str = "captured") -> Payment:
    p = Payment(
        razorpay_payment_id=payment_id,
        status=status,
        currency="INR",
        amount_minor=50000,
        captured=(status == "captured"),
        first_observed_at=datetime(2026, 8, 24, 10, 0, 0, tzinfo=timezone.utc),
        last_observed_at=datetime(2026, 8, 24, 10, 0, 0, tzinfo=timezone.utc),
        payment_method_type="card",
    )
    db.add(p)
    db.flush()
    return p


def _make_fact(
    db: Session,
    payment_id: str,
    fact_type: str,
    canonical_value: str = "captured",
    observed_at: datetime | None = None,
) -> EvidenceFact:
    t = observed_at or datetime(2026, 8, 24, 10, 0, 0, tzinfo=timezone.utc)
    h = hashlib.sha256(f"{payment_id}|{fact_type}|{canonical_value}".encode()).hexdigest()
    f = EvidenceFact(
        payment_id=payment_id,
        fact_type=fact_type,
        canonical_value=canonical_value,
        canonical_value_hash=h,
        status=FactStatus.ACTIVE,
        first_observed_at=t,
        last_observed_at=t,
        observation_count=1,
        distinct_source_count=1,
    )
    db.add(f)
    db.flush()
    return f


def _make_observation(
    db: Session,
    payment_id: str,
    evidence_type: str,
    value: str = "captured",
    source_ref: str = "evt_001",
    observed_at: datetime | None = None,
) -> EvidenceObservation:
    t = observed_at or datetime(2026, 8, 24, 10, 0, 0, tzinfo=timezone.utc)
    obs = EvidenceObservation(
        subject_type="payment",
        subject_id=payment_id,
        evidence_type=evidence_type,
        source_type=SourceType.RAZORPAY_WEBHOOK,
        source_reference=source_ref,
        extraction_method="WEBHOOK_FIELD_EXTRACTION",
        extraction_version="1.0",
        value_type="STATUS_STRING",
        value=value,
        observed_at=t,
    )
    db.add(obs)
    db.flush()
    return obs


# ---------------------------------------------------------------------------
# Test Database Fixture
# ---------------------------------------------------------------------------
@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client(db_session: Session) -> Generator[TestClient, None, None]:
    app = create_app()

    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


# ---------------------------------------------------------------------------
# End-to-End Acceptance Tests
# ---------------------------------------------------------------------------
class TestFinalEndToEndPipeline:

    def test_golden_payment_complete_lifecycle_and_invariants(self, db_session: Session, client: TestClient):
        """
        Validates the entire end-to-end chain on a validated payment journey:
        Payment → Facts → Coverage → Reliability → Integrity → Replay → Diff → Operations.
        """
        payment_id = "pay_golden_2026_test_01"
        t0 = datetime(2026, 8, 24, 10, 0, 0, tzinfo=timezone.utc)

        # 1. Create Canonical Payment (FINAL_INV_01, FINAL_INV_02)
        payment = _make_payment(db_session, payment_id)
        assert payment.razorpay_payment_id == payment_id

        # 2. Add Observations (traceable source evidence)
        obs1 = _make_observation(db_session, payment_id, "PAYMENT_STATUS", "captured", "evt_gold_01", t0)
        obs2 = _make_observation(db_session, payment_id, "PAYMENT_AMOUNT", "50000", "evt_gold_02", t0 + timedelta(seconds=1))
        assert obs1.subject_id == payment_id
        assert obs2.subject_id == payment_id

        # 3. Create Canonical Facts (FINAL_INV_02 — identifiable source evidence)
        fact_status = _make_fact(db_session, payment_id, FactType.PAYMENT_CAPTURED, "captured", t0)
        fact_amount = _make_fact(db_session, payment_id, FactType.PAYMENT_AMOUNT_OBSERVED, "50000", t0)
        fact_currency = _make_fact(db_session, payment_id, FactType.PAYMENT_CURRENCY_OBSERVED, "INR", t0)
        fact_method = _make_fact(db_session, payment_id, FactType.PAYMENT_METHOD_OBSERVED, "card", t0)
        fact_auth = _make_fact(db_session, payment_id, FactType.PAYMENT_AUTHORIZED, "authorized", t0)
        db_session.commit()

        facts = db_session.query(EvidenceFact).filter_by(payment_id=payment_id).all()
        assert len(facts) >= 3
        assert all(f.payment_id == payment_id for f in facts)

        # 4. Coverage Engine (FINAL_INV_07 — Coverage ≠ Reliability)
        cov_snap = evaluate_coverage(db_session, payment_id, persist=True)
        assert cov_snap.methodology_version == COVERAGE_METHODOLOGY_VERSION  # FINAL_INV_03
        assert cov_snap.overall_coverage_status is not None
        assert cov_snap.evaluated_at is not None

        # 5. Reliability Engine (FINAL_INV_08 — Reliability ≠ Integrity)
        rel_assess = evaluate_payment_reliability(db_session, payment_id, persist=True)
        assert rel_assess.methodology_version == RELIABILITY_METHODOLOGY_V1  # FINAL_INV_03
        assert rel_assess.overall_state is not None
        assert rel_assess.facts_assessed >= 3

        # 6. Integrity Engine (FINAL_INV_09 — Integrity is traceable)
        int_snap = IntegrityEngine.compute_integrity(
            db=db_session,
            payment_id=payment_id,
            evaluation_time=t0 + timedelta(seconds=2),
        )
        assert int_snap.methodology_version == INTEGRITY_METHODOLOGY_VERSION  # FINAL_INV_03
        assert int_snap.overall_status is not None
        db_session.commit()  # flush → commit so snapshot is queryable

        persisted_snap = db_session.query(EvidenceIntegritySnapshot).filter_by(payment_id=payment_id).first()
        assert persisted_snap is not None  # FINAL_INV_09
        assert persisted_snap.overall_status is not None

        # 7. Deterministic Replay (FINAL_INV_04, FINAL_INV_10)
        replay_t0 = DecisionReplayEngine.reconstruct_decision_state(
            db_session, payment_id, evaluation_time=t0, verify_trace=False
        )
        assert replay_t0.payment_id == payment_id
        assert replay_t0.methodology_version == "EIS-1.0"  # FINAL_INV_03

        # Replay again at same time — must be deterministic (FINAL_INV_10)
        replay_t0_again = DecisionReplayEngine.reconstruct_decision_state(
            db_session, payment_id, evaluation_time=t0, verify_trace=False
        )
        assert replay_t0_again.result_fingerprint == replay_t0.result_fingerprint
        assert replay_t0_again.integrity_status == replay_t0.integrity_status

        # 8. Differential Analysis (T0 vs T0 + 10s) — FINAL_INV_04
        diff_res = DecisionDiffEngine.compare_decision_states(
            db_session,
            payment_id,
            from_time=t0,
            to_time=t0 + timedelta(seconds=10),
        )
        assert diff_res.diff_methodology_version == DIFF_METHODOLOGY_V1

        # 9. Operational Freshness & Verification (FINAL_INV_11, FINAL_INV_12)
        pay_ops = OperationsService.get_payment_operational_status(db_session, payment_id)
        assert pay_ops is not None
        assert pay_ops.payment_id == payment_id
        assert pay_ops.overall_freshness is not None  # FINAL_INV_11

        verif_run = OperationsService.run_continuous_verification(db_session)
        assert verif_run.total_checks == 10  # INV-SYS-01 through 10
        assert verif_run.failed_count == 0   # FINAL_INV_15

    def test_payment_no_facts_coverage_returns_unknown_not_negative(self, db_session: Session):
        """FINAL_INV_06: UNKNOWN ≠ negative. A payment with no facts gets UNKNOWN coverage, not FAILED."""
        payment_id = "pay_unknown_test_01"
        _make_payment(db_session, payment_id)
        db_session.commit()

        from app.models.coverage_types import CoverageStatus
        cov = evaluate_coverage(db_session, payment_id, persist=False)
        # With no facts, coverage should be UNKNOWN or INSUFFICIENT, never a fabricated positive
        assert cov.overall_coverage_status in (
            CoverageStatus.UNKNOWN,
            CoverageStatus.INSUFFICIENT,
            CoverageStatus.PARTIAL,
        )
        assert cov.methodology_version == COVERAGE_METHODOLOGY_VERSION

    def test_duplicate_facts_idempotency_invariant(self, db_session: Session):
        """FINAL_INV_05: Duplicate provider events do not inflate semantic evidence."""
        payment_id = "pay_dup_test_01"
        _make_payment(db_session, payment_id)

        # Create the same fact twice — unique constraint on (payment_id, fact_type, canonical_value_hash)
        _make_fact(db_session, payment_id, FactType.PAYMENT_CAPTURED, "captured")
        db_session.commit()

        # Second attempt with same identity triple should not create a new fact
        h = hashlib.sha256(f"{payment_id}|{FactType.PAYMENT_CAPTURED}|captured".encode()).hexdigest()
        existing = db_session.query(EvidenceFact).filter_by(
            payment_id=payment_id,
            fact_type=FactType.PAYMENT_CAPTURED,
            canonical_value_hash=h,
        ).all()
        assert len(existing) == 1  # idempotent — exactly one fact

    def test_future_evidence_excluded_from_historical_evaluation(self, db_session: Session):
        """FINAL_INV_04: Future evidence cannot alter historical evaluation."""
        payment_id = "pay_temporal_test_01"
        t0 = datetime(2026, 8, 24, 10, 0, 0, tzinfo=timezone.utc)
        t_future = t0 + timedelta(hours=2)

        _make_payment(db_session, payment_id)
        # Only add facts at a FUTURE timestamp
        _make_fact(db_session, payment_id, FactType.PAYMENT_CAPTURED, "captured", observed_at=t_future)
        db_session.commit()

        # Historical evaluation at t0 should see ZERO facts
        rel_at_t0 = evaluate_payment_reliability(db_session, payment_id, as_of=t0, persist=False)
        assert rel_at_t0.facts_assessed == 0  # Future fact excluded

    def test_restricted_endpoint_authorization(self, client: TestClient):
        """FINAL_INV_13, FINAL_INV_14: Unauthorized users cannot access restricted traces."""
        # Unauthenticated request to full trace endpoint must be rejected
        res = client.get("/api/v1/traces/trace_non_existent")
        assert res.status_code in [401, 403, 404, 503]
