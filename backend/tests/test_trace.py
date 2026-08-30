"""
Tests for Phase 10 — Evidence Integrity Decision Trace & Cryptographic Auditability.

Coverage:
  - Canonical serialization determinism (CG-1.0)
  - SHA-256 hashing: stability, sensitivity, algorithm recording
  - Trace lifecycle: STARTED → COMPLETED / FAILED with ordered audit events
  - Evidence inclusion/exclusion recording (temporal + scope + invalidation)
  - Rule execution traces reflect the ACTUAL computation path
  - Methodology snapshot preservation
  - Hash verification (VALID / INVALID / VERIFICATION_UNAVAILABLE / NOT_FOUND)
  - Per-payment hash chain (valid, broken, start, replay exclusion)
  - Immutability: no update path; new evaluations create NEW traces
  - Idempotency: one COMPLETED EVALUATION trace per identity tuple
  - Replay: MATCH on unchanged world; MISMATCH categories; original untouched
  - Failure traces: auditable, never masquerade as completed
  - Security: authorization tiers, no secrets/raw payloads, no mutation APIs
  - Temporal leakage: future evidence cannot appear in historical traces
"""

from __future__ import annotations

import time
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
from app.main import app
from app.db.session import get_db
from app.models.evidence import EvidenceObservation
from app.models.evidence_conflict import EvidenceConflict
from app.models.evidence_integrity import EvidenceIntegritySnapshot
from app.models.evidence_quality import EvidenceQualitySnapshot
from app.models.evidence_structure import (
    Claim,
    EvidenceCorroboration,
    EvidenceStructureSnapshot,
)
from app.models.evidence_types import EvidenceType, SourceType, ValueType
from app.models.integrity_trace import EvidenceIntegrityTrace, IntegrityTraceEvent
from app.models.payment import Payment
from app.models.quality_types import (
    AuthorityLevel,
    FreshnessState,
    HistoricalReliabilityStatus,
    SourceDirectness,
)
from app.models.trace_types import (
    CANONICALIZATION_VERSION,
    HASH_ALGORITHM,
    TRACE_SCHEMA_VERSION,
    ExclusionReason,
    TraceEventType,
    TraceStatus,
    TraceType,
)
from app.services.replay_service import ReplayNotPossibleError, ReplayService
from app.services.integrity_trace_service import IntegrityTraceService
from app.services.trace_canonicalization import (
    CanonicalizationError,
    canonical_hash,
    canonical_json,
    canonicalize,
    methodology_snapshot_hash,
)
from app.services.trace_verification import TraceVerificationService

ADMIN_KEY = "test-admin-key-12345"
ADMIN_HEADERS = {"X-API-Key": ADMIN_KEY}

T_BASE = datetime(2026, 8, 23, 10, 0, 0, tzinfo=timezone.utc)
T_PLUS_1 = T_BASE + timedelta(minutes=1)
T_PLUS_5 = T_BASE + timedelta(minutes=5)
T_PLUS_10 = T_BASE + timedelta(minutes=10)

PAY_ID = "pay_trace_test_01"


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

    app.dependency_overrides[get_db] = override_get_db
    seed_session = Session()
    try:
        yield seed_session
    finally:
        seed_session.close()
        app.dependency_overrides.clear()


@pytest.fixture
def client(api_db):
    return TestClient(app)


# ---------------------------------------------------------------------------
# Helper factories (mirror Phase 9 test patterns)
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
    observed_at: datetime | None = None,
    valid_until: datetime | None = None,
    subject_type: str = "payment",
    subject_id: str | None = None,
) -> EvidenceObservation:
    obs = EvidenceObservation(
        internal_id=internal_id,
        evidence_type=evidence_type,
        subject_type=subject_type,
        subject_id=subject_id or payment_id,
        value=value,
        value_type=ValueType.STRING,
        source_type=source_type,
        source_reference="test_ref",
        extraction_method="TEST",
        extraction_version="1.0",
        observed_at=observed_at or T_BASE,
        valid_until=valid_until,
        payment_event_id=1,
        webhook_event_id=1,
    )
    db.add(obs)
    db.flush()
    return obs


def _make_quality_snapshot(db, evidence_id: int, evaluated_at=None) -> EvidenceQualitySnapshot:
    snap = EvidenceQualitySnapshot(
        evidence_id=evidence_id,
        evaluated_at=evaluated_at or T_BASE,
        age_seconds=60.0,
        freshness_state=FreshnessState.CURRENT,
        freshness_policy_key="DEFAULT",
        freshness_methodology_version="1.0",
        source_type=SourceType.RAZORPAY_WEBHOOK,
        source_directness=SourceDirectness.DIRECT,
        source_authority_level=AuthorityLevel.PRIMARY,
        source_methodology_version="1.0",
        historical_reliability_status=HistoricalReliabilityStatus.NO_OUTCOME_DATA,
        reliability_methodology_version="1.0",
    )
    db.add(snap)
    db.flush()
    return snap


def _make_structure_snapshot(db, payment_id=PAY_ID, evaluated_at=None, **kw) -> EvidenceStructureSnapshot:
    snap = EvidenceStructureSnapshot(
        payment_id=payment_id,
        evaluated_at=evaluated_at or T_BASE,
        total_observations=kw.get("total_observations", 2),
        distinct_claims=1,
        distinct_sources=kw.get("distinct_sources", 1),
        distinct_events=kw.get("distinct_events", 1),
        distinct_groups=kw.get("distinct_groups", 1),
        largest_group_size=2,
        group_hhi=1.0,
    )
    db.add(snap)
    db.flush()
    return snap


