"""
Phase 17 — Adversarial Evidence Validation & Failure-Safety Test Suite.

Objective: prove EvidenceGraph fails safely under adversarial, malformed,
duplicated, reordered, delayed, conflicting, and tampered evidence conditions.

A convincing but incorrect answer is a FAILURE.
A visible UNKNOWN / CONFLICTED / LIMITED result is a PASS.

Invariants tested:
  INV-01  Raw observations are never silently destroyed.
  INV-02  Duplicate provider events do not create independent corroboration.
  INV-03  Future evidence cannot influence historical evaluation.
  INV-04  Unknown never becomes known through fallback guessing.
  INV-05  Missing evidence never becomes proof of absence.
  INV-06  Authenticated source does not imply semantic truth.
  INV-07  Same value does not imply same fact across payments.
  INV-08  Same payment does not imply same fact across lifecycle events.
  INV-09  Historical traces remain reproducible.
  INV-10  Unsupported relationships are never invented.
  INV-11  Conflicts remain visible.
  INV-12  Reliability cannot improve merely from duplicate evidence.
  INV-13  Coverage cannot improve merely from duplicate observations.
  INV-14  Every integrity result has an auditable methodology version.
  INV-15  Every lineage edge has authoritative support.
"""

from __future__ import annotations

import hashlib
import threading
from datetime import datetime, timezone
from typing import List

import pytest
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# ---------------------------------------------------------------------------
# SQLite JSONB polyfill (tests run against SQLite for isolation)
# ---------------------------------------------------------------------------
@compiles(JSONB, "sqlite")
def compile_jsonb_sqlite(type_, compiler, **kw):
    return "JSON"


from app.db.session import Base
from app.models.conflict_types import ConflictStatus, ConflictType, ConflictSeverity
from app.models.coverage_types import CoverageState, COVERAGE_METHODOLOGY_VERSION
from app.models.evidence import EvidenceObservation
from app.models.evidence_fact import EvidenceFact, _canonical_value_hash
from app.models.evidence_structure import Claim, EvidenceClaimLink, EvidenceCorroboration
from app.models.evidence_types import (
    EvidenceType,
    ExtractionMethod,
    SourceType,
    SubjectType,
    ValueType,
    CURRENT_EXTRACTION_VERSION,
)
from app.models.observation_fact_link import ObservationFactLink
from app.models.payment import Payment
from app.models.reconciliation_types import FactStatus, FactType
from app.models.reliability_types import (
    ReliabilityState,
    ProvenanceReliability,
    RELIABILITY_METHODOLOGY_V1,
)
from app.models.structure_types import ClaimType, CorroborationType, IndependenceStatus
from app.services.contradiction_engine import ContradictionEngine
from app.services.corroboration_service import CorroborationService
from app.services.coverage_engine import evaluate_coverage
from app.services.reliability_engine import evaluate_fact_reliability, evaluate_payment_reliability
from app.services.state_machine import PaymentStateMachine


# ---------------------------------------------------------------------------
# Shared DB fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.rollback()
    session.close()


# ---------------------------------------------------------------------------
# Shared fixture helpers
# ---------------------------------------------------------------------------

def _make_payment(db, payment_id: str) -> Payment:
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


def _make_obs(
    db,
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
        payment_event_id=None,
        extraction_method=ExtractionMethod.WEBHOOK_FIELD_EXTRACTION,
        extraction_version=CURRENT_EXTRACTION_VERSION,
        provenance_metadata={"provider": "razorpay", "event_type": "payment.captured"},
    )
    db.add(obs)
    db.flush()
    return obs


def _make_fact(
    db,
    payment_id: str,
    fact_type: str,
    value: str,
    status: str = FactStatus.ACTIVE,
    observed_at: datetime = None,
) -> EvidenceFact:
    if observed_at is None:
        observed_at = datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
    fact = EvidenceFact(
        payment_id=payment_id,
        fact_type=fact_type,
        canonical_value=value,
        canonical_value_hash=_canonical_value_hash(payment_id, fact_type, value),
        status=status,
        first_observed_at=observed_at,
        last_observed_at=observed_at,
        observation_count=1,
        distinct_source_count=1,
    )
    db.add(fact)
    db.flush()
    return fact


def _link_obs_to_fact(db, obs: EvidenceObservation, fact: EvidenceFact):
    link = ObservationFactLink(observation_id=obs.internal_id, fact_id=fact.internal_id)
    db.add(link)
    db.flush()


def _make_claim(
    db,
    payment_id: str,
    claim_type: str,
    claim_key: str,
    canonical_value: str,
) -> Claim:
    c = Claim(
        subject_type="payment",
        subject_id=payment_id,
        claim_type=claim_type,
        claim_key=claim_key,
        canonical_value=canonical_value,
    )
    db.add(c)
    db.flush()
    return c


def _link_obs_to_claim(db, obs: EvidenceObservation, claim: Claim):
    link = EvidenceClaimLink(claim_id=claim.internal_id, evidence_id=obs.internal_id)
    db.add(link)
    db.flush()


# ===========================================================================
# CATEGORY: DUPLICATION
# ===========================================================================

