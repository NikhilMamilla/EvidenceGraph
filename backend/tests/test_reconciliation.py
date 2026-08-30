"""
Phase 13 — Multi-Source Evidence Reconciliation & Evidence Identity Test Suite.

22 Comprehensive Tests:
1. Exact same provider event (SAME_FACT with SAME_PROVIDER_EVENT_V1)
2. Duplicate webhook delivery does not inflate independent facts
3. Same fact from different observation mechanisms (SAME_FACT_DIFFERENT_SOURCE_V1)
4. Different lifecycle facts remain separate and related (DIFFERENT_LIFECYCLE_V1)
5. Same value but different payments never merged globally
6. Temporal ambiguity (timestamps > window -> UNKNOWN with TEMPORAL_AMBIGUITY_V1)
7. Unknown identity for insufficient event metadata
8. Conflicting facts (CONFLICTING_FACT with CONFLICTING_VALUE_V1)
9. Provenance preservation: raw observations are never deleted or mutated
10. Fact supersession representation
11. Fact invalidation and status representations
12. Backfill execution across multiple payments
13. Backfill idempotency (running twice produces 0 duplicate facts)
14. Phase 7 corroboration integration (same provider event != independent corroboration)
15. Phase 8 conflict integration (conflicting facts reflect in conflict models)
16. Phase 9 integrity integration
17. Phase 10 trace integration
18. Phase 11 temporal integration
19. API route status codes and structures
20. Sensitive data filtering (no raw_payload, credentials, or PII exposed)
21. Candidate blocking avoids O(N^2) global comparisons
22. Real event ingestion compatibility (Razorpay webhook -> fact extraction)
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import pytest
from fastapi import FastAPI as _FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# SQLite JSONB polyfill
@compiles(JSONB, "sqlite")
def compile_jsonb_sqlite(type_, compiler, **kw):
    return "JSON"


from app.api.v1.reconciliation import router as _reconciliation_router
from app.db.session import Base, get_db
from app.models.evidence import EvidenceObservation
from app.models.evidence_fact import EvidenceFact
from app.models.evidence_reconciliation import EvidenceReconciliation
from app.models.evidence_structure import Claim, EvidenceClaimLink, EvidenceCorroboration
from app.models.evidence_types import EvidenceType, SourceType, ValueType
from app.models.observation_fact_link import ObservationFactLink
from app.models.payment import Payment
from app.models.payment_event import PaymentEvent
from app.models.reconciliation_types import (
    FactStatus,
    FactType,
    ReconciliationResult,
    ReconciliationRule,
    RECONCILIATION_RULE_VERSION,
)
from app.models.structure_types import CorroborationType, IndependenceStatus
from app.models.webhook_event import WebhookEvent
from app.services.corroboration_service import CorroborationService
from app.services.fact_service import FactService
from app.services.reconciliation_engine import ReconciliationEngine

_test_app = _FastAPI()
_test_app.include_router(_reconciliation_router, prefix="/api/v1")

T_BASE = datetime(2026, 8, 23, 10, 0, 0, tzinfo=timezone.utc)
T_PLUS_1S = T_BASE + timedelta(seconds=1)
T_PLUS_2S = T_BASE + timedelta(seconds=2)
T_PLUS_10M = T_BASE + timedelta(minutes=10)


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

    def override_get_db():
        session = Session()
        try:
            yield session
        finally:
            session.close()

    _test_app.dependency_overrides[get_db] = override_get_db
    seed_session = Session()
    try:
        yield seed_session
    finally:
        seed_session.close()
        _test_app.dependency_overrides.clear()


@pytest.fixture
def client(api_db):
    with TestClient(_test_app) as c:
        yield c


def _create_obs(
    db,
    *,
    subject_id="pay_test_01",
    evidence_type="PAYMENT_STATUS",
    value="captured",
    source_type="RAZORPAY_WEBHOOK",
    observed_at=T_BASE,
    webhook_event_id=1,
    payment_event_id=1,
    provenance_metadata=None,
) -> EvidenceObservation:
    obs = EvidenceObservation(
        evidence_type=evidence_type,
        subject_type="payment",
        subject_id=subject_id,
        value=value,
        value_type="ENUM",
        source_type=source_type,
        source_reference=str(webhook_event_id) if webhook_event_id else "ref",
        observed_at=observed_at,
        webhook_event_id=webhook_event_id,
        payment_event_id=payment_event_id,
        extraction_method="WEBHOOK_FIELD_EXTRACTION",
        extraction_version="1.0",
        provenance_metadata=provenance_metadata or {"event_type": "payment.captured"},
        created_at=T_BASE,
    )
    db.add(obs)
    db.flush()
    return obs


# =============================================================================
# 1. Exact Same Provider Event
# =============================================================================
def test_1_exact_same_provider_event(db):
    obs1 = _create_obs(db, webhook_event_id=101, payment_event_id=201)
    obs2 = _create_obs(db, webhook_event_id=101, payment_event_id=201)

    decision = ReconciliationEngine.reconcile_pair(obs1, obs2)
    assert decision.result == ReconciliationResult.SAME_FACT
    assert decision.rule_id == ReconciliationRule.SAME_PROVIDER_EVENT_V1
    assert "same Razorpay provider webhook delivery" in decision.explanation


# =============================================================================
# 2. Duplicate Webhook Does Not Inflate Facts
# =============================================================================
def test_2_duplicate_webhook_does_not_create_duplicate_fact(db):
    # Two observations extracted from duplicate deliveries of same event
    obs1 = _create_obs(db, webhook_event_id=101, payment_event_id=201)
    obs2 = _create_obs(db, webhook_event_id=101, payment_event_id=201)

    facts = ReconciliationEngine.reconcile_payment(db, "pay_test_01")
    assert len(facts) == 1
    fact = facts[0]
    assert fact.fact_type == FactType.PAYMENT_CAPTURED
    assert fact.canonical_value == "captured"
    assert fact.observation_count == 2
    assert fact.distinct_source_count == 1


# =============================================================================
# 3. Same Fact From Different Observation Mechanisms
# =============================================================================
def test_3_same_fact_different_source(db):
    obs1 = _create_obs(db, source_type="RAZORPAY_WEBHOOK", observed_at=T_BASE, webhook_event_id=101)
    obs2 = _create_obs(db, source_type="INTERNAL_SYSTEM", observed_at=T_PLUS_1S, webhook_event_id=None, payment_event_id=None)

    decision = ReconciliationEngine.reconcile_pair(obs1, obs2)
    assert decision.result == ReconciliationResult.SAME_FACT
    assert decision.rule_id == ReconciliationRule.SAME_FACT_DIFFERENT_SOURCE_V1

    facts = ReconciliationEngine.reconcile_payment(db, "pay_test_01")
    assert len(facts) == 1
    assert facts[0].distinct_source_count == 2
    assert facts[0].observation_count == 2


# =============================================================================
# 4. Different Lifecycle Facts
# =============================================================================
def test_4_different_lifecycle_facts(db):
    obs_auth = _create_obs(
        db,
        evidence_type="PAYMENT_STATUS",
        value="authorized",
        observed_at=T_BASE,
        webhook_event_id=101,
        provenance_metadata={"event_type": "payment.authorized"},
    )
    obs_cap = _create_obs(
        db,
        evidence_type="PAYMENT_STATUS",
        value="captured",
        observed_at=T_PLUS_1S,
        webhook_event_id=102,
        provenance_metadata={"event_type": "payment.captured"},
    )

    decision = ReconciliationEngine.reconcile_pair(obs_auth, obs_cap)
    assert decision.result == ReconciliationResult.RELATED_FACT
    assert decision.rule_id == ReconciliationRule.DIFFERENT_LIFECYCLE_V1

    facts = ReconciliationEngine.reconcile_payment(db, "pay_test_01")
    assert len(facts) == 2
    fact_types = {f.fact_type for f in facts}
    assert FactType.PAYMENT_AUTHORIZED in fact_types
    assert FactType.PAYMENT_CAPTURED in fact_types


# =============================================================================
# 5. Same Value Different Payment (No Global Merging)
# =============================================================================
def test_5_same_value_different_payment(db):
    obs_a = _create_obs(db, subject_id="pay_aaa", evidence_type="PAYMENT_AMOUNT", value="50000")
    obs_b = _create_obs(db, subject_id="pay_bbb", evidence_type="PAYMENT_AMOUNT", value="50000")

    decision = ReconciliationEngine.reconcile_pair(obs_a, obs_b)
    assert decision.result == ReconciliationResult.DIFFERENT_FACT
    assert "different entities" in decision.explanation


# =============================================================================
# 6. Temporal Ambiguity (> Window -> UNKNOWN)
# =============================================================================
def test_6_temporal_ambiguity(db):
    # Same value, but observed 10 minutes apart without shared provider event ID
    obs1 = _create_obs(db, observed_at=T_BASE, webhook_event_id=101, payment_event_id=201)
    obs2 = _create_obs(db, observed_at=T_PLUS_10M, webhook_event_id=102, payment_event_id=202)

    decision = ReconciliationEngine.reconcile_pair(obs1, obs2)
    assert decision.result == ReconciliationResult.UNKNOWN
    assert decision.rule_id == ReconciliationRule.TEMPORAL_AMBIGUITY_V1


# =============================================================================
# 7. Unknown Identity
# =============================================================================
def test_7_unknown_identity(db):
    obs1 = _create_obs(db, webhook_event_id=None, payment_event_id=None, observed_at=T_BASE)
    obs2 = _create_obs(db, webhook_event_id=None, payment_event_id=None, observed_at=T_PLUS_10M)

    decision = ReconciliationEngine.reconcile_pair(obs1, obs2)
    assert decision.result == ReconciliationResult.UNKNOWN


# =============================================================================
# 8. Conflicting Facts
# =============================================================================
def test_8_conflicting_facts(db):
    obs1 = _create_obs(db, evidence_type="PAYMENT_AMOUNT", value="50000", webhook_event_id=101)
    obs2 = _create_obs(db, evidence_type="PAYMENT_AMOUNT", value="70000", webhook_event_id=102)

    decision = ReconciliationEngine.reconcile_pair(obs1, obs2)
    assert decision.result == ReconciliationResult.CONFLICTING_FACT
    assert decision.rule_id == ReconciliationRule.CONFLICTING_VALUE_V1
    assert "incompatible values" in decision.explanation


# =============================================================================
# 9. Provenance Preservation
# =============================================================================
def test_9_provenance_preservation(db):
    obs1 = _create_obs(db, webhook_event_id=101)
    obs2 = _create_obs(db, webhook_event_id=101)

    facts = ReconciliationEngine.reconcile_payment(db, "pay_test_01")
    assert len(facts) == 1

    # Verify both raw observations exist unchanged
    all_obs = db.execute(select(EvidenceObservation)).scalars().all()
    assert len(all_obs) == 2

    # Verify links
    links = db.execute(select(ObservationFactLink)).scalars().all()
    assert len(links) == 2
    for l in links:
        assert l.fact_id == facts[0].internal_id


# =============================================================================
# 10. Fact Supersession
# =============================================================================
def test_10_fact_supersession(db):
    fact = EvidenceFact(
        payment_id="pay_test_01",
        fact_type=FactType.PAYMENT_AUTHORIZED,
        canonical_value="authorized",
        canonical_value_hash="dummy_hash_1",
        status=FactStatus.SUPERSEDED,
        first_observed_at=T_BASE,
        last_observed_at=T_BASE,
        observation_count=1,
        distinct_source_count=1,
        methodology_version="1.0",
    )
    db.add(fact)
    db.flush()

    fetched = db.get(EvidenceFact, fact.internal_id)
    assert fetched.status == FactStatus.SUPERSEDED


# =============================================================================
# 11. Fact Invalidation
# =============================================================================
def test_11_fact_invalidation_and_statuses(db):
    statuses = [FactStatus.ACTIVE, FactStatus.SUPERSEDED, FactStatus.INVALIDATED, FactStatus.UNRESOLVED]
    for idx, s in enumerate(statuses):
        fact = EvidenceFact(
            payment_id=f"pay_status_{idx}",
            fact_type=FactType.PAYMENT_STATUS_OBSERVED,
            canonical_value=s.lower(),
            canonical_value_hash=f"hash_{idx}",
            status=s,
            first_observed_at=T_BASE,
            last_observed_at=T_BASE,
            observation_count=1,
            distinct_source_count=1,
            methodology_version="1.0",
        )
        db.add(fact)
    db.flush()

    count = db.execute(select(func.count(EvidenceFact.internal_id))).scalar()
    assert count == 4


# =============================================================================
# 12. Backfill Execution
# =============================================================================
def test_12_backfill_execution(db):
    _create_obs(db, subject_id="pay_01", value="captured")
    _create_obs(db, subject_id="pay_02", value="failed")

    report = ReconciliationEngine.backfill_all_payments(db)
    assert report.payments_processed == 2
    assert report.facts_created == 2
    assert report.failures == 0


# =============================================================================
# 13. Backfill Idempotency
# =============================================================================
def test_13_backfill_idempotency(db):
    _create_obs(db, subject_id="pay_01", value="captured")

    report1 = ReconciliationEngine.backfill_all_payments(db)
    assert report1.facts_created == 1

    report2 = ReconciliationEngine.backfill_all_payments(db)
    assert report2.facts_created == 0  # No duplicate facts created
    assert report2.facts_matched_existing == 1

    total_facts = db.execute(select(func.count(EvidenceFact.internal_id))).scalar()
    assert total_facts == 1


# =============================================================================
# 14. Phase 7 Corroboration Integration
# =============================================================================
def test_14_corroboration_integration(db):
    # Two observations sharing exact same webhook delivery
    obs1 = _create_obs(db, webhook_event_id=101, payment_event_id=201)
    obs2 = _create_obs(db, webhook_event_id=101, payment_event_id=201)

    claim = Claim(
        subject_type="payment",
        subject_id="pay_test_01",
        claim_type="PAYMENT_STATUS",
        claim_key="status",
        canonical_value="captured",
    )
    db.add(claim)
    db.flush()

    db.add(EvidenceClaimLink(claim_id=claim.internal_id, evidence_id=obs1.internal_id))
    db.add(EvidenceClaimLink(claim_id=claim.internal_id, evidence_id=obs2.internal_id))
    db.flush()

    corrob = CorroborationService.evaluate_claim_corroboration(db, claim, "pay_test_01")
    # Same provider event -> must be SAME_SOURCE, not MULTI_SOURCE or INDEPENDENT_CANDIDATE
    assert corrob.corroboration_type == CorroborationType.SAME_SOURCE_CORROBORATION
    assert corrob.independence_status == IndependenceStatus.SAME_SOURCE


# =============================================================================
# 15. Phase 8 Conflict Integration
# =============================================================================
def test_15_conflict_integration(db):
    obs1 = _create_obs(db, evidence_type="PAYMENT_AMOUNT", value="50000")
    obs2 = _create_obs(db, evidence_type="PAYMENT_AMOUNT", value="70000")

    ReconciliationEngine.reconcile_payment(db, "pay_test_01")

    reconciliations = db.execute(select(EvidenceReconciliation)).scalars().all()
    conflicting = [r for r in reconciliations if r.result == ReconciliationResult.CONFLICTING_FACT]
    assert len(conflicting) == 1
    assert conflicting[0].rule_id == ReconciliationRule.CONFLICTING_VALUE_V1


# =============================================================================
# 16. Phase 9 Integrity Integration
# =============================================================================
def test_16_integrity_integration(db):
    # Single webhook delivery producing 3 observations
    obs1 = _create_obs(db, evidence_type="PAYMENT_STATUS", value="captured", webhook_event_id=101)
    obs2 = _create_obs(db, evidence_type="PAYMENT_AMOUNT", value="50000", webhook_event_id=101)
    obs3 = _create_obs(db, evidence_type="PAYMENT_CURRENCY", value="INR", webhook_event_id=101)

    facts = ReconciliationEngine.reconcile_payment(db, "pay_test_01")
    assert len(facts) == 3
    for f in facts:
        assert f.distinct_source_count == 1  # Accurately reflects 1 provider mechanism


# =============================================================================
# 17. Phase 10 Trace Integration
# =============================================================================
def test_17_trace_integration(db):
    obs = _create_obs(db)
    facts = ReconciliationEngine.reconcile_payment(db, "pay_test_01")

    fact_detail = FactService.get_fact_detail(db, facts[0].internal_id)
    assert len(fact_detail.supporting_observations) == 1
    assert fact_detail.supporting_observations[0].internal_id == obs.internal_id


# =============================================================================
# 18. Phase 11 Temporal Integration
# =============================================================================
def test_18_temporal_integration(db):
    obs1 = _create_obs(db, observed_at=T_BASE, webhook_event_id=101)
    obs2 = _create_obs(db, observed_at=T_PLUS_1S, webhook_event_id=101)

    facts = ReconciliationEngine.reconcile_payment(db, "pay_test_01")
    assert len(facts) == 1
    fact = facts[0]
    assert fact.first_observed_at == T_BASE
    assert fact.last_observed_at == T_PLUS_1S


# =============================================================================
# 19. API Route Status Codes & Responses
# =============================================================================
def test_19_api_status_codes_and_structures(client, api_db):
    obs = _create_obs(api_db)
    facts = ReconciliationEngine.reconcile_payment(api_db, "pay_test_01")
    api_db.commit()
    fact_id = facts[0].internal_id

    # 1. GET fact detail
    res_fact = client.get(f"/api/v1/facts/{fact_id}")
    assert res_fact.status_code == 200
    data_fact = res_fact.json()
    assert data_fact["fact"]["internal_id"] == fact_id
    assert len(data_fact["supporting_observations"]) == 1

    # 2. GET payment facts
    res_pfacts = client.get("/api/v1/payments/pay_test_01/facts")
    assert res_pfacts.status_code == 200
    data_pfacts = res_pfacts.json()
    assert data_pfacts["total_facts"] == 1

    # 3. GET observation reconciliation
    res_obs_rec = client.get(f"/api/v1/observations/{obs.internal_id}/reconciliation")
    assert res_obs_rec.status_code == 200
    data_obs_rec = res_obs_rec.json()
    assert data_obs_rec["observation"]["internal_id"] == obs.internal_id
    assert data_obs_rec["matched_fact"]["internal_id"] == fact_id

    # 4. 404 for nonexistent fact
    res_404 = client.get("/api/v1/facts/99999")
    assert res_404.status_code == 404


# =============================================================================
# 20. Sensitive Data Filtering
# =============================================================================
def test_20_sensitive_data_filtering(client, api_db):
    obs = _create_obs(
        api_db,
        provenance_metadata={"event_type": "payment.captured", "secret": "DO_NOT_EXPOSE"},
    )
    facts = ReconciliationEngine.reconcile_payment(api_db, "pay_test_01")
    api_db.commit()

    res = client.get(f"/api/v1/facts/{facts[0].internal_id}")
    assert res.status_code == 200
    text_content = res.text
    assert "DO_NOT_EXPOSE" not in text_content
    assert "raw_payload" not in text_content


# =============================================================================
# 21. Candidate Blocking & Performance
# =============================================================================
def test_21_candidate_blocking_performance(db):
    # 5 payments with 2 observations each
    for i in range(5):
        pid = f"pay_block_{i}"
        _create_obs(db, subject_id=pid, value="captured", webhook_event_id=100 + i)
        _create_obs(db, subject_id=pid, value="captured", webhook_event_id=100 + i)

    # Reconciling pay_block_0 should ONLY evaluate pairs for pay_block_0
    ReconciliationEngine.reconcile_payment(db, "pay_block_0")

    recs = db.execute(select(EvidenceReconciliation)).scalars().all()
    # 2 observations for pay_block_0 produce exactly 1 pairwise decision
    assert len(recs) == 1
    assert recs[0].result == ReconciliationResult.SAME_FACT


# =============================================================================
# 22. Real Event Ingestion Compatibility
# =============================================================================
def test_22_real_event_ingestion_compatibility(db):
    # Simulate real Razorpay payment.captured webhook delivery
    payment = Payment(
        razorpay_payment_id="pay_real_01",
        amount_minor=50000,
        currency="INR",
        status="captured",
        captured=True,
    )
    db.add(payment)
    db.flush()

    we = WebhookEvent(
        id=501,
        razorpay_event_id="evt_real_501",
        event_type="payment.captured",
        raw_payload={"entity": "event", "event": "payment.captured"},
        payload_hash="real_hash_501",
        payment_id="pay_real_01",
        received_at=T_BASE,
    )
    db.add(we)
    db.flush()

    pe = PaymentEvent(
        internal_id=601,
        payment_id=payment.internal_id,
        webhook_event_id=we.id,
        event_type="payment.captured",
        event_timestamp=T_BASE,
    )
    db.add(pe)
    db.flush()

    obs_status = _create_obs(
        db,
        subject_id="pay_real_01",
        evidence_type="PAYMENT_STATUS",
        value="captured",
        webhook_event_id=we.id,
        payment_event_id=pe.internal_id,
    )
    obs_amt = _create_obs(
        db,
        subject_id="pay_real_01",
        evidence_type="PAYMENT_AMOUNT",
        value="50000",
        webhook_event_id=we.id,
        payment_event_id=pe.internal_id,
    )

    facts = ReconciliationEngine.reconcile_payment(db, "pay_real_01")
    assert len(facts) == 2
    types = {f.fact_type for f in facts}
    assert FactType.PAYMENT_CAPTURED in types
    assert FactType.PAYMENT_AMOUNT_OBSERVED in types
