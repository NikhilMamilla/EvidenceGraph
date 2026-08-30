"""
Unit and integration tests for Phase 8 — Contradiction & Temporal Consistency Engine.

Tests cover:
- Valid lifecycle transitions (NO conflict)
- Out-of-order webhook delivery with valid provider timestamps (NO conflict)
- Invalid state transitions (TEMPORAL_CONFLICT / STATE_CONFLICT)
- Contradictory terminal states (STATE_CONFLICT)
- Value conflicts on amount and currency (VALUE_CONFLICT)
- Relationship conflicts on order association (RELATIONSHIP_CONFLICT)
- Same-timestamp ordering ambiguity (ORDERING_AMBIGUITY)
- Conflict idempotency (repeated evaluations do not duplicate)
- State machine semantics
- Conflict resolution
- Conflict API endpoints
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
import pytest
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


# ---------------------------------------------------------------------------
# SQLite JSONB polyfill
# ---------------------------------------------------------------------------
@compiles(JSONB, "sqlite")
def compile_jsonb_sqlite(type_, compiler, **kw):
    return "JSON"


from app.db.session import Base
from app.models.conflict_types import ConflictType, ConflictSeverity, ConflictStatus, ResolutionType
from app.models.evidence import EvidenceObservation
from app.models.evidence_types import EvidenceType, SourceType, ValueType
from app.models.evidence_structure import Claim, EvidenceClaimLink
from app.models.evidence_conflict import EvidenceConflict, ConflictResolution
from app.models.structure_types import ClaimType
from app.services.state_machine import PaymentStateMachine
from app.services.contradiction_engine import ContradictionEngine


# ---------------------------------------------------------------------------
# Shared Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def in_memory_db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()


T_BASE = datetime(2026, 8, 22, 10, 0, 0, tzinfo=timezone.utc)


def make_obs(
    db,
    internal_id: int,
    evidence_type: str,
    value: str,
    subject_id: str = "pay_test_001",
    source_type: str = SourceType.RAZORPAY_WEBHOOK,
    payment_event_id: int = 1,
    webhook_event_id: int = 1,
    observed_at: datetime = None,
) -> EvidenceObservation:
    obs = EvidenceObservation(
        internal_id=internal_id,
        evidence_type=evidence_type,
        subject_type="payment",
        subject_id=subject_id,
        value=value,
        value_type=ValueType.STRING,
        source_type=source_type,
        source_reference="test_ref",
        extraction_method="TEST",
        extraction_version="1.0",
        observed_at=observed_at or T_BASE,
        payment_event_id=payment_event_id,
        webhook_event_id=webhook_event_id,
        provenance_metadata={"test": True},
    )
    db.add(obs)
    db.flush()
    return obs


def make_claim(
    db,
    claim_type: str,
    claim_key: str,
    canonical_value: str,
    subject_id: str = "pay_test_001",
    created_at: datetime = None,
) -> Claim:
    claim = Claim(
        subject_type="payment",
        subject_id=subject_id,
        claim_type=claim_type,
        claim_key=claim_key,
        canonical_value=canonical_value,
        created_at=created_at or T_BASE,
    )
    db.add(claim)
    db.flush()
    return claim


def link_obs_to_claim(db, claim: Claim, obs: EvidenceObservation):
    link = EvidenceClaimLink(claim_id=claim.internal_id, evidence_id=obs.internal_id)
    db.add(link)
    db.flush()


# ---------------------------------------------------------------------------
# Class 1: PaymentStateMachine Tests
# ---------------------------------------------------------------------------
class TestStateMachine:
    """Verify that the state machine correctly classifies transitions."""

    def test_valid_authorized_to_captured(self):
        result = PaymentStateMachine.classify_transition("authorized", "captured")
        assert result["is_valid"] is True
        assert result["transition_type"] == "VALID_FORWARD"

    def test_valid_created_to_authorized(self):
        result = PaymentStateMachine.classify_transition("created", "authorized")
        assert result["is_valid"] is True
        assert result["transition_type"] == "VALID_FORWARD"

    def test_valid_authorized_to_failed(self):
        result = PaymentStateMachine.classify_transition("authorized", "failed")
        assert result["is_valid"] is True
        assert result["transition_type"] == "VALID_FORWARD"

    def test_valid_captured_to_refunded(self):
        result = PaymentStateMachine.classify_transition("captured", "refunded")
        assert result["is_valid"] is True
        assert result["transition_type"] == "VALID_FORWARD"

    def test_invalid_backward_captured_to_authorized(self):
        result = PaymentStateMachine.classify_transition("captured", "authorized")
        assert result["is_valid"] is False
        assert result["transition_type"] == "INVALID_BACKWARD"

    def test_contradictory_terminal_captured_vs_failed(self):
        result = PaymentStateMachine.classify_transition("captured", "failed")
        assert result["is_valid"] is False
        assert result["transition_type"] == "CONTRADICTORY_TERMINAL"

    def test_same_state_idempotent(self):
        result = PaymentStateMachine.classify_transition("captured", "captured")
        assert result["is_valid"] is True
        assert result["transition_type"] == "SAME_STATE"

    def test_paid_normalized_to_captured(self):
        """'paid' is an alias for 'captured' in Razorpay order context."""
        result = PaymentStateMachine.classify_transition("authorized", "paid")
        assert result["is_valid"] is True
        assert result["transition_type"] == "VALID_FORWARD"


# ---------------------------------------------------------------------------
# Class 2: Valid Lifecycle — No Conflict Produced
# ---------------------------------------------------------------------------
class TestValidLifecycle:
    """Valid lifecycle transitions must produce ZERO conflicts."""

    def test_authorized_then_captured_no_conflict(self, in_memory_db):
        db = in_memory_db
        pid = "pay_valid_lifecycle"

        obs_auth = make_obs(db, 1, EvidenceType.PAYMENT_STATUS, "authorized", pid, observed_at=T_BASE)
        obs_cap = make_obs(db, 2, EvidenceType.PAYMENT_STATUS, "captured", pid, observed_at=T_BASE + timedelta(minutes=2))

        claim_auth = make_claim(db, ClaimType.PAYMENT_STATUS.value, "STATUS", "authorized", pid, created_at=T_BASE)
        claim_cap = make_claim(db, ClaimType.PAYMENT_STATUS.value, "STATUS", "captured", pid, created_at=T_BASE + timedelta(minutes=2))
        link_obs_to_claim(db, claim_auth, obs_auth)
        link_obs_to_claim(db, claim_cap, obs_cap)

        eval_time = T_BASE + timedelta(minutes=5)
        conflicts = ContradictionEngine.evaluate_payment_consistency(db, pid, eval_time)

        state_conflicts = [c for c in conflicts if c.conflict_type == ConflictType.STATE_CONFLICT.value]
        temporal_conflicts = [c for c in conflicts if c.conflict_type == ConflictType.TEMPORAL_CONFLICT.value]
        assert len(state_conflicts) == 0
        assert len(temporal_conflicts) == 0

    def test_created_authorized_captured_full_lifecycle_no_conflict(self, in_memory_db):
        db = in_memory_db
        pid = "pay_full_lifecycle"

        for i, (status, dt) in enumerate([
            ("created", T_BASE),
            ("authorized", T_BASE + timedelta(minutes=1)),
            ("captured", T_BASE + timedelta(minutes=3)),
        ]):
            obs = make_obs(db, i + 1, EvidenceType.PAYMENT_STATUS, status, pid, observed_at=dt)
            claim = make_claim(db, ClaimType.PAYMENT_STATUS.value, "STATUS", status, pid, created_at=dt)
            link_obs_to_claim(db, claim, obs)

        conflicts = ContradictionEngine.evaluate_payment_consistency(db, pid, T_BASE + timedelta(minutes=10))
        state_conflicts = [c for c in conflicts if c.conflict_type == ConflictType.STATE_CONFLICT.value]
        assert len(state_conflicts) == 0


# ---------------------------------------------------------------------------
# Class 3: Out-of-Order Delivery — No Conflict
# ---------------------------------------------------------------------------
class TestOutOfOrderDelivery:
    """
    Out-of-order webhook receipt (captured before authorized) but chronological
    provider timestamps must not produce a conflict.
    """

    def test_out_of_order_receipt_no_conflict(self, in_memory_db):
        db = in_memory_db
        pid = "pay_ooo_delivery"

        # Provider timestamps: authorized at T_BASE, captured at T_BASE + 2m
        # Webhook delivery (system receipt): captured arrived first, authorized later
        # We use observed_at = provider timestamp (not receipt time)
        obs_auth = make_obs(db, 1, EvidenceType.PAYMENT_STATUS, "authorized", pid, observed_at=T_BASE)
        obs_cap = make_obs(db, 2, EvidenceType.PAYMENT_STATUS, "captured", pid, observed_at=T_BASE + timedelta(minutes=2))

        claim_auth = make_claim(db, ClaimType.PAYMENT_STATUS.value, "STATUS", "authorized", pid, created_at=T_BASE)
        claim_cap = make_claim(db, ClaimType.PAYMENT_STATUS.value, "STATUS", "captured", pid, created_at=T_BASE + timedelta(minutes=2))
        link_obs_to_claim(db, claim_auth, obs_auth)
        link_obs_to_claim(db, claim_cap, obs_cap)

        conflicts = ContradictionEngine.evaluate_payment_consistency(
            db, pid, T_BASE + timedelta(minutes=10)
        )
        state_conflicts = [c for c in conflicts if c.conflict_type == ConflictType.STATE_CONFLICT.value]
        temporal_conflicts = [c for c in conflicts if c.conflict_type == ConflictType.TEMPORAL_CONFLICT.value]
        assert len(state_conflicts) == 0
        assert len(temporal_conflicts) == 0


# ---------------------------------------------------------------------------
# Class 4: State Conflicts
# ---------------------------------------------------------------------------
class TestStateConflict:

    def test_captured_and_failed_at_same_time_state_conflict(self, in_memory_db):
        db = in_memory_db
        pid = "pay_terminal_conflict"

        obs_cap = make_obs(db, 1, EvidenceType.PAYMENT_STATUS, "captured", pid, observed_at=T_BASE)
        obs_fail = make_obs(db, 2, EvidenceType.PAYMENT_STATUS, "failed", pid, observed_at=T_BASE)

        claim_cap = make_claim(db, ClaimType.PAYMENT_STATUS.value, "STATUS", "captured", pid, created_at=T_BASE)
        claim_fail = make_claim(db, ClaimType.PAYMENT_STATUS.value, "STATUS", "failed", pid, created_at=T_BASE)
        link_obs_to_claim(db, claim_cap, obs_cap)
        link_obs_to_claim(db, claim_fail, obs_fail)

        conflicts = ContradictionEngine.evaluate_payment_consistency(db, pid, T_BASE + timedelta(minutes=5))

        state_conflicts = [c for c in conflicts if c.conflict_type == ConflictType.STATE_CONFLICT.value]
        assert len(state_conflicts) == 1
        assert state_conflicts[0].severity == ConflictSeverity.HIGH.value
        assert "captured" in str(state_conflicts[0].explanation)
        assert "failed" in str(state_conflicts[0].explanation)

    def test_backward_transition_temporal_conflict(self, in_memory_db):
        db = in_memory_db
        pid = "pay_backward"

        obs_cap = make_obs(db, 1, EvidenceType.PAYMENT_STATUS, "captured", pid, observed_at=T_BASE)
        obs_auth = make_obs(db, 2, EvidenceType.PAYMENT_STATUS, "authorized", pid, observed_at=T_BASE + timedelta(minutes=2))

        claim_cap = make_claim(db, ClaimType.PAYMENT_STATUS.value, "STATUS", "captured", pid, created_at=T_BASE)
        claim_auth = make_claim(db, ClaimType.PAYMENT_STATUS.value, "STATUS", "authorized", pid, created_at=T_BASE + timedelta(minutes=2))
        link_obs_to_claim(db, claim_cap, obs_cap)
        link_obs_to_claim(db, claim_auth, obs_auth)

        conflicts = ContradictionEngine.evaluate_payment_consistency(db, pid, T_BASE + timedelta(minutes=10))
        temporal_conflicts = [c for c in conflicts if c.conflict_type == ConflictType.TEMPORAL_CONFLICT.value]
        assert len(temporal_conflicts) == 1
        assert temporal_conflicts[0].severity == ConflictSeverity.MEDIUM.value


# ---------------------------------------------------------------------------
# Class 5: Value Conflicts
# ---------------------------------------------------------------------------
class TestValueConflict:

    def test_two_different_amounts_value_conflict(self, in_memory_db):
        db = in_memory_db
        pid = "pay_amount_conflict"

        obs1 = make_obs(db, 1, EvidenceType.PAYMENT_AMOUNT, "50000", pid, observed_at=T_BASE)
        obs2 = make_obs(db, 2, EvidenceType.PAYMENT_AMOUNT, "70000", pid, observed_at=T_BASE + timedelta(minutes=1))

        claim1 = make_claim(db, ClaimType.PAYMENT_AMOUNT.value, "AMOUNT", "50000", pid, created_at=T_BASE)
        claim2 = make_claim(db, ClaimType.PAYMENT_AMOUNT.value, "AMOUNT", "70000", pid, created_at=T_BASE + timedelta(minutes=1))
        link_obs_to_claim(db, claim1, obs1)
        link_obs_to_claim(db, claim2, obs2)

        conflicts = ContradictionEngine.evaluate_payment_consistency(db, pid, T_BASE + timedelta(minutes=5))
        value_conflicts = [c for c in conflicts if c.conflict_type == ConflictType.VALUE_CONFLICT.value]

        assert len(value_conflicts) == 1
        assert value_conflicts[0].severity == ConflictSeverity.HIGH.value
        exp = value_conflicts[0].explanation
        assert "50000" in str(exp)
        assert "70000" in str(exp)

    def test_same_amount_no_conflict(self, in_memory_db):
        """
        Two observations for the SAME canonical amount must not conflict.
        By design, identical canonical values resolve to the SAME Claim — no conflict possible.
        """
        db = in_memory_db
        pid = "pay_same_amount"

        obs1 = make_obs(db, 1, EvidenceType.PAYMENT_AMOUNT, "50000", pid, observed_at=T_BASE)
        obs2 = make_obs(db, 2, EvidenceType.PAYMENT_AMOUNT, "50000", pid, observed_at=T_BASE + timedelta(minutes=1))

        # Identical canonical value → same canonical claim (by unique constraint semantics)
        claim = make_claim(db, ClaimType.PAYMENT_AMOUNT.value, "AMOUNT", "50000", pid, created_at=T_BASE)
        link_obs_to_claim(db, claim, obs1)
        link_obs_to_claim(db, claim, obs2)

        conflicts = ContradictionEngine.evaluate_payment_consistency(db, pid, T_BASE + timedelta(minutes=5))
        value_conflicts = [c for c in conflicts if c.conflict_type == ConflictType.VALUE_CONFLICT.value]
        assert len(value_conflicts) == 0

    def test_currency_conflict(self, in_memory_db):
        db = in_memory_db
        pid = "pay_currency_conflict"

        obs1 = make_obs(db, 1, EvidenceType.PAYMENT_CURRENCY, "INR", pid, observed_at=T_BASE)
        obs2 = make_obs(db, 2, EvidenceType.PAYMENT_CURRENCY, "USD", pid, observed_at=T_BASE + timedelta(minutes=1))

        claim1 = make_claim(db, ClaimType.PAYMENT_CURRENCY.value, "CURRENCY", "INR", pid, created_at=T_BASE)
        claim2 = make_claim(db, ClaimType.PAYMENT_CURRENCY.value, "CURRENCY", "USD", pid, created_at=T_BASE + timedelta(minutes=1))
        link_obs_to_claim(db, claim1, obs1)
        link_obs_to_claim(db, claim2, obs2)

        conflicts = ContradictionEngine.evaluate_payment_consistency(db, pid, T_BASE + timedelta(minutes=5))
        value_conflicts = [c for c in conflicts if c.conflict_type == ConflictType.VALUE_CONFLICT.value]
        assert len(value_conflicts) == 1
        assert value_conflicts[0].severity == ConflictSeverity.HIGH.value


# ---------------------------------------------------------------------------
# Class 6: Relationship Conflict
# ---------------------------------------------------------------------------
class TestRelationshipConflict:

    def test_two_different_orders_relationship_conflict(self, in_memory_db):
        db = in_memory_db
        pid = "pay_order_conflict"

        obs1 = make_obs(db, 1, EvidenceType.PAYMENT_ORDER_RELATIONSHIP, "order_aaa", pid, observed_at=T_BASE)
        obs2 = make_obs(db, 2, EvidenceType.PAYMENT_ORDER_RELATIONSHIP, "order_bbb", pid, observed_at=T_BASE + timedelta(seconds=30))

        claim1 = make_claim(db, ClaimType.ORDER_ASSOCIATION.value, "ORDER_ID", "order_aaa", pid, created_at=T_BASE)
        claim2 = make_claim(db, ClaimType.ORDER_ASSOCIATION.value, "ORDER_ID", "order_bbb", pid, created_at=T_BASE + timedelta(seconds=30))
        link_obs_to_claim(db, claim1, obs1)
        link_obs_to_claim(db, claim2, obs2)

        conflicts = ContradictionEngine.evaluate_payment_consistency(db, pid, T_BASE + timedelta(minutes=5))
        rel_conflicts = [c for c in conflicts if c.conflict_type == ConflictType.RELATIONSHIP_CONFLICT.value]
        assert len(rel_conflicts) == 1
        assert rel_conflicts[0].severity == ConflictSeverity.HIGH.value


# ---------------------------------------------------------------------------
# Class 7: Ordering Ambiguity (same timestamp, not a direct state conflict)
# ---------------------------------------------------------------------------
class TestOrderingAmbiguity:

    def test_different_statuses_within_clock_tolerance_produces_ambiguity(self, in_memory_db):
        """
        authorized -> failed within 1s should trigger ORDERING_AMBIGUITY (INFO)
        not a hard STATE_CONFLICT since they're within clock tolerance window.
        """
        db = in_memory_db
        pid = "pay_ambiguous"

        # Within clock tolerance (0.5 seconds apart)
        obs1 = make_obs(db, 1, EvidenceType.PAYMENT_STATUS, "authorized", pid, observed_at=T_BASE)
        obs2 = make_obs(db, 2, EvidenceType.PAYMENT_STATUS, "failed", pid, observed_at=T_BASE + timedelta(milliseconds=500))

        claim1 = make_claim(db, ClaimType.PAYMENT_STATUS.value, "STATUS", "authorized", pid, created_at=T_BASE)
        claim2 = make_claim(db, ClaimType.PAYMENT_STATUS.value, "STATUS", "failed", pid, created_at=T_BASE + timedelta(milliseconds=500))
        link_obs_to_claim(db, claim1, obs1)
        link_obs_to_claim(db, claim2, obs2)

        conflicts = ContradictionEngine.evaluate_payment_consistency(
            db, pid, T_BASE + timedelta(minutes=5), clock_tolerance_seconds=2.0
        )
        ambiguities = [c for c in conflicts if c.conflict_type == ConflictType.ORDERING_AMBIGUITY.value]
        # authorized -> failed within tolerance: not terminal conflict, so ambiguity
        assert len(ambiguities) >= 1
        for a in ambiguities:
            assert a.severity == ConflictSeverity.INFO.value


# ---------------------------------------------------------------------------
# Class 8: Idempotency
# ---------------------------------------------------------------------------
class TestIdempotency:

    def test_repeated_evaluation_does_not_duplicate_conflicts(self, in_memory_db):
        db = in_memory_db
        pid = "pay_idempotent"

        obs1 = make_obs(db, 1, EvidenceType.PAYMENT_AMOUNT, "50000", pid, observed_at=T_BASE)
        obs2 = make_obs(db, 2, EvidenceType.PAYMENT_AMOUNT, "70000", pid, observed_at=T_BASE + timedelta(minutes=1))

        claim1 = make_claim(db, ClaimType.PAYMENT_AMOUNT.value, "AMOUNT", "50000", pid, created_at=T_BASE)
        claim2 = make_claim(db, ClaimType.PAYMENT_AMOUNT.value, "AMOUNT", "70000", pid, created_at=T_BASE + timedelta(minutes=1))
        link_obs_to_claim(db, claim1, obs1)
        link_obs_to_claim(db, claim2, obs2)

        eval_time = T_BASE + timedelta(minutes=5)
        ContradictionEngine.evaluate_payment_consistency(db, pid, eval_time)
        ContradictionEngine.evaluate_payment_consistency(db, pid, eval_time)
        ContradictionEngine.evaluate_payment_consistency(db, pid, eval_time)

        total_conflicts = db.query(EvidenceConflict).filter(EvidenceConflict.payment_id == pid).all()
        assert len(total_conflicts) == 1, "Idempotency failed: duplicate conflicts created"

    def test_pair_ordering_normalization(self, in_memory_db):
        """Conflict pair (A, B) must not duplicate as (B, A)."""
        db = in_memory_db
        pid = "pay_pair_norm"

        obs1 = make_obs(db, 1, EvidenceType.PAYMENT_AMOUNT, "100", pid, observed_at=T_BASE)
        obs2 = make_obs(db, 2, EvidenceType.PAYMENT_AMOUNT, "200", pid, observed_at=T_BASE + timedelta(minutes=1))

        claim1 = make_claim(db, ClaimType.PAYMENT_AMOUNT.value, "AMOUNT", "100", pid, created_at=T_BASE)
        claim2 = make_claim(db, ClaimType.PAYMENT_AMOUNT.value, "AMOUNT", "200", pid, created_at=T_BASE + timedelta(minutes=1))
        link_obs_to_claim(db, claim1, obs1)
        link_obs_to_claim(db, claim2, obs2)

        ContradictionEngine.evaluate_payment_consistency(db, pid, T_BASE + timedelta(minutes=5))
        all_conflicts = db.query(EvidenceConflict).filter(EvidenceConflict.payment_id == pid).all()
        assert len(all_conflicts) == 1
        # Ensure lower ID is always claim_a_id
        c = all_conflicts[0]
        assert c.claim_a_id < c.claim_b_id


# ---------------------------------------------------------------------------
# Class 9: Conflict Resolution
# ---------------------------------------------------------------------------
class TestConflictResolution:

    def test_conflict_can_be_resolved_preserving_original(self, in_memory_db):
        db = in_memory_db
        pid = "pay_resolution"

        obs1 = make_obs(db, 1, EvidenceType.PAYMENT_AMOUNT, "50000", pid, observed_at=T_BASE)
        obs2 = make_obs(db, 2, EvidenceType.PAYMENT_AMOUNT, "70000", pid, observed_at=T_BASE + timedelta(minutes=1))
        obs3 = make_obs(db, 3, EvidenceType.PAYMENT_AMOUNT, "70000", pid, observed_at=T_BASE + timedelta(minutes=10))

        claim1 = make_claim(db, ClaimType.PAYMENT_AMOUNT.value, "AMOUNT", "50000", pid, created_at=T_BASE)
        claim2 = make_claim(db, ClaimType.PAYMENT_AMOUNT.value, "AMOUNT", "70000", pid, created_at=T_BASE + timedelta(minutes=1))
        link_obs_to_claim(db, claim1, obs1)
        link_obs_to_claim(db, claim2, obs2)

        conflicts = ContradictionEngine.evaluate_payment_consistency(db, pid, T_BASE + timedelta(minutes=5))
        value_conflicts = [c for c in conflicts if c.conflict_type == ConflictType.VALUE_CONFLICT.value]
        assert len(value_conflicts) == 1

        conflict = value_conflicts[0]
        original_id = conflict.internal_id

        # Record resolution
        resolution = ConflictResolution(
            conflict_id=conflict.internal_id,
            resolving_evidence_id=obs3.internal_id,
            resolution_type=ResolutionType.SUPERSEDED_BY_LATER_OBSERVATION.value,
            explanation="Later authoritative observation confirmed amount=70000",
            resolved_at=T_BASE + timedelta(minutes=12),
            rule_version="1.0",
        )
        db.add(resolution)
        conflict.status = ConflictStatus.RESOLVED.value
        db.flush()

        # Original conflict must still exist and be queryable
        persisted = db.query(EvidenceConflict).filter(EvidenceConflict.internal_id == original_id).first()
        assert persisted is not None
        assert persisted.status == ConflictStatus.RESOLVED.value
        assert len(persisted.resolutions) == 1


# ---------------------------------------------------------------------------
# Class 10: No Claims — No Conflicts
# ---------------------------------------------------------------------------
class TestEdgeCases:

    def test_no_claims_returns_empty(self, in_memory_db):
        db = in_memory_db
        conflicts = ContradictionEngine.evaluate_payment_consistency(db, "pay_no_claims", T_BASE)
        assert conflicts == []

    def test_single_status_claim_no_conflict(self, in_memory_db):
        db = in_memory_db
        pid = "pay_single_status"
        obs = make_obs(db, 1, EvidenceType.PAYMENT_STATUS, "captured", pid, observed_at=T_BASE)
        claim = make_claim(db, ClaimType.PAYMENT_STATUS.value, "STATUS", "captured", pid, created_at=T_BASE)
        link_obs_to_claim(db, claim, obs)
        conflicts = ContradictionEngine.evaluate_payment_consistency(db, pid, T_BASE + timedelta(minutes=1))
        assert len(conflicts) == 0

    def test_rule_version_is_recorded(self, in_memory_db):
        db = in_memory_db
        pid = "pay_version"

        obs1 = make_obs(db, 1, EvidenceType.PAYMENT_AMOUNT, "100", pid, observed_at=T_BASE)
        obs2 = make_obs(db, 2, EvidenceType.PAYMENT_AMOUNT, "200", pid, observed_at=T_BASE + timedelta(minutes=1))
        claim1 = make_claim(db, ClaimType.PAYMENT_AMOUNT.value, "AMOUNT", "100", pid, created_at=T_BASE)
        claim2 = make_claim(db, ClaimType.PAYMENT_AMOUNT.value, "AMOUNT", "200", pid, created_at=T_BASE + timedelta(minutes=1))
        link_obs_to_claim(db, claim1, obs1)
        link_obs_to_claim(db, claim2, obs2)

        conflicts = ContradictionEngine.evaluate_payment_consistency(db, pid, T_BASE + timedelta(minutes=5))
        assert len(conflicts) >= 1
        for c in conflicts:
            assert c.rule_version == ContradictionEngine.RULE_VERSION

    def test_explanation_is_structured(self, in_memory_db):
        """Every conflict must have a structured explanation dict, not a vague string."""
        db = in_memory_db
        pid = "pay_explanation"

        obs1 = make_obs(db, 1, EvidenceType.PAYMENT_AMOUNT, "100", pid, observed_at=T_BASE)
        obs2 = make_obs(db, 2, EvidenceType.PAYMENT_AMOUNT, "200", pid, observed_at=T_BASE + timedelta(minutes=1))
        claim1 = make_claim(db, ClaimType.PAYMENT_AMOUNT.value, "AMOUNT", "100", pid, created_at=T_BASE)
        claim2 = make_claim(db, ClaimType.PAYMENT_AMOUNT.value, "AMOUNT", "200", pid, created_at=T_BASE + timedelta(minutes=1))
        link_obs_to_claim(db, claim1, obs1)
        link_obs_to_claim(db, claim2, obs2)

        conflicts = ContradictionEngine.evaluate_payment_consistency(db, pid, T_BASE + timedelta(minutes=5))
        assert len(conflicts) >= 1
        for c in conflicts:
            assert isinstance(c.explanation, dict)
            assert "what" in c.explanation
            assert "why" in c.explanation
            assert "rule" in c.explanation


# ---------------------------------------------------------------------------
# Class 11: API Endpoint Tests
# ---------------------------------------------------------------------------
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
from app.main import app


@pytest.fixture
def client(in_memory_db):
    def override_get_db():
        try:
            yield in_memory_db
        finally:
            pass

    from app.db.session import get_db
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


class TestConflictAPI:

    def test_payment_conflicts_empty(self, client):
        response = client.get("/api/v1/payments/pay_no_conflicts/conflicts")
        assert response.status_code == 200
        assert response.json() == []

    def test_payment_consistency_no_conflicts(self, client):
        response = client.get("/api/v1/payments/pay_clean/consistency")
        assert response.status_code == 200
        data = response.json()
        assert data["payment_id"] == "pay_clean"
        assert data["is_consistent"] is True
        assert data["total_conflicts"] == 0

    def test_conflict_not_found_404(self, client):
        response = client.get("/api/v1/conflicts/99999")
        assert response.status_code == 404
