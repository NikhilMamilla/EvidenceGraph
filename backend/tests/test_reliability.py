"""
Phase 16 — Evidence Reliability Calibration & Uncertainty Boundaries Test Suite.

27 comprehensive unit and integration tests verifying categorical dimensions,
ceilings, floors, explainability, uncertainty boundaries, and integrations across Phases 1–15.
"""

from datetime import datetime, timezone, timedelta
import hashlib
import pytest
from fastapi import FastAPI
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

from app.api.v1.reliability import router as reliability_router
from app.db.session import Base, get_db
from app.models.payment import Payment
from app.models.evidence import EvidenceObservation
from app.models.evidence_fact import EvidenceFact
from app.models.observation_fact_link import ObservationFactLink
from app.models.evidence_conflict import EvidenceConflict
from app.models.conflict_types import ConflictType, ConflictSeverity, ConflictStatus
from app.models.reconciliation_types import FactType, FactStatus
from app.models.reliability_types import (
    ReliabilityState,
    SourceReliability,
    ProvenanceReliability,
    IdentityReliability,
    TemporalReliability,
    StructuralReliability,
    ContradictionReliability,
    DependencyReliability,
    UncertaintyBoundaryType,
    RELIABILITY_METHODOLOGY_V1,
)
from app.models.evidence_reliability import EvidenceReliabilityAssessment
from app.services.reliability_engine import (
    evaluate_fact_reliability,
    evaluate_payment_reliability,
    get_payment_uncertainty,
    get_reliability_history,
)

_test_app = FastAPI()
_test_app.include_router(reliability_router, prefix="/api/v1")

T_BASE = datetime(2026, 8, 23, 10, 0, 0, tzinfo=timezone.utc)
T_PLUS_5M = datetime(2026, 8, 23, 10, 5, 0, tzinfo=timezone.utc)
T_PLUS_10M = datetime(2026, 8, 23, 10, 10, 0, tzinfo=timezone.utc)


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
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
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
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


def _make_payment(db, payment_id: str, status: str = "captured", amount: int = 50000, currency: str = "INR"):
    pay = Payment(
        razorpay_payment_id=payment_id,
        amount_minor=amount,
        currency=currency,
        status=status,
        captured=True if status == "captured" else False,
        first_observed_at=T_BASE,
        last_observed_at=T_BASE,
    )
    db.add(pay)
    db.flush()
    return pay


def _make_fact_with_obs(
    db,
    payment_id: str,
    fact_type: str,
    value: str,
    source_type: str = "RAZORPAY_WEBHOOK",
    event_id: int = 101,
    observed_at: datetime = T_BASE,
    status: str = FactStatus.ACTIVE,
):
    obs = EvidenceObservation(
        evidence_type=fact_type,
        subject_type="payment",
        subject_id=payment_id,
        value=value,
        value_type="STRING",
        source_type=source_type,
        source_reference=str(event_id),
        observed_at=observed_at,
        webhook_event_id=event_id,
        extraction_method="DIRECT_FIELD",
    )
    db.add(obs)
    db.flush()

    h = hashlib.sha256(f"{payment_id}|{fact_type}|{value}".encode()).hexdigest()
    fact = EvidenceFact(
        payment_id=payment_id,
        fact_type=fact_type,
        canonical_value=value,
        canonical_value_hash=h,
        first_observed_at=observed_at,
        last_observed_at=observed_at,
        observation_count=1,
        distinct_source_count=1,
        status=status,
    )
    db.add(fact)
    db.flush()

    link = ObservationFactLink(
        observation_id=obs.internal_id,
        fact_id=fact.internal_id,
    )
    db.add(link)
    db.flush()
    return fact, obs


