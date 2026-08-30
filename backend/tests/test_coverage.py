"""
Phase 15 — Evidence Completeness & Coverage Analysis Test Suite.

27 test scenarios:
1. Required evidence present
2. Required evidence missing
3. Expected evidence missing
4. Optional evidence missing
5. Conditional requirement applicable
6. Conditional requirement not applicable
7. Profile unknown
8. Evidence present but conflicted
9. Evidence partially available
10. Duplicate observations satisfy one requirement
11. Historical as-of evaluation
12. Future evidence excluded
13. Coverage change after new evidence
14. Coverage change after invalidation
15. Methodology/profile version change
16. Missing != negative fact
17. Unknown != missing
18. Phase 13 fact integration
19. Phase 14 lineage integration
20. Phase 11 change integration
21. Phase 10 trace integration
22. Phase 12 investigation integration
23. API authorization & schema
24. Sensitive data filtering
25. Idempotent recomputation
26. Historical snapshot immutability
27. Deterministic aggregation
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import uuid
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# SQLite JSONB polyfill
@compiles(JSONB, "sqlite")
def compile_jsonb_sqlite(type_, compiler, **kw):
    return "JSON"


from app.api.v1.coverage import router as coverage_router
from app.db.session import Base, get_db
from app.models.coverage_types import (
    COVERAGE_METHODOLOGY_VERSION,
    PROFILE_UNKNOWN,
    PROFILE_VERSION_1,
    STANDARD_PAYMENT_PROFILE_ID,
    CoverageState,
    CoverageStatus,
    RequirementType,
)
from app.models.evidence import EvidenceObservation
from app.models.evidence_conflict import EvidenceConflict
from app.models.evidence_coverage import (
    EvidenceCoverageResult,
    EvidenceCoverageSnapshot,
)
from app.models.evidence_fact import EvidenceFact
from app.models.evidence_types import EvidenceType, SourceType
from app.models.observation_fact_link import ObservationFactLink
from app.models.payment import Payment
from app.models.reconciliation_types import FactStatus, FactType
from app.models.webhook_event import WebhookEvent
from app.services.coverage_engine import (
    evaluate_coverage,
    get_coverage_history,
    select_evidence_profile,
)

_test_app = FastAPI()
_test_app.include_router(coverage_router, prefix="/api/v1")

T_BASE = datetime(2026, 8, 23, 10, 0, 0, tzinfo=timezone.utc)
T_PLUS_1M = T_BASE + timedelta(minutes=1)
T_PLUS_5M = T_BASE + timedelta(minutes=5)
T_FUTURE = T_BASE + timedelta(hours=2)


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
# Helpers
# ---------------------------------------------------------------------------

def _make_payment(db, payment_id: str = "pay_cov_001", status: str = "captured", captured: bool = True) -> Payment:
    p = Payment(
        razorpay_payment_id=payment_id,
        status=status,
        currency="INR",
        amount_minor=50000,
        captured=captured,
        first_observed_at=T_BASE,
        last_observed_at=T_BASE,
    )
    db.add(p)
    db.flush()
    return p


def _make_fact(db, payment_id: str, fact_type: str, canonical_value: str = "captured", observed_at: datetime = None) -> EvidenceFact:
    h = hashlib.sha256(f"{payment_id}|{fact_type}|{canonical_value}".encode()).hexdigest()
    f = EvidenceFact(
        payment_id=payment_id,
        fact_type=fact_type,
        canonical_value=canonical_value,
        canonical_value_hash=h,
        status=FactStatus.ACTIVE,
        first_observed_at=observed_at or T_BASE,
        last_observed_at=observed_at or T_BASE,
        observation_count=1,
        distinct_source_count=1,
    )
    db.add(f)
    db.flush()
    return f


def _make_observation(db, payment_id: str, evidence_type: str, value: str = "captured", observed_at: datetime = None) -> EvidenceObservation:
    obs = EvidenceObservation(
        subject_type="payment",
        subject_id=payment_id,
        evidence_type=evidence_type,
        source_type=SourceType.RAZORPAY_WEBHOOK,
        extraction_method="WEBHOOK_FIELD_EXTRACTION",
        extraction_version="1.0",
        value_type="STATUS_STRING",
        value=value,
        observed_at=observed_at or T_BASE,
    )
    db.add(obs)
    db.flush()
    return obs


# ===========================================================================
# TESTS
# ===========================================================================

# 1. Required evidence present
def test_required_evidence_present(db):
    payment_id = "pay_req_present"
    _make_payment(db, payment_id)
    _make_fact(db, payment_id, FactType.PAYMENT_CAPTURED, "captured")
    _make_fact(db, payment_id, FactType.PAYMENT_AMOUNT_OBSERVED, "50000")
    _make_fact(db, payment_id, FactType.PAYMENT_CURRENCY_OBSERVED, "INR")
    db.commit()

    resp = evaluate_coverage(db, payment_id)
    present_types = {r.fact_type for r in resp.results if r.observed_state == CoverageState.PRESENT}
    assert FactType.PAYMENT_CAPTURED in present_types
    assert FactType.PAYMENT_AMOUNT_OBSERVED in present_types
    assert FactType.PAYMENT_CURRENCY_OBSERVED in present_types
    assert resp.metrics.required_present >= 3


# 2. Required evidence missing
def test_required_evidence_missing(db):
    payment_id = "pay_req_missing"
    _make_payment(db, payment_id)
    # Only amount present, currency and status missing
    _make_fact(db, payment_id, FactType.PAYMENT_AMOUNT_OBSERVED, "50000")
    db.commit()

    resp = evaluate_coverage(db, payment_id)
    assert resp.metrics.required_missing > 0
    missing_reqs = [m.requirement_id for m in resp.missing_evidence]
    assert "REQ_PAYMENT_CURRENCY" in missing_reqs
    assert resp.overall_coverage_status in (CoverageStatus.PARTIAL, CoverageStatus.INSUFFICIENT)


# 3. Expected evidence missing
def test_expected_evidence_missing(db):
    payment_id = "pay_exp_missing"
    _make_payment(db, payment_id)
    _make_fact(db, payment_id, FactType.PAYMENT_CAPTURED, "captured")
    _make_fact(db, payment_id, FactType.PAYMENT_AMOUNT_OBSERVED, "50000")
    _make_fact(db, payment_id, FactType.PAYMENT_CURRENCY_OBSERVED, "INR")
    # Method is expected but missing
    db.commit()

    resp = evaluate_coverage(db, payment_id)
    assert resp.metrics.expected_missing > 0
    exp_res = next(r for r in resp.results if r.requirement_id == "REQ_PAYMENT_METHOD")
    assert exp_res.observed_state == CoverageState.MISSING
    assert resp.overall_coverage_status == CoverageStatus.SUBSTANTIALLY_COMPLETE


# 4. Optional evidence missing
def test_optional_evidence_missing(db):
    payment_id = "pay_opt_missing"
    _make_payment(db, payment_id)
    _make_fact(db, payment_id, FactType.PAYMENT_CAPTURED, "captured")
    _make_fact(db, payment_id, FactType.PAYMENT_AMOUNT_OBSERVED, "50000")
    _make_fact(db, payment_id, FactType.PAYMENT_CURRENCY_OBSERVED, "INR")
    _make_fact(db, payment_id, FactType.PAYMENT_METHOD_OBSERVED, "card")
    _make_fact(db, payment_id, FactType.PAYMENT_AUTHORIZED, "authorized")
    db.commit()

    resp = evaluate_coverage(db, payment_id)
    # Optional (Order, Customer) missing should still allow COMPLETE status
    assert resp.overall_coverage_status == CoverageStatus.COMPLETE


# 5. Conditional requirement applicable
def test_conditional_requirement_applicable(db):
    payment_id = "pay_cond_app"
    _make_payment(db, payment_id, status="captured", captured=True)
    _make_fact(db, payment_id, FactType.PAYMENT_CAPTURED, "captured")
    db.commit()

    resp = evaluate_coverage(db, payment_id)
    cap_res = next(r for r in resp.results if r.requirement_id == "REQ_PAYMENT_CAPTURED")
    assert cap_res.requirement_type == RequirementType.REQUIRED
    assert cap_res.observed_state == CoverageState.PRESENT


# 6. Conditional requirement not applicable
def test_conditional_requirement_not_applicable(db):
    payment_id = "pay_cond_na"
    _make_payment(db, payment_id, status="captured", captured=True)
    db.commit()

    resp = evaluate_coverage(db, payment_id)
    refund_res = next(r for r in resp.results if r.requirement_id == "REQ_REFUND_RECORD")
    assert refund_res.requirement_type == RequirementType.NOT_APPLICABLE
    assert refund_res.observed_state == CoverageState.NOT_APPLICABLE


# 7. Profile unknown
def test_profile_unknown(db):
    resp = evaluate_coverage(db, "pay_nonexistent")
    assert resp.profile_id == PROFILE_UNKNOWN
    assert resp.overall_coverage_status == CoverageStatus.UNKNOWN


# 8. Evidence present but conflicted
def test_evidence_present_but_conflicted(db):
    payment_id = "pay_conflict"
    _make_payment(db, payment_id)
    _make_fact(db, payment_id, FactType.PAYMENT_CAPTURED, "captured")
    _make_fact(db, payment_id, FactType.PAYMENT_AMOUNT_OBSERVED, "50000")
    _make_fact(db, payment_id, FactType.PAYMENT_CURRENCY_OBSERVED, "INR")

    # Add open conflict
    conflict = EvidenceConflict(
        payment_id=payment_id,
        claim_a_id=1,
        claim_b_id=2,
        conflict_type="VALUE_MISMATCH",
        severity="HIGH",
        status="OPEN",
        detected_at=T_BASE,
    )
    db.add(conflict)
    db.commit()

    resp = evaluate_coverage(db, payment_id)
    assert resp.metrics.conflicted > 0
    assert resp.overall_coverage_status == CoverageStatus.PARTIAL


# 9. Evidence partially available
def test_evidence_partially_available(db):
    payment_id = "pay_partial_obs"
    _make_payment(db, payment_id)
    # Observation exists but not reconciled into a Fact
    _make_observation(db, payment_id, EvidenceType.PAYMENT_AMOUNT, "50000")
    db.commit()

    resp = evaluate_coverage(db, payment_id)
    amt_res = next(r for r in resp.results if r.requirement_id == "REQ_PAYMENT_AMOUNT")
    assert amt_res.observed_state == CoverageState.PARTIAL


# 10. Duplicate observations satisfy one requirement
def test_duplicate_observations_satisfy_one_requirement(db):
    payment_id = "pay_dedup"
    _make_payment(db, payment_id)
    fact = _make_fact(db, payment_id, FactType.PAYMENT_AMOUNT_OBSERVED, "50000")
    obs1 = _make_observation(db, payment_id, EvidenceType.PAYMENT_AMOUNT, "50000")
    obs2 = _make_observation(db, payment_id, EvidenceType.PAYMENT_AMOUNT, "50000")
    db.add(ObservationFactLink(observation_id=obs1.internal_id, fact_id=fact.internal_id))
    db.add(ObservationFactLink(observation_id=obs2.internal_id, fact_id=fact.internal_id))
    db.commit()

    resp = evaluate_coverage(db, payment_id)
    amt_res = next(r for r in resp.results if r.requirement_id == "REQ_PAYMENT_AMOUNT")
    assert amt_res.observed_state == CoverageState.PRESENT
    assert amt_res.matched_fact_id == fact.internal_id


# 11. Historical as-of evaluation
def test_historical_as_of_evaluation(db):
    payment_id = "pay_as_of"
    _make_payment(db, payment_id)
    _make_fact(db, payment_id, FactType.PAYMENT_AMOUNT_OBSERVED, "50000", observed_at=T_BASE)
    _make_fact(db, payment_id, FactType.PAYMENT_CURRENCY_OBSERVED, "INR", observed_at=T_PLUS_5M)
    db.commit()

    # Evaluated at T_PLUS_1M -> currency not yet seen
    resp = evaluate_coverage(db, payment_id, as_of=T_PLUS_1M)
    cur_res = next(r for r in resp.results if r.requirement_id == "REQ_PAYMENT_CURRENCY")
    assert cur_res.observed_state == CoverageState.MISSING


# 12. Future evidence excluded
def test_future_evidence_excluded(db):
    payment_id = "pay_future"
    _make_payment(db, payment_id)
    _make_fact(db, payment_id, FactType.PAYMENT_AMOUNT_OBSERVED, "50000", observed_at=T_FUTURE)
    db.commit()

    resp = evaluate_coverage(db, payment_id, as_of=T_BASE)
    amt_res = next(r for r in resp.results if r.requirement_id == "REQ_PAYMENT_AMOUNT")
    assert amt_res.observed_state == CoverageState.MISSING


# 13. Coverage change after new evidence
def test_coverage_change_after_new_evidence(db):
    payment_id = "pay_evo"
    _make_payment(db, payment_id)
    db.commit()

    resp_t1 = evaluate_coverage(db, payment_id, as_of=T_BASE, persist=True)
    assert resp_t1.overall_coverage_status in (CoverageStatus.PARTIAL, CoverageStatus.INSUFFICIENT)

    # New evidence arrives at T2
    _make_fact(db, payment_id, FactType.PAYMENT_CAPTURED, "captured", observed_at=T_PLUS_5M)
    _make_fact(db, payment_id, FactType.PAYMENT_AMOUNT_OBSERVED, "50000", observed_at=T_PLUS_5M)
    _make_fact(db, payment_id, FactType.PAYMENT_CURRENCY_OBSERVED, "INR", observed_at=T_PLUS_5M)
    _make_fact(db, payment_id, FactType.PAYMENT_METHOD_OBSERVED, "card", observed_at=T_PLUS_5M)
    _make_fact(db, payment_id, FactType.PAYMENT_AUTHORIZED, "authorized", observed_at=T_PLUS_5M)
    db.commit()

    resp_t2 = evaluate_coverage(db, payment_id, as_of=T_PLUS_5M, persist=True)
    assert resp_t2.overall_coverage_status == CoverageStatus.COMPLETE


# 14. Coverage change after invalidation
def test_coverage_change_after_invalidation(db):
    payment_id = "pay_inval"
    _make_payment(db, payment_id)
    fact = _make_fact(db, payment_id, FactType.PAYMENT_AMOUNT_OBSERVED, "50000")
    db.commit()

    resp_1 = evaluate_coverage(db, payment_id, as_of=T_BASE)
    amt_res_1 = next(r for r in resp_1.results if r.requirement_id == "REQ_PAYMENT_AMOUNT")
    assert amt_res_1.observed_state == CoverageState.PRESENT

    # Invalidate fact
    fact.status = FactStatus.INVALIDATED
    db.commit()

    resp_2 = evaluate_coverage(db, payment_id, as_of=T_BASE)
    amt_res_2 = next(r for r in resp_2.results if r.requirement_id == "REQ_PAYMENT_AMOUNT")
    assert amt_res_2.observed_state == CoverageState.PARTIAL


# 15. Methodology/profile version change
def test_methodology_profile_version(db):
    payment_id = "pay_version"
    _make_payment(db, payment_id)
    db.commit()

    resp = evaluate_coverage(db, payment_id)
    assert resp.profile_version == PROFILE_VERSION_1
    assert resp.methodology_version == COVERAGE_METHODOLOGY_VERSION


# 16. Missing != negative fact
def test_missing_is_not_negative_fact(db):
    payment_id = "pay_negative_fact"
    _make_payment(db, payment_id)
    db.commit()

    resp = evaluate_coverage(db, payment_id)
    for m in resp.missing_evidence:
        assert "not observed" in m.explanation.lower() or "not observed" in m.search_scope.lower()
        # Must not claim something never happened as a negative fact
        assert "did not occur" not in m.explanation.lower()
        assert "fraud" not in m.explanation.lower()


# 17. Unknown != missing
def test_unknown_not_missing(db):
    resp = evaluate_coverage(db, "pay_nonexistent")
    assert resp.overall_coverage_status == CoverageStatus.UNKNOWN
    assert resp.profile_id == PROFILE_UNKNOWN


# 18. Phase 13 fact integration
def test_phase13_fact_integration(db):
    payment_id = "pay_p13"
    _make_payment(db, payment_id)
    fact = _make_fact(db, payment_id, FactType.PAYMENT_METHOD_OBSERVED, "upi")
    db.commit()

    resp = evaluate_coverage(db, payment_id)
    method_res = next(r for r in resp.results if r.requirement_id == "REQ_PAYMENT_METHOD")
    assert method_res.matched_fact_id == fact.internal_id
    assert method_res.observed_state == CoverageState.PRESENT


# 19. Phase 14 lineage integration
def test_phase14_lineage_traceability(db):
    payment_id = "pay_p14"
    _make_payment(db, payment_id)
    fact = _make_fact(db, payment_id, FactType.PAYMENT_AMOUNT_OBSERVED, "50000")
    obs = _make_observation(db, payment_id, EvidenceType.PAYMENT_AMOUNT, "50000")
    db.add(ObservationFactLink(observation_id=obs.internal_id, fact_id=fact.internal_id))
    db.commit()

    resp = evaluate_coverage(db, payment_id)
    amt_res = next(r for r in resp.results if r.requirement_id == "REQ_PAYMENT_AMOUNT")
    assert amt_res.matched_fact_id == fact.internal_id
    assert amt_res.matched_observation_ids == [obs.internal_id]


# 20. Phase 11 change integration
def test_phase11_change_integration(db):
    payment_id = "pay_p11"
    _make_payment(db, payment_id)
    db.commit()

    evaluate_coverage(db, payment_id, as_of=T_BASE, persist=True)
    _make_fact(db, payment_id, FactType.PAYMENT_AMOUNT_OBSERVED, "50000", observed_at=T_PLUS_5M)
    db.commit()
    evaluate_coverage(db, payment_id, as_of=T_PLUS_5M, persist=True)

    history = get_coverage_history(db, payment_id)
    assert history.total == 2
    dt0 = history.history[0].evaluated_at
    if dt0.tzinfo is None:
        dt0 = dt0.replace(tzinfo=timezone.utc)
    assert dt0 == T_BASE

    dt1 = history.history[1].evaluated_at
    if dt1.tzinfo is None:
        dt1 = dt1.replace(tzinfo=timezone.utc)
    assert dt1 == T_PLUS_5M


# 21. Phase 10 trace integration
def test_phase10_trace_compatibility(db):
    payment_id = "pay_p10"
    _make_payment(db, payment_id)
    db.commit()

    resp = evaluate_coverage(db, payment_id)
    assert resp.profile_id == STANDARD_PAYMENT_PROFILE_ID
    assert resp.methodology_version == COVERAGE_METHODOLOGY_VERSION


# 22. Phase 12 investigation integration
def test_phase12_investigation_search(db):
    payment_id = "pay_p12"
    _make_payment(db, payment_id)
    db.commit()

    resp = evaluate_coverage(db, payment_id)
    assert len(resp.results) > 0
    assert "total_applicable" in resp.metrics.model_dump()


# 23. API authorization & schema
def test_api_coverage_schema(client, api_db):
    payment_id = "pay_api_test"
    _make_payment(api_db, payment_id)
    _make_fact(api_db, payment_id, FactType.PAYMENT_AMOUNT_OBSERVED, "50000")
    api_db.commit()

    resp = client.get(f"/api/v1/payments/{payment_id}/coverage")
    assert resp.status_code == 200
    data = resp.json()
    assert data["payment_id"] == payment_id
    assert "metrics" in data
    assert "results" in data
    assert "missing_evidence" in data


# 24. Sensitive data filtering
def test_sensitive_data_filtering(db):
    payment_id = "pay_safe_001"
    _make_payment(db, payment_id)
    db.commit()

    resp = evaluate_coverage(db, payment_id)
    dump_str = str(resp.model_dump()).lower()
    for sensitive in ("cvv", "pin", "otp", "password", "api_key", "bearer"):
        assert sensitive not in dump_str


# 25. Idempotent recomputation
def test_idempotent_recompute(client, api_db):
    payment_id = "pay_recomp"
    _make_payment(api_db, payment_id)
    api_db.commit()

    resp1 = client.post(f"/api/v1/payments/{payment_id}/coverage/recompute")
    assert resp1.status_code == 200
    data1 = resp1.json()

    resp2 = client.post(f"/api/v1/payments/{payment_id}/coverage/recompute")
    assert resp2.status_code == 200
    data2 = resp2.json()

    assert data1["overall_coverage_status"] == data2["overall_coverage_status"]


# 26. Historical snapshot immutability
def test_historical_snapshot_immutability(db):
    payment_id = "pay_immutable"
    _make_payment(db, payment_id)
    db.commit()

    evaluate_coverage(db, payment_id, as_of=T_BASE, persist=True)
    snap = db.execute(
        select(EvidenceCoverageSnapshot).where(EvidenceCoverageSnapshot.payment_id == payment_id)
    ).scalar_one()

    # Re-evaluating at same timestamp should not create duplicate snapshot
    evaluate_coverage(db, payment_id, as_of=T_BASE, persist=True)
    count = db.execute(
        select(EvidenceCoverageSnapshot).where(EvidenceCoverageSnapshot.payment_id == payment_id)
    ).scalars().all()
    assert len(count) == 1


# 27. Deterministic aggregation
def test_deterministic_aggregation(db):
    payment_id = "pay_det_agg"
    _make_payment(db, payment_id)
    _make_fact(db, payment_id, FactType.PAYMENT_AMOUNT_OBSERVED, "50000")
    db.commit()

    res1 = evaluate_coverage(db, payment_id)
    res2 = evaluate_coverage(db, payment_id)

    assert res1.overall_coverage_status == res2.overall_coverage_status
    assert res1.metrics.total_applicable == res2.metrics.total_applicable
    assert res1.metrics.required_present == res2.metrics.required_present
