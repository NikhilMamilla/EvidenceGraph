"""
Phase 15 — Evidence Completeness & Coverage Analysis Engine.

Core engine for deterministic evidence completeness and coverage analysis.
Invariants:
- Absence of evidence != Evidence of absence.
- Missing evidence is never asserted as a negative real-world claim or fraud.
- Evaluations reason over reconciled EvidenceFacts (Phase 13) and check Phase 8 conflicts.
- Time-aware: evidence observed after evaluation_time is strictly excluded.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.orm import Session

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
from app.models.evidence_types import EvidenceType
from app.models.observation_fact_link import ObservationFactLink
from app.models.payment import Payment
from app.models.reconciliation_types import FactStatus, FactType
from app.schemas.coverage import (
    CoverageHistoryResponse,
    CoverageRecomputeResponse,
    CoverageResultSchema,
    CoverageSnapshotSummary,
    CoverageSummaryMetrics,
    EvidenceRequirementSchema,
    MissingEvidenceDetail,
    PaymentCoverageResponse,
)


@dataclass(frozen=True)
class RequirementDef:
    requirement_id: str
    base_requirement_type: str
    evidence_type: str
    fact_type: str
    description: str


STANDARD_REQUIREMENTS: List[RequirementDef] = [
    RequirementDef(
        requirement_id="REQ_PAYMENT_CREATION",
        base_requirement_type=RequirementType.REQUIRED,
        evidence_type=EvidenceType.PAYMENT_STATUS,
        fact_type=FactType.PAYMENT_STATUS_OBSERVED,
        description="Evidence that payment was created or initiated.",
    ),
    RequirementDef(
        requirement_id="REQ_PAYMENT_AMOUNT",
        base_requirement_type=RequirementType.REQUIRED,
        evidence_type=EvidenceType.PAYMENT_AMOUNT,
        fact_type=FactType.PAYMENT_AMOUNT_OBSERVED,
        description="Authoritative numerical amount of the payment.",
    ),
    RequirementDef(
        requirement_id="REQ_PAYMENT_CURRENCY",
        base_requirement_type=RequirementType.REQUIRED,
        evidence_type=EvidenceType.PAYMENT_CURRENCY,
        fact_type=FactType.PAYMENT_CURRENCY_OBSERVED,
        description="Authoritative ISO-4217 currency of the payment.",
    ),
    RequirementDef(
        requirement_id="REQ_PAYMENT_METHOD",
        base_requirement_type=RequirementType.EXPECTED,
        evidence_type=EvidenceType.PAYMENT_METHOD,
        fact_type=FactType.PAYMENT_METHOD_OBSERVED,
        description="Payment instrument or method used (card, UPI, netbanking).",
    ),
    RequirementDef(
        requirement_id="REQ_PAYMENT_AUTHORIZED",
        base_requirement_type=RequirementType.EXPECTED,
        evidence_type=EvidenceType.PAYMENT_STATUS,
        fact_type=FactType.PAYMENT_AUTHORIZED,
        description="Gateway authorization evidence prior to capture.",
    ),
    RequirementDef(
        requirement_id="REQ_PAYMENT_CAPTURED",
        base_requirement_type=RequirementType.CONDITIONAL,
        evidence_type=EvidenceType.PAYMENT_STATUS,
        fact_type=FactType.PAYMENT_CAPTURED,
        description="Final settlement or capture confirmation.",
    ),
    RequirementDef(
        requirement_id="REQ_ORDER_LINKAGE",
        base_requirement_type=RequirementType.OPTIONAL,
        evidence_type=EvidenceType.PAYMENT_ORDER_RELATIONSHIP,
        fact_type=FactType.PAYMENT_ORDER_ASSOCIATION,
        description="Merchant order identifier associated with the payment.",
    ),
    RequirementDef(
        requirement_id="REQ_CUSTOMER_LINKAGE",
        base_requirement_type=RequirementType.OPTIONAL,
        evidence_type=EvidenceType.PAYMENT_STATUS,
        fact_type=FactType.PAYMENT_STATUS_OBSERVED,
        description="Customer or contact reference associated with the payment.",
    ),
    RequirementDef(
        requirement_id="REQ_REFUND_RECORD",
        base_requirement_type=RequirementType.CONDITIONAL,
        evidence_type=EvidenceType.PAYMENT_STATUS,
        fact_type=FactType.PAYMENT_REFUNDED,
        description="Refund transaction and reversal evidence.",
    ),
    RequirementDef(
        requirement_id="REQ_FAILURE_REASON",
        base_requirement_type=RequirementType.CONDITIONAL,
        evidence_type=EvidenceType.PAYMENT_STATUS,
        fact_type=FactType.PAYMENT_FAILED,
        description="Provider failure code and descriptive error message.",
    ),
]


def select_evidence_profile(
    payment: Optional[Payment],
    observations: List[EvidenceObservation],
    facts: List[EvidenceFact],
) -> Tuple[str, str]:
    """
    Deterministically selects the applicable evidence profile for a payment.
    Returns (profile_id, profile_version).
    """
    if payment is not None:
        return STANDARD_PAYMENT_PROFILE_ID, PROFILE_VERSION_1

    if any(obs.subject_type == "payment" for obs in observations):
        return STANDARD_PAYMENT_PROFILE_ID, PROFILE_VERSION_1

    if any(f.payment_id for f in facts):
        return STANDARD_PAYMENT_PROFILE_ID, PROFILE_VERSION_1

    return PROFILE_UNKNOWN, "0.0"


def _determine_applicability(
    req: RequirementDef,
    payment: Optional[Payment],
    facts: List[EvidenceFact],
    observations: List[EvidenceObservation],
) -> Tuple[bool, str, str]:
    """
    Determines if a requirement is applicable and its effective requirement type.
    Returns (is_applicable, effective_requirement_type, reason).
    """
    if req.base_requirement_type == RequirementType.REQUIRED:
        return True, RequirementType.REQUIRED, "Mandatory for canonical payment completeness."

    if req.base_requirement_type == RequirementType.EXPECTED:
        return True, RequirementType.EXPECTED, "Standard expectation for typical payment lifecycles."

    if req.base_requirement_type == RequirementType.OPTIONAL:
        return True, RequirementType.OPTIONAL, "Optional enrichment metadata."

    # CONDITIONAL requirements
    if req.requirement_id == "REQ_PAYMENT_CAPTURED":
        is_captured = (
            (payment and payment.captured)
            or (payment and payment.status == "captured")
            or any(f.fact_type == FactType.PAYMENT_CAPTURED for f in facts)
            or any(o.value == "captured" for o in observations)
        )
        if is_captured:
            return True, RequirementType.REQUIRED, "Payment status indicates capture; capture confirmation is required."
        return False, RequirementType.NOT_APPLICABLE, "Payment has not reached captured state."

    if req.requirement_id == "REQ_REFUND_RECORD":
        is_refunded = (
            (payment and "refund" in (payment.status or "").lower())
            or any(f.fact_type == FactType.PAYMENT_REFUNDED for f in facts)
        )
        if is_refunded:
            return True, RequirementType.REQUIRED, "Payment has been refunded; refund reversal evidence is required."
        return False, RequirementType.NOT_APPLICABLE, "No refund lifecycle signals observed for this payment."

    if req.requirement_id == "REQ_FAILURE_REASON":
        is_failed = (
            (payment and payment.status == "failed")
            or any(f.fact_type == FactType.PAYMENT_FAILED for f in facts)
            or any(o.value == "failed" for o in observations)
        )
        if is_failed:
            return True, RequirementType.REQUIRED, "Payment failed; failure diagnostic evidence is required."
        return False, RequirementType.NOT_APPLICABLE, "Payment is not in a failed state."

    return False, RequirementType.NOT_APPLICABLE, "Not applicable for this payment context."


def _evaluate_single_requirement(
    req: RequirementDef,
    is_applicable: bool,
    effective_req_type: str,
    applicability_reason: str,
    facts: List[EvidenceFact],
    observations: List[EvidenceObservation],
    obs_fact_links: List[ObservationFactLink],
    conflicts: List[EvidenceConflict],
    as_of: datetime,
) -> Tuple[CoverageResultSchema, Optional[MissingEvidenceDetail]]:
    """
    Evaluates one requirement against in-scope facts and observations.
    """
    if not is_applicable:
        res = CoverageResultSchema(
            requirement_id=req.requirement_id,
            requirement_type=effective_req_type,
            evidence_type=req.evidence_type,
            fact_type=req.fact_type,
            expected_state=CoverageState.NOT_APPLICABLE,
            observed_state=CoverageState.NOT_APPLICABLE,
            matched_fact_id=None,
            matched_observation_ids=None,
            search_scope_summary="None (Requirement not applicable in current context)",
            explanation=f"Requirement not applicable: {applicability_reason}",
        )
        return res, None

    # Search for matching reconciled facts
    matching_facts = [
        f for f in facts
        if f.fact_type == req.fact_type or (
            req.requirement_id == "REQ_PAYMENT_CREATION"
            and f.fact_type in (FactType.PAYMENT_CAPTURED, FactType.PAYMENT_AUTHORIZED, FactType.PAYMENT_FAILED)
        )
    ]

    # Search for matching observations if fact not present
    matching_obs = [
        o for o in observations
        if o.evidence_type == req.evidence_type or (
            req.requirement_id in ("REQ_PAYMENT_CREATION", "REQ_PAYMENT_CAPTURED", "REQ_PAYMENT_AUTHORIZED", "REQ_FAILURE_REASON")
            and o.evidence_type == EvidenceType.PAYMENT_STATUS
        )
    ]

    # Check for conflicts involving this evidence
    has_conflict = any(
        c.status == "OPEN" and (
            c.conflict_type in ("VALUE_MISMATCH", "TEMPORAL_INCONSISTENCY")
        )
        for c in conflicts
    )

    if matching_facts:
        fact = matching_facts[0]
        # Find observation IDs linked to this fact
        linked_obs_ids = [
            link.observation_id
            for link in obs_fact_links
            if link.fact_id == fact.internal_id
        ]
        if not linked_obs_ids:
            linked_obs_ids = [o.internal_id for o in matching_obs]

        if has_conflict:
            observed_state = CoverageState.CONFLICTED
            exp = (
                f"Evidence fact #{fact.internal_id} for {req.fact_type} is present but has open contradictions "
                f"or consistency issues detected."
            )
        elif fact.status in (FactStatus.INVALIDATED, FactStatus.SUPERSEDED) or not fact.canonical_value:
            observed_state = CoverageState.PARTIAL
            exp = f"Evidence fact #{fact.internal_id} is present but contains partial or inactive status."
        else:
            observed_state = CoverageState.PRESENT
            exp = (
                f"Authoritative evidence fact #{fact.internal_id} ({fact.fact_type}) observed with "
                f"{fact.observation_count} observation(s)."
            )

        res = CoverageResultSchema(
            requirement_id=req.requirement_id,
            requirement_type=effective_req_type,
            evidence_type=req.evidence_type,
            fact_type=req.fact_type,
            expected_state=CoverageState.PRESENT,
            observed_state=observed_state,
            matched_fact_id=fact.internal_id,
            matched_observation_ids=linked_obs_ids or None,
            search_scope_summary=f"Reconciled facts & observations for payment before {as_of.isoformat()}",
            explanation=exp,
        )
        return res, None

    elif matching_obs:
        # Observation exists but not yet reconciled into a Fact
        obs_ids = [o.internal_id for o in matching_obs]
        observed_state = CoverageState.PARTIAL
        exp = (
            f"Observation(s) {obs_ids} observed for {req.evidence_type}, but no reconciled Fact "
            f"has been established."
        )
        res = CoverageResultSchema(
            requirement_id=req.requirement_id,
            requirement_type=effective_req_type,
            evidence_type=req.evidence_type,
            fact_type=req.fact_type,
            expected_state=CoverageState.PRESENT,
            observed_state=observed_state,
            matched_fact_id=None,
            matched_observation_ids=obs_ids,
            search_scope_summary=f"Observations for payment before {as_of.isoformat()}",
            explanation=exp,
        )
        return res, None

    else:
        # Missing evidence
        observed_state = CoverageState.MISSING
        search_scope = f"Searched EvidenceFacts & EvidenceObservations for payment prior to {as_of.isoformat()}"
        exp = (
            f"Evidence expected under {effective_req_type} priority for {req.description.lower()} "
            f"was not observed prior to evaluation time."
        )
        res = CoverageResultSchema(
            requirement_id=req.requirement_id,
            requirement_type=effective_req_type,
            evidence_type=req.evidence_type,
            fact_type=req.fact_type,
            expected_state=CoverageState.PRESENT,
            observed_state=observed_state,
            matched_fact_id=None,
            matched_observation_ids=None,
            search_scope_summary=search_scope,
            explanation=exp,
        )
        missing_detail = MissingEvidenceDetail(
            requirement_id=req.requirement_id,
            requirement_type=effective_req_type,
            evidence_type=req.evidence_type,
            fact_type=req.fact_type,
            why_expected=applicability_reason,
            search_scope=search_scope,
            search_result="No qualifying evidence observation or fact found.",
            explanation=exp,
        )
        return res, missing_detail


def _compute_overall_status(
    total_applicable: int,
    req_present: int,
    req_missing: int,
    exp_present: int,
    exp_missing: int,
    conflicted: int,
    unknown: int,
    profile_id: str,
) -> str:
    """
    Computes overall deterministic coverage status.
    """
    if profile_id == PROFILE_UNKNOWN or total_applicable == 0:
        return CoverageStatus.UNKNOWN

    if req_missing > 0:
        # If any mandatory requirement is completely missing
        if req_present == 0:
            return CoverageStatus.INSUFFICIENT
        return CoverageStatus.PARTIAL

    if conflicted > 0:
        return CoverageStatus.PARTIAL

    if exp_missing > 0:
        # All required present, but some expected missing
        return CoverageStatus.SUBSTANTIALLY_COMPLETE

    return CoverageStatus.COMPLETE


def evaluate_coverage(
    db: Session,
    payment_id: str,
    as_of: Optional[datetime] = None,
    profile_id: Optional[str] = None,
    persist: bool = True,
) -> PaymentCoverageResponse:
    """
    Evaluates evidence coverage and completeness for a payment as of a given timestamp.
    """
    evaluation_time = as_of or datetime.now(timezone.utc)

    # 1. Fetch Payment anchor
    payment: Optional[Payment] = db.execute(
        select(Payment).where(Payment.razorpay_payment_id == payment_id)
    ).scalar_one_or_none()

    # 2. Fetch Observations observed_at <= evaluation_time
    observations = list(
        db.execute(
            select(EvidenceObservation)
            .where(
                EvidenceObservation.subject_id == payment_id,
                EvidenceObservation.observed_at <= evaluation_time,
            )
            .order_by(EvidenceObservation.observed_at)
        ).scalars().all()
    )

    # 3. Fetch Reconciled Facts first_observed_at <= evaluation_time
    facts = list(
        db.execute(
            select(EvidenceFact)
            .where(
                EvidenceFact.payment_id == payment_id,
                EvidenceFact.first_observed_at <= evaluation_time,
            )
            .order_by(EvidenceFact.first_observed_at)
        ).scalars().all()
    )

    # 4. Fetch ObservationFactLinks for in-scope facts
    fact_ids = [f.internal_id for f in facts]
    obs_fact_links = []
    if fact_ids:
        obs_fact_links = list(
            db.execute(
                select(ObservationFactLink).where(
                    ObservationFactLink.fact_id.in_(fact_ids)
                )
            ).scalars().all()
        )

    # 5. Fetch Open Conflicts detected <= evaluation_time
    conflicts = list(
        db.execute(
            select(EvidenceConflict).where(
                EvidenceConflict.payment_id == payment_id,
                EvidenceConflict.detected_at <= evaluation_time,
            )
        ).scalars().all()
    )

    # 6. Profile Selection
    selected_profile_id, selected_profile_version = select_evidence_profile(
        payment=payment, observations=observations, facts=facts
    )
    if profile_id and profile_id != selected_profile_id:
        # Override only if requested and valid
        selected_profile_id = profile_id

    # 7. Requirements Evaluation
    if selected_profile_id == PROFILE_UNKNOWN:
        req_results = []
        missing_evidence = []
        overall_status = CoverageStatus.UNKNOWN
        metrics = CoverageSummaryMetrics(
            total_applicable=0,
            required_present=0,
            required_missing=0,
            expected_present=0,
            expected_missing=0,
            optional_present=0,
            conflicted=0,
            unknown=1,
            not_applicable=0,
        )
        explanation_str = "No applicable evidence profile could be deterministically selected for this payment."
    else:
        req_results: List[CoverageResultSchema] = []
        missing_evidence: List[MissingEvidenceDetail] = []

        total_applicable = 0
        req_present = 0
        req_missing = 0
        exp_present = 0
        exp_missing = 0
        opt_present = 0
        conflicted_cnt = 0
        unknown_cnt = 0
        na_cnt = 0

        for req in STANDARD_REQUIREMENTS:
            is_app, eff_type, app_reason = _determine_applicability(
                req=req, payment=payment, facts=facts, observations=observations
            )
            res_schema, miss_detail = _evaluate_single_requirement(
                req=req,
                is_applicable=is_app,
                effective_req_type=eff_type,
                applicability_reason=app_reason,
                facts=facts,
                observations=observations,
                obs_fact_links=obs_fact_links,
                conflicts=conflicts,
                as_of=evaluation_time,
            )
            req_results.append(res_schema)
            if miss_detail:
                missing_evidence.append(miss_detail)

            if is_app:
                total_applicable += 1
                if res_schema.observed_state == CoverageState.CONFLICTED:
                    conflicted_cnt += 1
                elif res_schema.observed_state == CoverageState.PRESENT:
                    if eff_type == RequirementType.REQUIRED:
                        req_present += 1
                    elif eff_type == RequirementType.EXPECTED:
                        exp_present += 1
                    elif eff_type == RequirementType.OPTIONAL:
                        opt_present += 1
                elif res_schema.observed_state == CoverageState.MISSING:
                    if eff_type == RequirementType.REQUIRED:
                        req_missing += 1
                    elif eff_type == RequirementType.EXPECTED:
                        exp_missing += 1
                elif res_schema.observed_state == CoverageState.UNKNOWN:
                    unknown_cnt += 1
            else:
                na_cnt += 1

        overall_status = _compute_overall_status(
            total_applicable=total_applicable,
            req_present=req_present,
            req_missing=req_missing,
            exp_present=exp_present,
            exp_missing=exp_missing,
            conflicted=conflicted_cnt,
            unknown=unknown_cnt,
            profile_id=selected_profile_id,
        )

        metrics = CoverageSummaryMetrics(
            total_applicable=total_applicable,
            required_present=req_present,
            required_missing=req_missing,
            expected_present=exp_present,
            expected_missing=exp_missing,
            optional_present=opt_present,
            conflicted=conflicted_cnt,
            unknown=unknown_cnt,
            not_applicable=na_cnt,
        )

        if overall_status == CoverageStatus.COMPLETE:
            explanation_str = "All required and expected evidence is present with full coverage."
        elif overall_status == CoverageStatus.SUBSTANTIALLY_COMPLETE:
            explanation_str = f"All required evidence is present; {exp_missing} expected requirement(s) unobserved."
        elif overall_status == CoverageStatus.PARTIAL:
            explanation_str = f"Partial coverage: {req_missing} required requirement(s) missing or conflicted."
        elif overall_status == CoverageStatus.INSUFFICIENT:
            explanation_str = f"Insufficient coverage: critical lifecycle evidence is missing."
        else:
            explanation_str = "Coverage evaluation status unknown."

    # 8. Idempotent Persistence (if requested)
    if persist and selected_profile_id != PROFILE_UNKNOWN:
        # Check if snapshot for this exact tuple already exists
        existing_snap = db.execute(
            select(EvidenceCoverageSnapshot).where(
                EvidenceCoverageSnapshot.payment_id == payment_id,
                EvidenceCoverageSnapshot.evaluated_at == evaluation_time,
                EvidenceCoverageSnapshot.profile_version == selected_profile_version,
                EvidenceCoverageSnapshot.methodology_version == COVERAGE_METHODOLOGY_VERSION,
            )
        ).scalar_one_or_none()

        if existing_snap is None:
            new_snap = EvidenceCoverageSnapshot(
                payment_id=payment_id,
                evaluated_at=evaluation_time,
                profile_id=selected_profile_id,
                profile_version=selected_profile_version,
                methodology_version=COVERAGE_METHODOLOGY_VERSION,
                overall_coverage_status=overall_status,
                total_applicable_requirements=metrics.total_applicable,
                required_present_count=metrics.required_present,
                required_missing_count=metrics.required_missing,
                expected_present_count=metrics.expected_present,
                expected_missing_count=metrics.expected_missing,
                optional_present_count=metrics.optional_present,
                conflicted_count=metrics.conflicted,
                unknown_count=metrics.unknown,
                not_applicable_count=metrics.not_applicable,
                summary_explanation={
                    "status": overall_status,
                    "explanation": explanation_str,
                    "metrics": metrics.model_dump(),
                },
            )
            db.add(new_snap)
            db.flush()

            for r in req_results:
                res_model = EvidenceCoverageResult(
                    snapshot_id=new_snap.internal_id,
                    payment_id=payment_id,
                    requirement_id=r.requirement_id,
                    requirement_type=r.requirement_type,
                    evidence_type=r.evidence_type,
                    fact_type=r.fact_type,
                    expected_state=r.expected_state,
                    observed_state=r.observed_state,
                    matched_fact_id=r.matched_fact_id,
                    matched_observation_ids=r.matched_observation_ids,
                    search_scope_summary=r.search_scope_summary,
                    explanation=r.explanation,
                )
                db.add(res_model)
            db.commit()

    return PaymentCoverageResponse(
        payment_id=payment_id,
        profile_id=selected_profile_id,
        profile_version=selected_profile_version,
        methodology_version=COVERAGE_METHODOLOGY_VERSION,
        overall_coverage_status=overall_status,
        evaluated_at=evaluation_time,
        metrics=metrics,
        results=req_results,
        missing_evidence=missing_evidence,
        explanation=explanation_str,
        evaluation_context={
            "observations_in_scope": len(observations),
            "facts_in_scope": len(facts),
            "conflicts_in_scope": len(conflicts),
            "as_of": evaluation_time.isoformat(),
        },
    )


def get_coverage_history(
    db: Session, payment_id: str
) -> CoverageHistoryResponse:
    """
    Returns historical coverage snapshots for a payment, ordered chronologically.
    """
    snapshots = list(
        db.execute(
            select(EvidenceCoverageSnapshot)
            .where(EvidenceCoverageSnapshot.payment_id == payment_id)
            .order_by(EvidenceCoverageSnapshot.evaluated_at.asc())
        ).scalars().all()
    )

    summaries = [
        CoverageSnapshotSummary(
            internal_id=s.internal_id,
            payment_id=s.payment_id,
            evaluated_at=s.evaluated_at,
            profile_id=s.profile_id,
            profile_version=s.profile_version,
            methodology_version=s.methodology_version,
            overall_coverage_status=s.overall_coverage_status,
            total_applicable_requirements=s.total_applicable_requirements,
            required_present_count=s.required_present_count,
            required_missing_count=s.required_missing_count,
            expected_present_count=s.expected_present_count,
            expected_missing_count=s.expected_missing_count,
            conflicted_count=s.conflicted_count,
        )
        for s in snapshots
    ]

    return CoverageHistoryResponse(
        payment_id=payment_id,
        history=summaries,
        total=len(summaries),
    )