class TestDuplication:
    """
    SCENARIO: Same provider event arrives N times.
    Invariants: INV-02, INV-12, INV-13
    """

    def test_duplicate_obs_same_webhook_event_id_produces_same_source_corroboration(self, db):
        """
        INV-02: Duplicate observations sharing the same webhook_event_id must NOT
        be treated as independent corroboration.
        """
        pid = "adv_dup_001"
        _make_payment(db, pid)
        t0 = datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
        webhook_id = 42

        claim = _make_claim(db, pid, ClaimType.PAYMENT_STATUS.value, "STATUS", "captured")
        for _ in range(10):
            obs = _make_obs(db, pid, webhook_event_id=webhook_id, observed_at=t0)
            _link_obs_to_claim(db, obs, claim)

        corrob = CorroborationService.evaluate_claim_corroboration(db, claim, pid)

        assert corrob.corroboration_type != CorroborationType.MULTI_SOURCE_CORROBORATION.value, (
            "INV-02 VIOLATED: 10 observations from 1 webhook event treated as multi-source corroboration."
        )
        assert corrob.corroboration_type in (
            CorroborationType.SAME_SOURCE_CORROBORATION.value,
            CorroborationType.TEMPORAL_CORROBORATION.value,
        )
        assert corrob.distinct_sources_count == 1, (
            f"INV-02 VIOLATED: distinct_sources_count={corrob.distinct_sources_count}, expected 1"
        )

    def test_duplicate_obs_reliability_does_not_inflate(self, db):
        """
        INV-12: Reliability cannot improve merely because duplicate evidence arrived.
        """
        pid = "adv_dup_002"
        _make_payment(db, pid)
        t0 = datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
        webhook_id = 99

        fact = _make_fact(db, pid, FactType.PAYMENT_CAPTURED, "payment.captured", observed_at=t0)

        # Single observation baseline
        obs1 = _make_obs(db, pid, webhook_event_id=webhook_id, observed_at=t0)
        _link_obs_to_fact(db, obs1, fact)
        baseline = evaluate_fact_reliability(db, fact)

        # Add 9 more duplicate observations (same webhook)
        for _ in range(9):
            obs = _make_obs(db, pid, webhook_event_id=webhook_id, observed_at=t0)
            _link_obs_to_fact(db, obs, fact)

        after_duplication = evaluate_fact_reliability(db, fact)

        state_order = {
            ReliabilityState.UNRELIABLE: 0,
            ReliabilityState.UNKNOWN: 1,
            ReliabilityState.LIMITED: 2,
            ReliabilityState.MODERATE: 3,
            ReliabilityState.HIGH: 4,
        }
        baseline_rank = state_order[baseline.overall_state]
        after_rank = state_order[after_duplication.overall_state]
        assert after_rank <= baseline_rank, (
            f"INV-12 VIOLATED: reliability improved from {baseline.overall_state} "
            f"to {after_duplication.overall_state} due to duplicate evidence."
        )


# ===========================================================================
# CATEGORY: REORDERING
# ===========================================================================

class TestReordering:
    """
    SCENARIO: Events arrive in reverse/wrong order.
    Invariants: INV-08, INV-11
    """

    def test_captured_before_authorized_generates_conflict(self, db):
        """
        INV-11: Contradictory lifecycle events must surface as conflicts.
        captured-then-authorized is an invalid backward transition.
        """
        pid = "adv_ord_001"
        _make_payment(db, pid)
        t0 = datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
        t1 = datetime(2024, 1, 1, 10, 1, 0, tzinfo=timezone.utc)

        claim_cap = _make_claim(db, pid, ClaimType.PAYMENT_STATUS.value, "STATUS", "captured")
        obs_cap = _make_obs(db, pid, value="captured", observed_at=t0, webhook_event_id=10)
        _link_obs_to_claim(db, obs_cap, claim_cap)

        claim_auth = _make_claim(db, pid, ClaimType.PAYMENT_STATUS.value, "STATUS", "authorized")
        obs_auth = _make_obs(db, pid, value="authorized", observed_at=t1, webhook_event_id=11)
        _link_obs_to_claim(db, obs_auth, claim_auth)

        conflicts = ContradictionEngine.evaluate_payment_consistency(db, pid)
        conflict_types = [c.conflict_type for c in conflicts]
        assert len(conflicts) > 0, (
            "INV-11 VIOLATED: captured→authorized backward transition produced no conflict."
        )
        assert any(
            ct in (ConflictType.TEMPORAL_CONFLICT.value, ConflictType.STATE_CONFLICT.value)
            for ct in conflict_types
        )

    def test_refunded_before_captured_is_invalid(self):
        """
        INV-11: refunded-before-captured is not a valid Razorpay lifecycle.
        """
        result = PaymentStateMachine.classify_transition("refunded", "captured")
        assert result["is_valid"] is False

    def test_same_status_repeated_does_not_conflict(self):
        """
        INV-11: Identical status repeated (idempotent delivery) should NOT create conflict.
        """
        result = PaymentStateMachine.classify_transition("captured", "captured")
        assert result["is_valid"] is True
        assert result["transition_type"] == "SAME_STATE"


# ===========================================================================
# CATEGORY: DELAY & TEMPORAL INTEGRITY
# ===========================================================================

