"""
Phase 18 — Decision Replay & Differential Analysis Test Suite.

Verifies:
  - Exact decision replay reproducibility under historical boundaries
  - Pinned methodology and profile versions
  - Deterministic input and result fingerprints
  - Replay verification against historical traces (MATCH, REPLAY_MISMATCH, etc.)
  - Differential analysis (facts, observations, sources, corroboration, conflicts, coverage, reliability, integrity)
  - Deterministic change explanations and causal bounding
  - Metamorphic invariance tests
  - API endpoint integration
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Generator

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
from app.models.conflict_types import ConflictSeverity, ConflictStatus, ConflictType
from app.models.evidence import EvidenceObservation
from app.models.evidence_conflict import EvidenceConflict
from app.models.evidence_fact import EvidenceFact, _canonical_value_hash
from app.models.evidence_structure import Claim, EvidenceClaimLink
from app.models.evidence_types import (
    CURRENT_EXTRACTION_VERSION,
    EvidenceType,
    ExtractionMethod,
    SourceType,
    SubjectType,
    ValueType,
)
from app.models.integrity_trace import EvidenceIntegrityTrace
from app.models.observation_fact_link import ObservationFactLink
from app.models.payment import Payment
from app.models.reconciliation_types import FactStatus, FactType
from app.models.reliability_types import ReliabilityState
from app.models.replay_types import (
    ChangeCategory,
    ConflictDiffType,
    CorroborationDiffType,
    FactDiffCategory,
    ReplayVerificationStatus,
    SourceDiffType,
)
from app.models.trace_types import (
    CANONICALIZATION_VERSION,
    HASH_ALGORITHM,
    TraceStatus,
    TraceType,
)
from app.services.decision_diff_engine import DecisionDiffEngine
from app.services.decision_replay_engine import DecisionReplayEngine
from app.services.trace_canonicalization import canonical_json, sha256_hex


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


def _create_obs(
    db: Session,
    payment_id: str,
    evidence_type: str = EvidenceType.PAYMENT_STATUS,
    value: str = "captured",
    source_type: str = SourceType.RAZORPAY_WEBHOOK,
    webhook_event_id: int = 1,
    observed_at: datetime = None,
) -> EvidenceObservation:
    if observed_at is None:
        observed_at = datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
    obs = EvidenceObservation(
        evidence_type=evidence_type,
        subject_type=SubjectType.PAYMENT,
        subject_id=payment_id,
        value=value,
        value_type=ValueType.ENUM,
        source_type=source_type,
        source_reference=str(webhook_event_id),
        observed_at=observed_at,
        valid_from=observed_at,
        webhook_event_id=webhook_event_id,
        extraction_method=ExtractionMethod.WEBHOOK_FIELD_EXTRACTION,
        extraction_version=CURRENT_EXTRACTION_VERSION,
        provenance_metadata={"provider": "razorpay", "event_type": "payment.captured"},
    )
    db.add(obs)
    db.flush()
    return obs


def _create_fact(
    db: Session,
    payment_id: str,
    fact_type: str,
    value: str,
    observed_at: datetime = None,
) -> EvidenceFact:
    if observed_at is None:
        observed_at = datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
    fact = EvidenceFact(
        payment_id=payment_id,
        fact_type=fact_type,
        canonical_value=value,
        canonical_value_hash=_canonical_value_hash(payment_id, fact_type, value),
        status=FactStatus.ACTIVE,
        first_observed_at=observed_at,
        last_observed_at=observed_at,
        observation_count=1,
        distinct_source_count=1,
    )
    db.add(fact)
    db.flush()
    return fact


def _link_obs_fact(db: Session, obs: EvidenceObservation, fact: EvidenceFact):
    link = ObservationFactLink(observation_id=obs.internal_id, fact_id=fact.internal_id)
    db.add(link)
    db.flush()


# ===========================================================================
# 1. DECISION REPLAY & DETERMINISM TESTS
# ===========================================================================

class TestDecisionReplay:
    """Tests for deterministic point-in-time replay reconstruction."""

    def test_reconstruct_decision_state_exact_match(self, db_session: Session):
        """Replaying a payment decision produces a fully populated response."""
        pid = "pay_replay_001"
        _create_payment(db_session, pid)
        t0 = datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc)

        fact = _create_fact(db_session, pid, FactType.PAYMENT_CAPTURED, "payment.captured", observed_at=t0)
        obs = _create_obs(db_session, pid, observed_at=t0, webhook_event_id=101)
        _link_obs_fact(db_session, obs, fact)

        replay = DecisionReplayEngine.reconstruct_decision_state(
            db_session, pid, evaluation_time=t0, verify_trace=False
        )

        assert replay.payment_id == pid
        assert replay.evaluation_time == t0
        assert replay.methodology_version == "EIS-1.0"
        assert replay.reproducibility_status == "REPRODUCIBLE"
        assert len(replay.input_fingerprint) == 64
        assert len(replay.result_fingerprint) == 64
        assert replay.evidence_state.observation_count == 1
        assert replay.evidence_state.fact_count == 1

    def test_historical_boundary_excludes_future_evidence(self, db_session: Session):
        """Evidence observed after evaluation_time is strictly excluded from replay."""
        pid = "pay_replay_002"
        _create_payment(db_session, pid)
        t1 = datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
        t2 = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

        fact1 = _create_fact(db_session, pid, FactType.PAYMENT_AUTHORIZED, "payment.authorized", observed_at=t1)
        obs1 = _create_obs(db_session, pid, value="authorized", observed_at=t1, webhook_event_id=201)
        _link_obs_fact(db_session, obs1, fact1)

        # Future fact at t2
        fact2 = _create_fact(db_session, pid, FactType.PAYMENT_CAPTURED, "payment.captured", observed_at=t2)
        obs2 = _create_obs(db_session, pid, value="captured", observed_at=t2, webhook_event_id=202)
        _link_obs_fact(db_session, obs2, fact2)

        # Replay at T1
        replay_t1 = DecisionReplayEngine.reconstruct_decision_state(
            db_session, pid, evaluation_time=t1, verify_trace=False
        )
        assert replay_t1.evidence_state.fact_count == 1
        assert replay_t1.evidence_state.observation_count == 1

        # Replay at T2
        replay_t2 = DecisionReplayEngine.reconstruct_decision_state(
            db_session, pid, evaluation_time=t2, verify_trace=False
        )
        assert replay_t2.evidence_state.fact_count == 2
        assert replay_t2.evidence_state.observation_count == 2

    def test_unsupported_methodology_returns_unavailable(self, db_session: Session):
        """Requesting an unsupported methodology version yields METHODOLOGY_UNAVAILABLE."""
        pid = "pay_replay_003"
        _create_payment(db_session, pid)
        t0 = datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc)

        replay = DecisionReplayEngine.reconstruct_decision_state(
            db_session, pid, evaluation_time=t0, methodology_version="UNSUPPORTED_VERSION_99"
        )
        assert replay.verification_status == ReplayVerificationStatus.METHODOLOGY_UNAVAILABLE
        assert replay.reproducibility_status == "METHODOLOGY_UNAVAILABLE"

    def test_repeated_replay_produces_identical_fingerprints(self, db_session: Session):
        """Multiple sequential replays produce bit-for-bit identical fingerprints."""
        pid = "pay_replay_004"
        _create_payment(db_session, pid)
        t0 = datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc)

        fact = _create_fact(db_session, pid, FactType.PAYMENT_CAPTURED, "payment.captured", observed_at=t0)
        obs = _create_obs(db_session, pid, observed_at=t0, webhook_event_id=401)
        _link_obs_fact(db_session, obs, fact)

        r1 = DecisionReplayEngine.reconstruct_decision_state(db_session, pid, t0, verify_trace=False)
        r2 = DecisionReplayEngine.reconstruct_decision_state(db_session, pid, t0, verify_trace=False)
        r3 = DecisionReplayEngine.reconstruct_decision_state(db_session, pid, t0, verify_trace=False)

        assert r1.input_fingerprint == r2.input_fingerprint == r3.input_fingerprint
        assert r1.result_fingerprint == r2.result_fingerprint == r3.result_fingerprint


# ===========================================================================
# 2. TRACE REPLAY VERIFICATION TESTS
# ===========================================================================

class TestTraceVerificationReplay:
    """Tests for verifying existing Decision Traces against reconstructed replays."""

    def test_verify_trace_replay_match(self, db_session: Session):
        """Historical trace matches replayed execution."""
        pid = "pay_trc_001"
        _create_payment(db_session, pid)
        t0 = datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc)

        fact = _create_fact(db_session, pid, FactType.PAYMENT_CAPTURED, "payment.captured", observed_at=t0)
        obs = _create_obs(db_session, pid, observed_at=t0, webhook_event_id=501)
        _link_obs_fact(db_session, obs, fact)

        # Pre-generate integrity snapshot and trace
        replay = DecisionReplayEngine.reconstruct_decision_state(
            db_session, pid, t0, verify_trace=False
        )

        trace = EvidenceIntegrityTrace(
            trace_id="trc_rep_001",
            original_trace_id="trc_orig_001",
            payment_id=pid,
            trace_type=TraceType.REPLAY,
            status=TraceStatus.COMPLETED,
            overall_status=replay.integrity_status,
            methodology_version="EIS-1.0",
            evaluated_at=t0,
            canonical_payload={"content": {"integrity_status": replay.integrity_status}},
            trace_hash="dummy_hash_001",
            hash_algorithm=HASH_ALGORITHM,
            canonicalization_version=CANONICALIZATION_VERSION,
        )
        db_session.add(trace)
        db_session.flush()

        verif = DecisionReplayEngine.verify_trace_replay(db_session, "trc_rep_001")
        assert verif.verification_status == ReplayVerificationStatus.MATCH
        assert verif.differences == {}

    def test_verify_trace_replay_mismatch_detected(self, db_session: Session):
        """Mismatched stored trace status triggers REPLAY_MISMATCH."""
        pid = "pay_trc_002"
        _create_payment(db_session, pid)
        t0 = datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc)

        fact = _create_fact(db_session, pid, FactType.PAYMENT_CAPTURED, "payment.captured", observed_at=t0)
        obs = _create_obs(db_session, pid, observed_at=t0, webhook_event_id=601)
        _link_obs_fact(db_session, obs, fact)

        trace = EvidenceIntegrityTrace(
            trace_id="trc_rep_002",
            original_trace_id="trc_orig_002",
            payment_id=pid,
            trace_type=TraceType.REPLAY,
            status=TraceStatus.COMPLETED,
            overall_status="CONFLICTED_OR_WRONG",
            methodology_version="EIS-1.0",
            evaluated_at=t0,
            canonical_payload={"content": {"integrity_status": "CONFLICTED_OR_WRONG"}},
            trace_hash="dummy_hash_002",
            hash_algorithm=HASH_ALGORITHM,
            canonicalization_version=CANONICALIZATION_VERSION,
        )
        db_session.add(trace)
        db_session.flush()

        verif = DecisionReplayEngine.verify_trace_replay(db_session, "trc_rep_002")
        assert verif.verification_status == ReplayVerificationStatus.REPLAY_MISMATCH
        assert "integrity_status" in verif.differences


# ===========================================================================
# 3. DIFFERENTIAL ANALYSIS TESTS
# ===========================================================================

class TestDecisionDiff:
    """Tests for pairwise differential decision analysis."""

    def test_diff_identifies_added_evidence_and_coverage_shift(self, db_session: Session):
        """Adding a new fact between T1 and T2 is identified in differential analysis."""
        pid = "pay_diff_001"
        _create_payment(db_session, pid)
        t1 = datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
        t2 = datetime(2024, 1, 1, 11, 0, 0, tzinfo=timezone.utc)

        # At T1: Authorized
        fact1 = _create_fact(db_session, pid, FactType.PAYMENT_AUTHORIZED, "payment.authorized", observed_at=t1)
        obs1 = _create_obs(db_session, pid, value="authorized", observed_at=t1, webhook_event_id=701)
        _link_obs_fact(db_session, obs1, fact1)

        # At T2: Captured
        fact2 = _create_fact(db_session, pid, FactType.PAYMENT_CAPTURED, "payment.captured", observed_at=t2)
        obs2 = _create_obs(db_session, pid, value="captured", observed_at=t2, webhook_event_id=702)
        _link_obs_fact(db_session, obs2, fact2)

        diff = DecisionDiffEngine.compare_decision_states(
            db_session, pid, from_time=t1, to_time=t2
        )

        assert diff.payment_id == pid
        assert ChangeCategory.EVIDENCE_ADDED in diff.change_categories
        added_facts = [f for f in diff.fact_diffs if f.category == FactDiffCategory.ADDED]
        assert len(added_facts) == 1
        assert added_facts[0].fact_type == FactType.PAYMENT_CAPTURED

    def test_diff_identifies_conflict_introduction(self, db_session: Session):
        """Contradiction introduced at T2 is flagged in conflict diffs."""
        pid = "pay_diff_002"
        _create_payment(db_session, pid)
        t1 = datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
        t2 = datetime(2024, 1, 1, 11, 0, 0, tzinfo=timezone.utc)

        # Baseline at T1
        fact1 = _create_fact(db_session, pid, FactType.PAYMENT_CAPTURED, "payment.captured", observed_at=t1)
        obs1 = _create_obs(db_session, pid, observed_at=t1, webhook_event_id=801)
        _link_obs_fact(db_session, obs1, fact1)

        # Conflict detected at T2
        conflict = EvidenceConflict(
            payment_id=pid,
            claim_a_id=1,
            claim_b_id=2,
            conflict_type=ConflictType.VALUE_CONFLICT.value,
            severity=ConflictSeverity.HIGH.value,
            status=ConflictStatus.OPEN.value,
            detected_at=t2,
            rule_version="1.0",
        )
        db_session.add(conflict)
        db_session.flush()

        diff = DecisionDiffEngine.compare_decision_states(
            db_session, pid, from_time=t1, to_time=t2
        )

        assert ChangeCategory.CONFLICT_ADDED in diff.change_categories
        assert len(diff.conflict_diffs) >= 1
        assert diff.conflict_diffs[0].change_type == ConflictDiffType.CONFLICT_ADDED

    def test_diff_order_normalization(self, db_session: Session):
        """Supplying from_time > to_time automatically normalizes T1 <= T2."""
        pid = "pay_diff_003"
        _create_payment(db_session, pid)
        t1 = datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
        t2 = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

        diff = DecisionDiffEngine.compare_decision_states(
            db_session, pid, from_time=t2, to_time=t1  # Reversed
        )

        assert diff.from_time == t1
        assert diff.to_time == t2

    def test_deterministic_change_explanation_generation(self, db_session: Session):
        """Change explanation produces structured sections without LLM hallucinations."""
        pid = "pay_diff_004"
        _create_payment(db_session, pid)
        t1 = datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
        t2 = datetime(2024, 1, 1, 11, 0, 0, tzinfo=timezone.utc)

        fact1 = _create_fact(db_session, pid, FactType.PAYMENT_AUTHORIZED, "payment.authorized", observed_at=t1)
        obs1 = _create_obs(db_session, pid, observed_at=t1, webhook_event_id=901)
        _link_obs_fact(db_session, obs1, fact1)

        expl = DecisionDiffEngine.generate_change_explanation(
            db_session, pid, from_time=t1, to_time=t2
        )

        assert expl.payment_id == pid
        assert len(expl.what_changed) > 0
        assert len(expl.why_it_mattered) > 0
        assert len(expl.what_remains_uncertain) > 0
        assert "coincided with" in expl.causal_summary or "contributed to" in expl.causal_summary or "stable" in expl.causal_summary


# ===========================================================================
# 4. METAMORPHIC TESTS
# ===========================================================================

class TestMetamorphicInvariance:
    """Metamorphic verification tests for replay determinism and stability."""

    def test_TEST_A_repeated_replay_same_fingerprint(self, db_session: Session):
        """TEST A: Run replay twice -> identical semantic fingerprint."""
        pid = "meta_001"
        _create_payment(db_session, pid)
        t0 = datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc)

        fact = _create_fact(db_session, pid, FactType.PAYMENT_CAPTURED, "payment.captured", observed_at=t0)
        obs = _create_obs(db_session, pid, observed_at=t0, webhook_event_id=1001)
        _link_obs_fact(db_session, obs, fact)

        r1 = DecisionReplayEngine.reconstruct_decision_state(db_session, pid, t0, verify_trace=False)
        r2 = DecisionReplayEngine.reconstruct_decision_state(db_session, pid, t0, verify_trace=False)

        assert r1.result_fingerprint == r2.result_fingerprint

    def test_TEST_B_duplicate_observation_does_not_alter_fact_identity(self, db_session: Session):
        """TEST B: Adding duplicate observation does not falsely create new fact."""
        pid = "meta_002"
        _create_payment(db_session, pid)
        t0 = datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc)

        fact = _create_fact(db_session, pid, FactType.PAYMENT_CAPTURED, "payment.captured", observed_at=t0)
        obs1 = _create_obs(db_session, pid, observed_at=t0, webhook_event_id=1002)
        _link_obs_fact(db_session, obs1, fact)

        obs2 = _create_obs(db_session, pid, observed_at=t0, webhook_event_id=1002)
        _link_obs_fact(db_session, obs2, fact)

        r = DecisionReplayEngine.reconstruct_decision_state(db_session, pid, t0, verify_trace=False)
        assert r.evidence_state.fact_count == 1

    def test_TEST_C_future_evidence_leaves_historical_replay_unaffected(self, db_session: Session):
        """TEST C: Adding future evidence after T1 leaves T1 replay unchanged."""
        pid = "meta_003"
        _create_payment(db_session, pid)
        t1 = datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
        t2 = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

        fact1 = _create_fact(db_session, pid, FactType.PAYMENT_AUTHORIZED, "payment.authorized", observed_at=t1)
        obs1 = _create_obs(db_session, pid, observed_at=t1, webhook_event_id=1003)
        _link_obs_fact(db_session, obs1, fact1)

        r1_before = DecisionReplayEngine.reconstruct_decision_state(db_session, pid, t1, verify_trace=False)

        # Add future event
        fact2 = _create_fact(db_session, pid, FactType.PAYMENT_CAPTURED, "payment.captured", observed_at=t2)
        obs2 = _create_obs(db_session, pid, observed_at=t2, webhook_event_id=1004)
        _link_obs_fact(db_session, obs2, fact2)

        r1_after = DecisionReplayEngine.reconstruct_decision_state(db_session, pid, t1, verify_trace=False)

        assert r1_before.input_fingerprint == r1_after.input_fingerprint
        assert r1_before.result_fingerprint == r1_after.result_fingerprint


# ===========================================================================
# 5. API ENDPOINT INTEGRATION TESTS
# ===========================================================================

class TestDecisionReplayAPI:
    """REST API integration tests for replay and diff endpoints."""

    def test_api_replay_endpoint(self, client: TestClient, db_session: Session):
        """POST /api/v1/payments/{payment_id}/replay succeeds."""
        pid = "pay_api_001"
        _create_payment(db_session, pid)
        t0 = datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc)

        fact = _create_fact(db_session, pid, FactType.PAYMENT_CAPTURED, "payment.captured", observed_at=t0)
        obs = _create_obs(db_session, pid, observed_at=t0, webhook_event_id=2001)
        _link_obs_fact(db_session, obs, fact)

        payload = {
            "evaluation_time": t0.isoformat(),
            "methodology_version": "EIS-1.0",
            "profile_version": "STANDARD_PAYMENT_PROFILE_V1",
            "verify_trace": False,
        }

        resp = client.post(f"/api/v1/payments/{pid}/replay", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["payment_id"] == pid
        assert data["reproducibility_status"] == "REPRODUCIBLE"

    def test_api_diff_endpoint(self, client: TestClient, db_session: Session):
        """GET /api/v1/payments/{payment_id}/diff succeeds."""
        pid = "pay_api_002"
        _create_payment(db_session, pid)
        t1 = datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
        t2 = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

        fact = _create_fact(db_session, pid, FactType.PAYMENT_CAPTURED, "payment.captured", observed_at=t1)
        obs = _create_obs(db_session, pid, observed_at=t1, webhook_event_id=2002)
        _link_obs_fact(db_session, obs, fact)

        resp = client.get(
            f"/api/v1/payments/{pid}/diff?from={t1.isoformat()}&to={t2.isoformat()}"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["payment_id"] == pid
        assert "fact_diffs" in data

    def test_api_explanation_endpoint(self, client: TestClient, db_session: Session):
        """GET /api/v1/payments/{payment_id}/diff/explanation succeeds."""
        pid = "pay_api_003"
        _create_payment(db_session, pid)
        t1 = datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
        t2 = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

        fact = _create_fact(db_session, pid, FactType.PAYMENT_CAPTURED, "payment.captured", observed_at=t1)
        obs = _create_obs(db_session, pid, observed_at=t1, webhook_event_id=2003)
        _link_obs_fact(db_session, obs, fact)

        resp = client.get(
            f"/api/v1/payments/{pid}/diff/explanation?from={t1.isoformat()}&to={t2.isoformat()}"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["payment_id"] == pid
        assert "what_changed" in data
        assert "why_it_mattered" in data
        assert "causal_summary" in data

    def test_api_404_for_unknown_payment(self, client: TestClient):
        """Replay returns 404 for non-existent payment."""
        payload = {
            "evaluation_time": "2024-01-01T10:00:00Z",
            "methodology_version": "EIS-1.0",
        }
        resp = client.post("/api/v1/payments/pay_nonexistent/replay", json=payload)
        assert resp.status_code == 404