def _make_corroboration(db, claim, observation_count=2, distinct_sources=2):
    corr = EvidenceCorroboration(
        claim_id=claim.internal_id,
        payment_id=PAY_ID,
        corroboration_type="SAME_CLAIM",
        independence_status="MULTI_SOURCE",
        observation_count=observation_count,
        distinct_sources_count=distinct_sources,
        distinct_events_count=1,
    )
    db.add(corr)
    db.flush()
    return corr


def _seed_rich_world(db, payment_id: str = PAY_ID):
    """A realistic evidence world producing a STRONG/VERY_STRONG evaluation."""
    _make_payment(db, payment_id)
    _make_obs(db, 1, payment_id, observed_at=T_BASE)
    _make_obs(
        db, 2, payment_id,
        evidence_type=EvidenceType.PAYMENT_AMOUNT, value="10000", observed_at=T_BASE,
    )
    _make_quality_snapshot(db, 1)
    _make_quality_snapshot(db, 2)
    _make_structure_snapshot(db, payment_id, distinct_sources=2, distinct_events=2)
    claim = Claim(
        subject_type="payment",
        subject_id=payment_id,
        claim_type="PAYMENT_STATUS",
        claim_key="STATUS",
        canonical_value="captured",
        created_at=T_BASE,
    )
    db.add(claim)
    db.flush()
    _make_corroboration(db, claim)
    return claim


# ===========================================================================
# Class 1 — Canonical serialization (CG-1.0)
# ===========================================================================

class TestCanonicalSerialization:
    def test_key_order_is_sorted_regardless_of_input(self):
        a = {"b": 1, "a": {"z": 1, "y": 2}}
        b = {"a": {"y": 2, "z": 1}, "b": 1}
        assert canonical_json(a) == canonical_json(b)

    def test_same_content_same_bytes(self):
        payload = {"x": [3, 1, 2], "t": T_BASE, "n": None}
        assert canonical_json(payload) == canonical_json(
            {"n": None, "t": T_BASE.replace(tzinfo=timezone.utc), "x": [3, 1, 2]}
        )

    def test_datetime_rendering_deterministic_utc(self):
        ist = timezone(timedelta(hours=5, minutes=30))
        dt_local = T_BASE.astimezone(ist)
        assert '"2026-08-23T10:00:00.000000Z"' in canonical_json({"t": dt_local})

    def test_integral_floats_normalized(self):
        assert canonical_json({"v": 2.0}) == '{"v":2}'

    def test_non_finite_float_rejected(self):
        with pytest.raises(CanonicalizationError):
            canonical_json({"v": float("nan")})
        with pytest.raises(CanonicalizationError):
            canonical_json({"v": float("inf")})

    def test_nulls_preserved_explicitly(self):
        assert canonical_json({"k": None}) == '{"k":null}'

    def test_unicode_deterministic(self):
        text = canonical_json({"s": "₹ amount ✓"})
        assert text == canonical_json({"s": "₹ amount ✓"})
        assert "\\u20b9" in text  # ensure_ascii escaping

    def test_canonicalization_is_idempotent_for_storage_roundtrip(self):
        raw = {"t": T_BASE, "f": 0.5, "i": 7}
        once = canonicalize(raw)
        twice = canonicalize(once)
        assert once == twice
        assert canonical_json(once) == canonical_json(twice)


# ===========================================================================
# Class 2 — Trace hashing fundamentals
# ===========================================================================

class TestTraceHashing:
    def test_same_logical_content_same_digest(self):
        _, h1 = canonical_hash({"a": 1, "b": [T_BASE]})
        _, h2 = canonical_hash({"b": [T_BASE], "a": 1})
        assert h1 == h2 and len(h1) == 64

    def test_different_content_different_digest(self):
        _, h1 = canonical_hash({"result": "STRONG"})
        _, h2 = canonical_hash({"result": "LIMITED"})
        assert h1 != h2

    def test_methodology_snapshot_hash_deterministic(self):
        from app.models.integrity_methodology import EIS_V1

        assert (
            methodology_snapshot_hash(EIS_V1.describe())
            == methodology_snapshot_hash(EIS_V1.describe())
        )


# ===========================================================================
# Class 3 — Trace lifecycle & content completeness
# ===========================================================================