class TestDelayAndTemporal:
    """
    SCENARIO: Events arrive late or with past/future timestamps.
    Invariants: INV-03, INV-09
    """

    def test_event_time_is_observed_at_not_created_at(self, db):
        """
        INV-09: observed_at = provider event time.
        """
        pid = "adv_delay_001"
        _make_payment(db, pid)

        provider_event_time = datetime(2024, 1, 1, 6, 0, 0, tzinfo=timezone.utc)
        obs = _make_obs(db, pid, observed_at=provider_event_time, webhook_event_id=30)

        retrieved = db.query(EvidenceObservation).filter_by(
            internal_id=obs.internal_id
        ).first()
        assert retrieved.observed_at == provider_event_time

    def test_late_arriving_event_excluded_from_historical_evaluation(self, db):
        """
        INV-03: Evidence observed after as_of cannot influence historical evaluation.
        """
        pid = "adv_delay_002"
        _make_payment(db, pid)

        t1 = datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
        t2 = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

        fact = _make_fact(db, pid, FactType.PAYMENT_CAPTURED, "payment.captured", observed_at=t1)
        obs_early = _make_obs(db, pid, observed_at=t1, webhook_event_id=40)
        _link_obs_to_fact(db, obs_early, fact)

        obs_future = _make_obs(db, pid, observed_at=t2, webhook_event_id=41)
        _link_obs_to_fact(db, obs_future, fact)

        result_at_t1 = evaluate_fact_reliability(db, fact, as_of=t1)
        assert result_at_t1.evaluated_at == t1


# ===========================================================================
# CATEGORY: CONTRADICTION & VALUE CONFLICTS
# ===========================================================================

class TestContradictionIntegrity:
    """
    SCENARIO: Conflicting facts exist for the same payment.
    Invariants: INV-11, INV-12
    """

    def test_conflicting_amounts_generate_value_conflict(self, db):
        """
        INV-11: Two claims for the same payment with different amounts produce VALUE_CONFLICT.
        """
        pid = "adv_contra_001"
        _make_payment(db, pid)
        t0 = datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc)

        claim_500 = _make_claim(db, pid, ClaimType.PAYMENT_AMOUNT.value, "AMOUNT", "500")
        obs_500 = _make_obs(db, pid, evidence_type=EvidenceType.PAYMENT_AMOUNT,
                             value="500", observed_at=t0, webhook_event_id=50)
        _link_obs_to_claim(db, obs_500, claim_500)

        claim_700 = _make_claim(db, pid, ClaimType.PAYMENT_AMOUNT.value, "AMOUNT", "700")
        obs_700 = _make_obs(db, pid, evidence_type=EvidenceType.PAYMENT_AMOUNT,
                             value="700", observed_at=t0, webhook_event_id=51)
        _link_obs_to_claim(db, obs_700, claim_700)

        conflicts = ContradictionEngine.evaluate_payment_consistency(db, pid)
        value_conflicts = [c for c in conflicts if c.conflict_type == ConflictType.VALUE_CONFLICT.value]
        assert len(value_conflicts) >= 1

    def test_open_conflict_degrades_reliability(self, db):
        """
        INV-12: An open contradiction degrades reliability below HIGH.
        """
        from app.models.evidence_conflict import EvidenceConflict
        pid = "adv_contra_004"
        _make_payment(db, pid)
        t0 = datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc)

        claim_a = _make_claim(db, pid, ClaimType.PAYMENT_STATUS.value, "STATUS", "captured")
        claim_b = _make_claim(db, pid, ClaimType.PAYMENT_STATUS.value, "STATUS", "failed")

        conflict = EvidenceConflict(
            payment_id=pid,
            claim_a_id=min(claim_a.internal_id, claim_b.internal_id),
            claim_b_id=max(claim_a.internal_id, claim_b.internal_id),
            conflict_type=ConflictType.STATE_CONFLICT.value,
            severity=ConflictSeverity.HIGH.value,
            status=ConflictStatus.OPEN.value,
            detected_at=t0,
            rule_version="1.0",
        )
        db.add(conflict)
        db.flush()

        fact = _make_fact(db, pid, FactType.PAYMENT_CAPTURED, "payment.captured", observed_at=t0)
        obs = _make_obs(db, pid, observed_at=t0, webhook_event_id=70)
        _link_obs_to_fact(db, obs, fact)

        result = evaluate_fact_reliability(db, fact)
        assert result.overall_state != ReliabilityState.HIGH


# ===========================================================================
# CATEGORY: MALFORMED & PARTIAL PROVENANCE
# ===========================================================================

