"""
Unit and integration tests for Phase 7 — Evidence Structure, Claims, Grouping & Corroboration.
"""
from datetime import datetime, timezone
import pytest
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker

@compiles(JSONB, "sqlite")
def compile_jsonb_sqlite(type_, compiler, **kw):
    return "JSON"

from app.db.session import Base
from app.models.evidence import EvidenceObservation
from app.models.evidence_types import EvidenceType, SourceType, ValueType
from app.models.structure_types import (
    ClaimType,
    GroupType,
    CorroborationType,
    IndependenceStatus,
)
from app.models.evidence_structure import (
    Claim,
    EvidenceClaimLink,
    EvidenceGroup,
    EvidenceCorroboration,
    EvidenceStructureSnapshot,
)
from app.services.claim_service import ClaimService
from app.services.grouping_service import GroupingService
from app.services.corroboration_service import CorroborationService
from app.services.structure_engine import StructureEngine


# ---------------------------------------------------------------------------
# Test Fixtures & SQLite Setup
# ---------------------------------------------------------------------------

from sqlalchemy.pool import StaticPool

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


def _make_obs(
    internal_id: int,
    evidence_type: str,
    value: str,
    subject_id: str = "pay_test_123",
    subject_type: str = "payment",
    source_type: str = SourceType.RAZORPAY_WEBHOOK,
    payment_event_id: int = 1,
    webhook_event_id: int = 1,
    observed_at: datetime = None,
) -> EvidenceObservation:
    obs = EvidenceObservation(
        internal_id=internal_id,
        evidence_type=evidence_type,
        subject_type=subject_type,
        subject_id=subject_id,
        value=value,
        value_type=ValueType.STRING,
        source_type=source_type,
        source_reference="test_ref",
        extraction_method="TEST",
        extraction_version="1.0",
        observed_at=observed_at or datetime(2026, 8, 22, 12, 0, 0, tzinfo=timezone.utc),
        payment_event_id=payment_event_id,
        webhook_event_id=webhook_event_id,
        provenance_metadata={"test": True},
    )
    return obs


# ---------------------------------------------------------------------------
# 1. Claims Tests
# ---------------------------------------------------------------------------

class TestClaims:
    def test_claim_mapping_specs(self):
        obs_status = _make_obs(1, EvidenceType.PAYMENT_STATUS, "captured")
        spec_status = ClaimService.map_observation_to_claim_spec(obs_status)
        assert spec_status["claim_type"] == ClaimType.PAYMENT_STATUS.value
        assert spec_status["canonical_value"] == "captured"

        obs_amount = _make_obs(2, EvidenceType.PAYMENT_AMOUNT, "50000")
        spec_amount = ClaimService.map_observation_to_claim_spec(obs_amount)
        assert spec_amount["claim_type"] == ClaimType.PAYMENT_AMOUNT.value
        assert spec_amount["canonical_value"] == "50000"

        obs_method = _make_obs(3, EvidenceType.PAYMENT_METHOD, "UPI")
        spec_method = ClaimService.map_observation_to_claim_spec(obs_method)
        assert spec_method["claim_type"] == ClaimType.PAYMENT_METHOD.value
        assert spec_method["canonical_value"] == "upi"

    def test_equivalent_observations_map_to_same_claim(self, in_memory_db):
        obs1 = _make_obs(1, EvidenceType.PAYMENT_STATUS, "captured", payment_event_id=1)
        obs2 = _make_obs(2, EvidenceType.PAYMENT_STATUS, "captured", payment_event_id=2)
        in_memory_db.add_all([obs1, obs2])
        in_memory_db.flush()

        claims = ClaimService.process_observations(in_memory_db, [obs1, obs2])
        assert len(claims) == 1
        assert claims[0].canonical_value == "captured"

        # Check links
        links = in_memory_db.query(EvidenceClaimLink).filter(EvidenceClaimLink.claim_id == claims[0].internal_id).all()
        assert len(links) == 2
        linked_evidence_ids = {l.evidence_id for l in links}
        assert linked_evidence_ids == {1, 2}

    def test_missing_value_produces_no_claim(self):
        obs = _make_obs(1, EvidenceType.PAYMENT_STATUS, "")
        obs.value = None
        spec = ClaimService.map_observation_to_claim_spec(obs)
        assert spec is None


# ---------------------------------------------------------------------------
# 2. Grouping Tests
# ---------------------------------------------------------------------------