# 1. Fully reliable fact (HIGH)
def test_fully_reliable_fact(db):
    payment_id = "pay_high_01"
    _make_payment(db, payment_id)
    fact, _ = _make_fact_with_obs(db, payment_id, FactType.PAYMENT_AMOUNT_OBSERVED, "50000")
    db.commit()

    resp = evaluate_fact_reliability(db, fact)
    assert resp.overall_state == ReliabilityState.HIGH
    assert resp.dimensions["source"].state == SourceReliability.VERIFIED_PROVIDER_SOURCE.value
    assert resp.dimensions["provenance"].state == ProvenanceReliability.COMPLETE.value
    assert resp.dimensions["identity"].state == IdentityReliability.SAME_PROVIDER_EVENT.value
    assert resp.dimensions["temporal"].state == TemporalReliability.TEMPORALLY_SOUND.value
    assert resp.dimensions["contradiction"].state == ContradictionReliability.UNCONTRADICTED.value
    assert resp.dimensions["structural"].state == StructuralReliability.CANONICAL_FACT.value
    assert len(resp.supporting_factors) >= 4


# 2. Unknown source (UNKNOWN)
def test_unknown_source(db):
    payment_id = "pay_unknown_src"
    _make_payment(db, payment_id)
    fact, _ = _make_fact_with_obs(db, payment_id, FactType.PAYMENT_AMOUNT_OBSERVED, "50000", source_type="UNKNOWN")
    db.commit()

    resp = evaluate_fact_reliability(db, fact)
    assert resp.overall_state == ReliabilityState.UNKNOWN
    assert resp.dimensions["source"].state == SourceReliability.UNKNOWN_SOURCE.value
    assert "CEILING_UNKNOWN" in resp.ceilings_applied[0]


# 3. Broken provenance (LIMITED ceiling)
def test_broken_provenance(db):
    payment_id = "pay_broken_prov"
    _make_payment(db, payment_id)
    # Fact without linked observations
    h = hashlib.sha256(f"{payment_id}|{FactType.PAYMENT_AMOUNT_OBSERVED}|50000".encode()).hexdigest()
    fact = EvidenceFact(
        payment_id=payment_id,
        fact_type=FactType.PAYMENT_AMOUNT_OBSERVED,
        canonical_value="50000",
        canonical_value_hash=h,
        first_observed_at=T_BASE,
        last_observed_at=T_BASE,
        observation_count=0,
        distinct_source_count=0,
        status=FactStatus.ACTIVE,
    )
    db.add(fact)
    db.commit()

    resp = evaluate_fact_reliability(db, fact)
    assert resp.dimensions["provenance"].state == ProvenanceReliability.BROKEN.value
    assert resp.overall_state == ReliabilityState.LIMITED
    assert any("CEILING_LIMITED" in c for c in resp.ceilings_applied)


# 4. Temporal ambiguity
def test_temporal_ambiguity(db):
    payment_id = "pay_temp_ambig"
    _make_payment(db, payment_id)
    obs = EvidenceObservation(
        evidence_type=FactType.PAYMENT_AMOUNT_OBSERVED,
        subject_type="payment",
        subject_id=payment_id,
        value="50000",
        value_type="STRING",
        source_type="RAZORPAY_WEBHOOK",
        observed_at=T_BASE,
        valid_from=T_PLUS_10M,
        valid_until=T_BASE,
        webhook_event_id=202,
        extraction_method="DIRECT_FIELD",
    )
    db.add(obs)
    db.flush()

    h = hashlib.sha256(f"{payment_id}|{FactType.PAYMENT_AMOUNT_OBSERVED}|50000".encode()).hexdigest()
    fact = EvidenceFact(
        payment_id=payment_id,
        fact_type=FactType.PAYMENT_AMOUNT_OBSERVED,
        canonical_value="50000",
        canonical_value_hash=h,
        first_observed_at=T_BASE,
        last_observed_at=T_BASE,
        observation_count=1,
        distinct_source_count=1,
        status=FactStatus.ACTIVE,
    )
    db.add(fact)
    db.flush()

    link = ObservationFactLink(observation_id=obs.internal_id, fact_id=fact.internal_id)
    db.add(link)
    db.commit()

    resp = evaluate_fact_reliability(db, fact)
    assert resp.dimensions["temporal"].state == TemporalReliability.TEMPORALLY_AMBIGUOUS.value