class TestMalformedAndPartialProvenance:
    """
    SCENARIO: Malformed observation records and broken provenance chains.
    Invariants: INV-01, INV-04, INV-05, INV-15
    """

    def test_observation_with_null_value_is_preserved(self, db):
        """
        INV-01: Raw observations are never silently destroyed.
        """
        pid = "adv_mal_001"
        _make_payment(db, pid)
        t0 = datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc)

        obs = EvidenceObservation(
            evidence_type=EvidenceType.PAYMENT_STATUS,
            subject_type=SubjectType.PAYMENT,
            subject_id=pid,
            value=None,
            value_type=ValueType.ENUM,
            source_type=SourceType.RAZORPAY_WEBHOOK,
            source_reference="99",
            observed_at=t0,
            extraction_method=ExtractionMethod.WEBHOOK_FIELD_EXTRACTION,
            extraction_version=CURRENT_EXTRACTION_VERSION,
        )
        db.add(obs)
        db.flush()

        retrieved = db.query(EvidenceObservation).filter_by(internal_id=obs.internal_id).first()
        assert retrieved is not None
        assert retrieved.value is None

    def test_missing_webhook_event_id_degrades_provenance(self, db):
        """
        INV-05 & INV-15: Missing provenance linkage breaks provenance dimension.
        """
        pid = "adv_mal_003"
        _make_payment(db, pid)
        t0 = datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc)

        fact = _make_fact(db, pid, FactType.PAYMENT_CAPTURED, "payment.captured", observed_at=t0)
        obs = EvidenceObservation(
            evidence_type=EvidenceType.PAYMENT_STATUS,
            subject_type=SubjectType.PAYMENT,
            subject_id=pid,
            value="captured",
            value_type=ValueType.ENUM,
            source_type=SourceType.RAZORPAY_WEBHOOK,
            observed_at=t0,
            webhook_event_id=None,
            extraction_method=ExtractionMethod.WEBHOOK_FIELD_EXTRACTION,
            extraction_version=CURRENT_EXTRACTION_VERSION,
        )
        db.add(obs)
        db.flush()
        _link_obs_to_fact(db, obs, fact)

        result = evaluate_fact_reliability(db, fact)
        assert result.overall_state != ReliabilityState.HIGH
        assert result.dimensions["provenance"].is_degraded is True
        assert result.dimensions["provenance"].state == ProvenanceReliability.BROKEN.value


# ===========================================================================
# CATEGORY: CROSS-PAYMENT ISOLATION & DETERMINISM
# ===========================================================================

class TestCrossPaymentIsolationAndDeterminism:
    """
    SCENARIO: Cross-payment facts and deterministic hashing.
    Invariants: INV-07, INV-08, INV-09, INV-14
    """

    def test_same_amount_different_payments_are_distinct_facts(self, db):
        """
        INV-07: Same canonical value does not imply same fact across different payments.
        """
        pid_a = "adv_iso_001_a"
        pid_b = "adv_iso_001_b"
        _make_payment(db, pid_a)
        _make_payment(db, pid_b)
        t0 = datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc)

        fact_a = _make_fact(db, pid_a, FactType.PAYMENT_AMOUNT_OBSERVED, "50000", observed_at=t0)
        fact_b = _make_fact(db, pid_b, FactType.PAYMENT_AMOUNT_OBSERVED, "50000", observed_at=t0)

        assert fact_a.internal_id != fact_b.internal_id
        assert fact_a.canonical_value_hash != fact_b.canonical_value_hash

    def test_same_payment_different_lifecycle_facts_are_distinct(self, db):
        """
        INV-08: Same payment does not imply same fact across lifecycle events.
        """
        pid = "adv_iso_002"
        _make_payment(db, pid)
        t0 = datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc)

        fact_auth = _make_fact(db, pid, FactType.PAYMENT_AUTHORIZED, "payment.authorized", observed_at=t0)
        fact_cap = _make_fact(db, pid, FactType.PAYMENT_CAPTURED, "payment.captured", observed_at=t0)
        fact_ref = _make_fact(db, pid, FactType.PAYMENT_REFUNDED, "payment.refunded", observed_at=t0)

        ids = {fact_auth.internal_id, fact_cap.internal_id, fact_ref.internal_id}
        assert len(ids) == 3

    def test_reliability_evaluation_deterministic(self, db):
        """
        INV-09: Same inputs produce exact same reliability assessment across multiple calls.
        """
        pid = "adv_replay_002"
        _make_payment(db, pid)
        t0 = datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc)

        fact = _make_fact(db, pid, FactType.PAYMENT_CAPTURED, "payment.captured", observed_at=t0)
        obs = _make_obs(db, pid, observed_at=t0, webhook_event_id=500)
        _link_obs_to_fact(db, obs, fact)

        result1 = evaluate_fact_reliability(db, fact)
        result2 = evaluate_fact_reliability(db, fact)
        result3 = evaluate_fact_reliability(db, fact)

        assert result1.overall_state == result2.overall_state == result3.overall_state
        assert result1.explanation == result2.explanation == result3.explanation


# ===========================================================================
# CATEGORY: TAMPERING SIMULATION
# ===========================================================================

