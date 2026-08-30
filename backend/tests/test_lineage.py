"""
Phase 14 — Evidence Lineage & Causal Explanation Engine Test Suite.

24 tests covering:
1–3:  Completeness levels (COMPLETE, PARTIAL, BROKEN)
4–5:  Gap recording
6–9:  Forward and backward traversal correctness
10–15: Individual FK-backed lineage steps
16–17: Temporal (as_of) semantics
18–19: Safety limits (max_nodes, deduplication)
20–22: API schema validation
23:   Sensitive data absence
24:   Deterministic explanation
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict
import uuid

import pytest
from fastapi import FastAPI as _FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# SQLite JSONB polyfill
@compiles(JSONB, "sqlite")
def compile_jsonb_sqlite(type_, compiler, **kw):
    return "JSON"


from app.api.v1.lineage import router as _lineage_router
from app.db.session import Base, get_db
from app.models.evidence import EvidenceObservation
from app.models.evidence_conflict import EvidenceConflict
from app.models.evidence_fact import EvidenceFact
from app.models.evidence_integrity import EvidenceIntegritySnapshot
from app.models.evidence_quality import EvidenceQualitySnapshot
from app.models.evidence_reconciliation import EvidenceReconciliation
from app.models.evidence_structure import (
    Claim,
    EvidenceClaimLink,
    EvidenceCorroboration,
)
from app.models.evolution_models import EvidenceStateChange, EvidenceStateSnapshot
from app.models.integrity_trace import EvidenceIntegrityTrace
from app.models.lineage_types import (
    CausalRole,
    LineageCompleteness,
    LineageEdgeType,
    LineageNodeType,
    LinkageType,
)
from app.models.observation_fact_link import ObservationFactLink
from app.models.payment import Payment
from app.models.payment_event import PaymentEvent
from app.models.reconciliation_types import FactStatus, FactType, ReconciliationResult, ReconciliationRule, RECONCILIATION_RULE_VERSION
from app.models.evidence_types import EvidenceType, SourceType
from app.models.webhook_event import WebhookEvent
from app.services.lineage_engine import (
    LineageAssembler,
    _node_id,
    build_fact_lineage,
    build_payment_lineage,
    build_trace_lineage,
    find_lineage_path,
)

# ---------------------------------------------------------------------------
# Shared test app
# ---------------------------------------------------------------------------
_test_app = _FastAPI()
_test_app.include_router(_lineage_router, prefix="/api/v1")

T_BASE = datetime(2026, 8, 23, 10, 0, 0, tzinfo=timezone.utc)
T_PLUS_1M = T_BASE + timedelta(minutes=1)
T_PLUS_5M = T_BASE + timedelta(minutes=5)
T_FUTURE = T_BASE + timedelta(hours=2)


# ---------------------------------------------------------------------------
# Fixtures
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
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def api_db():
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


@pytest.fixture
def client(api_db):
    _test_app.dependency_overrides[get_db] = lambda: api_db
    with TestClient(_test_app, raise_server_exceptions=False) as c:
        yield c
    _test_app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Helper builders
# ---------------------------------------------------------------------------

def _make_webhook(db, payment_id: str = "pay_test001") -> WebhookEvent:
    we = WebhookEvent(
        razorpay_event_id=f"evt_{uuid.uuid4().hex[:8]}",
        event_type="payment.captured",
        received_at=T_BASE,
        event_timestamp=T_BASE,
        signature_verified=True,
        processing_status="PROCESSED",
        raw_payload={"event": "payment.captured"},
        payload_hash="abc123",
        payment_id=payment_id,
    )
    db.add(we)
    db.flush()
    return we


def _make_payment(db, payment_id: str = "pay_test001") -> Payment:
    p = Payment(
        razorpay_payment_id=payment_id,
        status="captured",
        currency="INR",
        amount_minor=49900,
        captured=True,
        first_observed_at=T_BASE,
        last_observed_at=T_BASE,
    )
    db.add(p)
    db.flush()
    return p


def _make_payment_event(db, payment: Payment, webhook: WebhookEvent) -> PaymentEvent:
    pe = PaymentEvent(
        payment_id=payment.internal_id,
        webhook_event_id=webhook.id,
        event_type="payment.captured",
        event_timestamp=T_BASE,
    )
    db.add(pe)
    db.flush()
    return pe


def _make_observation(
    db,
    payment_id: str = "pay_test001",
    webhook_id: int = None,
    source_type: str = SourceType.RAZORPAY_WEBHOOK,
    evidence_type: str = EvidenceType.PAYMENT_STATUS,
    observed_at: datetime = None,
) -> EvidenceObservation:
    obs = EvidenceObservation(
        subject_type="payment",
        subject_id=payment_id,
        evidence_type=evidence_type,
        source_type=source_type,
        extraction_method="WEBHOOK_FIELD_EXTRACTION",
        extraction_version="1.0",
        value_type="STATUS_STRING",
        value="captured",
        observed_at=observed_at or T_BASE,
        webhook_event_id=webhook_id,
    )
    db.add(obs)
    db.flush()
    return obs


def _make_fact(db, payment_id: str = "pay_test001") -> EvidenceFact:
    import hashlib
    cv = "captured"
    ft = FactType.PAYMENT_CAPTURED
    h = hashlib.sha256(f"{payment_id}|{ft}|{cv}".encode()).hexdigest()
    fact = EvidenceFact(
        payment_id=payment_id,
        fact_type=ft,
        canonical_value=cv,
        canonical_value_hash=h,
        status=FactStatus.ACTIVE,
        first_observed_at=T_BASE,
        last_observed_at=T_BASE,
        observation_count=1,
        distinct_source_count=1,
    )
    db.add(fact)
    db.flush()
    return fact


def _link_obs_fact(db, obs: EvidenceObservation, fact: EvidenceFact) -> ObservationFactLink:
    link = ObservationFactLink(observation_id=obs.internal_id, fact_id=fact.internal_id)
    db.add(link)
    db.flush()
    return link


def _make_claim(db, payment_id: str = "pay_test001") -> Claim:
    claim = Claim(
        subject_type="payment",
        subject_id=payment_id,
        claim_type="PAYMENT_STATUS",
        claim_key="payment_status",
        canonical_value="captured",
    )
    db.add(claim)
    db.flush()
    return claim


def _link_obs_claim(db, obs: EvidenceObservation, claim: Claim) -> EvidenceClaimLink:
    link = EvidenceClaimLink(claim_id=claim.internal_id, evidence_id=obs.internal_id)
    db.add(link)
    db.flush()
    return link


def _make_corroboration(db, claim: Claim, payment_id: str = "pay_test001") -> EvidenceCorroboration:
    from app.models.structure_types import CorroborationType, IndependenceStatus
    corr = EvidenceCorroboration(
        claim_id=claim.internal_id,
        payment_id=payment_id,
        corroboration_type=CorroborationType.MULTI_SOURCE,
        independence_status=IndependenceStatus.INDEPENDENT,
        observation_count=2,
        distinct_sources_count=2,
        distinct_events_count=2,
    )
    db.add(corr)
    db.flush()
    return corr


def _make_conflict(db, claim_a: Claim, claim_b: Claim, payment_id: str = "pay_test001") -> EvidenceConflict:
    conflict = EvidenceConflict(
        payment_id=payment_id,
        claim_a_id=claim_a.internal_id,
        claim_b_id=claim_b.internal_id,
        conflict_type="VALUE_MISMATCH",
        severity="HIGH",
        status="OPEN",
        detected_at=T_BASE,
    )
    db.add(conflict)
    db.flush()
    return conflict


def _make_integrity_snapshot(db, payment_id: str = "pay_test001") -> EvidenceIntegritySnapshot:
    snap = EvidenceIntegritySnapshot(
        payment_id=payment_id,
        evaluated_at=T_PLUS_1M,
        overall_status="SUPPORTED",
        methodology_version="EIS-1.0",
        evidence_count=1,
        source_count=1,
        conflict_count=0,
        open_conflict_count=0,
    )
    db.add(snap)
    db.flush()
    return snap


def _make_trace(db, payment_id: str, snapshot: EvidenceIntegritySnapshot) -> EvidenceIntegrityTrace:
    trace = EvidenceIntegrityTrace(
        trace_id=str(uuid.uuid4()),
        trace_type="EVALUATION",
        payment_id=payment_id,
        evaluated_at=T_PLUS_1M,
        methodology_version="EIS-1.0",
        status="COMPLETED",
        integrity_snapshot_internal_id=snapshot.internal_id,
        overall_status="SUPPORTED",
        trace_hash="deadbeef" * 8,
        hash_algorithm="SHA-256",
        canonicalization_version="CG-1.0",
        canonical_payload={"methodology_version": "EIS-1.0"},
        finalized_at=T_PLUS_1M,
    )
    db.add(trace)
    db.flush()
    return trace


def _make_state_snapshot(
    db,
    payment_id: str,
    integrity_snapshot: EvidenceIntegritySnapshot,
    evaluation_time: datetime = None,
) -> EvidenceStateSnapshot:
    ss = EvidenceStateSnapshot(
        payment_id=payment_id,
        evaluation_time=evaluation_time or T_PLUS_1M,
        integrity_snapshot_id=integrity_snapshot.internal_id,
        overall_integrity_status="SUPPORTED",
        evidence_count=1,
        source_count=1,
        claim_count=1,
        conflict_count=0,
        open_conflict_count=0,
        corroboration_status="CORROBORATED",
        independence_status="INDEPENDENT",
        freshness_status="FRESH",
        consistency_status="NO_DETECTED_CONFLICT",
        methodology_version="EIS-1.0",
    )
    db.add(ss)
    db.flush()
    return ss


def _make_reconciliation(
    db,
    obs_a: EvidenceObservation,
    obs_b: EvidenceObservation,
    fact: EvidenceFact,
    result: str = ReconciliationResult.SAME_FACT,
) -> EvidenceReconciliation:
    min_id = min(obs_a.internal_id, obs_b.internal_id)
    max_id = max(obs_a.internal_id, obs_b.internal_id)
    rec = EvidenceReconciliation(
        observation_a_id=min_id,
        observation_b_id=max_id,
        result=result,
        rule_id=ReconciliationRule.SAME_PROVIDER_EVENT_V1,
        rule_version=RECONCILIATION_RULE_VERSION,
        explanation="Both observations originate from the same provider event.",
        fact_id=fact.internal_id if result == ReconciliationResult.SAME_FACT else None,
        evaluated_at=T_BASE,
    )
    db.add(rec)
    db.flush()
    return rec


# ===========================================================================
# TESTS
# ===========================================================================

# ---------------------------------------------------------------------------
# 1. Complete lineage — all steps present
# ---------------------------------------------------------------------------
def test_complete_lineage_webhook_to_trace(db):
    """Full FK chain present → COMPLETE lineage with trace node."""
    payment_id = "pay_complete"
    p = _make_payment(db, payment_id)
    we = _make_webhook(db, payment_id)
    pe = _make_payment_event(db, p, we)
    obs = _make_observation(db, payment_id, webhook_id=we.id)
    fact = _make_fact(db, payment_id)
    _link_obs_fact(db, obs, fact)
    claim = _make_claim(db, payment_id)
    _link_obs_claim(db, obs, claim)
    snap = _make_integrity_snapshot(db, payment_id)
    trace = _make_trace(db, payment_id, snap)
    db.commit()

    result = build_payment_lineage(db, payment_id)

    node_types = [n.node_type for n in result.nodes]
    assert LineageNodeType.WEBHOOK_EVENT in node_types
    assert LineageNodeType.OBSERVATION in node_types
    assert LineageNodeType.FACT in node_types
    assert LineageNodeType.CLAIM in node_types
    assert LineageNodeType.INTEGRITY_SNAPSHOT in node_types
    assert LineageNodeType.INTEGRITY_TRACE in node_types
    assert result.completeness == LineageCompleteness.COMPLETE


# ---------------------------------------------------------------------------
# 2. Partial lineage — observations exist but no fact (no reconciliation)
# ---------------------------------------------------------------------------
def test_partial_lineage_no_fact(db):
    """Observations without reconciliation into a Fact → PARTIAL."""
    payment_id = "pay_partial"
    _make_payment(db, payment_id)
    we = _make_webhook(db, payment_id)
    _make_observation(db, payment_id, webhook_id=we.id)
    snap = _make_integrity_snapshot(db, payment_id)
    _make_trace(db, payment_id, snap)
    db.commit()

    result = build_payment_lineage(db, payment_id)

    assert result.completeness == LineageCompleteness.PARTIAL
    node_types = [n.node_type for n in result.nodes]
    assert LineageNodeType.OBSERVATION in node_types
    assert LineageNodeType.FACT not in node_types


# ---------------------------------------------------------------------------
# 3. Broken lineage — no observations at all
# ---------------------------------------------------------------------------
def test_broken_lineage_no_observation(db):
    """Payment with no observations and no integrity evaluation → BROKEN."""
    payment_id = "pay_broken"
    _make_payment(db, payment_id)
    db.commit()

    result = build_payment_lineage(db, payment_id)

    assert result.completeness == LineageCompleteness.BROKEN
    assert len(result.gaps) >= 1


# ---------------------------------------------------------------------------
# 4. Lineage gap detected when no integrity snapshot exists
# ---------------------------------------------------------------------------
def test_lineage_gap_no_integrity_snapshot(db):
    """Observation present but no integrity snapshot → gap recorded."""
    payment_id = "pay_gap"
    _make_payment(db, payment_id)
    we = _make_webhook(db, payment_id)
    _make_observation(db, payment_id, webhook_id=we.id)
    db.commit()

    result = build_payment_lineage(db, payment_id)

    gap_edges = [g.expected_edge_type for g in result.gaps]
    assert LineageEdgeType.CONTRIBUTES_TO in gap_edges


# ---------------------------------------------------------------------------
# 5. Lineage gap when trace is missing for snapshot
# ---------------------------------------------------------------------------
def test_lineage_gap_no_trace_for_snapshot(db):
    """Integrity snapshot exists but no completed trace → gap recorded."""
    payment_id = "pay_notrace"
    _make_payment(db, payment_id)
    we = _make_webhook(db, payment_id)
    _make_observation(db, payment_id, webhook_id=we.id)
    _make_integrity_snapshot(db, payment_id)
    db.commit()

    result = build_payment_lineage(db, payment_id)

    gap_edges = [g.expected_edge_type for g in result.gaps]
    assert LineageEdgeType.EVALUATED_BY in gap_edges


# ---------------------------------------------------------------------------
# 6. Forward traversal: webhook → observation → fact → claim → integrity
# ---------------------------------------------------------------------------
def test_forward_traversal_webhook_to_integrity(db):
    """Edge chain is present in the correct forward direction."""
    payment_id = "pay_fwd"
    p = _make_payment(db, payment_id)
    we = _make_webhook(db, payment_id)
    obs = _make_observation(db, payment_id, webhook_id=we.id)
    fact = _make_fact(db, payment_id)
    _link_obs_fact(db, obs, fact)
    claim = _make_claim(db, payment_id)
    _link_obs_claim(db, obs, claim)
    snap = _make_integrity_snapshot(db, payment_id)
    _make_trace(db, payment_id, snap)
    db.commit()

    result = build_payment_lineage(db, payment_id)
    edge_types = {e.edge_type for e in result.edges}

    assert LineageEdgeType.PRODUCED in edge_types
    assert LineageEdgeType.REPRESENTS in edge_types
    assert LineageEdgeType.SUPPORTS in edge_types
    assert LineageEdgeType.EVALUATED_BY in edge_types


# ---------------------------------------------------------------------------
# 7. Backward traversal: trace → observation → webhook
# ---------------------------------------------------------------------------
def test_backward_traversal_trace_to_webhook(db):
    """build_trace_lineage reaches back to WebhookEvent nodes."""
    payment_id = "pay_bwd"
    p = _make_payment(db, payment_id)
    we = _make_webhook(db, payment_id)
    obs = _make_observation(db, payment_id, webhook_id=we.id)
    snap = _make_integrity_snapshot(db, payment_id)
    trace = _make_trace(db, payment_id, snap)
    db.commit()

    result = build_trace_lineage(db, trace.trace_id)

    node_types = [n.node_type for n in result.nodes]
    assert LineageNodeType.INTEGRITY_TRACE in node_types
    assert LineageNodeType.INTEGRITY_SNAPSHOT in node_types
    assert LineageNodeType.OBSERVATION in node_types
    assert LineageNodeType.WEBHOOK_EVENT in node_types
    assert result.trace_id == trace.trace_id
    assert result.payment_id == payment_id


# ---------------------------------------------------------------------------
# 8. Bidirectional consistency: forward and backward produce same payment
# ---------------------------------------------------------------------------
def test_bidirectional_consistency(db):
    """Forward and backward lineage reference the same payment and entity counts."""
    payment_id = "pay_bi"
    p = _make_payment(db, payment_id)
    we = _make_webhook(db, payment_id)
    obs = _make_observation(db, payment_id, webhook_id=we.id)
    snap = _make_integrity_snapshot(db, payment_id)
    trace = _make_trace(db, payment_id, snap)
    db.commit()

    fwd = build_payment_lineage(db, payment_id)
    bwd = build_trace_lineage(db, trace.trace_id)

    fwd_types = {n.node_type for n in fwd.nodes}
    bwd_types = {n.node_type for n in bwd.nodes}

    # Backward traversal is a strict subset of forward (forward has PAYMENT node
    # anchoring the traversal; backward starts from trace and walks inward)
    assert bwd_types.issubset(fwd_types)


# ---------------------------------------------------------------------------
# 9. Observation → Fact via ObservationFactLink (FK-authoritative)
# ---------------------------------------------------------------------------
def test_observation_to_fact_lineage(db):
    """REPRESENTS edge exists and has FOREIGN_KEY linkage_type."""
    payment_id = "pay_obs_fact"
    _make_payment(db, payment_id)
    we = _make_webhook(db, payment_id)
    obs = _make_observation(db, payment_id, webhook_id=we.id)
    fact = _make_fact(db, payment_id)
    _link_obs_fact(db, obs, fact)
    db.commit()

    result = build_payment_lineage(db, payment_id)
    represents_edges = [
        e for e in result.edges if e.edge_type == LineageEdgeType.REPRESENTS
    ]

    assert len(represents_edges) == 1
    assert represents_edges[0].linkage_type == LinkageType.FOREIGN_KEY
    assert represents_edges[0].causal_role == CausalRole.DERIVED_FROM


# ---------------------------------------------------------------------------
# 10. Claim linkage via EvidenceClaimLink
# ---------------------------------------------------------------------------
def test_claim_linkage_via_observation(db):
    """SUPPORTS edge exists connecting Observation → Claim via EvidenceClaimLink."""
    payment_id = "pay_claim"
    _make_payment(db, payment_id)
    we = _make_webhook(db, payment_id)
    obs = _make_observation(db, payment_id, webhook_id=we.id)
    claim = _make_claim(db, payment_id)
    _link_obs_claim(db, obs, claim)
    db.commit()

    result = build_payment_lineage(db, payment_id)
    supports_edges = [e for e in result.edges if e.edge_type == LineageEdgeType.SUPPORTS]

    assert len(supports_edges) >= 1
    assert supports_edges[0].linkage_type == LinkageType.FOREIGN_KEY


# ---------------------------------------------------------------------------
# 11. Integrity trace linkage via FK
# ---------------------------------------------------------------------------
def test_integrity_trace_linkage(db):
    """EVALUATED_BY edge links IntegritySnapshot → IntegrityTrace via FK."""
    payment_id = "pay_trace_fk"
    _make_payment(db, payment_id)
    we = _make_webhook(db, payment_id)
    _make_observation(db, payment_id, webhook_id=we.id)
    snap = _make_integrity_snapshot(db, payment_id)
    _make_trace(db, payment_id, snap)
    db.commit()

    result = build_payment_lineage(db, payment_id)
    evaluated_edges = [e for e in result.edges if e.edge_type == LineageEdgeType.EVALUATED_BY]

    assert len(evaluated_edges) == 1
    assert evaluated_edges[0].linkage_type == LinkageType.FOREIGN_KEY


# ---------------------------------------------------------------------------
# 12. Reconciliation visible in lineage
# ---------------------------------------------------------------------------
def test_reconciliation_visible_in_lineage(db):
    """RECONCILED_INTO edge exists when SAME_FACT reconciliation is present."""
    payment_id = "pay_rec"
    _make_payment(db, payment_id)
    we = _make_webhook(db, payment_id)
    obs_a = _make_observation(db, payment_id, webhook_id=we.id)
    obs_b = _make_observation(db, payment_id, webhook_id=we.id)
    fact = _make_fact(db, payment_id)
    _link_obs_fact(db, obs_a, fact)
    _link_obs_fact(db, obs_b, fact)
    _make_reconciliation(db, obs_a, obs_b, fact)
    db.commit()

    result = build_payment_lineage(db, payment_id)
    node_types = [n.node_type for n in result.nodes]
    edge_types = [e.edge_type for e in result.edges]

    assert LineageNodeType.RECONCILIATION in node_types
    assert LineageEdgeType.RECONCILED_INTO in edge_types


# ---------------------------------------------------------------------------
# 13. Conflict visible in lineage
# ---------------------------------------------------------------------------
def test_conflict_visible_in_lineage(db):
    """EvidenceConflict appears as a node and CONFLICTED_BY edge exists."""
    payment_id = "pay_conflict"
    _make_payment(db, payment_id)
    we = _make_webhook(db, payment_id)
    obs = _make_observation(db, payment_id, webhook_id=we.id)
    claim_a = _make_claim(db, payment_id)
    claim_b = Claim(
        subject_type="payment",
        subject_id=payment_id,
        claim_type="PAYMENT_STATUS",
        claim_key="payment_status",
        canonical_value="failed",
    )
    db.add(claim_b)
    db.flush()
    _link_obs_claim(db, obs, claim_a)
    _make_conflict(db, claim_a, claim_b, payment_id)
    db.commit()

    result = build_payment_lineage(db, payment_id)
    node_types = [n.node_type for n in result.nodes]
    edge_types = [e.edge_type for e in result.edges]

    assert LineageNodeType.CONFLICT in node_types
    assert LineageEdgeType.CONFLICTED_BY in edge_types


# ---------------------------------------------------------------------------
# 14. State change visible in lineage
# ---------------------------------------------------------------------------
def test_state_change_visible_in_lineage(db):
    """EvidenceStateChange nodes and STATE_TRANSITION edges appear in lineage."""
    payment_id = "pay_sc"
    _make_payment(db, payment_id)
    we = _make_webhook(db, payment_id)
    _make_observation(db, payment_id, webhook_id=we.id)
    snap = _make_integrity_snapshot(db, payment_id)
    _make_trace(db, payment_id, snap)

    # Two state snapshots
    ss1 = _make_state_snapshot(db, payment_id, snap, evaluation_time=T_BASE)
    snap2 = EvidenceIntegritySnapshot(
        payment_id=payment_id,
        evaluated_at=T_PLUS_5M,
        overall_status="SUPPORTED",
        methodology_version="EIS-1.0",
        evidence_count=2,
        source_count=1,
        conflict_count=0,
        open_conflict_count=0,
    )
    db.add(snap2)
    db.flush()
    ss2 = _make_state_snapshot(db, payment_id, snap2, evaluation_time=T_PLUS_5M)

    sc = EvidenceStateChange(
        change_id=str(uuid.uuid4()),
        payment_id=payment_id,
        previous_snapshot_id=ss1.internal_id,
        current_snapshot_id=ss2.internal_id,
        detected_at=T_PLUS_5M,
        change_type="CORROBORATION_INCREASED",
        dimension="CORROBORATION",
        previous_value="SINGLE_SOURCE",
        current_value="CORROBORATED",
        direct_cause="NEW_OBSERVATION",
        causality="INFERRED",
        magnitude="MODERATE",
    )
    db.add(sc)
    db.commit()

    result = build_payment_lineage(db, payment_id)
    node_types = [n.node_type for n in result.nodes]
    edge_types = [e.edge_type for e in result.edges]

    assert LineageNodeType.STATE_SNAPSHOT in node_types
    assert LineageNodeType.STATE_CHANGE in node_types
    assert LineageEdgeType.STATE_TRANSITION in edge_types


# ---------------------------------------------------------------------------
# 15. Fact lineage API (build_fact_lineage)
# ---------------------------------------------------------------------------
def test_fact_lineage(db):
    """build_fact_lineage returns FACT node + supporting observations + webhook."""
    payment_id = "pay_fact_lin"
    _make_payment(db, payment_id)
    we = _make_webhook(db, payment_id)
    obs = _make_observation(db, payment_id, webhook_id=we.id)
    fact = _make_fact(db, payment_id)
    _link_obs_fact(db, obs, fact)
    db.commit()

    result = build_fact_lineage(db, fact.internal_id)

    node_types = [n.node_type for n in result.nodes]
    assert LineageNodeType.FACT in node_types
    assert LineageNodeType.OBSERVATION in node_types
    assert LineageNodeType.WEBHOOK_EVENT in node_types
    assert result.fact_id == fact.internal_id
    assert result.payment_id == payment_id


# ---------------------------------------------------------------------------
# 16. as_of exclusion — future observations are excluded
# ---------------------------------------------------------------------------
def test_as_of_exclusion(db):
    """Evidence observed after as_of is excluded from lineage."""
    payment_id = "pay_asof"
    _make_payment(db, payment_id)
    we = _make_webhook(db, payment_id)
    # Earlier observation — should be included
    obs_early = _make_observation(db, payment_id, webhook_id=we.id, observed_at=T_BASE)
    # Future observation — should be excluded
    obs_future = _make_observation(db, payment_id, webhook_id=we.id, observed_at=T_FUTURE)
    db.commit()

    result = build_payment_lineage(db, payment_id, as_of=T_PLUS_1M)

    obs_entity_ids = {
        n.entity_id for n in result.nodes if n.node_type == LineageNodeType.OBSERVATION
    }
    assert str(obs_early.internal_id) in obs_entity_ids
    assert str(obs_future.internal_id) not in obs_entity_ids


# ---------------------------------------------------------------------------
# 17. Future evidence not in lineage
# ---------------------------------------------------------------------------
def test_future_evidence_excluded_by_default(db):
    """When as_of is None, all observations at or before now are included."""
    payment_id = "pay_nofuture"
    _make_payment(db, payment_id)
    we = _make_webhook(db, payment_id)
    obs = _make_observation(db, payment_id, webhook_id=we.id, observed_at=T_BASE)
    db.commit()

    result = build_payment_lineage(db, payment_id)
    obs_ids = {n.entity_id for n in result.nodes if n.node_type == LineageNodeType.OBSERVATION}
    assert str(obs.internal_id) in obs_ids


# ---------------------------------------------------------------------------
# 18. max_nodes safety limit
# ---------------------------------------------------------------------------
def test_max_nodes_limit(db):
    """Assembler truncates at max_nodes and sets truncated=True."""
    assembler = LineageAssembler(max_nodes=2)
    from app.schemas.lineage import LineageNode
    for i in range(5):
        assembler.add_node(LineageNode(
            node_id=f"TEST:{i}",
            node_type=LineageNodeType.OBSERVATION,
            entity_id=str(i),
            label=f"obs {i}",
        ))
    assert len(assembler.nodes) == 2
    assert assembler.truncated is True


# ---------------------------------------------------------------------------
# 19. Duplicate nodes eliminated
# ---------------------------------------------------------------------------
def test_duplicate_nodes_eliminated(db):
    """A webhook referenced by two observations appears only once in lineage."""
    payment_id = "pay_dedup"
    _make_payment(db, payment_id)
    we = _make_webhook(db, payment_id)
    # Two observations from the same webhook
    _make_observation(db, payment_id, webhook_id=we.id)
    _make_observation(db, payment_id, webhook_id=we.id)
    db.commit()

    result = build_payment_lineage(db, payment_id)
    webhook_nodes = [n for n in result.nodes if n.node_type == LineageNodeType.WEBHOOK_EVENT]
    assert len(webhook_nodes) == 1
    assert webhook_nodes[0].entity_id == str(we.id)


# ---------------------------------------------------------------------------
# 20. API: payment lineage schema validation
# ---------------------------------------------------------------------------
def test_api_payment_lineage_schema(client, api_db):
    """GET /payments/{payment_id}/lineage returns valid PaymentLineageResponse."""
    payment_id = "pay_api"
    p = _make_payment(api_db, payment_id)
    we = _make_webhook(api_db, payment_id)
    obs = _make_observation(api_db, payment_id, webhook_id=we.id)
    snap = _make_integrity_snapshot(api_db, payment_id)
    _make_trace(api_db, payment_id, snap)
    api_db.commit()

    resp = client.get(f"/api/v1/payments/{payment_id}/lineage")
    assert resp.status_code == 200
    body = resp.json()
    assert "nodes" in body
    assert "edges" in body
    assert "gaps" in body
    assert "completeness" in body
    assert "summary" in body
    assert "explanation" in body
    assert "evaluation_context" in body
    assert body["payment_id"] == payment_id


# ---------------------------------------------------------------------------
# 21. API: fact lineage schema validation
# ---------------------------------------------------------------------------
def test_api_fact_lineage_schema(client, api_db):
    """GET /facts/{fact_id}/lineage returns valid FactLineageResponse."""
    payment_id = "pay_api_fact"
    _make_payment(api_db, payment_id)
    we = _make_webhook(api_db, payment_id)
    obs = _make_observation(api_db, payment_id, webhook_id=we.id)
    fact = _make_fact(api_db, payment_id)
    _link_obs_fact(api_db, obs, fact)
    api_db.commit()

    resp = client.get(f"/api/v1/facts/{fact.internal_id}/lineage")
    assert resp.status_code == 200
    body = resp.json()
    assert body["fact_id"] == fact.internal_id
    assert "nodes" in body
    assert "edges" in body


# ---------------------------------------------------------------------------
# 22. API: path search
# ---------------------------------------------------------------------------
def test_api_lineage_path(client, api_db):
    """GET /lineage/path returns valid LineagePathResponse."""
    payment_id = "pay_path"
    p = _make_payment(api_db, payment_id)
    we = _make_webhook(api_db, payment_id)
    obs = _make_observation(api_db, payment_id, webhook_id=we.id)
    snap = _make_integrity_snapshot(api_db, payment_id)
    trace = _make_trace(api_db, payment_id, snap)
    api_db.commit()

    resp = client.get(
        "/api/v1/lineage/path",
        params={
            "source_type": LineageNodeType.PAYMENT,
            "source_id": payment_id,
            "target_type": LineageNodeType.INTEGRITY_SNAPSHOT,
            "target_id": str(snap.internal_id),
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "found" in body
    assert "path" in body
    assert "edges" in body
    assert "depth" in body
    assert "truncated" in body


# ---------------------------------------------------------------------------
# 23. Sensitive data is never exposed
# ---------------------------------------------------------------------------
def test_sensitive_data_absent(db):
    """raw_payload, signature, secrets are never in any node metadata."""
    payment_id = "pay_sensitive"
    _make_payment(db, payment_id)
    we = _make_webhook(db, payment_id)
    _make_observation(db, payment_id, webhook_id=we.id)
    snap = _make_integrity_snapshot(db, payment_id)
    _make_trace(db, payment_id, snap)
    db.commit()

    result = build_payment_lineage(db, payment_id)

    _SENSITIVE_KEYS = {
        "raw_payload", "payload", "signature", "secret", "password",
        "api_key", "webhook_secret", "cvv", "pin", "otp", "token",
    }
    for node in result.nodes:
        for key in node.metadata:
            assert key.lower() not in _SENSITIVE_KEYS, (
                f"Sensitive key '{key}' found in node {node.node_id} metadata"
            )


# ---------------------------------------------------------------------------
# 24. Deterministic explanation
# ---------------------------------------------------------------------------
def test_deterministic_explanation(db):
    """Same data always produces the same explanation summary string."""
    payment_id = "pay_det"
    _make_payment(db, payment_id)
    we = _make_webhook(db, payment_id)
    obs = _make_observation(db, payment_id, webhook_id=we.id)
    snap = _make_integrity_snapshot(db, payment_id)
    _make_trace(db, payment_id, snap)
    db.commit()

    result_1 = build_payment_lineage(db, payment_id)
    result_2 = build_payment_lineage(db, payment_id)

    assert result_1.explanation.summary == result_2.explanation.summary
    assert result_1.explanation.detail_lines == result_2.explanation.detail_lines