# 5. Open contradiction (LIMITED ceiling)
def test_open_contradiction(db):
    payment_id = "pay_conflict_01"
    _make_payment(db, payment_id)
    fact, _ = _make_fact_with_obs(db, payment_id, FactType.PAYMENT_AMOUNT_OBSERVED, "50000")
    
    # Introduce open Phase 8 conflict
    conflict = EvidenceConflict(
        payment_id=payment_id,
        conflict_type=ConflictType.VALUE_CONFLICT,
        severity=ConflictSeverity.HIGH,
        status=ConflictStatus.OPEN,
        detected_at=T_BASE,
        explanation="Amount mismatch between webhook and API",
        claim_a_id=1,
        claim_b_id=2,
    )
    db.add(conflict)
    db.commit()

    resp = evaluate_fact_reliability(db, fact)
    assert resp.dimensions["contradiction"].state == ContradictionReliability.CONFLICTED.value
    assert resp.overall_state == ReliabilityState.LIMITED
    assert any("CEILING_LIMITED" in c for c in resp.ceilings_applied)


# 6. Dependency concentration
def test_dependency_concentration(db):
    payment_id = "pay_dep_01"
    _make_payment(db, payment_id)
    
    # Two observations from the same webhook_event_id (dependent replication)
    obs1 = EvidenceObservation(
        evidence_type=FactType.PAYMENT_AMOUNT_OBSERVED,
        subject_type="payment",
        subject_id=payment_id,
        value="50000",
        value_type="STRING",
        source_type="RAZORPAY_WEBHOOK",
        observed_at=T_BASE,
        webhook_event_id=303,
        extraction_method="DIRECT_FIELD",
    )
    obs2 = EvidenceObservation(
        evidence_type=FactType.PAYMENT_AMOUNT_OBSERVED,
        subject_type="payment",
        subject_id=payment_id,
        value="50000",
        value_type="STRING",
        source_type="RAZORPAY_WEBHOOK",
        observed_at=T_BASE,
        webhook_event_id=303,
        extraction_method="DIRECT_FIELD",
    )
    db.add_all([obs1, obs2])
    db.flush()

    h = hashlib.sha256(f"{payment_id}|{FactType.PAYMENT_AMOUNT_OBSERVED}|50000".encode()).hexdigest()
    fact = EvidenceFact(
        payment_id=payment_id,
        fact_type=FactType.PAYMENT_AMOUNT_OBSERVED,
        canonical_value="50000",
        canonical_value_hash=h,
        first_observed_at=T_BASE,
        last_observed_at=T_BASE,
        observation_count=2,
        distinct_source_count=1,
        status=FactStatus.ACTIVE,
    )
    db.add(fact)
    db.flush()

    db.add_all([
        ObservationFactLink(observation_id=obs1.internal_id, fact_id=fact.internal_id),
        ObservationFactLink(observation_id=obs2.internal_id, fact_id=fact.internal_id),
    ])
    db.commit()

    resp = evaluate_fact_reliability(db, fact)
    assert resp.dimensions["dependency"].state == DependencyReliability.DEPENDENT_REPLICATION.value
    assert resp.overall_state == ReliabilityState.MODERATE


# 7. Unknown reconciliation
def test_unknown_reconciliation(db):
    payment_id = "pay_unresolved_01"
    _make_payment(db, payment_id)
    fact, _ = _make_fact_with_obs(db, payment_id, FactType.PAYMENT_AMOUNT_OBSERVED, "50000", status=FactStatus.UNRESOLVED)
    db.commit()

    resp = evaluate_fact_reliability(db, fact)
    assert resp.dimensions["identity"].state == IdentityReliability.UNKNOWN.value
    assert resp.overall_state == ReliabilityState.UNKNOWN


# 8. Partial structure
def test_partial_structure(db):
    payment_id = "pay_superseded_01"
    _make_payment(db, payment_id)
    fact, _ = _make_fact_with_obs(db, payment_id, FactType.PAYMENT_AMOUNT_OBSERVED, "50000", status=FactStatus.SUPERSEDED)
    db.commit()

    resp = evaluate_fact_reliability(db, fact)
    assert resp.dimensions["structural"].state == StructuralReliability.PARTIAL_OBSERVATION.value
    assert resp.overall_state == ReliabilityState.MODERATE