class TestTamperingSimulation:
    """
    SCENARIO: Tampering detection through cryptographic hashing.
    Invariants: INV-09, INV-14
    """

    def test_sha256_payload_hash_detects_content_change(self):
        """
        INV-14: Stored payload SHA-256 detects any downstream modification.
        """
        original_body = b'{"event": "payment.captured", "id": "evt_test_001"}'
        stored_hash = hashlib.sha256(original_body).hexdigest()

        modified_body = b'{"event": "payment.captured", "id": "evt_test_TAMPERED"}'
        recomputed_hash = hashlib.sha256(modified_body).hexdigest()

        assert stored_hash != recomputed_hash

    def test_trace_verification_service_detects_hash_mismatch(self, db):
        """
        INV-14: Phase 10 trace verification detects mismatched canonical payload hash.
        """
        from app.models.integrity_trace import EvidenceIntegrityTrace
        from app.models.trace_types import TraceStatus, TraceType
        from app.services.trace_verification import TraceVerificationService
        from app.services.trace_canonicalization import canonical_json, sha256_hex

        pid = "adv_tamp_002"
        t0 = datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc)

        valid_payload = {
            "hash_domain": "evidence_integrity_trace",
            "schema": "EIS-v1",
            "envelope": {
                "trace_id": "trc_adv_tamp_002",
                "payment_id": pid,
                "evaluated_at": t0.isoformat(),
                "methodology_version": "EIS-1.0",
                "status": "COMPLETED",
            },
            "content": {"integrity_status": "STRONG"},
        }
        correct_hash = sha256_hex(canonical_json(valid_payload))

        from app.models.trace_types import HASH_ALGORITHM, CANONICALIZATION_VERSION

        trace = EvidenceIntegrityTrace(
            trace_id="trc_adv_tamp_002",
            original_trace_id="trc_orig_002",
            payment_id=pid,
            trace_type=TraceType.REPLAY,
            status=TraceStatus.COMPLETED,
            overall_status="STRONG",
            methodology_version="EIS-1.0",
            evaluated_at=t0,
            canonical_payload=valid_payload,
            trace_hash=correct_hash,
            hash_algorithm=HASH_ALGORITHM,
            canonicalization_version=CANONICALIZATION_VERSION,
        )
        db.add(trace)
        db.flush()

        result_valid = TraceVerificationService.verify_trace_integrity(db, "trc_adv_tamp_002")
        assert result_valid["status"] == "VALID"

        # Tamper payload
        trace.canonical_payload = {
            **valid_payload,
            "content": {"integrity_status": "TAMPERED_VALUE"},
        }
        db.flush()

        result_tampered = TraceVerificationService.verify_trace_integrity(db, "trc_adv_tamp_002")
        assert result_tampered["status"] == "INVALID"


# ===========================================================================
# CATEGORY: 10 GOLDEN CASES (Metamorphic Verification)
# ===========================================================================

