"""
Phase 13 — Fact Service.

Read-only aggregation and query service for EvidenceFacts, supporting observations,
provenance lineage, source diversity analysis, and reconciliation history.

Guarantees:
  - Sanitized outputs: no raw webhook payloads, credentials, or PII.
  - Returns empty lists or raises 404 for missing entities.
  - Pure read-only querying without side effects.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.evidence import EvidenceObservation
from app.models.evidence_conflict import EvidenceConflict
from app.models.evidence_fact import EvidenceFact
from app.models.evidence_reconciliation import EvidenceReconciliation
from app.models.evidence_structure import Claim, EvidenceClaimLink
from app.models.observation_fact_link import ObservationFactLink
from app.models.reconciliation_types import FactStatus, ReconciliationResult
from app.schemas.reconciliation import (
    EvidenceFactResponse,
    FactClaimSummary,
    FactConflictSummary,
    FactDetailResponse,
    ObservationReconciliationResponse,
    ObservationSummary,
    PaymentFactsResponse,
    ReconciliationDecisionResponse,
    RelatedFactSummary,
    SourceDiversityDetail,
)


class FactService:
    """
    Query and aggregation service for EvidenceFacts and reconciliation records.
    """

    @classmethod
    def get_fact_by_id(cls, db: Session, fact_id: int) -> Optional[EvidenceFact]:
        """Fetches an EvidenceFact by internal_id."""
        return db.execute(
            select(EvidenceFact).where(EvidenceFact.internal_id == fact_id)
        ).scalar_one_or_none()

    @classmethod
    def get_fact_detail(cls, db: Session, fact_id: int) -> FactDetailResponse:
        """
        Retrieves the full detail of an EvidenceFact including:
        - Supporting observations (sanitized)
        - Source diversity breakdown
        - Related lifecycle facts for the same payment
        - Associated conflicts
        - Associated claims
        """
        fact = cls.get_fact_by_id(db, fact_id)
        if not fact:
            raise ValueError(f"EvidenceFact with ID {fact_id} not found")

        # 1. Fetch supporting observations via ObservationFactLink
        links = db.execute(
            select(ObservationFactLink).where(ObservationFactLink.fact_id == fact.internal_id)
        ).scalars().all()

        obs_ids = [l.observation_id for l in links]
        observations: List[EvidenceObservation] = []
        if obs_ids:
            observations = db.execute(
                select(EvidenceObservation)
                .where(EvidenceObservation.internal_id.in_(obs_ids))
                .order_by(EvidenceObservation.observed_at.asc())
            ).scalars().all()

        obs_summaries = [ObservationSummary.model_validate(o) for o in observations]

        # 2. Source diversity calculation
        sources = list({o.source_type for o in observations if o.source_type})
        source_div = SourceDiversityDetail(
            source_types=sources,
            distinct_source_count=len(sources) if sources else 1,
            observation_count=len(observations),
            is_multi_source=len(sources) > 1,
        )

        # 3. Related facts for same payment
        other_facts = db.execute(
            select(EvidenceFact).where(
                EvidenceFact.payment_id == fact.payment_id,
                EvidenceFact.internal_id != fact.internal_id,
            )
        ).scalars().all()

        related_summaries: List[RelatedFactSummary] = []
        for of in other_facts:
            rel = "RELATED_LIFECYCLE"
            if of.first_observed_at < fact.first_observed_at:
                rel = "PRECEDES"
            elif of.first_observed_at > fact.first_observed_at:
                rel = "SUCCEEDS"
            related_summaries.append(
                RelatedFactSummary(
                    fact_id=of.internal_id,
                    fact_type=of.fact_type,
                    canonical_value=of.canonical_value,
                    status=of.status,
                    relationship=rel,
                )
            )

        # 4. Associated claims
        claims_list: List[FactClaimSummary] = []
        if obs_ids:
            claim_links = db.execute(
                select(EvidenceClaimLink).where(EvidenceClaimLink.evidence_id.in_(obs_ids))
            ).scalars().all()
            claim_ids = list({cl.claim_id for cl in claim_links})
            if claim_ids:
                claims = db.execute(
                    select(Claim).where(Claim.internal_id.in_(claim_ids))
                ).scalars().all()
                for c in claims:
                    claims_list.append(
                        FactClaimSummary(
                            claim_id=c.internal_id,
                            claim_type=c.claim_type,
                            canonical_value=c.canonical_value,
                        )
                    )

        # 5. Associated conflicts
        conflicts_list: List[FactConflictSummary] = []
        conflicts = db.execute(
            select(EvidenceConflict).where(EvidenceConflict.payment_id == fact.payment_id)
        ).scalars().all()
        for conf in conflicts:
            conflicts_list.append(
                FactConflictSummary(
                    conflict_id=conf.internal_id,
                    conflict_type=conf.conflict_type,
                    severity=conf.severity,
                    status=conf.status,
                )
            )

        return FactDetailResponse(
            fact=EvidenceFactResponse.model_validate(fact),
            supporting_observations=obs_summaries,
            source_diversity=source_div,
            related_facts=related_summaries,
            conflicts=conflicts_list,
            claims=claims_list,
        )

    @classmethod
    def get_payment_facts(
        cls,
        db: Session,
        payment_id: str,
        fact_type: Optional[str] = None,
        status: Optional[str] = None,
        from_time: Optional[datetime] = None,
        to_time: Optional[datetime] = None,
    ) -> PaymentFactsResponse:
        """
        Retrieves all canonical EvidenceFacts for a payment with optional filtering.
        """
        query = select(EvidenceFact).where(EvidenceFact.payment_id == payment_id)

        if fact_type:
            query = query.where(EvidenceFact.fact_type == fact_type)
        if status:
            query = query.where(EvidenceFact.status == status)
        if from_time:
            query = query.where(EvidenceFact.first_observed_at >= from_time)
        if to_time:
            query = query.where(EvidenceFact.last_observed_at <= to_time)

        query = query.order_by(EvidenceFact.first_observed_at.asc(), EvidenceFact.internal_id.asc())
        facts = db.execute(query).scalars().all()

        active_count = sum(1 for f in facts if f.status == FactStatus.ACTIVE)

        return PaymentFactsResponse(
            payment_id=payment_id,
            total_facts=len(facts),
            active_facts_count=active_count,
            facts=[EvidenceFactResponse.model_validate(f) for f in facts],
        )

    @classmethod
    def get_observation_reconciliation(
        cls,
        db: Session,
        observation_id: int,
    ) -> ObservationReconciliationResponse:
        """
        Retrieves matched fact and all pairwise reconciliation decisions involving
        the specified observation.
        """
        obs = db.execute(
            select(EvidenceObservation).where(EvidenceObservation.internal_id == observation_id)
        ).scalar_one_or_none()

        if not obs:
            raise ValueError(f"EvidenceObservation with ID {observation_id} not found")

        # Find linked fact
        link = db.execute(
            select(ObservationFactLink).where(ObservationFactLink.observation_id == observation_id)
        ).scalar_one_or_none()

        matched_fact: Optional[EvidenceFactResponse] = None
        if link:
            fact = db.execute(
                select(EvidenceFact).where(EvidenceFact.internal_id == link.fact_id)
            ).scalar_one_or_none()
            if fact:
                matched_fact = EvidenceFactResponse.model_validate(fact)

        # Find all pairwise decisions where this observation was involved
        reconciliations = db.execute(
            select(EvidenceReconciliation).where(
                (EvidenceReconciliation.observation_a_id == observation_id)
                | (EvidenceReconciliation.observation_b_id == observation_id)
            ).order_by(EvidenceReconciliation.evaluated_at.desc())
        ).scalars().all()

        decision_responses = [
            ReconciliationDecisionResponse.model_validate(r) for r in reconciliations
        ]

        # Gather related observations
        related_ids = set()
        for r in reconciliations:
            if r.observation_a_id != observation_id:
                related_ids.add(r.observation_a_id)
            if r.observation_b_id != observation_id:
                related_ids.add(r.observation_b_id)

        related_obs: List[ObservationSummary] = []
        if related_ids:
            rel_observations = db.execute(
                select(EvidenceObservation).where(EvidenceObservation.internal_id.in_(list(related_ids)))
            ).scalars().all()
            related_obs = [ObservationSummary.model_validate(o) for o in rel_observations]

        return ObservationReconciliationResponse(
            observation=ObservationSummary.model_validate(obs),
            matched_fact=matched_fact,
            decisions=decision_responses,
            related_observations=related_obs,
        )
