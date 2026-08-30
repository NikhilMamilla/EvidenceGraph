"""
Phase 18 — Differential Evidence Decision Analysis Engine.

Performs point-to-point differential analysis between two historical evaluation
moments (T1 and T2) for a payment. Produces structured, categorical diffs across
evidence facts, sources, corroboration, conflicts, coverage, reliability, and
integrity dimensions, paired with a deterministic, non-LLM change explanation chain.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

from sqlalchemy.orm import Session

from app.models.conflict_types import ConflictStatus
from app.models.evidence import EvidenceObservation
from app.models.evidence_fact import EvidenceFact
from app.models.replay_types import (
    DIFF_METHODOLOGY_V1,
    ChangeCategory,
    ConflictDiffType,
    CorroborationDiffType,
    FactDiffCategory,
    RequirementDiffType,
    SourceDiffType,
)
from app.schemas.decision_replay import (
    ConflictDiffItemSchema,
    CorroborationDiffSchema,
    CoverageDiffSchema,
    DecisionChangeExplanationResponse,
    EvidenceDecisionDiffResponse,
    FactDiffItemSchema,
    IntegrityDiffSchema,
    ReliabilityDiffSchema,
    SourceDiffSchema,
)
from app.services.decision_replay_engine import DecisionReplayEngine

logger = logging.getLogger(__name__)


def _ensure_utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


class DecisionDiffEngine:
    """Core engine for comparative evaluation analysis between two timestamps."""

    @classmethod
    def compare_decision_states(
        cls,
        db: Session,
        payment_id: str,
        from_time: datetime,
        to_time: datetime,
        methodology_version: str = "EIS-1.0",
        profile_version: str = "STANDARD_PAYMENT_PROFILE_V1",
    ) -> EvidenceDecisionDiffResponse:
        """
        Executes a deterministic differential comparison between from_time (T1) and to_time (T2).
        Normalizes T1 <= T2.
        """
        t1 = _ensure_utc(from_time)
        t2 = _ensure_utc(to_time)

        # Normalize ordering
        if t1 > t2:
            t1, t2 = t2, t1

        # 1. Replay decisions at T1 and T2
        replay_t1 = DecisionReplayEngine.reconstruct_decision_state(
            db, payment_id, t1, methodology_version, profile_version, verify_trace=False
        )
        replay_t2 = DecisionReplayEngine.reconstruct_decision_state(
            db, payment_id, t2, methodology_version, profile_version, verify_trace=False
        )

        # 2. Fact Differences (Phase 13 EvidenceFact identity)
        facts_t1 = (
            db.query(EvidenceFact)
            .filter(
                EvidenceFact.payment_id == payment_id,
                EvidenceFact.first_observed_at <= t1,
            )
            .all()
        )
        facts_t2 = (
            db.query(EvidenceFact)
            .filter(
                EvidenceFact.payment_id == payment_id,
                EvidenceFact.first_observed_at <= t2,
            )
            .all()
        )

        facts_t1_map = {f.canonical_value_hash: f for f in facts_t1}
        facts_t2_map = {f.canonical_value_hash: f for f in facts_t2}
        all_fact_hashes = sorted(list(set(facts_t1_map.keys()) | set(facts_t2_map.keys())))

        fact_diffs: List[FactDiffItemSchema] = []
        change_categories: List[ChangeCategory] = []

        for h in all_fact_hashes:
            f1 = facts_t1_map.get(h)
            f2 = facts_t2_map.get(h)

            if f1 is None and f2 is not None:
                fact_diffs.append(
                    FactDiffItemSchema(
                        fact_id=f2.internal_id,
                        fact_type=f2.fact_type,
                        canonical_value=f2.canonical_value,
                        category=FactDiffCategory.ADDED,
                        observations_t1_count=0,
                        observations_t2_count=f2.observation_count,
                        detail=f"Fact '{f2.fact_type}' was first observed after T1 (at {f2.first_observed_at.isoformat()}).",
                    )
                )
                if ChangeCategory.EVIDENCE_ADDED not in change_categories:
                    change_categories.append(ChangeCategory.EVIDENCE_ADDED)
            elif f1 is not None and f2 is None:
                # Historical deletion is impossible by design, but handle safely
                fact_diffs.append(
                    FactDiffItemSchema(
                        fact_id=f1.internal_id,
                        fact_type=f1.fact_type,
                        canonical_value=f1.canonical_value,
                        category=FactDiffCategory.REMOVED,
                        observations_t1_count=f1.observation_count,
                        observations_t2_count=0,
                        detail="Fact was present at T1 but missing from T2 query.",
                    )
                )
                if ChangeCategory.EVIDENCE_REMOVED not in change_categories:
                    change_categories.append(ChangeCategory.EVIDENCE_REMOVED)
            elif f1 is not None and f2 is not None:
                if f2.observation_count > f1.observation_count:
                    fact_diffs.append(
                        FactDiffItemSchema(
                            fact_id=f2.internal_id,
                            fact_type=f2.fact_type,
                            canonical_value=f2.canonical_value,
                            category=FactDiffCategory.CHANGED,
                            observations_t1_count=f1.observation_count,
                            observations_t2_count=f2.observation_count,
                            detail=f"Fact gained {f2.observation_count - f1.observation_count} additional supporting observation(s) between T1 and T2.",
                        )
                    )
                    if ChangeCategory.EVIDENCE_CHANGED not in change_categories:
                        change_categories.append(ChangeCategory.EVIDENCE_CHANGED)
                else:
                    fact_diffs.append(
                        FactDiffItemSchema(
                            fact_id=f1.internal_id,
                            fact_type=f1.fact_type,
                            canonical_value=f1.canonical_value,
                            category=FactDiffCategory.UNCHANGED,
                            observations_t1_count=f1.observation_count,
                            observations_t2_count=f2.observation_count,
                            detail="Fact remained unchanged in value and observation count.",
                        )
                    )

        # 3. Source Differences
        sources_t1 = set(replay_t1.evidence_state.sources)
        sources_t2 = set(replay_t2.evidence_state.sources)
        added_sources = sorted(list(sources_t2 - sources_t1))
        removed_sources = sorted(list(sources_t1 - sources_t2))

        if len(sources_t2) > len(sources_t1):
            div_change = SourceDiffType.SOURCE_DIVERSITY_INCREASED
            if ChangeCategory.SOURCE_ADDED not in change_categories:
                change_categories.append(ChangeCategory.SOURCE_ADDED)
        elif len(sources_t2) < len(sources_t1):
            div_change = SourceDiffType.SOURCE_DIVERSITY_DECREASED
            if ChangeCategory.SOURCE_REMOVED not in change_categories:
                change_categories.append(ChangeCategory.SOURCE_REMOVED)
        else:
            div_change = SourceDiffType.NO_SOURCE_CHANGE

        source_diff = SourceDiffSchema(
            sources_t1=sorted(list(sources_t1)),
            sources_t2=sorted(list(sources_t2)),
            added_sources=added_sources,
            removed_sources=removed_sources,
            diversity_change=div_change,
        )

        # 4. Corroboration Differences
        corr_t1 = replay_t1.reliability_dimensions.get("dependency", {}).get("state")
        corr_t2 = replay_t2.reliability_dimensions.get("dependency", {}).get("state")
        corr_change = CorroborationDiffType.NO_CORROBORATION_CHANGE
        if corr_t1 != corr_t2:
            if corr_t2 == "INDEPENDENT_CORROBORATION":
                corr_change = CorroborationDiffType.CORROBORATION_INCREASED
            else:
                corr_change = CorroborationDiffType.CORROBORATION_DECREASED

        corroboration_diff = CorroborationDiffSchema(
            corroboration_t1=corr_t1,
            corroboration_t2=corr_t2,
            independence_t1=replay_t1.integrity_dimensions.get("independence"),
            independence_t2=replay_t2.integrity_dimensions.get("independence"),
            change_type=corr_change,
        )

        # 5. Conflict Differences
        conf_ids_t1 = {c["conflict_id"] for c in replay_t1.active_conflicts}
        conf_ids_t2 = {c["conflict_id"] for c in replay_t2.active_conflicts}

        conflict_diffs: List[ConflictDiffItemSchema] = []
        for c in replay_t2.active_conflicts:
            if c["conflict_id"] not in conf_ids_t1:
                conflict_diffs.append(
                    ConflictDiffItemSchema(
                        conflict_id=c["conflict_id"],
                        conflict_type=c["conflict_type"],
                        status_t1=None,
                        status_t2=c["status"],
                        change_type=ConflictDiffType.CONFLICT_ADDED,
                        detail=f"New {c['conflict_type']} contradiction was detected between T1 and T2.",
                    )
                )
                if ChangeCategory.CONFLICT_ADDED not in change_categories:
                    change_categories.append(ChangeCategory.CONFLICT_ADDED)

        for c in replay_t1.active_conflicts:
            if c["conflict_id"] not in conf_ids_t2:
                conflict_diffs.append(
                    ConflictDiffItemSchema(
                        conflict_id=c["conflict_id"],
                        conflict_type=c["conflict_type"],
                        status_t1=c["status"],
                        status_t2="RESOLVED",
                        change_type=ConflictDiffType.CONFLICT_RESOLVED,
                        detail=f"{c['conflict_type']} contradiction present at T1 was resolved before T2.",
                    )
                )
                if ChangeCategory.CONFLICT_RESOLVED not in change_categories:
                    change_categories.append(ChangeCategory.CONFLICT_RESOLVED)

        # 6. Coverage Differences
        cov_status_t1 = replay_t1.coverage_state
        cov_status_t2 = replay_t2.coverage_state
        req_p1 = replay_t1.coverage_metrics.get("required_present", 0)
        req_p2 = replay_t2.coverage_metrics.get("required_present", 0)
        req_m1 = replay_t1.coverage_metrics.get("required_missing", 0)
        req_m2 = replay_t2.coverage_metrics.get("required_missing", 0)

        cov_transitions = []
        if cov_status_t1 != cov_status_t2 or req_p1 != req_p2 or req_m1 != req_m2:
            cov_transitions.append({
                "from_status": cov_status_t1,
                "to_status": cov_status_t2,
                "present_delta": req_p2 - req_p1,
                "missing_delta": req_m2 - req_m1,
            })
            if ChangeCategory.COVERAGE_CHANGED not in change_categories:
                change_categories.append(ChangeCategory.COVERAGE_CHANGED)

        coverage_diff = CoverageDiffSchema(
            status_t1=cov_status_t1,
            status_t2=cov_status_t2,
            required_present_t1=req_p1,
            required_present_t2=req_p2,
            required_missing_t1=req_m1,
            required_missing_t2=req_m2,
            transitions=cov_transitions,
        )

        # 7. Reliability Differences
        rel_overall_t1 = replay_t1.reliability_state
        rel_overall_t2 = replay_t2.reliability_state
        rel_dim_changes = {}
        rel_reasons = []

        for dim, val1 in replay_t1.reliability_dimensions.items():
            val2 = replay_t2.reliability_dimensions.get(dim, {})
            state1 = val1.get("state")
            state2 = val2.get("state")
            if state1 != state2:
                rel_dim_changes[dim] = {"t1": state1, "t2": state2}
                rel_reasons.append(f"Dimension '{dim}' shifted from {state1} to {state2}.")

        if rel_overall_t1 != rel_overall_t2:
            if ChangeCategory.RELIABILITY_CHANGED not in change_categories:
                change_categories.append(ChangeCategory.RELIABILITY_CHANGED)

        reliability_diff = ReliabilityDiffSchema(
            overall_t1=rel_overall_t1,
            overall_t2=rel_overall_t2,
            dimension_changes=rel_dim_changes,
            reasons=rel_reasons,
        )

        # 8. Integrity Differences
        integ_overall_t1 = replay_t1.integrity_status
        integ_overall_t2 = replay_t2.integrity_status
        integ_dim_changes = {}

        for dim, val1 in replay_t1.integrity_dimensions.items():
            val2 = replay_t2.integrity_dimensions.get(dim)
            if val1 != val2:
                integ_dim_changes[dim] = {"t1": val1, "t2": val2}

        if integ_overall_t1 != integ_overall_t2 or integ_dim_changes:
            if ChangeCategory.INTEGRITY_CHANGED not in change_categories:
                change_categories.append(ChangeCategory.INTEGRITY_CHANGED)

        integrity_diff = IntegrityDiffSchema(
            overall_t1=integ_overall_t1,
            overall_t2=integ_overall_t2,
            dimension_changes=integ_dim_changes,
        )

        return EvidenceDecisionDiffResponse(
            payment_id=payment_id,
            from_time=t1,
            to_time=t2,
            diff_methodology_version=DIFF_METHODOLOGY_V1,
            methodology_t1=methodology_version,
            methodology_t2=methodology_version,
            methodology_changed=False,
            profile_t1=profile_version,
            profile_t2=profile_version,
            profile_changed=False,
            change_categories=change_categories,
            fact_diffs=fact_diffs,
            source_diff=source_diff,
            corroboration_diff=corroboration_diff,
            conflict_diffs=conflict_diffs,
            coverage_diff=coverage_diff,
            reliability_diff=reliability_diff,
            integrity_diff=integrity_diff,
            input_fingerprint_t1=replay_t1.input_fingerprint,
            input_fingerprint_t2=replay_t2.input_fingerprint,
            result_fingerprint_t1=replay_t1.result_fingerprint,
            result_fingerprint_t2=replay_t2.result_fingerprint,
        )

    @classmethod
    def generate_change_explanation(
        cls,
        db: Session,
        payment_id: str,
        from_time: datetime,
        to_time: datetime,
        methodology_version: str = "EIS-1.0",
        profile_version: str = "STANDARD_PAYMENT_PROFILE_V1",
    ) -> DecisionChangeExplanationResponse:
        """
        Generates an auditable, deterministic change explanation chain.
        Follows strict epistemic and causal bounding rules.
        """
        diff = cls.compare_decision_states(
            db, payment_id, from_time, to_time, methodology_version, profile_version
        )

        what_changed: List[str] = []
        why_it_mattered: List[str] = []
        what_remains_uncertain: List[str] = []
        explanation_chain: List[str] = []

        # Step 1: Fact / Evidence Changes
        added_facts = [f for f in diff.fact_diffs if f.category == FactDiffCategory.ADDED]
        changed_facts = [f for f in diff.fact_diffs if f.category == FactDiffCategory.CHANGED]

        if added_facts:
            types_str = ", ".join(f.fact_type for f in added_facts)
            msg = f"{len(added_facts)} new fact(s) [{types_str}] were reconciled into the graph."
            what_changed.append(msg)
            explanation_chain.append(f"Evidence Arrival: {msg}")

        if changed_facts:
            types_str = ", ".join(f.fact_type for f in changed_facts)
            msg = f"{len(changed_facts)} existing fact(s) [{types_str}] received additional corroborating observations."
            what_changed.append(msg)
            explanation_chain.append(f"Observation Update: {msg}")

        # Step 2: Source Changes
        if diff.source_diff.added_sources:
            msg = f"New evidence source(s) observed: {', '.join(diff.source_diff.added_sources)}."
            what_changed.append(msg)
            explanation_chain.append(f"Source Expansion: {msg}")

        # Step 3: Conflict Changes
        added_conflicts = [c for c in diff.conflict_diffs if c.change_type == ConflictDiffType.CONFLICT_ADDED]
        if added_conflicts:
            c_types = ", ".join(c.conflict_type for c in added_conflicts)
            msg = f"{len(added_conflicts)} new contradiction(s) [{c_types}] detected."
            what_changed.append(msg)
            why_it_mattered.append(f"Open contradictions force reliability and consistency ceilings to degrade.")
            explanation_chain.append(f"Contradiction Detection: {msg}")

        # Step 4: Coverage Changes
        if diff.coverage_diff.status_t1 != diff.coverage_diff.status_t2:
            msg = f"Evidence coverage shifted from {diff.coverage_diff.status_t1} to {diff.coverage_diff.status_t2} (present required: {diff.coverage_diff.required_present_t1} -> {diff.coverage_diff.required_present_t2})."
            why_it_mattered.append(msg)
            explanation_chain.append(f"Coverage Shift: {msg}")

        # Step 5: Reliability Changes
        if diff.reliability_diff.overall_t1 != diff.reliability_diff.overall_t2:
            msg = f"Overall reliability shifted from {diff.reliability_diff.overall_t1} to {diff.reliability_diff.overall_t2}."
            why_it_mattered.append(msg)
            for r in diff.reliability_diff.reasons:
                why_it_mattered.append(f"  • {r}")
            explanation_chain.append(f"Reliability Recalibration: {msg}")

        # Step 6: Integrity Changes
        if diff.integrity_diff.overall_t1 != diff.integrity_diff.overall_t2:
            msg = f"Evidence integrity outcome changed from {diff.integrity_diff.overall_t1} to {diff.integrity_diff.overall_t2}."
            why_it_mattered.append(msg)
            explanation_chain.append(f"Final Integrity Verdict: {msg}")
        elif not what_changed:
            what_changed.append("No new evidence, source, or contradiction changes occurred between T1 and T2.")
            why_it_mattered.append("The evidence decision state remained fully stable and identical.")
            explanation_chain.append("State Invariance: T1 and T2 decision states are bit-for-bit identical.")

        # Step 7: Epistemic Uncertainty
        what_remains_uncertain.append(
            "Replay and differential analysis strictly evaluate recorded observations; external banking settlements not delivered via webhook remain unobserved."
        )

        # Causal Summary (guarded against overclaiming)
        if len(what_changed) > 1 and diff.integrity_diff.overall_t1 != diff.integrity_diff.overall_t2:
            causal_summary = (
                f"Between T1 ({diff.from_time.isoformat()}) and T2 ({diff.to_time.isoformat()}), "
                f"multiple evidence updates coincided with a shift in the overall integrity verdict "
                f"from {diff.integrity_diff.overall_t1} to {diff.integrity_diff.overall_t2}."
            )
        elif what_changed and diff.integrity_diff.overall_t1 != diff.integrity_diff.overall_t2:
            causal_summary = (
                f"Between T1 and T2, the observed evidence changes contributed to an integrity verdict shift "
                f"from {diff.integrity_diff.overall_t1} to {diff.integrity_diff.overall_t2}."
            )
        else:
            causal_summary = (
                f"Between T1 and T2, the evidence state remained stable with overall integrity "
                f"constant at {diff.integrity_diff.overall_t1}."
            )

        return DecisionChangeExplanationResponse(
            payment_id=payment_id,
            from_time=diff.from_time,
            to_time=diff.to_time,
            what_changed=what_changed,
            why_it_mattered=why_it_mattered,
            what_remains_uncertain=what_remains_uncertain,
            causal_summary=causal_summary,
            explanation_chain=explanation_chain,
        )