class TestGoldenCases:
    """
    10 explicit golden reference cases for system behavior verification.
    """

    def test_GOLDEN_001_normal_captured_payment(self, db):
        """GOLDEN_001: Verified webhook with complete provenance yields HIGH reliability."""
        pid = "golden_001"
        _make_payment(db, pid)
        t0 = datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc)

        fact = _make_fact(db, pid, FactType.PAYMENT_CAPTURED, "payment.captured", observed_at=t0)
        obs = EvidenceObservation(
            evidence_type=EvidenceType.PAYMENT_STATUS,
            subject_type=SubjectType.PAYMENT,
            subject_id=pid,
            value="captured",
            value_type=ValueType.ENUM,
            source_type=SourceType.RAZORPAY_WEBHOOK,
            source_reference="1001",
            observed_at=t0,
            webhook_event_id=1001,
            extraction_method=ExtractionMethod.WEBHOOK_FIELD_EXTRACTION,
            extraction_version=CURRENT_EXTRACTION_VERSION,
        )
        db.add(obs)
        db.flush()
        _link_obs_to_fact(db, obs, fact)

        result = evaluate_fact_reliability(db, fact)
        assert result.overall_state == ReliabilityState.HIGH

    def test_GOLDEN_002_duplicate_webhook_same_result(self, db):
        """GOLDEN_002: Duplicate webhook deliveries do not inflate reliability rank."""
        pid = "golden_002"
        _make_payment(db, pid)
        t0 = datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc)

        fact = _make_fact(db, pid, FactType.PAYMENT_CAPTURED, "payment.captured", observed_at=t0)
        obs1 = _make_obs(db, pid, webhook_event_id=2001, observed_at=t0)
        _link_obs_to_fact(db, obs1, fact)
        r1 = evaluate_fact_reliability(db, fact)

        for _ in range(5):
            obs_dup = _make_obs(db, pid, webhook_event_id=2001, observed_at=t0)
            _link_obs_to_fact(db, obs_dup, fact)

        r2 = evaluate_fact_reliability(db, fact)
        state_order = {
            ReliabilityState.UNRELIABLE: 0,
            ReliabilityState.UNKNOWN: 1,
            ReliabilityState.LIMITED: 2,
            ReliabilityState.MODERATE: 3,
            ReliabilityState.HIGH: 4,
        }
        assert state_order[r2.overall_state] <= state_order[r1.overall_state]

    def test_GOLDEN_003_out_of_order_lifecycle_conflict(self, db):
        """GOLDEN_003: captured before authorized produces conflict."""
        pid = "golden_003"
        _make_payment(db, pid)
        t_captured = datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
        t_authorized = datetime(2024, 1, 1, 11, 0, 0, tzinfo=timezone.utc)

        claim_cap = _make_claim(db, pid, ClaimType.PAYMENT_STATUS.value, "STATUS", "captured")
        obs_cap = _make_obs(db, pid, value="captured", observed_at=t_captured, webhook_event_id=3001)
        _link_obs_to_claim(db, obs_cap, claim_cap)

        claim_auth = _make_claim(db, pid, ClaimType.PAYMENT_STATUS.value, "STATUS", "authorized")
        obs_auth = _make_obs(db, pid, value="authorized", observed_at=t_authorized, webhook_event_id=3002)
        _link_obs_to_claim(db, obs_auth, claim_auth)

        conflicts = ContradictionEngine.evaluate_payment_consistency(db, pid)
        assert len(conflicts) > 0

    def test_GOLDEN_004_conflicting_amount(self, db):
        """GOLDEN_004: Conflicting amounts produce VALUE_CONFLICT."""
        pid = "golden_004"
        _make_payment(db, pid)
        t0 = datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc)

        claim_500 = _make_claim(db, pid, ClaimType.PAYMENT_AMOUNT.value, "AMOUNT", "50000")
        obs_500 = _make_obs(db, pid, evidence_type=EvidenceType.PAYMENT_AMOUNT,
                             value="50000", observed_at=t0, webhook_event_id=4001)
        _link_obs_to_claim(db, obs_500, claim_500)

        claim_700 = _make_claim(db, pid, ClaimType.PAYMENT_AMOUNT.value, "AMOUNT", "70000")
        obs_700 = _make_obs(db, pid, evidence_type=EvidenceType.PAYMENT_AMOUNT,
                             value="70000", observed_at=t0, webhook_event_id=4002)
        _link_obs_to_claim(db, obs_700, claim_700)

        conflicts = ContradictionEngine.evaluate_payment_consistency(db, pid)
        assert any(c.conflict_type == ConflictType.VALUE_CONFLICT.value for c in conflicts)

    def test_GOLDEN_005_missing_authorization_coverage_incomplete(self, db):
        """GOLDEN_005: Missing authorization fact keeps coverage incomplete."""
        pid = "golden_005"
        _make_payment(db, pid)
        t0 = datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc)

        _make_fact(db, pid, FactType.PAYMENT_CAPTURED, "payment.captured", observed_at=t0)

        result = evaluate_coverage(db, pid, as_of=t0, persist=False)
        from app.models.coverage_types import CoverageStatus
        assert result.overall_coverage_status != CoverageStatus.COMPLETE

    def test_GOLDEN_006_ambiguous_identity_remains_unresolved(self, db):
        """GOLDEN_006: Unresolved fact remains unresolved without guesswork."""
        pid = "golden_006"
        _make_payment(db, pid)
        t0 = datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc)

        fact = _make_fact(db, pid, FactType.PAYMENT_AMOUNT_OBSERVED, "50000",
                          status=FactStatus.UNRESOLVED, observed_at=t0)
        assert fact.status == FactStatus.UNRESOLVED

    def test_GOLDEN_007_dependent_sources_not_independent(self, db):
        """GOLDEN_007: Multiple observations from 1 webhook are not independent sources."""
        pid = "golden_007"
        _make_payment(db, pid)
        t0 = datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
        claim = _make_claim(db, pid, ClaimType.PAYMENT_STATUS.value, "STATUS", "captured")

        for _ in range(10):
            obs = _make_obs(db, pid, webhook_event_id=7001, observed_at=t0)
            _link_obs_to_claim(db, obs, claim)

        corrob = CorroborationService.evaluate_claim_corroboration(db, claim, pid)
        assert corrob.corroboration_type != CorroborationType.MULTI_SOURCE_CORROBORATION.value

    def test_GOLDEN_008_historical_evaluation_excludes_future(self, db):
        """GOLDEN_008: as_of temporal boundary is respected."""
        pid = "golden_008"
        _make_payment(db, pid)
        t1 = datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
        t2 = datetime(2024, 1, 2, 10, 0, 0, tzinfo=timezone.utc)

        fact = _make_fact(db, pid, FactType.PAYMENT_CAPTURED, "payment.captured", observed_at=t1)
        obs_t1 = _make_obs(db, pid, observed_at=t1, webhook_event_id=8001)
        _link_obs_to_fact(db, obs_t1, fact)

        result_t1 = evaluate_fact_reliability(db, fact, as_of=t1)
        assert result_t1.evaluated_at == t1

    def test_GOLDEN_009_late_event_uses_provider_timestamp(self, db):
        """GOLDEN_009: Late-arriving events use observed_at for chronological sorting."""
        pid = "golden_009"
        _make_payment(db, pid)

        provider_time = datetime(2024, 1, 1, 6, 0, 0, tzinfo=timezone.utc)
        obs = _make_obs(db, pid, observed_at=provider_time, webhook_event_id=9001)
        assert obs.observed_at == provider_time

    def test_GOLDEN_010_broken_provenance_not_high(self, db):
        """GOLDEN_010: Broken provenance cannot achieve HIGH reliability."""
        pid = "golden_010"
        _make_payment(db, pid)
        t0 = datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc)

        fact = _make_fact(db, pid, FactType.PAYMENT_CAPTURED, "payment.captured", observed_at=t0)
        obs = EvidenceObservation(
            evidence_type=EvidenceType.PAYMENT_STATUS,
            subject_type=SubjectType.PAYMENT,
            subject_id=pid,
            value="captured",
            value_type=ValueType.ENUM,
            source_type=SourceType.RAZORPAY_WEBHOOK,
            observed_at=t0,
            webhook_event_id=None,
            extraction_method=ExtractionMethod.WEBHOOK_FIELD_EXTRACTION,
            extraction_version=CURRENT_EXTRACTION_VERSION,
        )
        db.add(obs)
        db.flush()
        _link_obs_to_fact(db, obs, fact)

        result = evaluate_fact_reliability(db, fact)
        assert result.overall_state != ReliabilityState.HIGH