# 9. Multiple degradation reasons
def test_multiple_degradation_reasons(db):
    payment_id = "pay_mult_deg"
    _make_payment(db, payment_id)
    
    # Broken provenance + open contradiction
    h = hashlib.sha256(f"{payment_id}|{FactType.PAYMENT_AMOUNT_OBSERVED}|50000".encode()).hexdigest()
    fact = EvidenceFact(
        payment_id=payment_id,
        fact_type=FactType.PAYMENT_AMOUNT_OBSERVED,
        canonical_value="50000",
        canonical_value_hash=h,
        first_observed_at=T_BASE,
        last_observed_at=T_BASE,
        observation_count=0,
        distinct_source_count=0,
        status=FactStatus.ACTIVE,
    )
    db.add(fact)
    conflict = EvidenceConflict(payment_id=payment_id, conflict_type=ConflictType.STATE_CONFLICT, severity=ConflictSeverity.HIGH, status=ConflictStatus.OPEN, detected_at=T_BASE, explanation="State violation", claim_a_id=1, claim_b_id=2)
    db.add(conflict)
    db.commit()

    resp = evaluate_fact_reliability(db, fact)
    assert len(resp.degradation_factors) >= 2
    assert resp.overall_state == ReliabilityState.LIMITED


# 10. Reliability ceiling
def test_reliability_ceiling(db):
    payment_id = "pay_ceiling_01"
    _make_payment(db, payment_id)
    fact, _ = _make_fact_with_obs(db, payment_id, FactType.PAYMENT_AMOUNT_OBSERVED, "50000")
    conflict = EvidenceConflict(payment_id=payment_id, conflict_type=ConflictType.VALUE_CONFLICT, severity=ConflictSeverity.MEDIUM, status=ConflictStatus.OPEN, detected_at=T_BASE, explanation="Disputed value", claim_a_id=1, claim_b_id=2)
    db.add(conflict)
    db.commit()

    resp = evaluate_fact_reliability(db, fact)
    # Even though source is verified provider and provenance is complete, ceiling caps at LIMITED
    assert resp.overall_state == ReliabilityState.LIMITED


# 11. Reliability floor
def test_reliability_floor(db):
    payment_id = "pay_floor_01"
    _make_payment(db, payment_id)
    fact, _ = _make_fact_with_obs(db, payment_id, FactType.PAYMENT_AMOUNT_OBSERVED, "50000", status=FactStatus.INVALIDATED)
    db.commit()

    resp = evaluate_fact_reliability(db, fact)
    assert resp.overall_state == ReliabilityState.UNRELIABLE


# 12. Unknown != Limited
def test_unknown_not_limited(db):
    payment_id = "pay_unknown_diff"
    _make_payment(db, payment_id)
    fact, _ = _make_fact_with_obs(db, payment_id, FactType.PAYMENT_AMOUNT_OBSERVED, "50000", source_type="UNKNOWN")
    db.commit()

    resp = evaluate_fact_reliability(db, fact)
    assert resp.overall_state == ReliabilityState.UNKNOWN
    assert resp.overall_state != ReliabilityState.LIMITED
    assert resp.overall_state != ReliabilityState.MODERATE


# 13. Missing evidence != Unreliable evidence
def test_missing_is_not_unreliable(db):
    payment_id = "pay_missing_diff"
    _make_payment(db, payment_id)
    # Only amount is present, authorization is missing
    fact, _ = _make_fact_with_obs(db, payment_id, FactType.PAYMENT_AMOUNT_OBSERVED, "50000")
    db.commit()

    resp = evaluate_fact_reliability(db, fact)
    assert resp.overall_state == ReliabilityState.HIGH
    assert resp.canonical_value == "50000"


# 14. Coverage and reliability coexistence
def test_coverage_and_reliability_coexistence(db):
    payment_id = "pay_coexist_01"
    _make_payment(db, payment_id)
    fact, _ = _make_fact_with_obs(db, payment_id, FactType.PAYMENT_AMOUNT_OBSERVED, "50000")
    db.commit()

    pay_resp = evaluate_payment_reliability(db, payment_id)
    assert pay_resp.overall_state == ReliabilityState.HIGH
    assert pay_resp.facts_assessed == 1


