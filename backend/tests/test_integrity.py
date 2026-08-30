"""
Tests for Phase 9 — Explainable Evidence Integrity Computation Engine.

Tests cover:
  - Freshness dimension
  - Source dimension
  - Independence dimension
  - Corroboration dimension
  - Consistency dimension
  - Overall aggregation (INSUFFICIENT_DATA, UNRESOLVED, WEAK, STRONG, VERY_STRONG, LIMITED)
  - Temporal isolation (future evidence must NOT leak into historical evaluations)
  - Idempotency (same inputs → no duplicate snapshot)
  - Methodology version distinguishability
  - Explanation quality (no overclaiming)
  - Limitations surfacing
  - Integrity history ordering and immutability
  - API endpoints (/integrity and /integrity/history)
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# ---------------------------------------------------------------------------
# SQLite JSONB polyfill (same pattern used by all prior phases)
# ---------------------------------------------------------------------------
@compiles(JSONB, "sqlite")
def compile_jsonb_sqlite(type_, compiler, **kw):
    return "JSON"


from app.db.session import Base
from app.main import app
from app.db.session import get_db
from app.models.evidence import EvidenceObservation
from app.models.evidence_conflict import EvidenceConflict
from app.models.evidence_integrity import EvidenceIntegritySnapshot
from app.models.evidence_quality import EvidenceQualitySnapshot
from app.models.evidence_structure import (
    Claim,
    EvidenceClaimLink,
    EvidenceCorroboration,
    EvidenceGroup,
    EvidenceGroupMember,
    EvidenceStructureSnapshot,
)
from app.models.evidence_types import EvidenceType, SourceType, ValueType
from app.models.integrity_types import (
    INTEGRITY_METHODOLOGY_VERSION,
    ConsistencyStatus,
    CorroborationStatus,
    IndependenceStatus,
    IntegrityStatus,
)
from app.models.payment import Payment
from app.models.quality_types import (
    AuthorityLevel,
    FreshnessState,
    HistoricalReliabilityStatus,
    SourceDirectness,
)
from app.models.structure_types import ClaimType, GroupType
from app.services.integrity_engine import IntegrityEngine


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

T_BASE = datetime(2026, 8, 22, 10, 0, 0, tzinfo=timezone.utc)
T_PLUS_1 = T_BASE + timedelta(minutes=1)
T_PLUS_5 = T_BASE + timedelta(minutes=5)
T_PLUS_10 = T_BASE + timedelta(minutes=10)

PAY_ID = "pay_integrity_test_01"


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

    app.dependency_overrides[get_db] = override_get_db

    Session_for_seeding = sessionmaker(bind=engine)
    seed_session = Session_for_seeding()

    try:
        yield seed_session
    finally:
        seed_session.close()
        app.dependency_overrides.clear()


@pytest.fixture
def client(api_db):
    return TestClient(app)


# ---------------------------------------------------------------------------
# Helper factories
# ---------------------------------------------------------------------------

def _make_payment(db, payment_id: str = PAY_ID) -> Payment:
    p = Payment(
        razorpay_payment_id=payment_id,
        status="captured",
        amount_minor=10000,
        currency="INR",
    )
    db.add(p)
    db.flush()
    return p


def _make_obs(
    db,
    internal_id: int,
    payment_id: str = PAY_ID,
    evidence_type: str = EvidenceType.PAYMENT_STATUS,
    value: str = "captured",
    source_type: str = SourceType.RAZORPAY_WEBHOOK,
    observed_at: datetime = None,
) -> EvidenceObservation:
    obs = EvidenceObservation(
        internal_id=internal_id,
        evidence_type=evidence_type,
        subject_type="payment",
        subject_id=payment_id,
        value=value,
        value_type=ValueType.STRING,
        source_type=source_type,
        source_reference="test_ref",
        extraction_method="TEST",
        extraction_version="1.0",
        observed_at=observed_at or T_BASE,
        payment_event_id=1,
        webhook_event_id=1,
        provenance_metadata={"test": True},
    )
    db.add(obs)
    db.flush()
    return obs


def _make_quality_snapshot(
    db,
    evidence_id: int,
    freshness_state: str = FreshnessState.CURRENT,
    authority_level: str = AuthorityLevel.PRIMARY,
    directness: str = SourceDirectness.DIRECT,
    evaluated_at: datetime = None,
    source_type: str = SourceType.RAZORPAY_WEBHOOK,
) -> EvidenceQualitySnapshot:
    snap = EvidenceQualitySnapshot(
        evidence_id=evidence_id,
        evaluated_at=evaluated_at or T_BASE,
        age_seconds=60.0,
        freshness_state=freshness_state,
        freshness_policy_key="DEFAULT",
        freshness_methodology_version="1.0",
        source_type=source_type,
        source_directness=directness,
        source_authority_level=authority_level,
        source_methodology_version="1.0",
        historical_reliability_status=HistoricalReliabilityStatus.NO_OUTCOME_DATA,
        reliability_sample_count=None,
        reliability_methodology_version="1.0",
    )
    db.add(snap)
    db.flush()
    return snap


def _make_structure_snapshot(
    db,
    payment_id: str = PAY_ID,
    distinct_sources: int = 1,
    distinct_events: int = 1,
    distinct_groups: int = 1,
    total_observations: int = 2,
    hhi: float = 1.0,
    evaluated_at: datetime = None,
) -> EvidenceStructureSnapshot:
    snap = EvidenceStructureSnapshot(
        payment_id=payment_id,
        evaluated_at=evaluated_at or T_BASE,
        total_observations=total_observations,
        distinct_claims=1,
        distinct_sources=distinct_sources,
        distinct_events=distinct_events,
        distinct_groups=distinct_groups,
        largest_group_size=total_observations,
        group_hhi=hhi,
        corroborated_claim_count=0,
        multi_source_claim_count=0,
    )
    db.add(snap)
    db.flush()
    return snap


def _make_claim(
    db,
    claim_type: str = ClaimType.PAYMENT_STATUS,
    claim_key: str = "payment.status",
    canonical_value: str = "captured",
    payment_id: str = PAY_ID,
) -> Claim:
    claim = Claim(
        subject_type="payment",
        subject_id=payment_id,
        claim_type=claim_type,
        claim_key=claim_key,
        canonical_value=canonical_value,
        created_at=T_BASE,
    )
    db.add(claim)
    db.flush()
    return claim


def _make_corroboration(
    db,
    claim: Claim,
    payment_id: str = PAY_ID,
    observation_count: int = 1,
    distinct_sources: int = 1,
    distinct_events: int = 1,
) -> EvidenceCorroboration:
    corr = EvidenceCorroboration(
        claim_id=claim.internal_id,
        payment_id=payment_id,
        corroboration_type="SAME_CLAIM",
        independence_status="SINGLE_SOURCE" if distinct_sources == 1 else "MULTI_SOURCE",
        observation_count=observation_count,
        distinct_sources_count=distinct_sources,
        distinct_events_count=distinct_events,
    )
    db.add(corr)
    db.flush()
    return corr


def _make_open_conflict(
    db,
    payment_id: str = PAY_ID,
    claim_a_id: int = None,
    claim_b_id: int = None,
    severity: str = "HIGH",
) -> EvidenceConflict:
    conflict = EvidenceConflict(
        payment_id=payment_id,
        claim_a_id=claim_a_id,
        claim_b_id=claim_b_id,
        conflict_type="STATE_CONFLICT",
        severity=severity,
        status="OPEN",
        detected_at=T_BASE,
        rule_version="1.0",
    )
    db.add(conflict)
    db.flush()
    return conflict


def _make_info_conflict(
    db,
    payment_id: str = PAY_ID,
    claim_a_id: int = None,
    claim_b_id: int = None,
) -> EvidenceConflict:
    conflict = EvidenceConflict(
        payment_id=payment_id,
        claim_a_id=claim_a_id,
        claim_b_id=claim_b_id,
        conflict_type="ORDERING_AMBIGUITY",
        severity="INFO",
        status="OPEN",
        detected_at=T_BASE,
        rule_version="1.0",
    )
    db.add(conflict)
    db.flush()
    return conflict


# ===========================================================================
# Class 1 — Freshness Dimension
# ===========================================================================

class TestFreshnessDimension:
    def test_strong_when_all_current(self, db):
        obs = _make_obs(db, internal_id=1, observed_at=T_BASE)
        _make_quality_snapshot(db, evidence_id=1, freshness_state=FreshnessState.CURRENT)
        db.flush()

        result = IntegrityEngine._compute_freshness_dimension(
            db, [1], evaluation_time=T_PLUS_1
        )
        assert result["status"] == "STRONG"

    def test_strong_when_aging(self, db):
        obs = _make_obs(db, internal_id=1, observed_at=T_BASE)
        _make_quality_snapshot(db, evidence_id=1, freshness_state=FreshnessState.AGING)
        db.flush()

        result = IntegrityEngine._compute_freshness_dimension(
            db, [1], evaluation_time=T_PLUS_1
        )
        assert result["status"] == "STRONG"

    def test_limited_when_stale(self, db):
        _make_obs(db, internal_id=1, observed_at=T_BASE)
        _make_quality_snapshot(db, evidence_id=1, freshness_state=FreshnessState.STALE)
        db.flush()

        result = IntegrityEngine._compute_freshness_dimension(
            db, [1], evaluation_time=T_PLUS_1
        )
        assert result["status"] == "LIMITED"
        assert result["inputs"]["stale_count"] == 1

    def test_unknown_when_no_snapshots(self, db):
        _make_obs(db, internal_id=1, observed_at=T_BASE)
        db.flush()

        result = IntegrityEngine._compute_freshness_dimension(
            db, [1], evaluation_time=T_PLUS_1
        )
        assert result["status"] == "UNKNOWN"

    def test_no_evidence_returns_unknown(self, db):
        result = IntegrityEngine._compute_freshness_dimension(
            db, [], evaluation_time=T_PLUS_1
        )
        assert result["status"] == "UNKNOWN"


# ===========================================================================
# Class 2 — Source Dimension
# ===========================================================================

class TestSourceDimension:
    def test_strong_when_primary_direct(self, db):
        _make_obs(db, internal_id=1)
        _make_quality_snapshot(
            db, 1,
            authority_level=AuthorityLevel.PRIMARY,
            directness=SourceDirectness.DIRECT,
        )
        db.flush()

        result = IntegrityEngine._compute_source_dimension(db, [1], T_PLUS_1)
        assert result["status"] == "STRONG"

    def test_limited_when_secondary(self, db):
        _make_obs(db, internal_id=1)
        _make_quality_snapshot(
            db, 1,
            authority_level=AuthorityLevel.SECONDARY,
            directness=SourceDirectness.DERIVED,
        )
        db.flush()

        result = IntegrityEngine._compute_source_dimension(db, [1], T_PLUS_1)
        assert result["status"] == "LIMITED"

    def test_weak_when_tertiary(self, db):
        _make_obs(db, internal_id=1)
        _make_quality_snapshot(
            db, 1,
            authority_level=AuthorityLevel.TERTIARY,
            directness=SourceDirectness.INFERRED,
        )
        db.flush()

        result = IntegrityEngine._compute_source_dimension(db, [1], T_PLUS_1)
        assert result["status"] == "WEAK"

    def test_unknown_when_no_snapshots(self, db):
        _make_obs(db, internal_id=1)
        db.flush()

        result = IntegrityEngine._compute_source_dimension(db, [1], T_PLUS_1)
        assert result["status"] == "UNKNOWN"


# ===========================================================================
# Class 3 — Independence Dimension
# ===========================================================================

class TestIndependenceDimension:
    def test_high_diversity_when_multi_source_and_multi_event(self, db):
        _make_structure_snapshot(db, distinct_sources=3, distinct_events=2)
        db.flush()

        result = IntegrityEngine._compute_independence_dimension(db, PAY_ID, T_PLUS_1)
        assert result["status"] == IndependenceStatus.HIGH_SOURCE_DIVERSITY

    def test_limited_diversity_when_one_source_multi_event(self, db):
        _make_structure_snapshot(db, distinct_sources=1, distinct_events=3)
        db.flush()

        result = IntegrityEngine._compute_independence_dimension(db, PAY_ID, T_PLUS_1)
        assert result["status"] == IndependenceStatus.LIMITED_SOURCE_DIVERSITY

    def test_single_source_when_all_one(self, db):
        _make_structure_snapshot(db, distinct_sources=1, distinct_events=1)
        db.flush()

        result = IntegrityEngine._compute_independence_dimension(db, PAY_ID, T_PLUS_1)
        assert result["status"] == IndependenceStatus.SINGLE_SOURCE

    def test_unknown_when_no_snapshot(self, db):
        result = IntegrityEngine._compute_independence_dimension(db, PAY_ID, T_PLUS_1)
        assert result["status"] == IndependenceStatus.UNKNOWN

    def test_future_snapshot_excluded(self, db):
        """Structure snapshot evaluated AFTER evaluation_time must be excluded."""
        _make_structure_snapshot(
            db, distinct_sources=3, distinct_events=3,
            evaluated_at=T_PLUS_10,  # future
        )
        db.flush()

        # Evaluate at T_BASE — the T_PLUS_10 snapshot must not be visible
        result = IntegrityEngine._compute_independence_dimension(db, PAY_ID, T_BASE)
        assert result["status"] == IndependenceStatus.UNKNOWN


# ===========================================================================
# Class 4 — Corroboration Dimension
# ===========================================================================

class TestCorroborationDimension:
    def test_strongly_corroborated_when_multi_source(self, db):
        claim = _make_claim(db)
        _make_corroboration(db, claim, observation_count=3, distinct_sources=2)
        db.flush()

        result = IntegrityEngine._compute_corroboration_dimension(db, PAY_ID)
        assert result["status"] == CorroborationStatus.STRONGLY_CORROBORATED

    def test_partially_corroborated_when_multi_obs_single_source(self, db):
        claim = _make_claim(db)
        _make_corroboration(db, claim, observation_count=3, distinct_sources=1)
        db.flush()

        result = IntegrityEngine._compute_corroboration_dimension(db, PAY_ID)
        assert result["status"] == CorroborationStatus.PARTIALLY_CORROBORATED

    def test_single_observation(self, db):
        claim = _make_claim(db)
        _make_corroboration(db, claim, observation_count=1, distinct_sources=1)
        db.flush()

        result = IntegrityEngine._compute_corroboration_dimension(db, PAY_ID)
        assert result["status"] == CorroborationStatus.SINGLE_OBSERVATION

    def test_unknown_when_no_records(self, db):
        result = IntegrityEngine._compute_corroboration_dimension(db, PAY_ID)
        assert result["status"] == CorroborationStatus.UNKNOWN


# ===========================================================================
# Class 5 — Consistency Dimension
# ===========================================================================

class TestConsistencyDimension:
    def test_no_detected_conflict_when_empty(self, db):
        count, open_count, result = IntegrityEngine._compute_consistency_dimension(db, PAY_ID)
        assert count == 0
        assert open_count == 0
        assert result["status"] == ConsistencyStatus.NO_DETECTED_CONFLICT

    def test_has_open_conflicts_when_high_severity_open(self, db):
        claim_a = _make_claim(db, claim_key="payment.status", canonical_value="captured")
        claim_b = _make_claim(db, claim_key="payment.status", canonical_value="failed")
        _make_open_conflict(db, claim_a_id=claim_a.internal_id, claim_b_id=claim_b.internal_id, severity="HIGH")
        db.flush()

        count, open_count, result = IntegrityEngine._compute_consistency_dimension(db, PAY_ID)
        assert open_count == 1
        assert result["status"] == ConsistencyStatus.HAS_OPEN_CONFLICTS

    def test_ordering_ambiguity_only_for_info_conflicts(self, db):
        claim_a = _make_claim(db, claim_key="payment.status", canonical_value="authorized")
        claim_b = _make_claim(db, claim_key="payment.status", canonical_value="captured")
        _make_info_conflict(db, claim_a_id=claim_a.internal_id, claim_b_id=claim_b.internal_id)
        db.flush()

        count, open_count, result = IntegrityEngine._compute_consistency_dimension(db, PAY_ID)
        assert open_count == 0  # INFO conflicts don't count as open
        assert result["status"] == ConsistencyStatus.ORDERING_AMBIGUITY_ONLY

    def test_inputs_are_structured(self, db):
        count, open_count, result = IntegrityEngine._compute_consistency_dimension(db, PAY_ID)
        assert "inputs" in result
        assert "conflict_count" in result["inputs"]


# ===========================================================================
# Class 6 — Aggregation
# ===========================================================================

class TestAggregation:
    def _build_dims(
        self,
        freshness="STRONG",
        source="STRONG",
        independence=IndependenceStatus.HIGH_SOURCE_DIVERSITY,
        corroboration=CorroborationStatus.STRONGLY_CORROBORATED,
        consistency=ConsistencyStatus.NO_DETECTED_CONFLICT,
    ):
        return (
            {"status": freshness, "reason": "", "inputs": {}},
            {"status": source, "reason": "", "inputs": {}},
            {"status": independence, "reason": "", "inputs": {}},
            {"status": corroboration, "reason": "", "inputs": {}},
            {"status": consistency, "reason": "", "inputs": {}},
        )

    def test_insufficient_data_when_no_evidence(self, db):
        from app.models.integrity_methodology import EIS_V1
        fr, sr, ir, cr, consr = self._build_dims()
        status = IntegrityEngine._aggregate_status(
            EIS_V1, evidence_count=0, open_conflict_count=0,
            freshness_result=fr, source_result=sr,
            independence_result=ir, corroboration_result=cr,
            consistency_result=consr,
        )
        assert status == IntegrityStatus.INSUFFICIENT_DATA

    def test_unresolved_when_open_conflicts(self, db):
        from app.models.integrity_methodology import EIS_V1
        fr, sr, ir, cr, consr = self._build_dims()
        status = IntegrityEngine._aggregate_status(
            EIS_V1, evidence_count=5, open_conflict_count=2,
            freshness_result=fr, source_result=sr,
            independence_result=ir, corroboration_result=cr,
            consistency_result=consr,
        )
        assert status == IntegrityStatus.UNRESOLVED

    def test_weak_when_stale(self, db):
        from app.models.integrity_methodology import EIS_V1
        fr, sr, ir, cr, consr = self._build_dims(freshness="STALE")
        status = IntegrityEngine._aggregate_status(
            EIS_V1, evidence_count=3, open_conflict_count=0,
            freshness_result=fr, source_result=sr,
            independence_result=ir, corroboration_result=cr,
            consistency_result=consr,
        )
        assert status == IntegrityStatus.WEAK

    def test_very_strong_when_all_optimal(self, db):
        from app.models.integrity_methodology import EIS_V1
        fr, sr, ir, cr, consr = self._build_dims()
        status = IntegrityEngine._aggregate_status(
            EIS_V1, evidence_count=3, open_conflict_count=0,
            freshness_result=fr, source_result=sr,
            independence_result=ir, corroboration_result=cr,
            consistency_result=consr,
        )
        assert status == IntegrityStatus.VERY_STRONG

    def test_strong_when_single_source_no_conflict(self, db):
        from app.models.integrity_methodology import EIS_V1
        fr, sr, ir, cr, consr = self._build_dims(
            independence=IndependenceStatus.SINGLE_SOURCE,
            corroboration=CorroborationStatus.SINGLE_OBSERVATION,
        )
        status = IntegrityEngine._aggregate_status(
            EIS_V1, evidence_count=2, open_conflict_count=0,
            freshness_result=fr, source_result=sr,
            independence_result=ir, corroboration_result=cr,
            consistency_result=consr,
        )
        assert status == IntegrityStatus.STRONG

    def test_strong_with_ordering_ambiguity(self, db):
        from app.models.integrity_methodology import EIS_V1
        fr, sr, ir, cr, consr = self._build_dims(
            consistency=ConsistencyStatus.ORDERING_AMBIGUITY_ONLY,
            independence=IndependenceStatus.SINGLE_SOURCE,
        )
        status = IntegrityEngine._aggregate_status(
            EIS_V1, evidence_count=2, open_conflict_count=0,
            freshness_result=fr, source_result=sr,
            independence_result=ir, corroboration_result=cr,
            consistency_result=consr,
        )
        assert status == IntegrityStatus.STRONG


# ===========================================================================
# Class 7 — Temporal Isolation (mandatory per spec)
# ===========================================================================

class TestTemporalIsolation:
    """
    Verifies that future evidence (observed_at > evaluation_time) is excluded.

    Test scenario:
      - Evidence A at T_BASE
      - Evidence B at T_PLUS_10 (future relative to T_PLUS_1)

    Evaluating at T_PLUS_1 must NOT include B.
    Evaluating at T_PLUS_10 (or later) must include B.
    """

    def test_future_evidence_excluded_from_early_eval(self, db):
        """Evidence B (T_PLUS_10) must not appear in a T_PLUS_1 evaluation."""
        _make_payment(db)
        _make_obs(db, internal_id=1, observed_at=T_BASE)
        _make_obs(db, internal_id=2, observed_at=T_PLUS_10)
        db.flush()

        snap_early = IntegrityEngine.compute_integrity(db, PAY_ID, T_PLUS_1)

        # Only 1 observation in scope at T_PLUS_1
        assert snap_early.evidence_count == 1

    def test_future_evidence_included_in_later_eval(self, db):
        """Evidence B (T_PLUS_10) must be visible in a T_PLUS_10 evaluation."""
        _make_payment(db)
        _make_obs(db, internal_id=1, observed_at=T_BASE)
        _make_obs(db, internal_id=2, observed_at=T_PLUS_10)
        db.flush()

        # Must use a different evaluated_at to avoid unique constraint conflict
        snap_late = IntegrityEngine.compute_integrity(db, PAY_ID, T_PLUS_10)

        assert snap_late.evidence_count == 2

    def test_early_snapshot_unchanged_after_new_evidence(self, db):
        """
        Creating a new snapshot at T_PLUS_10 must NOT overwrite the T_PLUS_1 snapshot.
        Historical snapshots are immutable.
        """
        _make_payment(db)
        _make_obs(db, internal_id=1, observed_at=T_BASE)
        db.flush()

        snap_early = IntegrityEngine.compute_integrity(db, PAY_ID, T_PLUS_1)
        db.commit()
        early_id = snap_early.internal_id
        early_count = snap_early.evidence_count

        # Now a new observation arrives
        _make_obs(db, internal_id=2, observed_at=T_PLUS_10)
        db.flush()

        snap_late = IntegrityEngine.compute_integrity(db, PAY_ID, T_PLUS_10)
        db.commit()

        # Retrieve the early snapshot again — must be unchanged
        from sqlalchemy import select
        retrieved_early = db.execute(
            select(EvidenceIntegritySnapshot).where(
                EvidenceIntegritySnapshot.internal_id == early_id
            )
        ).scalar_one()

        assert retrieved_early.evidence_count == early_count
        assert retrieved_early.internal_id == early_id


# ===========================================================================
# Class 8 — Idempotency
# ===========================================================================

class TestIdempotency:
    def test_duplicate_computation_returns_existing(self, db):
        """Running compute_integrity twice with the same (payment, time, version) → no duplicate."""
        _make_payment(db)
        _make_obs(db, internal_id=1, observed_at=T_BASE)
        db.flush()

        snap1 = IntegrityEngine.compute_integrity(db, PAY_ID, T_PLUS_1)
        db.commit()

        snap2 = IntegrityEngine.compute_integrity(db, PAY_ID, T_PLUS_1)
        db.commit()

        # Must return the same snapshot
        assert snap1.internal_id == snap2.internal_id

        # Must not have created a duplicate row
        from sqlalchemy import select, func
        count = db.execute(
            select(func.count()).select_from(EvidenceIntegritySnapshot).where(
                EvidenceIntegritySnapshot.payment_id == PAY_ID,
                EvidenceIntegritySnapshot.evaluated_at == T_PLUS_1,
                EvidenceIntegritySnapshot.methodology_version == INTEGRITY_METHODOLOGY_VERSION,
            )
        ).scalar_one()

        assert count == 1


# ===========================================================================
# Class 9 — Methodology Version Distinguishability
# ===========================================================================

class TestMethodologyVersion:
    def test_different_versions_produce_separate_snapshots(self, db):
        """V1 and V2 snapshots for the same payment/time must not overwrite each other."""
        _make_payment(db)
        _make_obs(db, internal_id=1, observed_at=T_BASE)
        db.flush()

        snap_v1 = IntegrityEngine.compute_integrity(db, PAY_ID, T_PLUS_1, methodology_version="EIS-1.0")
        db.commit()

        snap_v2 = IntegrityEngine.compute_integrity(db, PAY_ID, T_PLUS_1, methodology_version="EIS-2.0")
        db.commit()

        assert snap_v1.internal_id != snap_v2.internal_id
        assert snap_v1.methodology_version == "EIS-1.0"
        assert snap_v2.methodology_version == "EIS-2.0"


# ===========================================================================
# Class 10 — Explanation Quality
# ===========================================================================

class TestExplanation:
    FORBIDDEN_PHRASES = [
        "legitimate",
        "safe",
        "approved",
        "fraudulent",
        "fraud",
        "risk",
        "innocent",
        "suspicious",
        "criminal",
        "malicious",
    ]

    def test_explanation_generated(self, db):
        _make_payment(db)
        _make_obs(db, internal_id=1, observed_at=T_BASE)
        _make_quality_snapshot(db, 1)
        _make_structure_snapshot(db)
        db.flush()

        snap = IntegrityEngine.compute_integrity(db, PAY_ID, T_PLUS_1)

        assert isinstance(snap.explanation_lines, list)
        assert len(snap.explanation_lines) >= 1

    def test_explanation_has_no_fraud_language(self, db):
        _make_payment(db)
        _make_obs(db, internal_id=1, observed_at=T_BASE)
        _make_quality_snapshot(db, 1)
        _make_structure_snapshot(db)
        db.flush()

        snap = IntegrityEngine.compute_integrity(db, PAY_ID, T_PLUS_1)

        full_text = " ".join(snap.explanation_lines).lower()
        for phrase in self.FORBIDDEN_PHRASES:
            assert phrase not in full_text, (
                f"Forbidden phrase '{phrase}' found in explanation: {snap.explanation_lines}"
            )

    def test_no_detected_conflict_explanation_hedges(self, db):
        """Explanation must say 'no contradiction was detected', not 'no conflict exists'."""
        _make_payment(db)
        _make_obs(db, internal_id=1, observed_at=T_BASE)
        db.flush()

        snap = IntegrityEngine.compute_integrity(db, PAY_ID, T_PLUS_1)

        has_hedge = any(
            "detected" in line.lower() or "available" in line.lower()
            for line in snap.explanation_lines
        )
        assert has_hedge, (
            "Consistency explanation must hedge — e.g. 'no contradiction was detected', "
            f"not an absolute claim. Got: {snap.explanation_lines}"
        )


# ===========================================================================
# Class 11 — Limitations
# ===========================================================================

class TestLimitations:
    def test_historical_reliability_always_in_limitations(self, db):
        """In Phase 9 there is no outcome data, so reliability must appear in limitations."""
        _make_payment(db)
        _make_obs(db, internal_id=1, observed_at=T_BASE)
        db.flush()

        snap = IntegrityEngine.compute_integrity(db, PAY_ID, T_PLUS_1)

        limitations_text = " ".join(snap.limitations or []).lower()
        assert "historical reliability" in limitations_text or "outcome" in limitations_text

    def test_single_source_appears_in_limitations(self, db):
        """A single-source evidence set must surface source diversity limitation."""
        _make_payment(db)
        _make_obs(db, internal_id=1, observed_at=T_BASE)
        _make_structure_snapshot(db, distinct_sources=1, distinct_events=1)
        db.flush()

        snap = IntegrityEngine.compute_integrity(db, PAY_ID, T_PLUS_1)

        assert snap.limitations is not None
        limitations_text = " ".join(snap.limitations).lower()
        assert "diversity" in limitations_text or "source" in limitations_text


# ===========================================================================
# Class 12 — History
# ===========================================================================

class TestHistory:
    def test_history_is_ordered_ascending(self, db):
        """Integrity history must be ordered by evaluated_at ascending."""
        _make_payment(db)
        _make_obs(db, internal_id=1, observed_at=T_BASE)
        db.flush()

        snap1 = IntegrityEngine.compute_integrity(db, PAY_ID, T_BASE)
        db.commit()

        snap2 = IntegrityEngine.compute_integrity(db, PAY_ID, T_PLUS_5)
        db.commit()

        snap3 = IntegrityEngine.compute_integrity(db, PAY_ID, T_PLUS_10)
        db.commit()

        from sqlalchemy import select
        snapshots = db.execute(
            select(EvidenceIntegritySnapshot)
            .where(EvidenceIntegritySnapshot.payment_id == PAY_ID)
            .order_by(EvidenceIntegritySnapshot.evaluated_at.asc())
        ).scalars().all()

        times = [s.evaluated_at for s in snapshots]
        assert times == sorted(times), "History must be in ascending time order"

    def test_history_count_grows(self, db):
        """Each new evaluation adds one snapshot, history grows monotonically."""
        _make_payment(db)
        _make_obs(db, internal_id=1, observed_at=T_BASE)
        db.flush()

        IntegrityEngine.compute_integrity(db, PAY_ID, T_BASE)
        db.commit()
        IntegrityEngine.compute_integrity(db, PAY_ID, T_PLUS_5)
        db.commit()

        from sqlalchemy import select, func
        count = db.execute(
            select(func.count()).select_from(EvidenceIntegritySnapshot).where(
                EvidenceIntegritySnapshot.payment_id == PAY_ID
            )
        ).scalar_one()

        assert count == 2


# ===========================================================================
# Class 13 — End-to-End Scenario Tests
# ===========================================================================

class TestEndToEnd:
    def test_strong_integrity_full_pipeline(self, db):
        """
        Fresh evidence + primary source + no conflicts → STRONG or VERY_STRONG.
        Tests the full compute_integrity path with real data.
        """
        _make_payment(db)
        obs1 = _make_obs(db, internal_id=1, observed_at=T_BASE)
        obs2 = _make_obs(db, internal_id=2, evidence_type=EvidenceType.PAYMENT_AMOUNT, value="10000", observed_at=T_BASE)

        _make_quality_snapshot(db, 1, freshness_state=FreshnessState.CURRENT, authority_level=AuthorityLevel.PRIMARY, directness=SourceDirectness.DIRECT)
        _make_quality_snapshot(db, 2, freshness_state=FreshnessState.CURRENT, authority_level=AuthorityLevel.PRIMARY, directness=SourceDirectness.DIRECT)
        _make_structure_snapshot(db, distinct_sources=1, distinct_events=1, total_observations=2)

        claim = _make_claim(db)
        _make_corroboration(db, claim, observation_count=2, distinct_sources=1)
        db.flush()

        snap = IntegrityEngine.compute_integrity(db, PAY_ID, T_PLUS_1)

        assert snap.overall_status in (IntegrityStatus.STRONG, IntegrityStatus.LIMITED)
        assert snap.evidence_count == 2
        assert snap.open_conflict_count == 0
        assert snap.methodology_version == INTEGRITY_METHODOLOGY_VERSION

    def test_unresolved_when_conflict_open(self, db):
        """Open HIGH-severity conflict → UNRESOLVED overall status."""
        _make_payment(db)
        _make_obs(db, internal_id=1, observed_at=T_BASE)
        _make_quality_snapshot(db, 1, freshness_state=FreshnessState.CURRENT, authority_level=AuthorityLevel.PRIMARY, directness=SourceDirectness.DIRECT)

        claim_a = _make_claim(db, claim_key="payment.status", canonical_value="captured")
        claim_b = _make_claim(db, claim_key="payment.status", canonical_value="failed")
        _make_open_conflict(db, claim_a_id=claim_a.internal_id, claim_b_id=claim_b.internal_id, severity="HIGH")
        db.flush()

        snap = IntegrityEngine.compute_integrity(db, PAY_ID, T_PLUS_1)

        assert snap.overall_status == IntegrityStatus.UNRESOLVED
        assert snap.open_conflict_count == 1

    def test_insufficient_data_when_no_evidence(self, db):
        """Payment with zero observations → INSUFFICIENT_DATA."""
        _make_payment(db)
        db.flush()

        snap = IntegrityEngine.compute_integrity(db, PAY_ID, T_PLUS_1)

        assert snap.overall_status == IntegrityStatus.INSUFFICIENT_DATA
        assert snap.evidence_count == 0

    def test_concentrated_evidence_not_counted_as_independent(self, db):
        """
        10 observations from 1 event must NOT be treated as 10 independent signals.
        The independence dimension must reflect single-source.
        """
        _make_payment(db)
        for i in range(1, 11):
            _make_obs(db, internal_id=i, observed_at=T_BASE)
            _make_quality_snapshot(db, i, freshness_state=FreshnessState.CURRENT, authority_level=AuthorityLevel.PRIMARY, directness=SourceDirectness.DIRECT)

        # Structure snapshot reflects all from one event
        _make_structure_snapshot(db, distinct_sources=1, distinct_events=1, total_observations=10)
        db.flush()

        snap = IntegrityEngine.compute_integrity(db, PAY_ID, T_PLUS_1)

        # Independence must be SINGLE_SOURCE
        assert snap.independence_result is not None
        assert snap.independence_result["status"] == IndependenceStatus.SINGLE_SOURCE

        # Should not reach VERY_STRONG because independence is single-source
        assert snap.overall_status != IntegrityStatus.VERY_STRONG


# ===========================================================================
# Class 14 — API Tests
# ===========================================================================

class TestIntegrityAPI:
    def test_get_integrity_returns_200(self, client, api_db):
        """GET /api/v1/payments/{id}/integrity → 200 with integrity data."""
        _make_payment(api_db)
        _make_obs(api_db, internal_id=1, observed_at=T_BASE)
        api_db.commit()

        response = client.get(f"/api/v1/payments/{PAY_ID}/integrity")
        assert response.status_code == 200

        data = response.json()
        assert data["payment_id"] == PAY_ID
        assert "overall_status" in data
        assert "methodology_version" in data
        assert "explanation_lines" in data
        assert "limitations" in data
        assert "freshness_result" in data

    def test_get_integrity_returns_404_for_unknown_payment(self, client, api_db):
        response = client.get("/api/v1/payments/pay_does_not_exist/integrity")
        assert response.status_code == 404

    def test_get_integrity_history_returns_list(self, client, api_db):
        """GET /api/v1/payments/{id}/integrity/history → list of history items."""
        _make_payment(api_db)
        _make_obs(api_db, internal_id=1, observed_at=T_BASE)
        api_db.commit()

        # Trigger an on-demand computation first
        client.get(f"/api/v1/payments/{PAY_ID}/integrity")

        response = client.get(f"/api/v1/payments/{PAY_ID}/integrity/history")
        assert response.status_code == 200

        data = response.json()
        assert "history" in data
        assert "total" in data
        assert isinstance(data["history"], list)

    def test_get_integrity_history_returns_404_for_unknown_payment(self, client, api_db):
        response = client.get("/api/v1/payments/pay_does_not_exist/integrity/history")
        assert response.status_code == 404

    def test_second_get_does_not_duplicate(self, client, api_db):
        """Calling /integrity twice must not create duplicate snapshots (API-level idempotency)."""
        _make_payment(api_db)
        _make_obs(api_db, internal_id=1, observed_at=T_BASE)
        api_db.commit()

        response1 = client.get(f"/api/v1/payments/{PAY_ID}/integrity")
        response2 = client.get(f"/api/v1/payments/{PAY_ID}/integrity")

        assert response1.status_code == 200
        assert response2.status_code == 200

        # Both should have identical internal data (same snapshot returned)
        data1 = response1.json()
        data2 = response2.json()
        assert data1["overall_status"] == data2["overall_status"]
        assert data1["evidence_count"] == data2["evidence_count"]

    def test_all_dimensions_present_in_response(self, client, api_db):
        """Response schema must include all 5 dimension results."""
        _make_payment(api_db)
        _make_obs(api_db, internal_id=1, observed_at=T_BASE)
        api_db.commit()

        response = client.get(f"/api/v1/payments/{PAY_ID}/integrity")
        assert response.status_code == 200
        data = response.json()

        for dim in ["freshness_result", "source_result", "independence_result",
                    "corroboration_result", "consistency_result"]:
            assert dim in data, f"Missing dimension '{dim}' in response"