class TestTraceLifecycle:
    def test_record_evaluation_creates_completed_trace(self, db):
        _seed_rich_world(db)
        trace = IntegrityTraceService.record_evaluation(
            db, PAY_ID, T_PLUS_1, trigger="WEBHOOK_PROCESSING"
        )
        db.commit()

        assert trace is not None
        assert trace.status == TraceStatus.COMPLETED
        assert trace.trace_type == TraceType.EVALUATION
        assert len(trace.trace_id) == 36
        assert trace.overall_status in ("VERY_STRONG", "STRONG")
        assert trace.trace_hash and len(trace.trace_hash) == 64
        assert trace.hash_algorithm == HASH_ALGORITHM == "SHA-256"
        assert trace.canonicalization_version == CANONICALIZATION_VERSION
        assert trace.finalized_at is not None

    def test_unique_trace_ids_across_evaluations(self, db):
        _seed_rich_world(db)
        t1 = IntegrityTraceService.record_evaluation(db, PAY_ID, T_PLUS_1)
        t2 = IntegrityTraceService.record_evaluation(db, PAY_ID, T_PLUS_10)
        db.commit()
        assert t1.trace_id != t2.trace_id

    def test_canonical_payload_contains_all_content_sections(self, db):
        _seed_rich_world(db)
        trace = IntegrityTraceService.record_evaluation(db, PAY_ID, T_PLUS_1)
        db.commit()

        payload = trace.canonical_payload
        assert payload["hash_domain"] == "evidencegraph.integrity_trace.v1"
        assert payload["schema"] == TRACE_SCHEMA_VERSION

        envelope = payload["envelope"]
        for key in ("trace_id", "payment_id", "evaluated_at", "methodology_version",
                    "status", "methodology_snapshot_hash"):
            assert key in envelope
        assert envelope["status"] == "COMPLETED"

        content = payload["content"]
        required_sections = [
            "evaluation_context", "methodology", "evidence_inputs",
            "excluded_evidence", "quality_measurements",
            "structural_measurements", "corroboration", "consistency",
            "rule_executions", "intermediate_results", "counts",
            "final_result", "limitations", "explanation_lines",
        ]
        for section in required_sections:
            assert section in content, f"Missing content section '{section}'"

        # Evaluation context exactness
        ctx = content["evaluation_context"]
        assert ctx["payment_id"] == PAY_ID
        assert ctx["evaluation_time"].startswith("2026-08-23T10:01")
        assert ctx["timezone_normalization"] == "UTC"
        assert ctx["methodology_version"] == "EIS-1.0"

    def test_audit_events_ordered_with_sequence_numbers(self, db):
        _seed_rich_world(db)
        trace = IntegrityTraceService.record_evaluation(db, PAY_ID, T_PLUS_1)
        db.commit()

        events = list(
            db.execute(
                select(IntegrityTraceEvent)
                .where(IntegrityTraceEvent.trace_id == trace.trace_id)
                .order_by(IntegrityTraceEvent.sequence_number.asc())
            ).scalars().all()
        )
        seqs = [e.sequence_number for e in events]
        assert seqs == list(range(1, len(events) + 1))

        types = [e.event_type for e in events]
        assert types[0] == TraceEventType.EVALUATION_STARTED
        assert types[-1] == TraceEventType.TRACE_FINALIZED
        assert TraceEventType.INTEGRITY_COMPUTED in types
        assert any(t == TraceEventType.RULE_EXECUTED for t in types)

    def test_no_raw_payload_or_secret_fields_in_trace(self, db):
        _seed_rich_world(db)
        trace = IntegrityTraceService.record_evaluation(db, PAY_ID, T_PLUS_1)
        db.commit()

        blob = canonical_json(trace.canonical_payload).lower()
        for forbidden in ("raw_payload", "secret", "cvv", "otp", "token", "password", "api_key"):
            assert forbidden not in blob, f"Forbidden field '{forbidden}' leaked into trace"

        # Evidence references are metadata only — values are NOT copied.
        for ref in trace.canonical_payload["content"]["evidence_inputs"]:
            assert "value" not in ref


# ===========================================================================
# Class 4 — Evidence inclusion/exclusion recording
# ===========================================================================

class TestEvidenceExclusions:
    def test_future_evidence_excluded_with_reason(self, db):
        _seed_rich_world(db)
        _make_obs(db, 50, PAY_ID, observed_at=T_PLUS_10)  # future vs T_PLUS_1

        trace = IntegrityTraceService.record_evaluation(db, PAY_ID, T_PLUS_1)
        db.commit()

        content = trace.canonical_payload["content"]
        included_ids = [e["evidence_internal_id"] for e in content["evidence_inputs"]]
        assert 50 not in included_ids
        excluded = {
            e["evidence_internal_id"]: e["exclusion_reason"]
            for e in content["excluded_evidence"]
        }
        assert excluded.get(50) == ExclusionReason.OBSERVED_AFTER_EVALUATION_TIME

    def test_invalidated_evidence_excluded_with_reason(self, db):
        _seed_rich_world(db)
        _make_obs(
            db, 51, PAY_ID, observed_at=T_BASE,
            valid_until=T_BASE + timedelta(seconds=30),
        )

        trace = IntegrityTraceService.record_evaluation(db, PAY_ID, T_PLUS_1)
        db.commit()

        excluded = {
            e["evidence_internal_id"]: e["exclusion_reason"]
            for e in trace.canonical_payload["content"]["excluded_evidence"]
        }
        assert excluded.get(51) == ExclusionReason.INVALIDATED

    def test_order_scoped_lineage_evidence_outside_scope(self, db):
        from app.models.order import Order

        payment = _make_payment(db)
        order = Order(razorpay_order_id="order_trace_x", status="paid")
        db.add(order)
        db.flush()
        payment.order_id = order.internal_id
        db.flush()

        _make_obs(db, 1, observed_at=T_BASE)
        _make_quality_snapshot(db, 1)
        # Order-scoped evidence tied to the payment's order via lineage
        _make_obs(
            db, 60, subject_type="order", subject_id="order_trace_x",
            evidence_type=EvidenceType.ORDER_STATUS, value="paid",
            observed_at=T_BASE,
        )

        trace = IntegrityTraceService.record_evaluation(db, PAY_ID, T_PLUS_1)
        db.commit()

        excluded = {
            e["evidence_internal_id"]: e["exclusion_reason"]
            for e in trace.canonical_payload["content"]["excluded_evidence"]
        }
        assert excluded.get(60) == ExclusionReason.OUTSIDE_EVALUATION_SCOPE