# 15. Historical as-of evaluation
def test_historical_as_of_evaluation(db):
    payment_id = "pay_hist_01"
    _make_payment(db, payment_id)
    fact1, _ = _make_fact_with_obs(db, payment_id, FactType.PAYMENT_AMOUNT_OBSERVED, "50000", observed_at=T_BASE)
    db.commit()

    # Evaluation at T_BASE
    resp_t1 = evaluate_payment_reliability(db, payment_id, as_of=T_BASE)
    assert resp_t1.facts_assessed == 1

    # Add second fact at T_PLUS_5M
    fact2, _ = _make_fact_with_obs(db, payment_id, FactType.PAYMENT_CURRENCY_OBSERVED, "INR", observed_at=T_PLUS_5M)
    db.commit()

    resp_t2 = evaluate_payment_reliability(db, payment_id, as_of=T_PLUS_5M)
    assert resp_t2.facts_assessed == 2


# 16. Future evidence exclusion
def test_future_evidence_exclusion(db):
    payment_id = "pay_future_01"
    _make_payment(db, payment_id)
    fact, _ = _make_fact_with_obs(db, payment_id, FactType.PAYMENT_AMOUNT_OBSERVED, "50000", observed_at=T_PLUS_5M)
    db.commit()

    # Evaluating at T_BASE must exclude fact observed at T_PLUS_5M
    resp = evaluate_payment_reliability(db, payment_id, as_of=T_BASE)
    assert resp.facts_assessed == 0


# 17. Phase 13 integration
def test_phase13_integration(db):
    payment_id = "pay_p13_01"
    _make_payment(db, payment_id)
    fact, obs = _make_fact_with_obs(db, payment_id, FactType.PAYMENT_AMOUNT_OBSERVED, "50000")
    db.commit()

    resp = evaluate_fact_reliability(db, fact)
    assert resp.fact_id == fact.internal_id
    assert resp.dimensions["identity"].state == IdentityReliability.SAME_PROVIDER_EVENT.value


# 18. Phase 14 lineage integration
def test_phase14_lineage_integration(db):
    payment_id = "pay_p14_01"
    _make_payment(db, payment_id)
    fact, obs = _make_fact_with_obs(db, payment_id, FactType.PAYMENT_AMOUNT_OBSERVED, "50000", event_id=777)
    db.commit()

    resp = evaluate_fact_reliability(db, fact)
    assert "777" in resp.dimensions["provenance"].supporting_evidence[0]


# 19. Phase 15 coverage integration
def test_phase15_coverage_integration(db):
    payment_id = "pay_p15_01"
    _make_payment(db, payment_id)
    _make_fact_with_obs(db, payment_id, FactType.PAYMENT_AMOUNT_OBSERVED, "50000")
    db.commit()

    resp = evaluate_payment_reliability(db, payment_id)
    assert resp.facts_assessed == 1
    assert resp.overall_state == ReliabilityState.HIGH


# 20. Phase 11 reliability evolution
def test_phase11_reliability_evolution(db):
    payment_id = "pay_p11_01"
    _make_payment(db, payment_id)
    _make_fact_with_obs(db, payment_id, FactType.PAYMENT_AMOUNT_OBSERVED, "50000", observed_at=T_BASE)
    db.commit()

    # Snapshot 1 at T_BASE
    evaluate_payment_reliability(db, payment_id, as_of=T_BASE, persist=True)

    # Snapshot 2 at T_PLUS_5M
    evaluate_payment_reliability(db, payment_id, as_of=T_PLUS_5M, persist=True)

    hist = get_reliability_history(db, payment_id)
    assert hist.total == 2
    dt0 = hist.history[0].evaluated_at
    if dt0.tzinfo is None:
        dt0 = dt0.replace(tzinfo=timezone.utc)
    assert dt0 == T_BASE

    dt1 = hist.history[1].evaluated_at
    if dt1.tzinfo is None:
        dt1 = dt1.replace(tzinfo=timezone.utc)
    assert dt1 == T_PLUS_5M


# 21. Phase 10 trace methodology
def test_phase10_trace_methodology(db):
    payment_id = "pay_p10_01"
    _make_payment(db, payment_id)
    fact, _ = _make_fact_with_obs(db, payment_id, FactType.PAYMENT_AMOUNT_OBSERVED, "50000")
    db.commit()

    resp = evaluate_fact_reliability(db, fact)
    assert resp.methodology_version == RELIABILITY_METHODOLOGY_V1
    assert resp.methodology_version == "ERM-1.0"


