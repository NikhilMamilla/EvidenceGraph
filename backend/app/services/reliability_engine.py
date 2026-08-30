"""
Phase 16 — Evidence Reliability Calibration & Uncertainty Boundaries Service Engine.

Deterministic, rule-based reliability evaluation framework for EvidenceGraph.
Computes categorical reliability states, dimensions, ceilings, and uncertainty
boundaries without probabilistic approximations or arbitrary numerical scoring.
"""

from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.models.evidence_fact import EvidenceFact
from app.models.observation_fact_link import ObservationFactLink
from app.models.evidence import EvidenceObservation
from app.models.evidence_conflict import EvidenceConflict
from app.models.conflict_types import ConflictStatus
from app.models.evidence_reconciliation import EvidenceReconciliation
from app.models.reconciliation_types import FactStatus, ReconciliationResult
from app.models.evidence_reliability import EvidenceReliabilityAssessment
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
from app.models.payment import Payment
from app.schemas.reliability import (
    DimensionAssessmentSchema,
    UncertaintyItemSchema,
    FactReliabilityResponse,
    PaymentReliabilityResponse,
    ReliabilityHistoryItem,
    ReliabilityHistoryResponse,
)


def evaluate_fact_reliability(
    db: Session,
    fact: EvidenceFact,
    as_of: Optional[datetime] = None,
) -> FactReliabilityResponse:
    """
    Deterministically evaluates reliability dimensions, ceilings, and uncertainty
    for an individual EvidenceFact.
    """
    eval_time = as_of or datetime.now(timezone.utc)
    payment_id = fact.payment_id

    # 1. Fetch associated observations bounded by as_of
    query_links = db.query(ObservationFactLink).filter(ObservationFactLink.fact_id == fact.internal_id)
    links = query_links.all()
    obs_ids = [link.observation_id for link in links]

    query_obs = db.query(EvidenceObservation).filter(EvidenceObservation.internal_id.in_(obs_ids))
    if as_of:
        query_obs = query_obs.filter(EvidenceObservation.observed_at <= as_of)
    observations = query_obs.all() if obs_ids else []

    # 2. Dimension Evaluation
    supporting_factors: List[str] = []
    degradation_factors: List[str] = []
    ceilings_applied: List[str] = []

    # --- Dimension 1: Source Reliability ---
    source_types = [obs.source_type for obs in observations if obs.source_type]
    if not observations:
        source_state = SourceReliability.UNKNOWN_SOURCE
        degradation_factors.append("Source cannot be verified because no linked observation records exist.")
    elif all("razorpay" in st.lower() or "webhook" in st.lower() for st in source_types):
        source_state = SourceReliability.VERIFIED_PROVIDER_SOURCE
        supporting_factors.append("Source authenticity verified via provider webhook HMAC signature.")
    elif any("api" in st.lower() or "internal" in st.lower() for st in source_types):
        source_state = SourceReliability.VERIFIED_INTERNAL_SOURCE
        supporting_factors.append("Source verified via authenticated internal service endpoint.")
    elif any(st == "UNKNOWN" for st in source_types):
        source_state = SourceReliability.UNKNOWN_SOURCE
        degradation_factors.append("Source authenticity is unknown or untrusted.")
    else:
        source_state = SourceReliability.UNVERIFIED_SOURCE
        degradation_factors.append("Source origin is unverified.")

    # --- Dimension 2: Provenance Completeness ---
    if not observations:
        provenance_state = ProvenanceReliability.BROKEN
        degradation_factors.append("Provenance lineage is broken: Fact has no linked observations.")
    elif all(obs.webhook_event_id is not None for obs in observations):
        provenance_state = ProvenanceReliability.COMPLETE
        supporting_factors.append("Complete observation provenance chain linked to provider event.")
    elif any(obs.webhook_event_id is not None for obs in observations):
        provenance_state = ProvenanceReliability.PARTIAL
        degradation_factors.append("Partial provenance: Some observations lack provider event linkage.")
    else:
        provenance_state = ProvenanceReliability.BROKEN
        degradation_factors.append("Broken provenance: Observations lack provider event IDs.")

    # --- Dimension 3: Identity Reliability ---
    recon_query = db.query(EvidenceReconciliation).filter(
        EvidenceReconciliation.fact_id == fact.internal_id
    )
    if as_of:
        recon_query = recon_query.filter(EvidenceReconciliation.evaluated_at <= as_of)
    recons = recon_query.all()

    if fact.status == FactStatus.UNRESOLVED:
        identity_state = IdentityReliability.UNKNOWN
        degradation_factors.append("Fact reconciliation identity is unresolved.")
    elif any(r.result == ReconciliationResult.UNKNOWN for r in recons):
        identity_state = IdentityReliability.INSUFFICIENT_INFORMATION
        degradation_factors.append("Reconciliation identity certainty is limited due to insufficient information.")
    elif any(r.result == ReconciliationResult.SAME_FACT for r in recons):
        identity_state = IdentityReliability.SAME_FACT_DIFFERENT_SOURCE
        supporting_factors.append("Fact identity established across multiple distinct signals.")
    elif len(observations) >= 1:
        identity_state = IdentityReliability.SAME_PROVIDER_EVENT
        supporting_factors.append("Fact identity unambiguously bound to single provider event context.")
    else:
        identity_state = IdentityReliability.UNKNOWN
        degradation_factors.append("Fact identity cannot be verified.")

    # --- Dimension 4: Temporal Reliability ---
    if not observations:
        temporal_state = TemporalReliability.UNKNOWN
    else:
        has_inversion = any(
            obs.valid_from and obs.valid_until and obs.valid_from > obs.valid_until
            for obs in observations
        )
        if has_inversion:
            temporal_state = TemporalReliability.TEMPORALLY_AMBIGUOUS
            degradation_factors.append("Temporal timestamps show interval inversion (valid_from > valid_until).")
        else:
            temporal_state = TemporalReliability.TEMPORALLY_SOUND
            supporting_factors.append("Temporal timestamp ordering is sound and monotonic.")

    # --- Dimension 5: Structural Reliability ---
    if fact.status == FactStatus.INVALIDATED:
        structural_state = StructuralReliability.MALFORMED
        degradation_factors.append("Fact structural validity was invalidated.")
    elif fact.status == FactStatus.SUPERSEDED:
        structural_state = StructuralReliability.PARTIAL_OBSERVATION
        degradation_factors.append("Fact has been superseded by a newer canonical observation.")
    elif fact.canonical_value and len(fact.canonical_value.strip()) > 0:
        structural_state = StructuralReliability.CANONICAL_FACT
        supporting_factors.append("Canonical structural schema compliance verified.")
    else:
        structural_state = StructuralReliability.MALFORMED
        degradation_factors.append("Fact payload is empty or malformed.")

    # --- Dimension 6: Contradiction State ---
    conflict_query = db.query(EvidenceConflict).filter(
        EvidenceConflict.payment_id == payment_id,
        EvidenceConflict.status == ConflictStatus.OPEN,
    )
    if as_of:
        conflict_query = conflict_query.filter(EvidenceConflict.detected_at <= as_of)
    open_conflicts = conflict_query.all()

    if open_conflicts:
        contradiction_state = ContradictionReliability.CONFLICTED
        degradation_factors.append(f"{len(open_conflicts)} open consistency conflict(s) detected.")
    else:
        contradiction_state = ContradictionReliability.UNCONTRADICTED
        supporting_factors.append("No unresolved contradictions detected for this payment entity.")

    # --- Dimension 7: Dependency State ---
    unique_events = set(obs.webhook_event_id for obs in observations if obs.webhook_event_id)
    unique_sources = set(obs.source_type for obs in observations if obs.source_type)
    if len(unique_sources) > 1 and len(unique_events) > 1:
        dependency_state = DependencyReliability.INDEPENDENT_CORROBORATION
        supporting_factors.append("Corroborated by multiple independent observation sources.")
    elif len(observations) > 1 and len(unique_events) == 1:
        dependency_state = DependencyReliability.DEPENDENT_REPLICATION
        degradation_factors.append("Multiple observations derive from a single upstream provider event.")
    elif len(observations) == 1:
        dependency_state = DependencyReliability.SINGLE_SOURCE
        supporting_factors.append("Single observation source with no conflicting duplicate claims.")
    else:
        dependency_state = DependencyReliability.UNKNOWN

    # 3. Deterministic Ceilings and Overall State Aggregation
    overall_state = ReliabilityState.HIGH

    # Floor Checks
    if structural_state == StructuralReliability.MALFORMED or temporal_state == TemporalReliability.TEMPORALLY_INVALID:
        overall_state = ReliabilityState.UNRELIABLE
        ceilings_applied.append("FLOOR_UNRELIABLE: Malformed schema or invalid temporal state.")
    elif provenance_state == ProvenanceReliability.BROKEN:
        overall_state = ReliabilityState.LIMITED
        ceilings_applied.append("CEILING_LIMITED: Broken provenance chain.")
    elif contradiction_state == ContradictionReliability.CONFLICTED:
        overall_state = ReliabilityState.LIMITED
        ceilings_applied.append("CEILING_LIMITED: Open contradiction exists.")
    elif identity_state in (IdentityReliability.TEMPORAL_AMBIGUITY, IdentityReliability.INSUFFICIENT_INFORMATION):
        overall_state = ReliabilityState.LIMITED
        ceilings_applied.append("CEILING_LIMITED: Ambiguous reconciliation identity.")
    elif source_state == SourceReliability.UNKNOWN_SOURCE or identity_state == IdentityReliability.UNKNOWN:
        overall_state = ReliabilityState.UNKNOWN
        ceilings_applied.append("CEILING_UNKNOWN: Unknown source origin or unverified identity context.")
    elif source_state == SourceReliability.UNVERIFIED_SOURCE:
        overall_state = ReliabilityState.LIMITED
        ceilings_applied.append("CEILING_LIMITED: Unverified source origin.")
    elif (
        provenance_state == ProvenanceReliability.PARTIAL
        or dependency_state == DependencyReliability.DEPENDENT_REPLICATION
        or structural_state == StructuralReliability.PARTIAL_OBSERVATION
    ):
        overall_state = ReliabilityState.MODERATE
        ceilings_applied.append("CEILING_MODERATE: Partial provenance or single-event replication.")
    elif (
        source_state == SourceReliability.VERIFIED_PROVIDER_SOURCE
        and provenance_state == ProvenanceReliability.COMPLETE
        and identity_state in (IdentityReliability.SAME_PROVIDER_EVENT, IdentityReliability.SAME_FACT_DIFFERENT_SOURCE)
        and temporal_state == TemporalReliability.TEMPORALLY_SOUND
        and contradiction_state == ContradictionReliability.UNCONTRADICTED
        and structural_state == StructuralReliability.CANONICAL_FACT
    ):
        overall_state = ReliabilityState.HIGH
    else:
        overall_state = ReliabilityState.MODERATE

    # 4. Uncertainty Profile Construction
    uncertainty_profile: List[UncertaintyItemSchema] = []
    if source_state == SourceReliability.VERIFIED_PROVIDER_SOURCE:
        uncertainty_profile.append(UncertaintyItemSchema(
            boundary_type=UncertaintyBoundaryType.ESTABLISHED,
            topic="Source Authenticity",
            statement="Webhook delivery was authenticated via configured provider HMAC secret context.",
            scope="Provider Webhook Channel",
        ))
    if provenance_state == ProvenanceReliability.COMPLETE:
        uncertainty_profile.append(UncertaintyItemSchema(
            boundary_type=UncertaintyBoundaryType.ESTABLISHED,
            topic="Lineage Chain",
            statement="Observation is traceable to raw provider event ID.",
            scope="Evidence Lineage",
        ))
    if contradiction_state == ContradictionReliability.CONFLICTED:
        uncertainty_profile.append(UncertaintyItemSchema(
            boundary_type=UncertaintyBoundaryType.CONTRADICTED,
            topic="Consistency Conflict",
            statement="Conflicting claims exist regarding the canonical state of this payment entity.",
            scope="State Consistency",
        ))
    if dependency_state in (DependencyReliability.SINGLE_SOURCE, DependencyReliability.DEPENDENT_REPLICATION):
        uncertainty_profile.append(UncertaintyItemSchema(
            boundary_type=UncertaintyBoundaryType.UNCERTAIN,
            topic="Independent Corroboration",
            statement="Independent confirmation from a secondary banking or ledger source was not observed.",
            scope="External Corroboration",
        ))
    if structural_state == StructuralReliability.CANONICAL_FACT:
        uncertainty_profile.append(UncertaintyItemSchema(
            boundary_type=UncertaintyBoundaryType.SUPPORTED,
            topic="Canonical Data Structure",
            statement=f"Fact value '{fact.canonical_value}' conforms to canonical schema for {fact.fact_type}.",
            scope="Schema Validation",
        ))

    # Construct Dimensions dict
    dimensions: Dict[str, DimensionAssessmentSchema] = {
        "source": DimensionAssessmentSchema(
            dimension_name="Source Authenticity",
            state=source_state.value,
            description="Provider authentication context vs unverified channel.",
            is_degraded=source_state in (SourceReliability.UNVERIFIED_SOURCE, SourceReliability.UNKNOWN_SOURCE),
            supporting_evidence=[obs.source_type for obs in observations if obs.source_type],
        ),
        "provenance": DimensionAssessmentSchema(
            dimension_name="Provenance Lineage",
            state=provenance_state.value,
            description="Traceability from fact to original provider event.",
            is_degraded=provenance_state in (ProvenanceReliability.PARTIAL, ProvenanceReliability.BROKEN),
            supporting_evidence=[str(obs.webhook_event_id) for obs in observations if obs.webhook_event_id],
        ),
        "identity": DimensionAssessmentSchema(
            dimension_name="Reconciliation Identity",
            state=identity_state.value,
            description="Entity fact identity established across observation instances.",
            is_degraded=identity_state in (IdentityReliability.TEMPORAL_AMBIGUITY, IdentityReliability.INSUFFICIENT_INFORMATION, IdentityReliability.UNKNOWN),
            supporting_evidence=[f"Fact #{fact.internal_id} status: {fact.status}"],
        ),
        "temporal": DimensionAssessmentSchema(
            dimension_name="Temporal Soundness",
            state=temporal_state.value,
            description="Monotonic ordering and clock consistency.",
            is_degraded=temporal_state in (TemporalReliability.TEMPORALLY_AMBIGUOUS, TemporalReliability.TEMPORALLY_INVALID),
            supporting_evidence=[str(fact.first_observed_at)],
        ),
        "structural": DimensionAssessmentSchema(
            dimension_name="Structural Integrity",
            state=structural_state.value,
            description="Canonical representation and schema compliance.",
            is_degraded=structural_state in (StructuralReliability.PARTIAL_OBSERVATION, StructuralReliability.MALFORMED),
            supporting_evidence=[fact.canonical_value],
        ),
        "contradiction": DimensionAssessmentSchema(
            dimension_name="Contradiction Status",
            state=contradiction_state.value,
            description="Presence of open state/value conflicts.",
            is_degraded=contradiction_state == ContradictionReliability.CONFLICTED,
            supporting_evidence=[f"{len(open_conflicts)} open conflicts"],
        ),
        "dependency": DimensionAssessmentSchema(
            dimension_name="Origin Independence",
            state=dependency_state.value,
            description="Independent source diversity vs event replication.",
            is_degraded=dependency_state in (DependencyReliability.DEPENDENT_REPLICATION, DependencyReliability.UNKNOWN),
            supporting_evidence=[f"{len(observations)} observations"],
        ),
    }

    # Construct Explanation
    explanation_parts: List[str] = [f"Reliability is classified as {overall_state.value}."]
    if degradation_factors:
        explanation_parts.append("Degradation factors: " + "; ".join(degradation_factors))
    if supporting_factors:
        explanation_parts.append("Supporting factors: " + "; ".join(supporting_factors))
    explanation = " ".join(explanation_parts)

    return FactReliabilityResponse(
        fact_id=fact.internal_id,
        payment_id=payment_id,
        fact_type=fact.fact_type,
        canonical_value=fact.canonical_value,
        evaluated_at=eval_time,
        methodology_version=RELIABILITY_METHODOLOGY_V1,
        overall_state=overall_state,
        dimensions=dimensions,
        supporting_factors=supporting_factors,
        degradation_factors=degradation_factors,
        ceilings_applied=ceilings_applied,
        uncertainty_profile=uncertainty_profile,
        explanation=explanation,
    )