# ===========================================================================
# Class 5 — Rule execution traces (actual computation path)
# ===========================================================================

class TestRuleExecution:
    def test_rules_refire_and_match_final_result(self, db):
        _make_payment(db)
        _make_obs(db, 1, observed_at=T_BASE)  # no quality snapshots → UNKNOWN freshness → WEAK

        trace = IntegrityTraceService.record_evaluation(db, PAY_ID, T_PLUS_1)
        db.commit()

        rules = trace.canonical_payload["content"]["rule_executions"]
        fired = [r for r in rules if r["fired"]]
        assert len(fired) >= 1
        # Exactly the last executed rule fired; short-circuit semantics hold.
        assert rules[-1]["fired"] is True
        assert all(not r["fired"] for r in rules[:-1])
        # Firing gate result equals overall status.
        assert rules[-1]["result"] == trace.overall_status == "WEAK"
        # Execution order strictly monotonic starting at 1.
        assert [r["execution_order"] for r in rules] == list(range(1, len(rules) + 1))
        # Real explanations reference actual inputs.
        for rule in rules:
            assert rule["explanation"]
            assert rule["rule_id"].startswith("EIS-")
            assert rule["inputs"]["evidence_count"] == 1

    def test_no_rule_records_without_execution(self, db):
        """Rule records must come from real executions, not fabrication."""
        _make_payment(db)
        _make_obs(db, 1, observed_at=T_BASE)
        trace = IntegrityTraceService.record_evaluation(db, PAY_ID, T_PLUS_1)
        db.commit()

        from app.models.integrity_methodology import EIS_V1

        rules = trace.canonical_payload["content"]["rule_executions"]
        assert len(rules) <= len(EIS_V1.gates)


# ===========================================================================
# Class 6 — Methodology snapshot
# ===========================================================================

class TestMethodologySnapshot:
    def test_methodology_identifiable_beyond_version_string(self, db):
        _seed_rich_world(db)
        trace = IntegrityTraceService.record_evaluation(db, PAY_ID, T_PLUS_1)
        db.commit()

        method = trace.canonical_payload["content"]["methodology"]
        assert method["version"] == "EIS-1.0"
        assert method["aggregation"] == "RULE_BASED"
        assert isinstance(method["snapshot"], dict)
        gates = method["snapshot"]["gates"]
        assert len(gates) == 6
        assert method["snapshot_hash"] == methodology_snapshot_hash(
            method["snapshot"]
        )
        assert trace.methodology_snapshot_hash == method["snapshot_hash"]

    def test_intermediate_dimension_results_preserved(self, db):
        _seed_rich_world(db)
        trace = IntegrityTraceService.record_evaluation(db, PAY_ID, T_PLUS_1)
        db.commit()

        dims = trace.canonical_payload["content"]["intermediate_results"]
        for dim in ("freshness", "source", "independence", "corroboration", "consistency"):
            assert dim in dims
            assert dims[dim]["status"]
            assert dims[dim]["reason"]
            assert "inputs" in dims[dim]


# ===========================================================================
# Class 7 — Hash verification
# ===========================================================================

class TestHashVerification:
    def test_valid_for_untouched_trace(self, db):
        _seed_rich_world(db)
        trace = IntegrityTraceService.record_evaluation(db, PAY_ID, T_PLUS_1)
        db.commit()

        result = TraceVerificationService.verify_trace_integrity(db, trace.trace_id)
        assert result["status"] == "VALID"

    def test_invalid_when_payload_tampered(self, db):
        _seed_rich_world(db)
        trace = IntegrityTraceService.record_evaluation(db, PAY_ID, T_PLUS_1)
        db.commit()

        # Simulate direct DB tampering of audit content.
        tampered = dict(trace.canonical_payload)
        content = dict(tampered["content"])
        final = dict(content["final_result"])
        assert final["overall_status"] != "WEAK"
        final["overall_status"] = "WEAK"  # forged downgrade
        content["final_result"] = final
        tampered["content"] = content
        trace.canonical_payload = tampered
        db.commit()

        result = TraceVerificationService.verify_trace_integrity(db, trace.trace_id)
        assert result["status"] == "INVALID"

    def test_invalid_when_hash_tampered(self, db):
        _seed_rich_world(db)
        trace = IntegrityTraceService.record_evaluation(db, PAY_ID, T_PLUS_1)
        db.commit()

        trace.trace_hash = "0" * 64
        db.commit()

        result = TraceVerificationService.verify_trace_integrity(db, trace.trace_id)
        assert result["status"] == "INVALID"

    def test_unavailable_before_finalization(self, db):
        from app.models.evidence_integrity import EvidenceIntegritySnapshot

        _make_payment(db)
        trace = EvidenceIntegrityTrace(
            trace_id="trc_started_001",
            trace_type=TraceType.EVALUATION,
            payment_id=PAY_ID,
            evaluated_at=T_PLUS_1,
            methodology_version="EIS-1.0",
            status=TraceStatus.EVALUATION_STARTED,
        )
        db.add(trace)
        db.commit()

        result = TraceVerificationService.verify_trace_integrity(db, "trc_started_001")
        assert result["status"] == "VERIFICATION_UNAVAILABLE"

    def test_not_found(self, db):
        result = TraceVerificationService.verify_trace_integrity(db, "trc_missing")
        assert result["status"] == "NOT_FOUND"