class TestGrouping:
    def test_grouping_by_event_and_source(self, in_memory_db):
        obs1 = _make_obs(1, EvidenceType.PAYMENT_STATUS, "captured", payment_event_id=10, webhook_event_id=100)
        obs2 = _make_obs(2, EvidenceType.PAYMENT_AMOUNT, "50000", payment_event_id=10, webhook_event_id=100)
        obs3 = _make_obs(3, EvidenceType.PAYMENT_STATUS, "captured", payment_event_id=20, webhook_event_id=200)
        in_memory_db.add_all([obs1, obs2, obs3])
        in_memory_db.flush()

        groups = GroupingService.group_payment_evidence(in_memory_db, "pay_test_123", [obs1, obs2, obs3])
        
        pe_groups = [g for g in groups if g.group_type == GroupType.SAME_PAYMENT_EVENT.value]
        we_groups = [g for g in groups if g.group_type == GroupType.SAME_WEBHOOK_EVENT.value]
        src_groups = [g for g in groups if g.group_type == GroupType.SAME_SOURCE.value]

        assert len(pe_groups) == 2  # event 10 and event 20
        assert len(we_groups) == 2  # webhook 100 and webhook 200
        assert len(src_groups) == 1  # RAZORPAY_WEBHOOK

        # Check members for event 10
        grp_10 = next(g for g in pe_groups if g.grouping_key == "payment_event_10")
        assert len(grp_10.members) == 2

    def test_grouping_does_not_mutate_observations(self, in_memory_db):
        obs = _make_obs(1, EvidenceType.PAYMENT_STATUS, "captured")
        in_memory_db.add(obs)
        in_memory_db.flush()

        GroupingService.group_payment_evidence(in_memory_db, "pay_test_123", [obs])
        reloaded = in_memory_db.query(EvidenceObservation).filter(EvidenceObservation.internal_id == 1).one()
        assert reloaded.value == "captured"


# ---------------------------------------------------------------------------
# 3. Corroboration & Independence Tests
# ---------------------------------------------------------------------------

class TestCorroboration:
    def test_single_observation_corroboration(self, in_memory_db):
        obs = _make_obs(1, EvidenceType.PAYMENT_STATUS, "captured")
        in_memory_db.add(obs)
        in_memory_db.flush()

        claims = ClaimService.process_observations(in_memory_db, [obs])
        corrob = CorroborationService.evaluate_claim_corroboration(in_memory_db, claims[0], "pay_test_123")

        assert corrob.corroboration_type == CorroborationType.SINGLE_OBSERVATION.value
        assert corrob.independence_status == IndependenceStatus.UNKNOWN.value
        assert corrob.observation_count == 1

    def test_same_source_multiple_observations(self, in_memory_db):
        obs1 = _make_obs(1, EvidenceType.PAYMENT_STATUS, "captured", payment_event_id=1, webhook_event_id=1)
        obs2 = _make_obs(2, EvidenceType.PAYMENT_STATUS, "captured", payment_event_id=1, webhook_event_id=1)
        in_memory_db.add_all([obs1, obs2])
        in_memory_db.flush()

        claims = ClaimService.process_observations(in_memory_db, [obs1, obs2])
        corrob = CorroborationService.evaluate_claim_corroboration(in_memory_db, claims[0], "pay_test_123")

        assert corrob.corroboration_type == CorroborationType.SAME_SOURCE_CORROBORATION.value
        assert corrob.independence_status == IndependenceStatus.SAME_SOURCE.value
        assert corrob.observation_count == 2

    def test_temporal_corroboration_across_events(self, in_memory_db):
        t1 = datetime(2026, 8, 22, 10, 0, 0, tzinfo=timezone.utc)
        t2 = datetime(2026, 8, 22, 11, 0, 0, tzinfo=timezone.utc)
        obs1 = _make_obs(1, EvidenceType.PAYMENT_STATUS, "captured", payment_event_id=1, observed_at=t1)
        obs2 = _make_obs(2, EvidenceType.PAYMENT_STATUS, "captured", payment_event_id=2, observed_at=t2)
        in_memory_db.add_all([obs1, obs2])
        in_memory_db.flush()

        claims = ClaimService.process_observations(in_memory_db, [obs1, obs2])
        corrob = CorroborationService.evaluate_claim_corroboration(in_memory_db, claims[0], "pay_test_123")

        assert corrob.corroboration_type == CorroborationType.TEMPORAL_CORROBORATION.value
        assert corrob.independence_status == IndependenceStatus.DEPENDENT.value
        assert corrob.distinct_events_count == 2

    def test_multi_source_corroboration_independent_candidate(self, in_memory_db):
        obs1 = _make_obs(1, EvidenceType.PAYMENT_STATUS, "captured", source_type=SourceType.RAZORPAY_WEBHOOK)
        obs2 = _make_obs(2, EvidenceType.PAYMENT_STATUS, "captured", source_type=SourceType.RAZORPAY_API)
        in_memory_db.add_all([obs1, obs2])
        in_memory_db.flush()

        claims = ClaimService.process_observations(in_memory_db, [obs1, obs2])
        corrob = CorroborationService.evaluate_claim_corroboration(in_memory_db, claims[0], "pay_test_123")

        assert corrob.corroboration_type == CorroborationType.MULTI_SOURCE_CORROBORATION.value
        assert corrob.independence_status == IndependenceStatus.INDEPENDENT_CANDIDATE.value
        assert corrob.distinct_sources_count == 2


# ---------------------------------------------------------------------------
# 4. Concentration & HHI Calculation Tests
# ---------------------------------------------------------------------------

