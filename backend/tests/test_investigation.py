"""
Phase 12 — Investigation & Graph Query Engine.

Exercises the real BFS engine (not the old stub): bounded traversal, cycle
safety, node/edge limits, as-of temporal filtering, node-type filtering,
sensitive-data stripping, shortest-path, provenance chains, claim support,
dependency chains, conflict paths, and entity search.

Runs against SQLite for isolation (JSONB polyfilled).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(type_, compiler, **kw):  # noqa: ANN001
    return "JSON"


from app.db.session import Base
from app.models.customer_reference import CustomerReference
from app.models.evidence import EvidenceObservation
from app.models.evidence_conflict import EvidenceConflict
from app.models.evidence_relationship import EvidenceRelationship
from app.models.evidence_structure import Claim, EvidenceClaimLink
from app.models.order import Order
from app.models.payment import Payment
from app.models.payment_event import PaymentEvent
from app.models.webhook_event import WebhookEvent
from app.models.investigation_types import TraversalStatus
from app.services.investigation_service import InvestigationService as IS

T0 = datetime(2026, 8, 20, 10, 0, 0, tzinfo=timezone.utc)


@pytest.fixture()
def db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine)()
    try:
        yield s
    finally:
        s.close()


@pytest.fixture()
def graph_data(db):
    """A realistic single-payment evidence graph."""
    order = Order(razorpay_order_id="order_INV1", amount_minor=50000, currency="INR", status="paid")
    cust = CustomerReference(razorpay_customer_id="cust_INV1")
    db.add_all([order, cust])
    db.flush()

    pay = Payment(
        razorpay_payment_id="pay_INV1", order_id=order.internal_id,
        customer_id=cust.internal_id, status="captured", amount_minor=50000,
        currency="INR", first_observed_at=T0, last_observed_at=T0,
    )
    db.add(pay)
    db.flush()

    wh = WebhookEvent(
        razorpay_event_id="evt_INV1", event_type="payment.captured", received_at=T0,
        signature_verified=True, processing_status="PROCESSED",
        raw_payload={"secret": "should-never-surface", "entity": {}},
        payload_hash="deadbeef" * 8, payment_id="pay_INV1",
    )
    db.add(wh)
    db.flush()

    pe = PaymentEvent(
        payment_id=pay.internal_id, webhook_event_id=wh.id,
        event_type="payment.captured", event_timestamp=T0,
    )
    db.add(pe)
    db.flush()

    # 3 evidence observations from the same event; #3 is future-dated
    obs = []
    for i, (etype, val, src, when) in enumerate([
        ("PAYMENT_STATUS", "captured", "RAZORPAY_WEBHOOK", T0),
        ("PAYMENT_AMOUNT", "50000", "RAZORPAY_WEBHOOK", T0),
        ("PAYMENT_METHOD", "card", "RAZORPAY_API", T0 + timedelta(days=5)),
    ]):
        o = EvidenceObservation(
            evidence_type=etype, subject_type="payment", subject_id="pay_INV1",
            value=val, value_type="STRING", source_type=src,
            source_reference=f"ref_{i}", observed_at=when,
            webhook_event_id=wh.id, payment_event_id=pe.internal_id,
            extraction_method="TEST", extraction_version="t",
        )
        db.add(o)
        obs.append(o)
    db.flush()

    # relationships: SAME_EVENT (a<->b), and a reciprocal pair to prove cycle safety
    db.add_all([
        EvidenceRelationship(
            source_evidence_id=obs[0].internal_id, target_evidence_id=obs[1].internal_id,
            relationship_type="SAME_EVENT", relationship_source="RULE", rule_version="1",
        ),
        EvidenceRelationship(
            source_evidence_id=obs[1].internal_id, target_evidence_id=obs[0].internal_id,
            relationship_type="SAME_EVENT", relationship_source="RULE", rule_version="1",
        ),
        EvidenceRelationship(
            source_evidence_id=obs[1].internal_id, target_evidence_id=obs[2].internal_id,
            relationship_type="DEPENDS_ON", relationship_source="RULE", rule_version="1",
            provenance_metadata={"reason": "derived amount"},
        ),
    ])

    # two claims + a conflict between them
    c_a = Claim(subject_type="payment", subject_id="pay_INV1", claim_type="PAYMENT_STATUS",
                claim_key="status", canonical_value="captured")
    c_b = Claim(subject_type="payment", subject_id="pay_INV1", claim_type="PAYMENT_STATUS",
                claim_key="status", canonical_value="failed")
    db.add_all([c_a, c_b])
    db.flush()
    db.add_all([
        EvidenceClaimLink(claim_id=c_a.internal_id, evidence_id=obs[0].internal_id),
        EvidenceClaimLink(claim_id=c_a.internal_id, evidence_id=obs[1].internal_id),
    ])
    conflict = EvidenceConflict(
        payment_id="pay_INV1", claim_a_id=c_a.internal_id, claim_b_id=c_b.internal_id,
        conflict_type="STATUS_CONTRADICTION", severity="HIGH", status="ACTIVE", detected_at=T0,
    )
    db.add(conflict)
    db.flush()
    db.commit()

    return {
        "payment_id": "pay_INV1", "obs": [o.internal_id for o in obs],
        "claim_a": c_a.internal_id, "claim_b": c_b.internal_id,
        "conflict": conflict.internal_id, "webhook_id": wh.id, "event_id": pe.internal_id,
    }


# ── graph ───────────────────────────────────────────────────────────────
class TestGraph:
    def test_neighbourhood_and_types(self, db, graph_data):
        g = IS.build_payment_graph(db, "pay_INV1", depth=3)
        types = {n.node_type for n in g.nodes}
        assert {"PAYMENT", "ORDER", "CUSTOMER", "PAYMENT_EVENT", "EVIDENCE",
                "WEBHOOK_EVENT", "SOURCE", "CLAIM", "CONFLICT"} <= types
        assert g.traversal_status == TraversalStatus.COMPLETE.value
        assert g.node_count == len(g.nodes) and g.edge_count == len(g.edges)

    def test_depth_1_is_shallow(self, db, graph_data):
        g1 = IS.build_payment_graph(db, "pay_INV1", depth=1)
        g3 = IS.build_payment_graph(db, "pay_INV1", depth=3)
        assert g1.node_count < g3.node_count
        # depth 1 reaches events/order/customer but not the evidence beyond them
        assert "EVIDENCE" not in {n.node_type for n in g1.nodes}

    def test_depth_is_clamped_to_max(self, db, graph_data):
        g = IS.build_payment_graph(db, "pay_INV1", depth=99)
        assert g.traversal_depth == 5

    def test_ids_are_unique(self, db, graph_data):
        g = IS.build_payment_graph(db, "pay_INV1", depth=5)
        nids = [n.node_id for n in g.nodes]
        eids = [(e.source_node_id, e.target_node_id, e.edge_type) for e in g.edges]
        assert len(nids) == len(set(nids))
        assert len(eids) == len(set(eids))

    def test_reciprocal_relationship_terminates(self, db, graph_data):
        # obs[0] <-> obs[1] reciprocal SAME_EVENT must not loop forever
        g = IS.build_payment_graph(db, "pay_INV1", depth=5, max_nodes=500)
        assert g.traversal_status in (
            TraversalStatus.COMPLETE.value, TraversalStatus.TRAVERSAL_LIMIT_REACHED.value)
        assert g.node_count < 30

    def test_node_limit_reports_truncation(self, db, graph_data):
        g = IS.build_payment_graph(db, "pay_INV1", depth=5, max_nodes=3)
        assert g.node_count <= 3
        assert g.traversal_status == TraversalStatus.TRAVERSAL_LIMIT_REACHED.value

    def test_as_of_excludes_future_evidence(self, db, graph_data):
        full = IS.build_payment_graph(db, "pay_INV1", depth=3)
        past = IS.build_payment_graph(db, "pay_INV1", depth=3, as_of=T0 + timedelta(days=1))
        full_ev = {n.label for n in full.nodes if n.node_type == "EVIDENCE"}
        past_ev = {n.label for n in past.nodes if n.node_type == "EVIDENCE"}
        assert any("METHOD" in x for x in full_ev)
        assert not any("METHOD" in x for x in past_ev)

    def test_node_type_filter(self, db, graph_data):
        g = IS.build_payment_graph(db, "pay_INV1", depth=3, node_types=["EVIDENCE", "PAYMENT_EVENT"])
        assert {n.node_type for n in g.nodes} <= {"PAYMENT", "EVIDENCE", "PAYMENT_EVENT"}

    def test_webhook_node_has_no_raw_payload(self, db, graph_data):
        g = IS.build_payment_graph(db, "pay_INV1", depth=3)
        for n in g.nodes:
            blob = str(n.metadata).lower()
            assert "raw_payload" not in blob
            assert "payload_hash" not in blob
            assert "should-never-surface" not in blob

    def test_unknown_payment_raises(self, db):
        with pytest.raises(ValueError):
            IS.build_payment_graph(db, "pay_nope")


# ── path ────────────────────────────────────────────────────────────────
class TestPath:
    def test_path_payment_to_evidence(self, db, graph_data):
        ev = graph_data["obs"][0]
        r = IS.find_path(db, "pay:pay_INV1", f"ev:{ev}")
        assert r.found
        assert r.path_nodes[0].node_id == "pay:pay_INV1"
        assert r.path_nodes[-1].node_id == f"ev:{ev}"
        assert r.path_length == len(r.path_edges) >= 1

    def test_same_node_is_zero_length(self, db, graph_data):
        r = IS.find_path(db, "pay:pay_INV1", "pay:pay_INV1")
        assert r.found and r.path_length == 0

    def test_missing_node_not_found(self, db, graph_data):
        r = IS.find_path(db, "pay:pay_INV1", "ev:99999")
        assert not r.found


# ── provenance ──────────────────────────────────────────────────────────
def test_provenance_chain(db, graph_data):
    r = IS.get_evidence_provenance(db, graph_data["obs"][0])
    kinds = [s.entity_type for s in r.provenance_chain]
    assert kinds == ["EVIDENCE", "PAYMENT_EVENT", "WEBHOOK_EVENT", "PAYMENT"]
    assert r.chain_length == 4
    assert all("raw_payload" not in str(s.metadata) for s in r.provenance_chain)


def test_provenance_missing_evidence_raises(db):
    with pytest.raises(ValueError):
        IS.get_evidence_provenance(db, 424242)


# ── claim support ───────────────────────────────────────────────────────
def test_claim_support(db, graph_data):
    r = IS.get_claim_support(db, graph_data["claim_a"])
    assert r.total_support_count == 2
    assert r.independent_support_count == 2  # ref_0 / ref_1 distinct
    assert all(e.is_independent for e in r.supporting_evidence)
    # obs0<->obs1 SAME_EVENT counts as a dependency among supporters
    assert r.dependency_count >= 1


# ── dependencies ────────────────────────────────────────────────────────
def test_dependencies_direct_and_indirect(db, graph_data):
    # obs[1] --DEPENDS_ON--> obs[2] direct; obs[0] --SAME_EVENT--> obs[1] --> obs[2] indirect
    r = IS.get_evidence_dependencies(db, graph_data["obs"][0])
    assert r.total_dependency_count == len(r.direct_dependencies) + len(r.indirect_dependencies)
    assert r.total_dependency_count >= 2
    types = {d.dependency_type for d in r.direct_dependencies + r.indirect_dependencies}
    assert "DEPENDS_ON" in types or "SAME_EVENT" in types


# ── conflict path ───────────────────────────────────────────────────────
def test_conflict_path(db, graph_data):
    r = IS.get_conflict_path(db, graph_data["conflict"])
    roles = [s.role for s in r.path_steps]
    assert roles[0] == "CONFLICT"
    assert "CLAIM_A" in roles and "CLAIM_B" in roles
    assert r.conflict_type == "STATUS_CONTRADICTION"
    assert any(s.role == "EVIDENCE" for s in r.path_steps)


# ── search ──────────────────────────────────────────────────────────────
class TestSearch:
    def test_finds_across_entity_types(self, db, graph_data):
        r = IS.search_entities(db, "INV1", limit=50)
        found = {x.entity_type for x in r.results}
        assert {"PAYMENT", "ORDER", "CUSTOMER"} <= found

    def test_evidence_and_claim_search(self, db, graph_data):
        r = IS.search_entities(db, "PAYMENT_STATUS", limit=50)
        assert {"EVIDENCE", "CLAIM"} & {x.entity_type for x in r.results}

    def test_no_pii_or_secrets_in_results(self, db, graph_data):
        r = IS.search_entities(db, "INV1", limit=50)
        blob = str([x.model_dump() for x in r.results]).lower()
        assert "raw_payload" not in blob and "should-never-surface" not in blob

    def test_limit_respected(self, db, graph_data):
        r = IS.search_entities(db, "INV1", limit=2)
        assert len(r.results) <= 2