# ===========================================================================
# Class 8 — Hash chain
# ===========================================================================

class TestHashChain:
    def test_chain_links_across_evaluations(self, db):
        _seed_rich_world(db)
        t1 = IntegrityTraceService.record_evaluation(db, PAY_ID, T_PLUS_1)
        t2 = IntegrityTraceService.record_evaluation(db, PAY_ID, T_PLUS_5)
        t3 = IntegrityTraceService.record_evaluation(db, PAY_ID, T_PLUS_10)
        db.commit()

        assert t1.previous_trace_hash is None
        assert t2.previous_trace_hash == t1.trace_hash
        assert t2.previous_trace_id == t1.trace_id
        assert t3.previous_trace_hash == t2.trace_hash

        result = TraceVerificationService.verify_trace_chain(db, PAY_ID)
        assert result["status"] == "CHAIN_VALID"
        assert result["verified_count"] == 3

    def test_single_link_reports_chain_start(self, db):
        _seed_rich_world(db)
        IntegrityTraceService.record_evaluation(db, PAY_ID, T_PLUS_1)
        db.commit()

        result = TraceVerificationService.verify_trace_chain(db, PAY_ID)
        assert result["status"] == "CHAIN_START"

    def test_empty_payment_reports_no_traces(self, db):
        _make_payment(db)
        result = TraceVerificationService.verify_trace_chain(db, PAY_ID)
        assert result["status"] == "NO_TRACES"

    def test_broken_previous_hash_detected(self, db):
        _seed_rich_world(db)
        t1 = IntegrityTraceService.record_evaluation(db, PAY_ID, T_PLUS_1)
        t2 = IntegrityTraceService.record_evaluation(db, PAY_ID, T_PLUS_5)
        db.commit()

        # Tamper with link 1's stored hash → both its own validity and the
        # linkage to it break.
        t1.trace_hash = "f" * 64
        db.commit()

        result = TraceVerificationService.verify_trace_chain(db, PAY_ID)
        assert result["status"] == "CHAIN_INVALID"
        issues = {p["issue"] for p in result["problems"]}
        assert "HASH_MISMATCH" in issues
        assert "BROKEN_LINK_HASH" in issues

    def test_failed_traces_join_chain_but_not_identity_slot(self, db):
        _seed_rich_world(db)
        t1 = IntegrityTraceService.record_evaluation(db, PAY_ID, T_PLUS_1)
        from unittest.mock import patch

        with patch(
            "app.services.integrity_trace_service.IntegrityEngine.compute_integrity",
            side_effect=RuntimeError("simulated engine crash"),
        ):
            failed = IntegrityTraceService.record_evaluation(db, PAY_ID, T_PLUS_5)
        t3 = IntegrityTraceService.record_evaluation(db, PAY_ID, T_PLUS_10)
        db.commit()

        assert failed.status == TraceStatus.FAILED
        assert t3.previous_trace_id == failed.trace_id
        assert t3.previous_trace_hash == failed.trace_hash
        # Chain still verifies across success/failure mix.
        result = TraceVerificationService.verify_trace_chain(db, PAY_ID)
        assert result["status"] == "CHAIN_VALID"
        assert t1.trace_id != failed.trace_id


# ===========================================================================
# Class 9 — Immutability & idempotency
# ===========================================================================

class TestImmutabilityAndIdempotency:
    def test_repeat_evaluation_returns_existing_trace(self, db):
        _seed_rich_world(db)
        first = IntegrityTraceService.record_evaluation(db, PAY_ID, T_PLUS_1)
        second = IntegrityTraceService.record_evaluation(db, PAY_ID, T_PLUS_1)
        db.commit()

        assert first.trace_id == second.trace_id
        count = db.execute(
            select(func.count()).select_from(EvidenceIntegrityTrace).where(
                EvidenceIntegrityTrace.payment_id == PAY_ID,
                EvidenceIntegrityTrace.status == TraceStatus.COMPLETED,
                EvidenceIntegrityTrace.trace_type == TraceType.EVALUATION,
            )
        ).scalar_one()
        assert count == 1

    def test_new_evaluation_never_touches_old_trace(self, db):
        _seed_rich_world(db)
        old = IntegrityTraceService.record_evaluation(db, PAY_ID, T_PLUS_1)
        db.commit()
        old_hash = old.trace_hash
        old_payload = canonical_json(old.canonical_payload)

        # World changes.
        _make_obs(db, 90, PAY_ID, observed_at=T_PLUS_10)
        new = IntegrityTraceService.record_evaluation(db, PAY_ID, T_PLUS_10)
        db.commit()

        db.refresh(old)
        assert old.trace_hash == old_hash
        assert canonical_json(old.canonical_payload) == old_payload
        assert new.trace_id != old.trace_id
        assert new.overall_status != old.overall_status or True  # may differ or not

    def test_service_has_no_update_path_for_traces(self, db):
        """The service API surface must expose no mutation of finalized traces."""
        mutating = [
            name for name in dir(IntegrityTraceService)
            if any(verb in name.lower() for verb in ("update", "edit", "modify", "rewrite"))
        ]
        assert mutating == []

    def test_legacy_snapshot_without_trace_is_not_backfilled(self, db):
        _seed_rich_world(db)
        # A pre-Phase-10 snapshot exists for this identity...
        existing_snap = EvidenceIntegritySnapshot(
            payment_id=PAY_ID,
            evaluated_at=T_PLUS_5,
            methodology_version="EIS-1.0",
            overall_status="STRONG",
        )
        db.add(existing_snap)
        db.commit()

        trace = IntegrityTraceService.record_evaluation(db, PAY_ID, T_PLUS_5)
        db.commit()
        assert trace is None  # history must not be fabricated


