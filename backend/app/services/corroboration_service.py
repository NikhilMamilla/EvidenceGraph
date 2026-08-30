"""
Phase 7 — Evidence Corroboration Service.

Evaluates how many distinct observations support each canonical claim,
whether they come from distinct source mechanisms or distinct temporal events,
and assigns structural independence candidate statuses.
"""
from __future__ import annotations

from typing import List
from sqlalchemy.orm import Session

from app.models.evidence import EvidenceObservation
from app.models.evidence_structure import Claim, EvidenceClaimLink, EvidenceCorroboration
from app.models.structure_types import CorroborationType, IndependenceStatus


class CorroborationService:
    """
    Deterministic corroboration evaluation engine.
    """

    METHODOLOGY_VERSION = "1.0"

    @classmethod
    def evaluate_claim_corroboration(
        cls,
        db: Session,
        claim: Claim,
        payment_id: str,
    ) -> EvidenceCorroboration:
        """
        Evaluates corroboration metrics and independence status for a single canonical claim.
        """
        # Fetch all supporting evidence for this claim
        links = (
            db.query(EvidenceClaimLink)
            .filter(EvidenceClaimLink.claim_id == claim.internal_id)
            .all()
        )
        evidence_ids = [l.evidence_id for l in links]
        if not evidence_ids:
            observations: List[EvidenceObservation] = []
        else:
            observations = (
                db.query(EvidenceObservation)
                .filter(EvidenceObservation.internal_id.in_(evidence_ids))
                .all()
            )

        obs_count = len(observations)
        distinct_sources = set(obs.source_type for obs in observations if obs.source_type)
        distinct_events = set(obs.payment_event_id for obs in observations if obs.payment_event_id is not None)
        distinct_webhooks = set(obs.webhook_event_id for obs in observations if obs.webhook_event_id is not None)
        distinct_timestamps = set(obs.observed_at for obs in observations if obs.observed_at is not None)

        sources_count = len(distinct_sources) if distinct_sources else 1
        events_count = len(distinct_events) if distinct_events else (len(distinct_webhooks) if distinct_webhooks else 1)

        # Classify CorroborationType
        if obs_count <= 1:
            corrob_type = CorroborationType.SINGLE_OBSERVATION.value
            indep_status = IndependenceStatus.UNKNOWN.value
        elif sources_count > 1:
            corrob_type = CorroborationType.MULTI_SOURCE_CORROBORATION.value
            indep_status = IndependenceStatus.INDEPENDENT_CANDIDATE.value
        elif events_count > 1 or (len(distinct_timestamps) > 1 and len(distinct_webhooks) > 1):
            corrob_type = CorroborationType.TEMPORAL_CORROBORATION.value
            indep_status = IndependenceStatus.DEPENDENT.value
        else:
            corrob_type = CorroborationType.SAME_SOURCE_CORROBORATION.value
            indep_status = IndependenceStatus.SAME_SOURCE.value

        details = {
            "evidence_ids": [o.internal_id for o in observations],
            "sources": list(distinct_sources),
            "events": list(distinct_events),
            "webhook_events": list(distinct_webhooks),
            "timestamps_count": len(distinct_timestamps),
            "claim_canonical_value": claim.canonical_value,
        }

        corrob = (
            db.query(EvidenceCorroboration)
            .filter(EvidenceCorroboration.claim_id == claim.internal_id)
            .first()
        )

        if not corrob:
            corrob = EvidenceCorroboration(
                claim_id=claim.internal_id,
                payment_id=payment_id,
                corroboration_type=corrob_type,
                independence_status=indep_status,
                observation_count=obs_count,
                distinct_sources_count=sources_count,
                distinct_events_count=events_count,
                methodology_version=cls.METHODOLOGY_VERSION,
                details=details,
            )
            db.add(corrob)
            db.flush()
        else:
            corrob.payment_id = payment_id
            corrob.corroboration_type = corrob_type
            corrob.independence_status = indep_status
            corrob.observation_count = obs_count
            corrob.distinct_sources_count = sources_count
            corrob.distinct_events_count = events_count
            corrob.methodology_version = cls.METHODOLOGY_VERSION
            corrob.details = details

        return corrob
