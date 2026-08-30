import pytest
from datetime import datetime, timezone
from app.models.evidence import EvidenceObservation
from app.models.evidence_types import EvidenceType, SubjectType
from app.models.relationship_types import RelationshipType
from app.services.relationship_engine import build_relationships_for_observations

def test_relationship_engine_rules():
    # Setup test observations
    obs1 = EvidenceObservation(
        internal_id=1,
        evidence_type=EvidenceType.PAYMENT_EVENT,
        subject_type=SubjectType.PAYMENT,
        subject_id="pay_123",
        value="captured",
        value_type="STRING",
        source_type="RAZORPAY_WEBHOOK",
        observed_at=datetime.now(timezone.utc),
        payment_event_id=10,
        webhook_event_id=100,
        extraction_version="1.0"
    )
    obs2 = EvidenceObservation(
        internal_id=2,
        evidence_type=EvidenceType.PAYMENT_STATUS,
        subject_type=SubjectType.PAYMENT,
        subject_id="pay_123",
        value="captured",
        value_type="ENUM",
        source_type="RAZORPAY_WEBHOOK",
        observed_at=datetime.now(timezone.utc),
        payment_event_id=10,
        webhook_event_id=100,
        extraction_version="1.0"
    )
    obs3 = EvidenceObservation(
        internal_id=3,
        evidence_type=EvidenceType.PAYMENT_EVENT,
        subject_type=SubjectType.PAYMENT,
        subject_id="pay_123", # Same payment
        value="authorized",
        value_type="STRING",
        source_type="RAZORPAY_WEBHOOK",
        observed_at=datetime.now(timezone.utc),
        payment_event_id=11, # Different event
        webhook_event_id=101, # Different source
        extraction_version="1.0"
    )

    rels = build_relationships_for_observations([obs1, obs2, obs3])
    
    # Check SAME_EVENT
    same_event = [r for r in rels if r.relationship_type == RelationshipType.SAME_EVENT]
    assert len(same_event) == 1
    assert same_event[0].source_evidence_id == 1
    assert same_event[0].target_evidence_id == 2

    # Check SAME_SOURCE
    same_source = [r for r in rels if r.relationship_type == RelationshipType.SAME_SOURCE]
    assert len(same_source) == 1
    assert same_source[0].source_evidence_id == 1
    assert same_source[0].target_evidence_id == 2

    # Check SAME_PAYMENT (all pairs: 1-2, 1-3, 2-3)
    same_payment = [r for r in rels if r.relationship_type == RelationshipType.SAME_PAYMENT]
    assert len(same_payment) == 3

    # Check DERIVED_FROM
    derived = [r for r in rels if r.relationship_type == RelationshipType.DERIVED_FROM]
    assert len(derived) == 1
    assert derived[0].source_evidence_id == 2 # STATUS
    assert derived[0].target_evidence_id == 1 # EVENT
    assert derived[0].provenance_metadata["shared_field"] == "payment_event_id"

    # Check INDEPENDENCE_CANDIDATE
    # obs1 and obs3 are candidates (different webhook_event_id, same payment)
    # obs2 and obs3 are candidates
    candidates = [r for r in rels if r.relationship_type == RelationshipType.INDEPENDENCE_CANDIDATE]
    assert len(candidates) == 2
    pairs = {(c.source_evidence_id, c.target_evidence_id) for c in candidates}
    assert pairs == {(1, 3), (2, 3)}
    
    # Verify no self-loops
    for r in rels:
        assert r.source_evidence_id != r.target_evidence_id