# ===========================================================================
# Class 10 — Replay
# ===========================================================================

class TestReplay:
    def test_replay_matches_on_unchanged_world(self, db):
        _seed_rich_world(db)
        original = IntegrityTraceService.record_evaluation(db, PAY_ID, T_PLUS_1)
        db.commit()

        before_hash = original.trace_hash
        before_payload = canonical_json(original.canonical_payload)
        before_status = original.status

        report = ReplayService.replay_trace(db, original.trace_id)
        db.commit()

        assert report["comparison_result"] == "MATCH"
        assert report["first_difference"] is None
        assert report["original_result"] == report["replay_result"]

        # Original untouched.
        db.refresh(original)
        assert original.trace_hash == before_hash
        assert canonical_json(original.canonical_payload) == before_payload
        assert original.status == before_status

        # Replay recorded as separate REPLAY trace.
        replay_trace = IntegrityTraceService.get_by_trace_id(
            db, report["replay_trace_id"]
        )
        assert replay_trace.trace_type == TraceType.REPLAY
        assert replay_trace.original_trace_id == original.trace_id
        assert replay_trace.status == TraceStatus.COMPLETED

    def test_replay_does_not_create_second_evaluation_snapshot(self, db):
        _seed_rich_world(db)
        original = IntegrityTraceService.record_evaluation(db, PAY_ID, T_PLUS_1)
        db.commit()

        snapshots_before = db.execute(
            select(func.count()).select_from(EvidenceIntegritySnapshot)
        ).scalar_one()
        ReplayService.replay_trace(db, original.trace_id)
        db.commit()
        snapshots_after = db.execute(
            select(func.count()).select_from(EvidenceIntegritySnapshot)
        ).scalar_one()
        assert snapshots_before == snapshots_after

    def test_replay_mismatch_identifies_new_evidence(self, db):
        _seed_rich_world(db)
        original = IntegrityTraceService.record_evaluation(db, PAY_ID, T_PLUS_1)
        db.commit()

        # New evidence arrives AFTER the original evaluation moment but we
        # replay at the SAME evaluation_time... it must be excluded (scope).
        # To create a genuine mismatch, change what was known AT that moment:
        # a quality snapshot measured after eval time changes nothing (filtered);
        # instead mutate conflict state visible to consistency dimension.
        claim_a = Claim(
            subject_type="payment", subject_id=PAY_ID,
            claim_type="PAYMENT_STATUS", claim_key="STATUS_A",
            canonical_value="captured", created_at=T_BASE,
        )
        claim_b = Claim(
            subject_type="payment", subject_id=PAY_ID,
            claim_type="PAYMENT_STATUS", claim_key="STATUS_B",
            canonical_value="failed", created_at=T_BASE,
        )
        db.add_all([claim_a, claim_b])
        db.flush()
        db.add(
            EvidenceConflict(
                payment_id=PAY_ID,
                claim_a_id=claim_a.internal_id,
                claim_b_id=claim_b.internal_id,
                conflict_type="STATE_CONFLICT",
                severity="HIGH",
                status="OPEN",
                detected_at=T_BASE,
                rule_version="1.0",
            )
        )
        db.commit()

        report = ReplayService.replay_trace(db, original.trace_id)
        db.commit()

        assert report["comparison_result"] == "MISMATCH"
        first = report["first_difference"]
        assert first is not None
        assert first["category"] == "CONFLICT_CHANGED"
        assert first["paths"], "Mismatch must explain WHERE it differs"

        # Original still intact.
        db.refresh(original)
        result = TraceVerificationService.verify_trace_integrity(db, original.trace_id)
        assert result["status"] == "VALID"

    def test_replay_of_missing_trace_raises(self, db):
        with pytest.raises(ReplayNotPossibleError):
            ReplayService.replay_trace(db, "trc_nope")

    def test_replay_of_failed_trace_raises(self, db):
        _seed_rich_world(db)
        from unittest.mock import patch

        with patch(
            "app.services.integrity_trace_service.IntegrityEngine.compute_integrity",
            side_effect=RuntimeError("boom"),
        ):
            IntegrityTraceService.record_evaluation(db, PAY_ID, T_PLUS_1)
        db.commit()

        failed = db.execute(
            select(EvidenceIntegrityTrace).where(
                EvidenceIntegrityTrace.status == TraceStatus.FAILED
            )
        ).scalar_one()
        with pytest.raises(ReplayNotPossibleError):
            ReplayService.replay_trace(db, failed.trace_id)

    def test_replays_do_not_join_evaluation_chain(self, db):
        _seed_rich_world(db)
        original = IntegrityTraceService.record_evaluation(db, PAY_ID, T_PLUS_1)
        db.commit()
        report = ReplayService.replay_trace(db, original.trace_id)
        db.commit()

        replay_trace = IntegrityTraceService.get_by_trace_id(
            db, report["replay_trace_id"]
        )
        assert replay_trace.previous_trace_hash is None
        assert replay_trace.previous_trace_id is None

        chain = TraceVerificationService.verify_trace_chain(db, PAY_ID)
        assert chain["verified_count"] == 1  # only the EVALUATION trace