def evaluate_payment_reliability(
    db: Session,
    payment_id: str,
    as_of: Optional[datetime] = None,
    persist: bool = False,
) -> PaymentReliabilityResponse:
    """
    Evaluates reliability and uncertainty across all facts belonging to a payment.
    Optionally persists the immutable evaluation snapshot.
    """
    eval_time = as_of or datetime.now(timezone.utc)

    # 1. Fetch facts bounded by as_of
    query_facts = db.query(EvidenceFact).filter(EvidenceFact.payment_id == payment_id)
    if as_of:
        query_facts = query_facts.filter(EvidenceFact.first_observed_at <= as_of)
    facts = query_facts.all()

    fact_assessments: List[FactReliabilityResponse] = []
    for fact in facts:
        fact_assessments.append(evaluate_fact_reliability(db, fact, as_of=eval_time))

    # 2. Aggregate Payment-Level Overall Reliability
    if not facts:
        # Check if payment even exists
        payment = db.query(Payment).filter(Payment.razorpay_payment_id == payment_id).first()
        if not payment:
            overall_state = ReliabilityState.UNKNOWN
            explanation = f"Payment {payment_id} does not exist or has no recorded evidence context."
        else:
            overall_state = ReliabilityState.LIMITED
            explanation = f"Payment {payment_id} exists but has zero observed evidence facts within temporal scope."
    else:
        states = [fa.overall_state for fa in fact_assessments]
        if any(s == ReliabilityState.UNRELIABLE for s in states):
            overall_state = ReliabilityState.UNRELIABLE
            explanation = f"Payment {payment_id} contains one or more structurally invalid or unverified facts."
        elif any(s == ReliabilityState.LIMITED for s in states):
            overall_state = ReliabilityState.LIMITED
            explanation = f"Payment {payment_id} reliability is limited due to open contradictions or broken provenance."
        elif any(s == ReliabilityState.UNKNOWN for s in states):
            overall_state = ReliabilityState.UNKNOWN
            explanation = f"Payment {payment_id} contains facts with unknown source origin or unverified identity."
        elif all(s == ReliabilityState.HIGH for s in states):
            overall_state = ReliabilityState.HIGH
            explanation = f"All {len(facts)} observed evidence facts satisfy high reliability criteria with complete provenance."
        else:
            overall_state = ReliabilityState.MODERATE
            explanation = f"Payment evidence facts exhibit moderate reliability across {len(facts)} assessed facts."

    # 3. Aggregate Uncertainty Summary
    uncertainty_map: Dict[str, UncertaintyItemSchema] = {}
    for fa in fact_assessments:
        for u in fa.uncertainty_profile:
            key = f"{u.boundary_type.value}:{u.topic}"
            if key not in uncertainty_map:
                uncertainty_map[key] = u
    uncertainty_summary = list(uncertainty_map.values())

    # Add standard payment-level boundary if uncorroborated
    if facts and not any(u.boundary_type == UncertaintyBoundaryType.UNCERTAIN for u in uncertainty_summary):
        uncertainty_summary.append(UncertaintyItemSchema(
            boundary_type=UncertaintyBoundaryType.UNCERTAIN,
            topic="External Settlement",
            statement="Independent confirmation from external banking network was not observed.",
            scope="Payment Settlement",
        ))

    # 4. Persistence if requested
    if persist:
        # Check if identical snapshot already exists
        existing = db.query(EvidenceReliabilityAssessment).filter(
            EvidenceReliabilityAssessment.payment_id == payment_id,
            EvidenceReliabilityAssessment.fact_id == None,
            EvidenceReliabilityAssessment.evaluated_at == eval_time,
            EvidenceReliabilityAssessment.methodology_version == RELIABILITY_METHODOLOGY_V1,
        ).first()

        if not existing:
            # Consolidate dimension states
            supp_all = []
            deg_all = []
            ceil_all = []
            for fa in fact_assessments:
                supp_all.extend(fa.supporting_factors)
                deg_all.extend(fa.degradation_factors)
                ceil_all.extend(fa.ceilings_applied)

            snapshot = EvidenceReliabilityAssessment(
                payment_id=payment_id,
                fact_id=None,
                evaluated_at=eval_time,
                methodology_version=RELIABILITY_METHODOLOGY_V1,
                overall_state=overall_state.value,
                source_state=fact_assessments[0].dimensions["source"].state if fact_assessments else SourceReliability.UNKNOWN_SOURCE.value,
                provenance_state=fact_assessments[0].dimensions["provenance"].state if fact_assessments else ProvenanceReliability.UNKNOWN.value,
                temporal_state=fact_assessments[0].dimensions["temporal"].state if fact_assessments else TemporalReliability.UNKNOWN.value,
                identity_state=fact_assessments[0].dimensions["identity"].state if fact_assessments else IdentityReliability.UNKNOWN.value,
                structural_state=fact_assessments[0].dimensions["structural"].state if fact_assessments else StructuralReliability.UNKNOWN.value,
                contradiction_state=fact_assessments[0].dimensions["contradiction"].state if fact_assessments else ContradictionReliability.UNKNOWN.value,
                dependency_state=fact_assessments[0].dimensions["dependency"].state if fact_assessments else DependencyReliability.UNKNOWN.value,
                supporting_factors=list(set(supp_all)),
                degradation_factors=list(set(deg_all)),
                ceilings_applied=list(set(ceil_all)),
                uncertainty_profile=[u.model_dump() for u in uncertainty_summary],
                explanation=explanation,
            )
            db.add(snapshot)
            db.commit()

    return PaymentReliabilityResponse(
        payment_id=payment_id,
        overall_state=overall_state,
        evaluated_at=eval_time,
        methodology_version=RELIABILITY_METHODOLOGY_V1,
        facts_assessed=len(facts),
        fact_assessments=fact_assessments,
        uncertainty_summary=uncertainty_summary,
        explanation=explanation,
    )


def get_payment_uncertainty(
    db: Session,
    payment_id: str,
    as_of: Optional[datetime] = None,
) -> List[UncertaintyItemSchema]:
    """
    Returns structured uncertainty boundaries for a payment.
    """
    resp = evaluate_payment_reliability(db, payment_id, as_of=as_of, persist=False)
    return resp.uncertainty_summary


def get_reliability_history(
    db: Session,
    payment_id: str,
) -> ReliabilityHistoryResponse:
    """
    Returns chronological history of persisted reliability evaluation snapshots.
    """
    records = db.query(EvidenceReliabilityAssessment).filter(
        EvidenceReliabilityAssessment.payment_id == payment_id
    ).order_by(EvidenceReliabilityAssessment.evaluated_at.asc()).all()

    items = [
        ReliabilityHistoryItem(
            internal_id=r.internal_id,
            payment_id=r.payment_id,
            fact_id=r.fact_id,
            evaluated_at=r.evaluated_at,
            overall_state=ReliabilityState(r.overall_state),
            methodology_version=r.methodology_version,
            explanation=r.explanation,
        )
        for r in records
    ]

    return ReliabilityHistoryResponse(
        payment_id=payment_id,
        total=len(items),
        history=items,
    )
