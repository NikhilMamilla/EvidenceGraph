"""
Phase 7 — API Endpoints for Evidence Structure, Claims, Groups, and Corroboration.
"""
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.evidence import EvidenceObservation
from app.models.evidence_structure import (
    Claim,
    EvidenceClaimLink,
    EvidenceGroup,
    EvidenceCorroboration,
    EvidenceStructureSnapshot,
)
from app.schemas.structure import (
    ClaimEvidenceDetailResponse,
    ClaimEvidenceItem,
    ClaimResponse,
    CorroborationResponse,
    EvidenceGroupResponse,
    PaymentStructureResponse,
    StructureSnapshotResponse,
)
from app.services.structure_engine import StructureEngine

router = APIRouter(tags=["Evidence Structure"])


@router.get(
    "/payments/{payment_id}/structure",
    response_model=PaymentStructureResponse,
    summary="Get structural evidence measurements and concentration for a payment",
)
def get_payment_structure(
    payment_id: str,
    db: Session = Depends(get_db),
):
    """
    Returns the latest structural snapshot, claims, evidence groups, and corroborations
    for a given payment. Evaluates on the fly if not yet analyzed.
    """
    snapshot = (
        db.query(EvidenceStructureSnapshot)
        .filter(EvidenceStructureSnapshot.payment_id == payment_id)
        .order_by(EvidenceStructureSnapshot.evaluated_at.desc(), EvidenceStructureSnapshot.internal_id.desc())
        .first()
    )

    if not snapshot:
        snapshot = StructureEngine.evaluate_payment_structure(db, payment_id)

    if not snapshot:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No evidence or structure found for payment '{payment_id}'",
        )

    # Fetch Claims for this payment
    claims = (
        db.query(Claim)
        .filter(Claim.subject_type == "payment", Claim.subject_id == payment_id)
        .all()
    )

    claim_responses = []
    for c in claims:
        link_cnt = db.query(EvidenceClaimLink).filter(EvidenceClaimLink.claim_id == c.internal_id).count()
        claim_responses.append(
            ClaimResponse(
                internal_id=c.internal_id,
                subject_type=c.subject_type,
                subject_id=c.subject_id,
                claim_type=c.claim_type,
                claim_key=c.claim_key,
                canonical_value=c.canonical_value,
                created_at=c.created_at,
                supporting_evidence_count=link_cnt,
            )
        )

    # Fetch Groups for this payment
    groups = (
        db.query(EvidenceGroup)
        .filter(EvidenceGroup.payment_id == payment_id)
        .all()
    )
    group_responses = [
        EvidenceGroupResponse(
            internal_id=g.internal_id,
            payment_id=g.payment_id,
            group_type=g.group_type,
            grouping_key=g.grouping_key,
            rule_version=g.rule_version,
            metadata=g.metadata_,
            created_at=g.created_at,
            member_count=len(g.members),
        )
        for g in groups
    ]

    # Fetch Corroborations for this payment
    corroborations = (
        db.query(EvidenceCorroboration)
        .filter(EvidenceCorroboration.payment_id == payment_id)
        .all()
    )
    corrob_responses = [
        CorroborationResponse(
            internal_id=cr.internal_id,
            claim_id=cr.claim_id,
            payment_id=cr.payment_id,
            corroboration_type=cr.corroboration_type,
            independence_status=cr.independence_status,
            observation_count=cr.observation_count,
            distinct_sources_count=cr.distinct_sources_count,
            distinct_events_count=cr.distinct_events_count,
            methodology_version=cr.methodology_version,
            details=cr.details,
            created_at=cr.created_at,
        )
        for cr in corroborations
    ]

    return PaymentStructureResponse(
        payment_id=payment_id,
        snapshot=StructureSnapshotResponse.model_validate(snapshot),
        claims=claim_responses,
        groups=group_responses,
        corroborations=corrob_responses,
    )


@router.get(
    "/payments/{payment_id}/claims",
    response_model=List[ClaimResponse],
    summary="Get all canonical claims for a payment",
)
def get_payment_claims(
    payment_id: str,
    db: Session = Depends(get_db),
):
    claims = (
        db.query(Claim)
        .filter(Claim.subject_type == "payment", Claim.subject_id == payment_id)
        .all()
    )
    if not claims:
        # Try evaluating on the fly
        StructureEngine.evaluate_payment_structure(db, payment_id)
        claims = (
            db.query(Claim)
            .filter(Claim.subject_type == "payment", Claim.subject_id == payment_id)
            .all()
        )

    responses = []
    for c in claims:
        link_cnt = db.query(EvidenceClaimLink).filter(EvidenceClaimLink.claim_id == c.internal_id).count()
        responses.append(
            ClaimResponse(
                internal_id=c.internal_id,
                subject_type=c.subject_type,
                subject_id=c.subject_id,
                claim_type=c.claim_type,
                claim_key=c.claim_key,
                canonical_value=c.canonical_value,
                created_at=c.created_at,
                supporting_evidence_count=link_cnt,
            )
        )
    return responses


@router.get(
    "/claims/{claim_id}/evidence",
    response_model=ClaimEvidenceDetailResponse,
    summary="Get all evidence observations supporting a specific claim",
)
def get_claim_evidence(
    claim_id: int,
    db: Session = Depends(get_db),
):
    claim = db.query(Claim).filter(Claim.internal_id == claim_id).first()
    if not claim:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Claim ID '{claim_id}' not found",
        )

    links = (
        db.query(EvidenceClaimLink)
        .filter(EvidenceClaimLink.claim_id == claim_id)
        .all()
    )
    evidence_ids = [l.evidence_id for l in links]

    observations = []
    if evidence_ids:
        observations = (
            db.query(EvidenceObservation)
            .filter(EvidenceObservation.internal_id.in_(evidence_ids))
            .all()
        )

    evidence_items = [
        ClaimEvidenceItem(
            evidence_id=o.internal_id,
            evidence_type=o.evidence_type,
            subject_type=o.subject_type,
            subject_id=o.subject_id,
            value=o.value,
            value_type=o.value_type,
            source_type=o.source_type,
            observed_at=o.observed_at,
            payment_event_id=o.payment_event_id,
            webhook_event_id=o.webhook_event_id,
        )
        for o in observations
    ]

    claim_resp = ClaimResponse(
        internal_id=claim.internal_id,
        subject_type=claim.subject_type,
        subject_id=claim.subject_id,
        claim_type=claim.claim_type,
        claim_key=claim.claim_key,
        canonical_value=claim.canonical_value,
        created_at=claim.created_at,
        supporting_evidence_count=len(evidence_items),
    )

    return ClaimEvidenceDetailResponse(
        claim=claim_resp,
        evidence=evidence_items,
    )
