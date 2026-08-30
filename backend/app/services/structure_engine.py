"""
Phase 7 — Evidence Structure & Concentration Engine.

Coordinates claim extraction, evidence grouping, corroboration assessment,
and computes structural concentration metrics (including raw counts and HHI).
Produces deterministic, versioned EvidenceStructureSnapshot instances.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional
from sqlalchemy.orm import Session

from app.models.evidence import EvidenceObservation
from app.models.evidence_structure import (
    Claim,
    EvidenceGroup,
    EvidenceCorroboration,
    EvidenceStructureSnapshot,
)
from app.models.structure_types import GroupType
from app.services.claim_service import ClaimService
from app.services.grouping_service import GroupingService
from app.services.corroboration_service import CorroborationService


class StructureEngine:
    """
    Orchestrates structural evidence analysis for a payment.
    """

    METHODOLOGY_VERSION = "1.0"

    @classmethod
    def evaluate_payment_structure(
        cls,
        db: Session,
        payment_id: str,
        evaluation_time: Optional[datetime] = None,
    ) -> Optional[EvidenceStructureSnapshot]:
        """
        Runs complete structural analysis on all evidence for a payment.
        Creates Claims, Groups, Corroborations, and persists an EvidenceStructureSnapshot.
        """
        eval_time = evaluation_time or datetime.now(timezone.utc)
        if eval_time.tzinfo is None:
            raise ValueError("evaluation_time must be timezone-aware (UTC)")

        # 1. Fetch all evidence for the payment
        observations: List[EvidenceObservation] = (
            db.query(EvidenceObservation)
            .filter(
                (
                    (EvidenceObservation.subject_type == "payment")
                    & (EvidenceObservation.subject_id == payment_id)
                )
                | (
                    (EvidenceObservation.subject_type == "order")
                    & (EvidenceObservation.provenance_metadata["payment_id"].astext == payment_id)
                )
            )
            .order_by(EvidenceObservation.observed_at.asc(), EvidenceObservation.internal_id.asc())
            .all()
        )

        if not observations:
            return None

        # 2. Process Canonical Claims
        claims: List[Claim] = ClaimService.process_observations(db, observations)

        # 3. Form Evidence Groups
        groups: List[EvidenceGroup] = GroupingService.group_payment_evidence(db, payment_id, observations)

        # 4. Evaluate Corroboration for each claim
        corroborations: List[EvidenceCorroboration] = []
        for claim in claims:
            corrob = CorroborationService.evaluate_claim_corroboration(db, claim, payment_id)
            corroborations.append(corrob)

        # 5. Compute Structural Concentration Metrics
        total_obs = len(observations)
        distinct_claims_cnt = len(claims)
        
        distinct_sources = set(o.source_type for o in observations if o.source_type)
        distinct_sources_cnt = len(distinct_sources) if distinct_sources else 1

        distinct_events = set(o.payment_event_id for o in observations if o.payment_event_id is not None)
        distinct_events_cnt = len(distinct_events) if distinct_events else 1

        distinct_groups_cnt = len(groups)

        # Find largest group size across payment event groups
        pe_groups = [g for g in groups if g.group_type == GroupType.SAME_PAYMENT_EVENT.value]
        if pe_groups:
            largest_grp_size = max(len(g.members) for g in pe_groups)
        elif groups:
            largest_grp_size = max(len(g.members) for g in groups)
        else:
            largest_grp_size = total_obs

        # Calculate Herfindahl-Hirschman Index (HHI) for event distribution
        # HHI = sum((n_i / N)^2) across payment events
        if total_obs > 0 and distinct_events:
            event_counts = {}
            for o in observations:
                pe = o.payment_event_id or 0
                event_counts[pe] = event_counts.get(pe, 0) + 1
            
            group_hhi = sum((cnt / total_obs) ** 2 for cnt in event_counts.values())
        else:
            group_hhi = 1.0 if total_obs > 0 else 0.0

        corroborated_claims_cnt = sum(1 for c in corroborations if c.observation_count > 1)
        multi_source_claims_cnt = sum(1 for c in corroborations if c.distinct_sources_count > 1)

        summary = {
            "total_observations": total_obs,
            "distinct_claims": distinct_claims_cnt,
            "distinct_sources": distinct_sources_cnt,
            "distinct_events": distinct_events_cnt,
            "distinct_groups": distinct_groups_cnt,
            "largest_group_size": largest_grp_size,
            "group_hhi": round(group_hhi, 4),
            "corroborated_claim_count": corroborated_claims_cnt,
            "multi_source_claim_count": multi_source_claims_cnt,
            "sources_breakdown": {
                src: sum(1 for o in observations if o.source_type == src)
                for src in distinct_sources
            },
        }

        # 6. Create Snapshot
        snapshot = EvidenceStructureSnapshot(
            payment_id=payment_id,
            evaluated_at=eval_time,
            total_observations=total_obs,
            distinct_claims=distinct_claims_cnt,
            distinct_sources=distinct_sources_cnt,
            distinct_events=distinct_events_cnt,
            distinct_groups=distinct_groups_cnt,
            largest_group_size=largest_grp_size,
            group_hhi=round(group_hhi, 4),
            corroborated_claim_count=corroborated_claims_cnt,
            multi_source_claim_count=multi_source_claims_cnt,
            methodology_version=cls.METHODOLOGY_VERSION,
            structural_summary=summary,
        )
        db.add(snapshot)
        db.flush()

        return snapshot