# ===========================================================================
# Class 11 — Failure traces
# ===========================================================================

class TestFailureTraces:
    def test_failure_produces_auditable_failed_trace(self, db):
        _make_payment(db)
        _make_obs(db, 1, observed_at=T_BASE)

        from unittest.mock import patch

        with patch(
            "app.services.integrity_trace_service.IntegrityEngine.compute_integrity",
            side_effect=RuntimeError("database exploded mid-evaluation"),
        ):
            trace = IntegrityTraceService.record_evaluation(
                db, PAY_ID, T_PLUS_1, trigger="WEBHOOK_PROCESSING"
            )
        db.commit()

        assert trace.status == TraceStatus.FAILED
        assert trace.overall_status is None
        assert trace.failure_category == "RuntimeError"
        assert trace.failure_stage
        assert trace.failure_detail and "stack" not in trace.failure_detail.lower()
        assert trace.trace_hash  # failure record itself is hashed

        payload = trace.canonical_payload
        assert payload["envelope"]["status"] == "FAILED"
        assert payload["content"]["failure"]["category"] == "RuntimeError"
        assert payload["content"]["final_result"] is None

        events = list(
            db.execute(
                select(IntegrityTraceEvent).where(
                    IntegrityTraceEvent.trace_id == trace.trace_id
                ).order_by(IntegrityTraceEvent.sequence_number.asc())
            ).scalars().all()
        )
        assert events[0].event_type == TraceEventType.EVALUATION_STARTED
        assert TraceEventType.EVALUATION_FAILED in [e.event_type for e in events]

    def test_failure_trace_verifies_but_is_not_completed(self, db):
        _make_payment(db)
        from unittest.mock import patch

        with patch(
            "app.services.integrity_trace_service.IntegrityEngine.compute_integrity",
            side_effect=ValueError("bad input"),
        ):
            trace = IntegrityTraceService.record_evaluation(db, PAY_ID, T_PLUS_1)
        db.commit()

        result = TraceVerificationService.verify_trace_integrity(db, trace.trace_id)
        assert result["status"] == "VALID"
        assert trace.status == TraceStatus.FAILED  # never reported completed

    def test_retry_after_failure_succeeds_into_new_trace(self, db):
        _seed_rich_world(db)
        from unittest.mock import patch

        with patch(
            "app.services.integrity_trace_service.IntegrityEngine.compute_integrity",
            side_effect=RuntimeError("transient"),
        ):
            failed = IntegrityTraceService.record_evaluation(db, PAY_ID, T_PLUS_1)
        ok = IntegrityTraceService.record_evaluation(db, PAY_ID, T_PLUS_1)
        db.commit()

        assert failed.status == TraceStatus.FAILED
        assert ok.status == TraceStatus.COMPLETED
        assert ok.trace_id != failed.trace_id


# ===========================================================================
# Class 12 — Temporal leakage protection
# ===========================================================================

class TestTemporalLeakage:
    def test_future_evidence_never_enters_historical_trace(self, db):
        _seed_rich_world(db)
        historical = IntegrityTraceService.record_evaluation(db, PAY_ID, T_PLUS_1)
        db.commit()
        _hash_before = historical.trace_hash

        # Today, much later evidence exists in the database...
        for i in range(100, 105):
            _make_obs(db, i, PAY_ID, observed_at=T_PLUS_10)
        db.commit()

        # ...but the historical trace remains frozen and free of it —
        # the future observations appear NOWHERE in it (they were not
        # candidates known at evaluation time).
        content = historical.canonical_payload["content"]
        included = {e["evidence_internal_id"] for e in content["evidence_inputs"]}
        excluded_known = {
            e["evidence_internal_id"] for e in content["excluded_evidence"]
        }
        future_ids = set(range(100, 105))
        assert included.isdisjoint(future_ids)
        assert excluded_known.isdisjoint(future_ids)
        blob = canonical_json(historical.canonical_payload)
        for fid in future_ids:
            assert f'"evidence_internal_id":{fid}' not in blob.replace(" ", ""), "future evidence id leaked into history"

        # A NEW evaluation at the later time sees them (world moved forward),
        # while the historical trace object itself stays unchanged.
        later = IntegrityTraceService.record_evaluation(db, PAY_ID, T_PLUS_10)
        db.commit()
        db.refresh(historical)
        later_included = {
            e["evidence_internal_id"]
            for e in later.canonical_payload["content"]["evidence_inputs"]
        }
        assert future_ids <= later_included
        assert historical.trace_hash == _hash_before


# ===========================================================================
# Class 13 — API security & behavior
# ===========================================================================

