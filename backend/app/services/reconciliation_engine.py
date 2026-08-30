"""
Phase 13 — Multi-Source Evidence Reconciliation & Evidence Identity Engine.

Determines whether multiple observations represent:
1. The SAME underlying real-world fact (SAME_FACT)
2. DIFFERENT facts about the same entity (DIFFERENT_FACT)
3. RELATED facts that must remain separate (RELATED_FACT)
4. CONFLICTING observations (CONFLICTING_FACT)
5. UNKNOWN / insufficiently identifiable observations (UNKNOWN)

Guarantees:
  - Observations are NEVER deleted or mutated (immutable provenance).
  - No probabilistic merging or ML — 100% deterministic rule-based decisions.
  - Pairwise decision ordering is deterministic: min(obs_a_id, obs_b_id) always first.
  - Re-running reconciliation is idempotent (unique constraints & get-or-create).
  - Candidate blocking avoids O(N^2) global comparison.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.evidence import EvidenceObservation
from app.models.evidence_fact import EvidenceFact, _canonical_value_hash
from app.models.evidence_reconciliation import EvidenceReconciliation
from app.models.observation_fact_link import ObservationFactLink
from app.models.reconciliation_types import (
    EVIDENCE_TYPE_TO_FACT_TYPE,
    EVENT_TYPE_TO_FACT_TYPE,
    FACT_METHODOLOGY_VERSION,
    FACT_RECONCILIATION_WINDOW_SECONDS,
    LIFECYCLE_FACT_TYPES,
    FactStatus,
    FactType,
    ReconciliationResult,
    ReconciliationRule,
    RECONCILIATION_RULE_VERSION,
)

logger = logging.getLogger(__name__)


def _ensure_utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


@dataclass
class ReconciliationDecision:
    """In-memory representation of an evaluated pairwise decision."""
    observation_a_id: int
    observation_b_id: int
    result: str
    rule_id: str
    rule_version: str
    explanation: str
    fact_id: Optional[int] = None


@dataclass
class BackfillReport:
    """Summary of historical backfill execution."""
    payments_processed: int = 0
    observations_processed: int = 0
    facts_created: int = 0
    facts_matched_existing: int = 0
    same_fact_decisions: int = 0
    different_fact_decisions: int = 0
    related_fact_decisions: int = 0
    conflicting_fact_decisions: int = 0
    unknown_decisions: int = 0
    failures: int = 0


class ReconciliationEngine:
    """
    Deterministic identity and reconciliation engine for EvidenceGraph.
    """

    RULE_VERSION = RECONCILIATION_RULE_VERSION
    METHODOLOGY_VERSION = FACT_METHODOLOGY_VERSION
    RECONCILIATION_WINDOW_SECONDS = FACT_RECONCILIATION_WINDOW_SECONDS

    # -------------------------------------------------------------------------
    # Normalization Helpers
    # -------------------------------------------------------------------------
    @classmethod
    def normalize_fact_type(cls, obs: EvidenceObservation) -> str:
        """
        Derives the canonical FactType from an EvidenceObservation.
        """
        # 1. Direct attribute mapping
        if obs.evidence_type in (
            "PAYMENT_AMOUNT",
            "PAYMENT_CURRENCY",
            "PAYMENT_METHOD",
            "PAYMENT_ORDER_RELATIONSHIP",
            "ORDER_AMOUNT",
            "ORDER_CURRENCY",
            "ORDER_STATUS",
        ):
            return EVIDENCE_TYPE_TO_FACT_TYPE[obs.evidence_type]

        # 2. Lifecycle event mapping (from provenance event_type)
        if obs.provenance_metadata and isinstance(obs.provenance_metadata, dict):
            event_type = obs.provenance_metadata.get("event_type")
            if event_type and event_type in EVENT_TYPE_TO_FACT_TYPE:
                return EVENT_TYPE_TO_FACT_TYPE[event_type]

        # 3. Fallback by evidence_type or value
        if obs.evidence_type in EVIDENCE_TYPE_TO_FACT_TYPE:
            return EVIDENCE_TYPE_TO_FACT_TYPE[obs.evidence_type]

        if obs.evidence_type == "PAYMENT_STATUS":
            val = (obs.value or "").lower()
            if val == "captured":
                return FactType.PAYMENT_CAPTURED
            elif val == "failed":
                return FactType.PAYMENT_FAILED
            elif val == "authorized":
                return FactType.PAYMENT_AUTHORIZED
            elif val == "refunded":
                return FactType.PAYMENT_REFUNDED
            return FactType.PAYMENT_STATUS_OBSERVED

        return FactType.PAYMENT_STATUS_OBSERVED

    @classmethod
    def normalize_canonical_value(cls, obs: EvidenceObservation) -> str:
        """
        Normalizes the observed value for canonical fact comparison.
        """
        if obs.value is None:
            return "unknown"
        val = str(obs.value).strip()
        # Case-normalize enums and statuses
        if obs.value_type == "ENUM":
            return val.lower()
        return val

    # -------------------------------------------------------------------------
    # Core Decision Tree: Pairwise Evaluation
    # -------------------------------------------------------------------------
    @classmethod
    def reconcile_pair(
        cls,
        obs_a: EvidenceObservation,
        obs_b: EvidenceObservation,
        reconciliation_window_seconds: float = RECONCILIATION_WINDOW_SECONDS,
    ) -> ReconciliationDecision:
        """
        Deterministically evaluates the identity relationship between two observations.
        Order is guaranteed: min(obs_a.internal_id, obs_b.internal_id) is observation_a.
        """
        if obs_a.internal_id > obs_b.internal_id:
            obs_a, obs_b = obs_b, obs_a

        id_a = obs_a.internal_id
        id_b = obs_b.internal_id

        # Rule 1: Same observation
        if id_a == id_b:
            return ReconciliationDecision(
                observation_a_id=id_a,
                observation_b_id=id_b,
                result=ReconciliationResult.SAME_FACT,
                rule_id=ReconciliationRule.SAME_PROVIDER_EVENT_V1,
                rule_version=cls.RULE_VERSION,
                explanation="Observations are identical (same internal ID).",
            )

        # Subject check: Must belong to same subject (payment) for fact identity
        if obs_a.subject_id != obs_b.subject_id:
            return ReconciliationDecision(
                observation_a_id=id_a,
                observation_b_id=id_b,
                result=ReconciliationResult.DIFFERENT_FACT,
                rule_id=ReconciliationRule.INSUFFICIENT_INFORMATION_V1,
                rule_version=cls.RULE_VERSION,
                explanation=f"Observations describe different entities ({obs_a.subject_id} vs {obs_b.subject_id}). Never merge across different subjects.",
            )

        fact_type_a = cls.normalize_fact_type(obs_a)
        fact_type_b = cls.normalize_fact_type(obs_b)
        val_a = cls.normalize_canonical_value(obs_a)
        val_b = cls.normalize_canonical_value(obs_b)

        t_a = _ensure_utc(obs_a.observed_at)
        t_b = _ensure_utc(obs_b.observed_at)
        time_diff = abs((t_a - t_b).total_seconds()) if t_a and t_b else None

        # Rule 2: Same Razorpay Provider Event (WebhookEvent ID match)
        if obs_a.webhook_event_id is not None and obs_a.webhook_event_id == obs_b.webhook_event_id:
            if fact_type_a == fact_type_b and val_a == val_b:
                return ReconciliationDecision(
                    observation_a_id=id_a,
                    observation_b_id=id_b,
                    result=ReconciliationResult.SAME_FACT,
                    rule_id=ReconciliationRule.SAME_PROVIDER_EVENT_V1,
                    rule_version=cls.RULE_VERSION,
                    explanation=f"Both observations originate from the same Razorpay provider webhook delivery (webhook_event_id={obs_a.webhook_event_id}) describing the same {fact_type_a}.",
                )
            elif fact_type_a != fact_type_b:
                return ReconciliationDecision(
                    observation_a_id=id_a,
                    observation_b_id=id_b,
                    result=ReconciliationResult.RELATED_FACT,
                    rule_id=ReconciliationRule.DIFFERENT_LIFECYCLE_V1,
                    rule_version=cls.RULE_VERSION,
                    explanation=f"Observations originate from the same provider event (webhook_event_id={obs_a.webhook_event_id}) but observe distinct attributes ({fact_type_a} vs {fact_type_b}).",
                )

        # Rule 3: Same PaymentEvent match
        if obs_a.payment_event_id is not None and obs_a.payment_event_id == obs_b.payment_event_id:
            if fact_type_a == fact_type_b and val_a == val_b:
                return ReconciliationDecision(
                    observation_a_id=id_a,
                    observation_b_id=id_b,
                    result=ReconciliationResult.SAME_FACT,
                    rule_id=ReconciliationRule.SAME_PAYMENT_EVENT_V1,
                    rule_version=cls.RULE_VERSION,
                    explanation=f"Both observations originate from the same canonical payment event (payment_event_id={obs_a.payment_event_id}).",
                )
            elif fact_type_a != fact_type_b:
                return ReconciliationDecision(
                    observation_a_id=id_a,
                    observation_b_id=id_b,
                    result=ReconciliationResult.RELATED_FACT,
                    rule_id=ReconciliationRule.DIFFERENT_LIFECYCLE_V1,
                    rule_version=cls.RULE_VERSION,
                    explanation=f"Observations originate from the same payment event (payment_event_id={obs_a.payment_event_id}) but describe different dimensions ({fact_type_a} vs {fact_type_b}).",
                )

        # Rule 4: Different Lifecycle facts for same payment (e.g. AUTHORIZED vs CAPTURED)
        if fact_type_a in LIFECYCLE_FACT_TYPES and fact_type_b in LIFECYCLE_FACT_TYPES and fact_type_a != fact_type_b:
            return ReconciliationDecision(
                observation_a_id=id_a,
                observation_b_id=id_b,
                result=ReconciliationResult.RELATED_FACT,
                rule_id=ReconciliationRule.DIFFERENT_LIFECYCLE_V1,
                rule_version=cls.RULE_VERSION,
                explanation=f"Observations represent distinct payment lifecycle events ({fact_type_a} and {fact_type_b}) for payment {obs_a.subject_id}. They remain separate and sequentially related.",
            )

        # Rule 5: Same attribute/fact type with conflicting values
        if fact_type_a == fact_type_b and val_a != val_b:
            return ReconciliationDecision(
                observation_a_id=id_a,
                observation_b_id=id_b,
                result=ReconciliationResult.CONFLICTING_FACT,
                rule_id=ReconciliationRule.CONFLICTING_VALUE_V1,
                rule_version=cls.RULE_VERSION,
                explanation=f"Observations assert incompatible values for {fact_type_a}: '{val_a}' vs '{val_b}'.",
            )

        # Rule 6: Same fact from distinct sources or distinct deliveries within time window
        if fact_type_a == fact_type_b and val_a == val_b:
            if time_diff is not None and time_diff <= reconciliation_window_seconds:
                return ReconciliationDecision(
                    observation_a_id=id_a,
                    observation_b_id=id_b,
                    result=ReconciliationResult.SAME_FACT,
                    rule_id=ReconciliationRule.SAME_FACT_DIFFERENT_SOURCE_V1,
                    rule_version=cls.RULE_VERSION,
                    explanation=f"Same underlying fact ({fact_type_a} = '{val_a}') observed within reconciliation window ({time_diff:.2f}s <= {reconciliation_window_seconds}s) across observations ({obs_a.source_type} and {obs_b.source_type}).",
                )
            else:
                # Rule 7: Temporal Ambiguity (timestamps separated by > window)
                diff_str = f"{time_diff:.2f}s" if time_diff is not None else "unknown"
                return ReconciliationDecision(
                    observation_a_id=id_a,
                    observation_b_id=id_b,
                    result=ReconciliationResult.UNKNOWN,
                    rule_id=ReconciliationRule.TEMPORAL_AMBIGUITY_V1,
                    rule_version=cls.RULE_VERSION,
                    explanation=f"Observations assert the same value '{val_a}' for {fact_type_a}, but timestamps are separated by {diff_str} (> {reconciliation_window_seconds}s). Cannot deterministically confirm identity.",
                )

        # Rule 8: Different attributes of the same payment (e.g. PAYMENT_AMOUNT vs PAYMENT_METHOD)
        if fact_type_a != fact_type_b:
            return ReconciliationDecision(
                observation_a_id=id_a,
                observation_b_id=id_b,
                result=ReconciliationResult.DIFFERENT_FACT,
                rule_id=ReconciliationRule.INSUFFICIENT_INFORMATION_V1,
                rule_version=cls.RULE_VERSION,
                explanation=f"Observations describe different attributes of payment {obs_a.subject_id} ({fact_type_a} vs {fact_type_b}).",
            )

        # Default fallback
        return ReconciliationDecision(
            observation_a_id=id_a,
            observation_b_id=id_b,
            result=ReconciliationResult.UNKNOWN,
            rule_id=ReconciliationRule.INSUFFICIENT_INFORMATION_V1,
            rule_version=cls.RULE_VERSION,
            explanation="Insufficient event identity and metadata to establish deterministic reconciliation.",
        )

    # -------------------------------------------------------------------------
    # Fact Creation & Aggregation
    # -------------------------------------------------------------------------
    @classmethod
    def get_or_create_fact(
        cls,
        db: Session,
        payment_id: str,
        fact_type: str,
        canonical_value: str,
        observed_at: datetime,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Tuple[EvidenceFact, bool]:
        """
        Retrieves an existing EvidenceFact by identity triple or creates a new one.
        Returns (fact, created_boolean).
        """
        val_hash = _canonical_value_hash(payment_id, fact_type, canonical_value)

        fact = db.execute(
            select(EvidenceFact).where(
                EvidenceFact.payment_id == payment_id,
                EvidenceFact.fact_type == fact_type,
                EvidenceFact.canonical_value_hash == val_hash,
            )
        ).scalar_one_or_none()

        obs_time = _ensure_utc(observed_at)

        if fact is not None:
            # Update temporal coverage and metadata if needed
            first_t = _ensure_utc(fact.first_observed_at)
            last_t = _ensure_utc(fact.last_observed_at)

            if obs_time and (first_t is None or obs_time < first_t):
                fact.first_observed_at = obs_time
            if obs_time and (last_t is None or obs_time > last_t):
                fact.last_observed_at = obs_time

            return fact, False

        fact = EvidenceFact(
            payment_id=payment_id,
            fact_type=fact_type,
            canonical_value=canonical_value,
            canonical_value_hash=val_hash,
            status=FactStatus.ACTIVE,
            first_observed_at=obs_time or datetime.now(timezone.utc),
            last_observed_at=obs_time or datetime.now(timezone.utc),
            observation_count=1,
            distinct_source_count=1,
            methodology_version=cls.METHODOLOGY_VERSION,
            fact_metadata=metadata,
        )
        db.add(fact)
        db.flush()
        return fact, True

    @classmethod
    def link_observation_to_fact(
        cls,
        db: Session,
        observation: EvidenceObservation,
        fact: EvidenceFact,
    ) -> ObservationFactLink:
        """
        Creates an ObservationFactLink between observation and fact if not present.
        """
        link = db.execute(
            select(ObservationFactLink).where(
                ObservationFactLink.observation_id == observation.internal_id,
                ObservationFactLink.fact_id == fact.internal_id,
            )
        ).scalar_one_or_none()

        if link is None:
            link = ObservationFactLink(
                observation_id=observation.internal_id,
                fact_id=fact.internal_id,
            )
            db.add(link)
            db.flush()

        return link

    @classmethod
    def update_fact_aggregates(cls, db: Session, fact: EvidenceFact) -> None:
        """
        Recomputes observation_count, distinct_source_count, first_observed_at,
        and last_observed_at from linked observations.
        """
        links = db.execute(
            select(ObservationFactLink).where(ObservationFactLink.fact_id == fact.internal_id)
        ).scalars().all()

        if not links:
            return

        obs_ids = [l.observation_id for l in links]
        observations = db.execute(
            select(EvidenceObservation).where(EvidenceObservation.internal_id.in_(obs_ids))
        ).scalars().all()

        if not observations:
            return

        fact.observation_count = len(observations)
        distinct_sources = {obs.source_type for obs in observations if obs.source_type}
        fact.distinct_source_count = max(1, len(distinct_sources))

        valid_timestamps = [_ensure_utc(obs.observed_at) for obs in observations if obs.observed_at is not None]
        if valid_timestamps:
            fact.first_observed_at = min(valid_timestamps)
            fact.last_observed_at = max(valid_timestamps)

    # -------------------------------------------------------------------------
    # Reconciliation Pipeline for a Payment
    # -------------------------------------------------------------------------
    @classmethod
    def reconcile_payment(
        cls,
        db: Session,
        payment_id: str,
        evaluation_time: Optional[datetime] = None,
    ) -> List[EvidenceFact]:
        """
        Executes full reconciliation across all observations for a payment.
        Creates/updates EvidenceFacts, ObservationFactLinks, and EvidenceReconciliations.
        Returns the list of EvidenceFacts for the payment.
        """
        eval_time = _ensure_utc(evaluation_time or datetime.now(timezone.utc))

        # 1. Fetch all observations for this payment
        observations = db.execute(
            select(EvidenceObservation)
            .where(
                EvidenceObservation.subject_type == "payment",
                EvidenceObservation.subject_id == payment_id,
            )
            .order_by(EvidenceObservation.observed_at.asc(), EvidenceObservation.internal_id.asc())
        ).scalars().all()

        if not observations:
            return []

        # 2. Candidate Blocking: Group by (fact_type, canonical_value)
        # to identify matching facts and compare pairs
        assigned_facts: Dict[int, EvidenceFact] = {}
        created_facts: List[EvidenceFact] = []

        # First pass: map each observation to an EvidenceFact
        for obs in observations:
            fact_type = cls.normalize_fact_type(obs)
            val = cls.normalize_canonical_value(obs)
            meta = {"evidence_type": obs.evidence_type, "source_type": obs.source_type}

            fact, created = cls.get_or_create_fact(
                db=db,
                payment_id=payment_id,
                fact_type=fact_type,
                canonical_value=val,
                observed_at=obs.observed_at,
                metadata=meta,
            )
            cls.link_observation_to_fact(db=db, observation=obs, fact=fact)
            assigned_facts[obs.internal_id] = fact
            if created:
                created_facts.append(fact)

        # 3. Blocked Pairwise Reconciliation:
        # Compare observations within same fact type and between lifecycle types
        n = len(observations)
        for i in range(n):
            for j in range(i + 1, n):
                obs_a = observations[i]
                obs_b = observations[j]

                # Check if decision already recorded
                existing_rec = db.execute(
                    select(EvidenceReconciliation).where(
                        EvidenceReconciliation.observation_a_id == obs_a.internal_id,
                        EvidenceReconciliation.observation_b_id == obs_b.internal_id,
                        EvidenceReconciliation.rule_version == cls.RULE_VERSION,
                    )
                ).scalar_one_or_none()

                if existing_rec is not None:
                    continue

                decision = cls.reconcile_pair(obs_a, obs_b)

                # If SAME_FACT, attach the fact ID
                fact_id = None
                if decision.result == ReconciliationResult.SAME_FACT:
                    fact_id = assigned_facts.get(obs_a.internal_id, assigned_facts.get(obs_b.internal_id)).internal_id

                rec = EvidenceReconciliation(
                    observation_a_id=decision.observation_a_id,
                    observation_b_id=decision.observation_b_id,
                    result=decision.result,
                    rule_id=decision.rule_id,
                    rule_version=decision.rule_version,
                    explanation=decision.explanation,
                    fact_id=fact_id,
                    evaluated_at=eval_time,
                )
                db.add(rec)

        db.flush()

        # 4. Recompute aggregates for all touched facts
        all_payment_facts = db.execute(
            select(EvidenceFact).where(EvidenceFact.payment_id == payment_id)
        ).scalars().all()

        for f in all_payment_facts:
            cls.update_fact_aggregates(db, f)

        db.flush()
        return all_payment_facts

    # -------------------------------------------------------------------------
    # Historical Backfill (Idempotent)
    # -------------------------------------------------------------------------
    @classmethod
    def backfill_all_payments(cls, db: Session) -> BackfillReport:
        """
        Runs reconciliation across all distinct payments in the database.
        Safe and idempotent.
        """
        report = BackfillReport()

        distinct_payment_ids = db.execute(
            select(EvidenceObservation.subject_id)
            .where(EvidenceObservation.subject_type == "payment")
            .distinct()
        ).scalars().all()

        for pid in distinct_payment_ids:
            try:
                obs_count = db.execute(
                    select(func.count(EvidenceObservation.internal_id)).where(
                        EvidenceObservation.subject_type == "payment",
                        EvidenceObservation.subject_id == pid,
                    )
                ).scalar() or 0

                initial_fact_count = db.execute(
                    select(func.count(EvidenceFact.internal_id)).where(
                        EvidenceFact.payment_id == pid
                    )
                ).scalar() or 0

                facts = cls.reconcile_payment(db, pid)

                final_fact_count = len(facts)
                newly_created = final_fact_count - initial_fact_count

                report.payments_processed += 1
                report.observations_processed += obs_count
                report.facts_created += max(0, newly_created)
                report.facts_matched_existing += initial_fact_count

            except Exception as e:
                logger.exception(f"Failed to reconcile payment {pid}: {e}")
                report.failures += 1

        # Count decisions by type
        decisions = db.execute(
            select(EvidenceReconciliation.result, func.count(EvidenceReconciliation.internal_id))
            .group_by(EvidenceReconciliation.result)
        ).all()

        for res, count in decisions:
            if res == ReconciliationResult.SAME_FACT:
                report.same_fact_decisions = count
            elif res == ReconciliationResult.DIFFERENT_FACT:
                report.different_fact_decisions = count
            elif res == ReconciliationResult.RELATED_FACT:
                report.related_fact_decisions = count
            elif res == ReconciliationResult.CONFLICTING_FACT:
                report.conflicting_fact_decisions = count
            elif res == ReconciliationResult.UNKNOWN:
                report.unknown_decisions = count

        return report