class TestConcentrationAndHHI:
    def test_single_event_concentration_hhi_equals_one(self, in_memory_db):
        # 4 observations all from event 1
        obs = [
            _make_obs(1, EvidenceType.PAYMENT_STATUS, "captured", payment_event_id=1),
            _make_obs(2, EvidenceType.PAYMENT_AMOUNT, "50000", payment_event_id=1),
            _make_obs(3, EvidenceType.PAYMENT_CURRENCY, "INR", payment_event_id=1),
            _make_obs(4, EvidenceType.PAYMENT_METHOD, "upi", payment_event_id=1),
        ]
        in_memory_db.add_all(obs)
        in_memory_db.flush()

        snapshot = StructureEngine.evaluate_payment_structure(in_memory_db, "pay_test_123")
        assert snapshot is not None
        assert snapshot.total_observations == 4
        assert snapshot.distinct_events == 1
        assert snapshot.largest_group_size == 4
        assert snapshot.group_hhi == 1.0

    def test_split_event_concentration_hhi(self, in_memory_db):
        # 8 observations from event 1, 2 observations from event 2
        obs = []
        for i in range(1, 9):
            obs.append(_make_obs(i, EvidenceType.PAYMENT_STATUS, "captured", payment_event_id=1, webhook_event_id=1))
        for i in range(9, 11):
            obs.append(_make_obs(i, EvidenceType.PAYMENT_STATUS, "captured", payment_event_id=2, webhook_event_id=2))

        in_memory_db.add_all(obs)
        in_memory_db.flush()

        snapshot = StructureEngine.evaluate_payment_structure(in_memory_db, "pay_test_123")
        assert snapshot is not None
        assert snapshot.total_observations == 10
        assert snapshot.distinct_events == 2
        assert snapshot.largest_group_size == 8
        # HHI = (8/10)^2 + (2/10)^2 = 0.64 + 0.04 = 0.68
        assert snapshot.group_hhi == 0.68


# ---------------------------------------------------------------------------
# 5. Determinism & Methodology Versioning
# ---------------------------------------------------------------------------

class TestDeterminismAndVersioning:
    def test_deterministic_output(self, in_memory_db):
        obs = [
            _make_obs(1, EvidenceType.PAYMENT_STATUS, "captured", payment_event_id=1),
            _make_obs(2, EvidenceType.PAYMENT_AMOUNT, "50000", payment_event_id=1),
        ]
        in_memory_db.add_all(obs)
        in_memory_db.flush()

        eval_time = datetime(2026, 8, 22, 15, 0, 0, tzinfo=timezone.utc)
        snap1 = StructureEngine.evaluate_payment_structure(in_memory_db, "pay_test_123", eval_time)
        snap2 = StructureEngine.evaluate_payment_structure(in_memory_db, "pay_test_123", eval_time)

        assert snap1.total_observations == snap2.total_observations
        assert snap1.distinct_claims == snap2.distinct_claims
        assert snap1.group_hhi == snap2.group_hhi
        assert snap1.methodology_version == "1.0"


# ---------------------------------------------------------------------------
# 6. Structure API Endpoints
# ---------------------------------------------------------------------------

class TestStructureAPI:
    def test_payment_structure_endpoint(self, in_memory_db):
        from fastapi.testclient import TestClient
        from app.main import create_app
        from app.db.session import get_db

        obs = [
            _make_obs(1, EvidenceType.PAYMENT_STATUS, "captured", payment_event_id=1),
            _make_obs(2, EvidenceType.PAYMENT_AMOUNT, "50000", payment_event_id=1),
        ]
        in_memory_db.add_all(obs)
        in_memory_db.flush()

        app = create_app()
        app.dependency_overrides[get_db] = lambda: in_memory_db

        client = TestClient(app)
        resp = client.get("/api/v1/payments/pay_test_123/structure")
        assert resp.status_code == 200
        data = resp.json()
        assert data["payment_id"] == "pay_test_123"
        assert data["snapshot"]["total_observations"] == 2
        assert len(data["claims"]) == 2
        assert len(data["groups"]) > 0

    def test_payment_claims_endpoint(self, in_memory_db):
        from fastapi.testclient import TestClient
        from app.main import create_app
        from app.db.session import get_db

        obs = [
            _make_obs(1, EvidenceType.PAYMENT_STATUS, "captured", payment_event_id=1),
        ]
        in_memory_db.add_all(obs)
        in_memory_db.flush()

        app = create_app()
        app.dependency_overrides[get_db] = lambda: in_memory_db

        client = TestClient(app)
        resp = client.get("/api/v1/payments/pay_test_123/claims")
        assert resp.status_code == 200
        claims = resp.json()
        assert len(claims) == 1
        claim_id = claims[0]["internal_id"]

        # Test claim evidence endpoint
        resp_ev = client.get(f"/api/v1/claims/{claim_id}/evidence")
        assert resp_ev.status_code == 200
        claim_ev = resp_ev.json()
        assert claim_ev["claim"]["internal_id"] == claim_id
        assert len(claim_ev["evidence"]) == 1
        assert claim_ev["evidence"][0]["evidence_id"] == 1

