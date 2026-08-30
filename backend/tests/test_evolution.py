"""
Tests for Phase 11 — Evidence Temporal Evolution & Change Intelligence.

Coverage:
  - EvidenceStateSnapshotService.take_snapshot (creation, idempotency, field fidelity,
    precondition enforcement)
  - EvidenceChangeEngine.compare_snapshots (no diff, evidence diff, freshness diff,
    methodology diff)
  - EvidenceChangeEngine.detect_and_persist_changes (causality: time passage, new
    evidence, conflict created/resolved, methodology change, no change, idempotency)
  - Historical isolation (old snapshots are never mutated)
  - Evolution API endpoints (state-history, changes, 404, security field check)
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
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
from app.db.session import get_db

from fastapi import FastAPI as _FastAPI
from app.api.v1.evolution import router as _evolution_router

_test_app = _FastAPI()
_test_app.include_router(_evolution_router, prefix="/api/v1")

from app.models.payment import Payment
from app.models.evidence_integrity import EvidenceIntegritySnapshot
from app.models.evolution_models import EvidenceStateSnapshot, EvidenceStateChange
from app.models.evolution_types import (
    ChangeType,
    ChangeDimension,
    DirectCause,
    CausalityLevel,
)
from app.services.evolution_snapshot_service import EvidenceStateSnapshotService
from app.services.evolution_change_engine import EvidenceChangeEngine

# ---------------------------------------------------------------------------
# Time constants
# ---------------------------------------------------------------------------

T_BASE = datetime(2026, 8, 23, 10, 0, 0, tzinfo=timezone.utc)
T_PLUS_5 = T_BASE + timedelta(minutes=5)

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


# ---------------------------------------------------------------------------
# Helper factories
# ---------------------------------------------------------------------------

def _make_payment(db, payment_id="pay_evo_01"):
    p = Payment(
        razorpay_payment_id=payment_id,
        status="captured",
        amount_minor=10000,
        currency="INR",
    )
    db.add(p)
    db.flush()
    return p


def _make_integrity_snapshot(
    db,
    payment_id="pay_evo_01",
    evaluated_at=None,
    methodology="EIS-1.0",
    overall_status="STRONG",
    evidence_count=1,
    source_count=1,
    conflict_count=0,
    open_conflict_count=0,
    freshness_status="CURRENT",
    corroboration_status="SINGLE_OBSERVATION",
    independence_status="SINGLE_SOURCE",
    consistency_status="NO_DETECTED_CONFLICT",
):
    """Create an EvidenceIntegritySnapshot with dimension results as JSONB dicts."""
    snap = EvidenceIntegritySnapshot(
        payment_id=payment_id,
        evaluated_at=evaluated_at or T_BASE,
        methodology_version=methodology,
        overall_status=overall_status,
        evidence_count=evidence_count,
        source_count=source_count,
        conflict_count=conflict_count,
        open_conflict_count=open_conflict_count,
        freshness_result={"status": freshness_status, "reason": "test", "inputs": {}},
        source_result={"status": "STRONG", "reason": "test", "inputs": {}},
        independence_result={"status": independence_status, "reason": "test", "inputs": {}},
        corroboration_result={"status": corroboration_status, "reason": "test", "inputs": {}},
        consistency_result={"status": consistency_status, "reason": "test", "inputs": {}},
        explanation_lines=["test"],
        limitations=[],
    )
    db.add(snap)
    db.flush()
    return snap


def _make_state_snapshot(
    db,
    payment_id="pay_evo_01",
    evaluation_time=None,
    integrity_snapshot_id=None,
    overall_integrity_status="STRONG",
    evidence_count=1,
    source_count=1,
    claim_count=0,
    conflict_count=0,
    open_conflict_count=0,
    corroboration_status="SINGLE_OBSERVATION",
    independence_status="SINGLE_SOURCE",
    freshness_status="CURRENT",
    consistency_status="NO_DETECTED_CONFLICT",
    methodology_version="EIS-1.0",
):
    """Create an EvidenceStateSnapshot directly (without going through the service)."""
    # We need a valid integrity_snapshot_id FK — create a minimal one if not provided
    if integrity_snapshot_id is None:
        integ = _make_integrity_snapshot(
            db,
            payment_id=payment_id,
            evaluated_at=evaluation_time or T_BASE,
            methodology=methodology_version,
            overall_status=overall_integrity_status,
            evidence_count=evidence_count,
            source_count=source_count,
            conflict_count=conflict_count,
            open_conflict_count=open_conflict_count,
            freshness_status=freshness_status,
            corroboration_status=corroboration_status,
            independence_status=independence_status,
            consistency_status=consistency_status,
        )
        integrity_snapshot_id = integ.internal_id

    snap = EvidenceStateSnapshot(
        payment_id=payment_id,
        evaluation_time=evaluation_time or T_BASE,
        integrity_snapshot_id=integrity_snapshot_id,
        overall_integrity_status=overall_integrity_status,
        evidence_count=evidence_count,
        source_count=source_count,
        claim_count=claim_count,
        conflict_count=conflict_count,
        open_conflict_count=open_conflict_count,
        corroboration_status=corroboration_status,
        independence_status=independence_status,
        freshness_status=freshness_status,
        consistency_status=consistency_status,
        methodology_version=methodology_version,
    )
    db.add(snap)
    db.flush()
    return snap


# ===========================================================================
# Class 1 — Snapshot Service
# ===========================================================================

class TestSnapshotService:

    def test_1_new_snapshot_created_from_integrity_snapshot(self, db):
        """take_snapshot reads a Phase 9 snapshot and creates a correct state snapshot."""
        _make_payment(db)
        _make_integrity_snapshot(
            db,
            payment_id="pay_evo_01",
            evaluated_at=T_BASE,
            methodology="EIS-1.0",
            overall_status="STRONG",
            evidence_count=3,
        )
        db.flush()

        result = EvidenceStateSnapshotService.take_snapshot(
            db,
            payment_id="pay_evo_01",
            evaluation_time=T_BASE,
            methodology_version="EIS-1.0",
        )

        assert result.payment_id == "pay_evo_01"
        assert result.overall_integrity_status == "STRONG"
        assert result.evidence_count == 3
        assert result.methodology_version == "EIS-1.0"

    def test_2_snapshot_idempotency(self, db):
        """Calling take_snapshot twice returns the same row; no duplicate created."""
        _make_payment(db)
        _make_integrity_snapshot(db, evaluated_at=T_BASE)
        db.flush()

        snap1 = EvidenceStateSnapshotService.take_snapshot(
            db, "pay_evo_01", T_BASE, "EIS-1.0"
        )
        snap2 = EvidenceStateSnapshotService.take_snapshot(
            db, "pay_evo_01", T_BASE, "EIS-1.0"
        )

        assert snap1.internal_id == snap2.internal_id

        count = db.execute(
            select(func.count()).select_from(EvidenceStateSnapshot).where(
                EvidenceStateSnapshot.payment_id == "pay_evo_01",
                EvidenceStateSnapshot.evaluation_time == T_BASE,
                EvidenceStateSnapshot.methodology_version == "EIS-1.0",
            )
        ).scalar_one()
        assert count == 1

    def test_3_snapshot_field_fidelity(self, db):
        """All scalar fields are correctly projected from the integrity snapshot."""
        _make_payment(db)
        _make_integrity_snapshot(
            db,
            evaluated_at=T_BASE,
            overall_status="LIMITED",
            evidence_count=5,
            source_count=2,
            conflict_count=1,
            open_conflict_count=1,
            freshness_status="STALE",
            corroboration_status="PARTIALLY_CORROBORATED",
            independence_status="HIGH_SOURCE_DIVERSITY",
            consistency_status="HAS_OPEN_CONFLICTS",
        )
        db.flush()

        snap = EvidenceStateSnapshotService.take_snapshot(
            db, "pay_evo_01", T_BASE, "EIS-1.0"
        )

        assert snap.overall_integrity_status == "LIMITED"
        assert snap.evidence_count == 5
        assert snap.source_count == 2
        assert snap.conflict_count == 1
        assert snap.open_conflict_count == 1
        assert snap.freshness_status == "STALE"
        assert snap.corroboration_status == "PARTIALLY_CORROBORATED"
        assert snap.independence_status == "HIGH_SOURCE_DIVERSITY"
        assert snap.consistency_status == "HAS_OPEN_CONFLICTS"

    def test_4_snapshot_requires_integrity_snapshot(self, db):
        """take_snapshot raises ValueError when no Phase 9 snapshot exists."""
        _make_payment(db)
        # No integrity snapshot created — precondition not met.

        with pytest.raises(ValueError, match="No Phase 9 EvidenceIntegritySnapshot"):
            EvidenceStateSnapshotService.take_snapshot(
                db, "pay_evo_01", T_BASE, "EIS-1.0"
            )


# ===========================================================================
# Class 2 — Snapshot Comparison
# ===========================================================================

class TestSnapshotComparison:

    def test_5_compare_identical_snapshots_returns_empty(self, db):
        """Comparing a snapshot against an identical copy returns no diffs."""
        _make_payment(db)
        snap = _make_state_snapshot(db, payment_id="pay_evo_01", evaluation_time=T_BASE)
        db.flush()

        # Compare snapshot with itself — must produce no diffs.
        diffs = EvidenceChangeEngine.compare_snapshots(snap, snap)
        assert diffs == []

    def test_6_compare_evidence_count_change(self, db):
        """Increased evidence_count produces one EVIDENCE / NEW_EVIDENCE diff."""
        _make_payment(db)
        snap_a = _make_state_snapshot(
            db, payment_id="pay_evo_01", evaluation_time=T_BASE, evidence_count=1
        )
        snap_b = _make_state_snapshot(
            db, payment_id="pay_evo_01", evaluation_time=T_PLUS_5, evidence_count=3,
            methodology_version="EIS-1.0",
        )
        db.flush()

        diffs = EvidenceChangeEngine.compare_snapshots(snap_a, snap_b)

        evidence_diffs = [d for d in diffs if d["dimension"] == ChangeDimension.EVIDENCE]
        assert len(evidence_diffs) == 1
        assert evidence_diffs[0]["change_type"] == ChangeType.NEW_EVIDENCE

    def test_7_compare_freshness_change(self, db):
        """Freshness degradation produces a FRESHNESS / FRESHNESS_CHANGED diff."""
        _make_payment(db)
        snap_a = _make_state_snapshot(
            db, payment_id="pay_evo_01", evaluation_time=T_BASE, freshness_status="CURRENT"
        )
        snap_b = _make_state_snapshot(
            db, payment_id="pay_evo_01", evaluation_time=T_PLUS_5, freshness_status="STALE",
            methodology_version="EIS-1.0",
        )
        db.flush()

        diffs = EvidenceChangeEngine.compare_snapshots(snap_a, snap_b)

        freshness_diffs = [d for d in diffs if d["dimension"] == ChangeDimension.FRESHNESS]
        assert len(freshness_diffs) == 1
        assert freshness_diffs[0]["change_type"] == ChangeType.FRESHNESS_CHANGED

    def test_8_compare_methodology_change(self, db):
        """Different methodology versions produce a METHODOLOGY / METHODOLOGY_CHANGED diff."""
        _make_payment(db)

        # Build integrity snapshots for each methodology version separately
        _make_integrity_snapshot(db, evaluated_at=T_BASE, methodology="EIS-1.0")
        integ_b = _make_integrity_snapshot(db, evaluated_at=T_PLUS_5, methodology="EIS-2.0")

        snap_a = EvidenceStateSnapshot(
            payment_id="pay_evo_01",
            evaluation_time=T_BASE,
            integrity_snapshot_id=db.execute(
                select(EvidenceIntegritySnapshot).where(
                    EvidenceIntegritySnapshot.methodology_version == "EIS-1.0"
                )
            ).scalar_one().internal_id,
            overall_integrity_status="STRONG",
            evidence_count=1,
            source_count=1,
            claim_count=0,
            conflict_count=0,
            open_conflict_count=0,
            corroboration_status="SINGLE_OBSERVATION",
            independence_status="SINGLE_SOURCE",
            freshness_status="CURRENT",
            consistency_status="NO_DETECTED_CONFLICT",
            methodology_version="EIS-1.0",
        )
        snap_b = EvidenceStateSnapshot(
            payment_id="pay_evo_01",
            evaluation_time=T_PLUS_5,
            integrity_snapshot_id=integ_b.internal_id,
            overall_integrity_status="STRONG",
            evidence_count=1,
            source_count=1,
            claim_count=0,
            conflict_count=0,
            open_conflict_count=0,
            corroboration_status="SINGLE_OBSERVATION",
            independence_status="SINGLE_SOURCE",
            freshness_status="CURRENT",
            consistency_status="NO_DETECTED_CONFLICT",
            methodology_version="EIS-2.0",
        )
        db.add(snap_a)
        db.add(snap_b)
        db.flush()

        diffs = EvidenceChangeEngine.compare_snapshots(snap_a, snap_b)

        methodology_diffs = [d for d in diffs if d["dimension"] == ChangeDimension.METHODOLOGY]
        assert len(methodology_diffs) == 1
        assert methodology_diffs[0]["change_type"] == ChangeType.METHODOLOGY_CHANGED


# ===========================================================================
# Class 3 — Change Engine
# ===========================================================================

class TestChangeEngine:

    def test_9_time_passage_causality(self, db):
        """Freshness degradation without new evidence → TIME_PASSAGE / DIRECT."""
        _make_payment(db)
        snap_a = _make_state_snapshot(
            db, payment_id="pay_evo_01", evaluation_time=T_BASE,
            evidence_count=2, freshness_status="CURRENT",
        )
        snap_b = _make_state_snapshot(
            db, payment_id="pay_evo_01", evaluation_time=T_PLUS_5,
            evidence_count=2, freshness_status="STALE",
        )
        db.flush()

        changes = EvidenceChangeEngine.detect_and_persist_changes(
            db, "pay_evo_01", snap_a, snap_b
        )

        freshness_changes = [
            c for c in changes if c.dimension == ChangeDimension.FRESHNESS
        ]
        assert len(freshness_changes) == 1
        fc = freshness_changes[0]
        assert fc.direct_cause == DirectCause.TIME_PASSAGE
        assert fc.causality == CausalityLevel.DIRECT
        assert fc.explanation is not None
        assert "aging" in fc.explanation.lower()

    def test_10_new_evidence_causality(self, db):
        """Increased evidence_count → NEW_EVIDENCE / DIRECT."""
        _make_payment(db)
        snap_a = _make_state_snapshot(
            db, payment_id="pay_evo_01", evaluation_time=T_BASE, evidence_count=1
        )
        snap_b = _make_state_snapshot(
            db, payment_id="pay_evo_01", evaluation_time=T_PLUS_5, evidence_count=3
        )
        db.flush()

        changes = EvidenceChangeEngine.detect_and_persist_changes(
            db, "pay_evo_01", snap_a, snap_b
        )

        evidence_changes = [
            c for c in changes if c.dimension == ChangeDimension.EVIDENCE
        ]
        assert len(evidence_changes) >= 1
        ec = evidence_changes[0]
        assert ec.direct_cause == DirectCause.NEW_EVIDENCE
        assert ec.causality == CausalityLevel.DIRECT

    def test_11_conflict_created(self, db):
        """New open conflict → CONFLICT_CREATED / CONFLICT / DIRECT."""
        _make_payment(db)
        snap_a = _make_state_snapshot(
            db, payment_id="pay_evo_01", evaluation_time=T_BASE,
            open_conflict_count=0, consistency_status="NO_DETECTED_CONFLICT",
        )
        snap_b = _make_state_snapshot(
            db, payment_id="pay_evo_01", evaluation_time=T_PLUS_5,
            open_conflict_count=1, consistency_status="HAS_OPEN_CONFLICTS",
            conflict_count=1,
        )
        db.flush()

        changes = EvidenceChangeEngine.detect_and_persist_changes(
            db, "pay_evo_01", snap_a, snap_b
        )

        consistency_changes = [
            c for c in changes if c.dimension == ChangeDimension.CONSISTENCY
        ]
        assert len(consistency_changes) == 1
        cc = consistency_changes[0]
        assert cc.change_type == ChangeType.CONFLICT_CREATED
        assert cc.direct_cause == DirectCause.CONFLICT

    def test_12_conflict_resolved(self, db):
        """Resolved open conflict → CONFLICT_RESOLVED / CONFLICT_RESOLUTION / DIRECT."""
        _make_payment(db)
        snap_a = _make_state_snapshot(
            db, payment_id="pay_evo_01", evaluation_time=T_BASE,
            open_conflict_count=1, consistency_status="HAS_OPEN_CONFLICTS",
            conflict_count=1,
        )
        snap_b = _make_state_snapshot(
            db, payment_id="pay_evo_01", evaluation_time=T_PLUS_5,
            open_conflict_count=0, consistency_status="NO_DETECTED_CONFLICT",
        )
        db.flush()

        changes = EvidenceChangeEngine.detect_and_persist_changes(
            db, "pay_evo_01", snap_a, snap_b
        )

        consistency_changes = [
            c for c in changes if c.dimension == ChangeDimension.CONSISTENCY
        ]
        assert len(consistency_changes) == 1
        cc = consistency_changes[0]
        assert cc.change_type == ChangeType.CONFLICT_RESOLVED
        assert cc.direct_cause == DirectCause.CONFLICT_RESOLUTION

    def test_13_methodology_change_detection(self, db):
        """Methodology version change → METHODOLOGY_CHANGED / METHODOLOGY_CHANGE / DIRECT."""
        _make_payment(db)

        _make_integrity_snapshot(db, evaluated_at=T_BASE, methodology="EIS-1.0")
        integ_b = _make_integrity_snapshot(db, evaluated_at=T_PLUS_5, methodology="EIS-2.0")

        snap_a = EvidenceStateSnapshot(
            payment_id="pay_evo_01",
            evaluation_time=T_BASE,
            integrity_snapshot_id=db.execute(
                select(EvidenceIntegritySnapshot).where(
                    EvidenceIntegritySnapshot.methodology_version == "EIS-1.0"
                )
            ).scalar_one().internal_id,
            overall_integrity_status="STRONG",
            evidence_count=1,
            source_count=1,
            claim_count=0,
            conflict_count=0,
            open_conflict_count=0,
            corroboration_status="SINGLE_OBSERVATION",
            independence_status="SINGLE_SOURCE",
            freshness_status="CURRENT",
            consistency_status="NO_DETECTED_CONFLICT",
            methodology_version="EIS-1.0",
        )
        snap_b = EvidenceStateSnapshot(
            payment_id="pay_evo_01",
            evaluation_time=T_PLUS_5,
            integrity_snapshot_id=integ_b.internal_id,
            overall_integrity_status="STRONG",
            evidence_count=1,
            source_count=1,
            claim_count=0,
            conflict_count=0,
            open_conflict_count=0,
            corroboration_status="SINGLE_OBSERVATION",
            independence_status="SINGLE_SOURCE",
            freshness_status="CURRENT",
            consistency_status="NO_DETECTED_CONFLICT",
            methodology_version="EIS-2.0",
        )
        db.add(snap_a)
        db.add(snap_b)
        db.flush()

        changes = EvidenceChangeEngine.detect_and_persist_changes(
            db, "pay_evo_01", snap_a, snap_b
        )

        methodology_changes = [
            c for c in changes if c.dimension == ChangeDimension.METHODOLOGY
        ]
        assert len(methodology_changes) == 1
        mc = methodology_changes[0]
        assert mc.change_type == ChangeType.METHODOLOGY_CHANGED
        assert mc.direct_cause == DirectCause.METHODOLOGY_CHANGE
        assert mc.causality == CausalityLevel.DIRECT

    def test_14_no_material_change(self, db):
        """Identical snapshots produce zero change records."""
        _make_payment(db)
        snap_a = _make_state_snapshot(
            db, payment_id="pay_evo_01", evaluation_time=T_BASE
        )
        snap_b = _make_state_snapshot(
            db, payment_id="pay_evo_01", evaluation_time=T_PLUS_5
        )
        # All fields identical except evaluation_time — no dimension differs.
        db.flush()

        changes = EvidenceChangeEngine.detect_and_persist_changes(
            db, "pay_evo_01", snap_a, snap_b
        )

        assert changes == []

        count = db.execute(
            select(func.count()).select_from(EvidenceStateChange).where(
                EvidenceStateChange.payment_id == "pay_evo_01"
            )
        ).scalar_one()
        assert count == 0

    def test_15_idempotency_no_duplicate_changes(self, db):
        """Calling detect_and_persist_changes twice with the same pair produces no duplicates."""
        _make_payment(db)
        snap_a = _make_state_snapshot(
            db, payment_id="pay_evo_01", evaluation_time=T_BASE, evidence_count=1
        )
        snap_b = _make_state_snapshot(
            db, payment_id="pay_evo_01", evaluation_time=T_PLUS_5, evidence_count=2
        )
        db.flush()

        EvidenceChangeEngine.detect_and_persist_changes(
            db, "pay_evo_01", snap_a, snap_b
        )
        db.commit()
        count_after_first = db.execute(
            select(func.count()).select_from(EvidenceStateChange).where(
                EvidenceStateChange.payment_id == "pay_evo_01"
            )
        ).scalar_one()

        EvidenceChangeEngine.detect_and_persist_changes(
            db, "pay_evo_01", snap_a, snap_b
        )
        db.commit()
        count_after_second = db.execute(
            select(func.count()).select_from(EvidenceStateChange).where(
                EvidenceStateChange.payment_id == "pay_evo_01"
            )
        ).scalar_one()

        assert count_after_first == count_after_second


# ===========================================================================
# Class 4 — Historical Isolation
# ===========================================================================

class TestHistoricalIsolation:

    def test_16_old_snapshots_not_modified(self, db):
        """Running change detection must not mutate the earlier snapshot."""
        _make_payment(db)

        # Snapshot S1 at T_BASE
        snap_s1 = _make_state_snapshot(
            db, payment_id="pay_evo_01", evaluation_time=T_BASE,
            evidence_count=1, freshness_status="CURRENT",
            overall_integrity_status="STRONG",
        )
        db.commit()

        # Capture original field values before change detection
        s1_id = snap_s1.internal_id
        s1_evidence_count = snap_s1.evidence_count
        s1_freshness = snap_s1.freshness_status
        s1_overall = snap_s1.overall_integrity_status
        s1_evaluation_time = snap_s1.evaluation_time

        # Snapshot S2 at T_PLUS_5 with different values
        snap_s2 = _make_state_snapshot(
            db, payment_id="pay_evo_01", evaluation_time=T_PLUS_5,
            evidence_count=3, freshness_status="STALE",
            overall_integrity_status="LIMITED",
        )
        db.flush()

        # Run change detection S1 → S2
        EvidenceChangeEngine.detect_and_persist_changes(
            db, "pay_evo_01", snap_s1, snap_s2
        )
        db.commit()

        # Reload S1 from DB and verify all original values are unchanged
        retrieved_s1 = db.execute(
            select(EvidenceStateSnapshot).where(
                EvidenceStateSnapshot.internal_id == s1_id
            )
        ).scalar_one()

        assert retrieved_s1.evidence_count == s1_evidence_count
        assert retrieved_s1.freshness_status == s1_freshness
        assert retrieved_s1.overall_integrity_status == s1_overall
        assert retrieved_s1.evaluation_time == s1_evaluation_time


# ===========================================================================
# Class 5 — Evolution API
# ===========================================================================

class TestEvolutionAPI:

    def test_17_api_state_history(self, api_db, client):
        """GET /payments/{id}/state-history returns 200 with snapshots ordered by time."""
        _make_payment(api_db, payment_id="pay_evo_api_01")

        # Two integrity snapshots at different times
        _make_integrity_snapshot(
            api_db, payment_id="pay_evo_api_01", evaluated_at=T_BASE,
        )
        _make_integrity_snapshot(
            api_db, payment_id="pay_evo_api_01", evaluated_at=T_PLUS_5,
        )
        api_db.flush()

        # Two state snapshots via service
        EvidenceStateSnapshotService.take_snapshot(
            api_db, "pay_evo_api_01", T_BASE, "EIS-1.0"
        )
        EvidenceStateSnapshotService.take_snapshot(
            api_db, "pay_evo_api_01", T_PLUS_5, "EIS-1.0"
        )
        api_db.commit()

        response = client.get("/api/v1/payments/pay_evo_api_01/state-history")
        assert response.status_code == 200

        data = response.json()
        assert data["payment_id"] == "pay_evo_api_01"
        assert data["total"] == 2
        history = data["history"]
        assert len(history) == 2

        # Ordered by evaluation_time ascending
        t0 = history[0]["evaluation_time"]
        t1 = history[1]["evaluation_time"]
        assert t0 < t1

    def test_18_api_changes(self, api_db, client):
        """GET /payments/{id}/changes returns 200 with at least 1 change after diff."""
        _make_payment(api_db, payment_id="pay_evo_api_02")

        _make_integrity_snapshot(
            api_db, payment_id="pay_evo_api_02", evaluated_at=T_BASE, evidence_count=1
        )
        _make_integrity_snapshot(
            api_db, payment_id="pay_evo_api_02", evaluated_at=T_PLUS_5, evidence_count=3
        )
        api_db.flush()

        snap_a = EvidenceStateSnapshotService.take_snapshot(
            api_db, "pay_evo_api_02", T_BASE, "EIS-1.0"
        )
        snap_b = EvidenceStateSnapshotService.take_snapshot(
            api_db, "pay_evo_api_02", T_PLUS_5, "EIS-1.0"
        )
        api_db.flush()

        EvidenceChangeEngine.detect_and_persist_changes(
            api_db, "pay_evo_api_02", snap_a, snap_b
        )
        api_db.commit()

        response = client.get("/api/v1/payments/pay_evo_api_02/changes")
        assert response.status_code == 200

        data = response.json()
        assert data["total"] >= 1

        change_types = [c["change_type"] for c in data["changes"]]
        assert ChangeType.NEW_EVIDENCE in change_types

    def test_19_api_404_for_unknown_payment(self, api_db, client):
        """GET /payments/{unknown}/changes returns 404."""
        response = client.get("/api/v1/payments/pay_unknown_xyz/changes")
        assert response.status_code == 404

    def test_20_security_no_forbidden_fields(self, api_db, client):
        """GET /changes/{change_id} must not expose any sensitive field names in JSON."""
        _make_payment(api_db, payment_id="pay_evo_api_03")

        _make_integrity_snapshot(
            api_db, payment_id="pay_evo_api_03", evaluated_at=T_BASE, evidence_count=1
        )
        _make_integrity_snapshot(
            api_db, payment_id="pay_evo_api_03", evaluated_at=T_PLUS_5, evidence_count=2
        )
        api_db.flush()

        snap_a = EvidenceStateSnapshotService.take_snapshot(
            api_db, "pay_evo_api_03", T_BASE, "EIS-1.0"
        )
        snap_b = EvidenceStateSnapshotService.take_snapshot(
            api_db, "pay_evo_api_03", T_PLUS_5, "EIS-1.0"
        )
        api_db.flush()

        changes = EvidenceChangeEngine.detect_and_persist_changes(
            api_db, "pay_evo_api_03", snap_a, snap_b
        )
        api_db.commit()
        assert len(changes) >= 1

        change_id = changes[0].change_id
        response = client.get(f"/api/v1/changes/{change_id}")
        assert response.status_code == 200

        # Dump the entire response as lowercased text and check for forbidden keys
        response_text = response.text.lower()
        forbidden_fields = [
            "raw_payload",
            "webhook_secret",
            "api_key",
            "secret",
            "cvv",
            "otp",
            "password",
            "token",
            "credentials",
        ]
        for field in forbidden_fields:
            assert field not in response_text, (
                f"Forbidden field '{field}' found in /changes/{change_id} response"
            )