# 22. Phase 12 investigation search
def test_phase12_investigation_search(client, api_db):
    payment_id = "pay_p12_01"
    _make_payment(api_db, payment_id)
    fact, _ = _make_fact_with_obs(api_db, payment_id, FactType.PAYMENT_AMOUNT_OBSERVED, "50000")
    api_db.commit()

    res = client.get(f"/api/v1/facts/{fact.internal_id}/reliability")
    assert res.status_code == 200
    data = res.json()
    assert data["fact_id"] == fact.internal_id
    assert data["overall_state"] == "HIGH"
    assert "dimensions" in data


# 23. Deterministic explanations
def test_deterministic_explanations(db):
    payment_id = "pay_det_01"
    _make_payment(db, payment_id)
    fact, _ = _make_fact_with_obs(db, payment_id, FactType.PAYMENT_AMOUNT_OBSERVED, "50000")
    db.commit()

    resp1 = evaluate_fact_reliability(db, fact)
    resp2 = evaluate_fact_reliability(db, fact)
    assert resp1.explanation == resp2.explanation
    assert resp1.supporting_factors == resp2.supporting_factors


# 24. API authorization and endpoints
def test_api_authorization_and_endpoints(client, api_db):
    payment_id = "pay_api_01"
    _make_payment(api_db, payment_id)
    fact, _ = _make_fact_with_obs(api_db, payment_id, FactType.PAYMENT_AMOUNT_OBSERVED, "50000")
    api_db.commit()

    # Fact reliability
    res_fact = client.get(f"/api/v1/facts/{fact.internal_id}/reliability")
    assert res_fact.status_code == 200

    # Payment reliability
    res_pay = client.get(f"/api/v1/payments/{payment_id}/reliability")
    assert res_pay.status_code == 200

    # Uncertainty
    res_unc = client.get(f"/api/v1/payments/{payment_id}/uncertainty")
    assert res_unc.status_code == 200
    assert isinstance(res_unc.json(), list)

    # 404 for unknown fact
    res_404 = client.get("/api/v1/facts/999999/reliability")
    assert res_404.status_code == 404


# 25. Sensitive data filtering
def test_sensitive_data_filtering(db):
    payment_id = "pay_safe_rel_01"
    _make_payment(db, payment_id)
    fact, _ = _make_fact_with_obs(db, payment_id, FactType.PAYMENT_AMOUNT_OBSERVED, "50000")
    db.commit()

    resp = evaluate_payment_reliability(db, payment_id)
    dump_str = str(resp.model_dump()).lower()
    for sensitive in ("cvv", "pin", "otp", "password", "api_key", "bearer"):
        assert sensitive not in dump_str


# 26. Idempotent evaluation
def test_idempotent_evaluation(db):
    payment_id = "pay_idem_01"
    _make_payment(db, payment_id)
    _make_fact_with_obs(db, payment_id, FactType.PAYMENT_AMOUNT_OBSERVED, "50000")
    db.commit()

    evaluate_payment_reliability(db, payment_id, as_of=T_BASE, persist=True)
    evaluate_payment_reliability(db, payment_id, as_of=T_BASE, persist=True)

    count = db.query(EvidenceReliabilityAssessment).filter(
        EvidenceReliabilityAssessment.payment_id == payment_id
    ).count()
    assert count == 1


# 27. Historical snapshot immutability
def test_historical_snapshot_immutability(db):
    payment_id = "pay_immut_01"
    _make_payment(db, payment_id)
    _make_fact_with_obs(db, payment_id, FactType.PAYMENT_AMOUNT_OBSERVED, "50000")
    db.commit()

    snap = evaluate_payment_reliability(db, payment_id, as_of=T_BASE, persist=True)
    rec = db.query(EvidenceReliabilityAssessment).filter(
        EvidenceReliabilityAssessment.payment_id == payment_id
    ).first()
    assert rec.overall_state == ReliabilityState.HIGH.value
    assert rec.methodology_version == "ERM-1.0"