class TestTraceAPI:
    def _completed_trace(self, api_db) -> EvidenceIntegrityTrace:
        _seed_rich_world(api_db)
        trace = IntegrityTraceService.record_evaluation(api_db, PAY_ID, T_PLUS_1)
        api_db.commit()
        return trace

    def test_trace_list_public_summary(self, client, api_db):
        self._completed_trace(api_db)
        response = client.get(f"/api/v1/payments/{PAY_ID}/integrity/traces")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        item = data["traces"][0]
        assert item["trace_id"]
        assert item["trace_hash"]
        assert "canonical_payload" not in item  # summaries carry no full content

    def test_trace_list_unknown_payment_404(self, client, api_db):
        response = client.get("/api/v1/payments/pay_ghost/integrity/traces")
        assert response.status_code == 404

    def test_full_trace_requires_api_key(self, client, api_db):
        trace = self._completed_trace(api_db)
        response = client.get(f"/api/v1/integrity/{trace.trace_id}")
        assert response.status_code == 401

    def test_full_trace_rejects_wrong_key(self, client, api_db):
        trace = self._completed_trace(api_db)
        response = client.get(
            f"/api/v1/integrity/{trace.trace_id}",
            headers={"X-API-Key": "wrong-key"},
        )
        assert response.status_code == 403

    def test_full_trace_with_valid_key(self, client, api_db):
        trace = self._completed_trace(api_db)
        response = client.get(
            f"/api/v1/integrity/{trace.trace_id}", headers=ADMIN_HEADERS
        )
        assert response.status_code == 200
        data = response.json()
        assert data["canonical_payload"]["schema"] == TRACE_SCHEMA_VERSION
        assert data["hash_algorithm"] == "SHA-256"
        seqs = [e["sequence_number"] for e in data["events"]]
        assert seqs == sorted(seqs)

    def test_verify_endpoint_restricted(self, client, api_db):
        trace = self._completed_trace(api_db)
        anon = client.get(f"/api/v1/integrity/{trace.trace_id}/verify")
        assert anon.status_code == 401

        wrong = client.get(
            f"/api/v1/integrity/{trace.trace_id}/verify",
            headers={"X-API-Key": "nope"},
        )
        assert wrong.status_code == 403

        ok = client.get(
            f"/api/v1/integrity/{trace.trace_id}/verify", headers=ADMIN_HEADERS
        )
        assert ok.status_code == 200
        assert ok.json()["status"] == "VALID"

    def test_chain_verify_endpoint_restricted_and_working(self, client, api_db):
        self._completed_trace(api_db)
        assert (
            client.get(f"/api/v1/payments/{PAY_ID}/integrity/chain-verify").status_code
            == 401
        )
        ok = client.get(
            f"/api/v1/payments/{PAY_ID}/integrity/chain-verify",
            headers=ADMIN_HEADERS,
        )
        assert ok.status_code == 200
        assert ok.json()["status"] == "CHAIN_START"

    def test_replay_endpoint_restricted(self, client, api_db):
        trace = self._completed_trace(api_db)
        assert (
            client.post(f"/api/v1/integrity/{trace.trace_id}/replay").status_code == 401
        )
        denied = client.post(
            f"/api/v1/integrity/{trace.trace_id}/replay",
            headers={"X-API-Key": "attacker"},
        )
        assert denied.status_code == 403

        ok = client.post(
            f"/api/v1/integrity/{trace.trace_id}/replay", headers=ADMIN_HEADERS
        )
        assert ok.status_code == 200
        assert ok.json()["comparison_result"] == "MATCH"

    def test_no_mutation_endpoints_exist(self, client, api_db):
        trace = self._completed_trace(api_db)
        base = f"/api/v1/integrity/{trace.trace_id}"
        for method in ("put", "patch", "delete", "post"):
            if method == "post":
                continue  # POST /replay exists by design (restricted)
            response = getattr(client, method)(base, headers=ADMIN_HEADERS)
            assert response.status_code in (405, 404), (
                f"{method.upper()} must not be a supported mutation route"
            )

    def test_on_demand_integrity_creates_trace(self, client, api_db):
        _seed_rich_world(api_db)
        response = client.get(f"/api/v1/payments/{PAY_ID}/integrity")
        assert response.status_code == 200

        traces = api_db.execute(
            select(EvidenceIntegrityTrace).where(
                EvidenceIntegrityTrace.payment_id == PAY_ID
            )
        ).scalars().all()
        assert len(traces) == 1
        assert traces[0].trigger == "ON_DEMAND_API"


# ===========================================================================
# Class 14 — Performance sanity
# ===========================================================================

class TestPerformanceSanity:
    def test_trace_creation_latency_reasonable(self, db):
        _seed_rich_world(db)
        start = time.perf_counter()
        IntegrityTraceService.record_evaluation(db, PAY_ID, T_PLUS_1)
        elapsed = time.perf_counter() - start
        db.commit()
        assert elapsed < 2.0, f"Trace creation took {elapsed:.2f}s"

    def test_verification_latency_reasonable(self, db):
        _seed_rich_world(db)
        trace = IntegrityTraceService.record_evaluation(db, PAY_ID, T_PLUS_1)
        db.commit()
        start = time.perf_counter()
        TraceVerificationService.verify_trace_integrity(db, trace.trace_id)
        elapsed = time.perf_counter() - start
        assert elapsed < 1.0, f"Verification took {elapsed:.2f}s"