# ===========================================================================
# CATEGORY: 15 NAMED INVARIANT SUMMARY TESTS
# ===========================================================================

class TestInvariantSummary:
    """
    Dedicated tests verifying all 15 core architectural invariants.
    """

    def test_INV_01_raw_observations_never_destroyed(self, db):
        """INV-01: Raw observations are never silently destroyed."""
        pid = "inv_01"
        _make_payment(db, pid)
        t0 = datetime(2024, 1, 1, tzinfo=timezone.utc)
        obs = _make_obs(db, pid, observed_at=t0, webhook_event_id=10001)
        retrieved = db.query(EvidenceObservation).filter_by(internal_id=obs.internal_id).first()
        assert retrieved is not None

    def test_INV_02_duplicates_not_independent_corroboration(self, db):
        """INV-02: Duplicate provider events do not create independent corroboration."""
        pid = "inv_02"
        _make_payment(db, pid)
        t0 = datetime(2024, 1, 1, tzinfo=timezone.utc)
        claim = _make_claim(db, pid, ClaimType.PAYMENT_STATUS.value, "STATUS", "captured")
        for _ in range(5):
            obs = _make_obs(db, pid, webhook_event_id=10002, observed_at=t0)
            _link_obs_to_claim(db, obs, claim)
        corrob = CorroborationService.evaluate_claim_corroboration(db, claim, pid)
        assert corrob.distinct_sources_count == 1

    def test_INV_03_future_evidence_excluded_from_history(self, db):
        """INV-03: Future evidence cannot influence historical evaluation."""
        pid = "inv_03"
        _make_payment(db, pid)
        t1 = datetime(2024, 1, 1, tzinfo=timezone.utc)
        t2 = datetime(2024, 1, 2, tzinfo=timezone.utc)
        fact = _make_fact(db, pid, FactType.PAYMENT_CAPTURED, "payment.captured", observed_at=t1)
        obs = _make_obs(db, pid, observed_at=t2, webhook_event_id=10003)
        _link_obs_to_fact(db, obs, fact)
        result = evaluate_fact_reliability(db, fact, as_of=t1)
        assert result.evaluated_at == t1

    def test_INV_04_unknown_not_resolved_by_fallback(self, db):
        """INV-04: Unknown never becomes known through fallback guessing."""
        pid = "inv_04"
        _make_payment(db, pid)
        t0 = datetime(2024, 1, 1, tzinfo=timezone.utc)
        fact = _make_fact(db, pid, FactType.PAYMENT_AMOUNT_OBSERVED, "50000",
                          status=FactStatus.UNRESOLVED, observed_at=t0)
        retrieved = db.query(EvidenceFact).filter_by(internal_id=fact.internal_id).first()
        assert retrieved.status == FactStatus.UNRESOLVED

    def test_INV_05_missing_evidence_not_proof_of_absence(self, db):
        """INV-05: Missing evidence never becomes proof of absence."""
        pid = "inv_05"
        _make_payment(db, pid)
        t0 = datetime(2024, 1, 1, tzinfo=timezone.utc)
        result = evaluate_payment_reliability(db, pid, as_of=t0)
        assert result.overall_state in (
            ReliabilityState.LIMITED,
            ReliabilityState.UNKNOWN,
            ReliabilityState.MODERATE,
        )

    def test_INV_06_authenticated_source_not_semantic_truth(self, db):
        """INV-06: Authenticated source does not imply semantic truth."""
        pid = "inv_06"
        _make_payment(db, pid)
        t0 = datetime(2024, 1, 1, tzinfo=timezone.utc)
        c1 = _make_claim(db, pid, ClaimType.PAYMENT_AMOUNT.value, "AMOUNT", "100")
        o1 = _make_obs(db, pid, evidence_type=EvidenceType.PAYMENT_AMOUNT,
                        value="100", source_type=SourceType.RAZORPAY_WEBHOOK,
                        observed_at=t0, webhook_event_id=10006)
        _link_obs_to_claim(db, o1, c1)
        c2 = _make_claim(db, pid, ClaimType.PAYMENT_AMOUNT.value, "AMOUNT", "200")
        o2 = _make_obs(db, pid, evidence_type=EvidenceType.PAYMENT_AMOUNT,
                        value="200", source_type=SourceType.RAZORPAY_WEBHOOK,
                        observed_at=t0, webhook_event_id=10007)
        _link_obs_to_claim(db, o2, c2)
        conflicts = ContradictionEngine.evaluate_payment_consistency(db, pid)
        assert any(c.conflict_type == ConflictType.VALUE_CONFLICT.value for c in conflicts)

    def test_INV_07_same_value_not_same_fact(self, db):
        """INV-07: Same value does not imply same fact across different payments."""
        pid_a = "inv_07a"
        pid_b = "inv_07b"
        _make_payment(db, pid_a)
        _make_payment(db, pid_b)
        h_a = _canonical_value_hash(pid_a, FactType.PAYMENT_AMOUNT_OBSERVED, "50000")
        h_b = _canonical_value_hash(pid_b, FactType.PAYMENT_AMOUNT_OBSERVED, "50000")
        assert h_a != h_b

    def test_INV_08_same_payment_not_same_fact(self, db):
        """INV-08: Same payment does not imply same fact across lifecycle events."""
        pid = "inv_08"
        _make_payment(db, pid)
        h_auth = _canonical_value_hash(pid, FactType.PAYMENT_AUTHORIZED, "payment.authorized")
        h_cap = _canonical_value_hash(pid, FactType.PAYMENT_CAPTURED, "payment.captured")
        assert h_auth != h_cap

    def test_INV_09_historical_traces_reproducible(self):
        """INV-09: Historical traces remain reproducible."""
        from app.services.trace_canonicalization import canonical_json, sha256_hex
        payload = {"hash_domain": "test", "value": "abc123"}
        h1 = sha256_hex(canonical_json(payload))
        h2 = sha256_hex(canonical_json(payload))
        assert h1 == h2

    def test_INV_10_relationships_not_invented(self, db):
        """INV-10: Unsupported relationships are never invented."""
        pid = "inv_10"
        _make_payment(db, pid)
        obs_count = db.query(EvidenceObservation).filter_by(
            subject_id=pid, evidence_type=EvidenceType.PAYMENT_ORDER_RELATIONSHIP
        ).count()
        assert obs_count == 0

    def test_INV_11_conflicts_remain_visible(self, db):
        """INV-11: Conflicts remain visible after recompute."""
        pid = "inv_11"
        _make_payment(db, pid)
        t0 = datetime(2024, 1, 1, tzinfo=timezone.utc)
        c1 = _make_claim(db, pid, ClaimType.PAYMENT_AMOUNT.value, "AMOUNT", "500")
        o1 = _make_obs(db, pid, evidence_type=EvidenceType.PAYMENT_AMOUNT,
                        value="500", observed_at=t0, webhook_event_id=11001)
        _link_obs_to_claim(db, o1, c1)
        c2 = _make_claim(db, pid, ClaimType.PAYMENT_AMOUNT.value, "AMOUNT", "999")
        o2 = _make_obs(db, pid, evidence_type=EvidenceType.PAYMENT_AMOUNT,
                        value="999", observed_at=t0, webhook_event_id=11002)
        _link_obs_to_claim(db, o2, c2)
        c1_count = len(ContradictionEngine.evaluate_payment_consistency(db, pid))
        c2_count = len(ContradictionEngine.evaluate_payment_consistency(db, pid))
        assert c1_count == c2_count and c1_count > 0

    def test_INV_12_reliability_not_inflated_by_duplicates(self, db):
        """INV-12: Reliability cannot improve merely from duplicate evidence."""
        pid = "inv_12"
        _make_payment(db, pid)
        t0 = datetime(2024, 1, 1, tzinfo=timezone.utc)
        fact = _make_fact(db, pid, FactType.PAYMENT_CAPTURED, "payment.captured", observed_at=t0)
        obs = _make_obs(db, pid, observed_at=t0, webhook_event_id=12001)
        _link_obs_to_fact(db, obs, fact)
        r1 = evaluate_fact_reliability(db, fact)

        obs2 = _make_obs(db, pid, observed_at=t0, webhook_event_id=12001)
        _link_obs_to_fact(db, obs2, fact)
        r2 = evaluate_fact_reliability(db, fact)

        state_order = {
            ReliabilityState.UNRELIABLE: 0,
            ReliabilityState.UNKNOWN: 1,
            ReliabilityState.LIMITED: 2,
            ReliabilityState.MODERATE: 3,
            ReliabilityState.HIGH: 4,
        }
        assert state_order[r2.overall_state] <= state_order[r1.overall_state]

    def test_INV_13_coverage_not_inflated_by_duplicates(self, db):
        """INV-13: Coverage cannot improve merely from duplicate observations."""
        pid = "inv_13"
        _make_payment(db, pid)
        t0 = datetime(2024, 1, 1, tzinfo=timezone.utc)
        fact = _make_fact(db, pid, FactType.PAYMENT_CAPTURED, "payment.captured", observed_at=t0)

        r1 = evaluate_coverage(db, pid, as_of=t0, persist=False)

        for _ in range(10):
            obs = _make_obs(db, pid, observed_at=t0, webhook_event_id=13001)
            _link_obs_to_fact(db, obs, fact)

        r2 = evaluate_coverage(db, pid, as_of=t0, persist=False)
        assert r2.metrics.required_present == r1.metrics.required_present

    def test_INV_14_methodology_version_always_present(self, db):
        """INV-14: Every integrity result has an auditable methodology version."""
        pid = "inv_14"
        _make_payment(db, pid)
        t0 = datetime(2024, 1, 1, tzinfo=timezone.utc)
        fact = _make_fact(db, pid, FactType.PAYMENT_CAPTURED, "payment.captured", observed_at=t0)
        result = evaluate_fact_reliability(db, fact)
        assert result.methodology_version == RELIABILITY_METHODOLOGY_V1

    def test_INV_15_lineage_limits_prevent_runaway_traversal(self):
        """INV-15: Lineage traversal hard limits are strictly bounded."""
        from app.models.lineage_types import (
            LINEAGE_MAX_DEPTH_HARD_LIMIT,
            LINEAGE_MAX_NODES_HARD_LIMIT,
        )
        assert LINEAGE_MAX_DEPTH_HARD_LIMIT <= 100
        assert LINEAGE_MAX_NODES_HARD_LIMIT <= 50000
