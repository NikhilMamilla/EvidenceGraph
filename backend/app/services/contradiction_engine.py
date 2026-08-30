"""
Phase 8 — Contradiction & Temporal Consistency Engine.

Evaluates whether claims and evidence observations for a payment are:
- Temporally consistent and valid lifecycle transitions
- Out-of-order deliveries that resolve chronologically
- Ambiguous in ordering
- Genuinely conflicting in state, value, relationship, or temporal sequence

Deterministic, versioned ("1.0"), and explainable.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
from sqlalchemy.orm import Session

from app.models.conflict_types import (
    ConflictSeverity,
    ConflictStatus,
    ConflictType,
    ResolutionType,
)
from app.models.evidence import EvidenceObservation
from app.models.evidence_conflict import ConflictResolution, EvidenceConflict
from app.models.evidence_structure import Claim, EvidenceClaimLink
from app.models.structure_types import ClaimType
from app.services.state_machine import PaymentStateMachine


def _ensure_utc(dt: Optional[datetime]) -> Optional[datetime]:
    """Normalize a potentially naive datetime to UTC-aware."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


class ContradictionEngine:
    """
    Evaluates temporal consistency and detects semantic contradictions among claims.
    """

    RULE_VERSION = "1.0"
    DEFAULT_CLOCK_TOLERANCE_SECONDS = 2.0

    @classmethod
    def evaluate_payment_consistency(
        cls,
        db: Session,
        payment_id: str,
        evaluation_time: Optional[datetime] = None,
        clock_tolerance_seconds: float = DEFAULT_CLOCK_TOLERANCE_SECONDS,
    ) -> List[EvidenceConflict]:
        """
        Runs comprehensive consistency analysis across all claims for a payment.
        """
        eval_time = evaluation_time or datetime.now(timezone.utc)
        if eval_time.tzinfo is None:
            raise ValueError("evaluation_time must be timezone-aware (UTC)")

        claims = (
            db.query(Claim)
            .filter(Claim.subject_type == "payment", Claim.subject_id == payment_id)
            .all()
        )

        if not claims:
            return []

        # Map claims with their earliest supporting observation timestamp and source info
        claim_details: Dict[int, Dict] = {}
        for claim in claims:
            links = (
                db.query(EvidenceClaimLink)
                .filter(EvidenceClaimLink.claim_id == claim.internal_id)
                .all()
            )
            ev_ids = [l.evidence_id for l in links]
            observations = (
                db.query(EvidenceObservation)
                .filter(EvidenceObservation.internal_id.in_(ev_ids))
                .order_by(EvidenceObservation.observed_at.asc())
                .all()
                if ev_ids
                else []
            )

            earliest_time = _ensure_utc(observations[0].observed_at) if observations else _ensure_utc(claim.created_at)
            latest_time = _ensure_utc(observations[-1].observed_at) if observations else _ensure_utc(claim.created_at)
            sources = list(set(o.source_type for o in observations if o.source_type))
            event_ids = list(set(o.payment_event_id for o in observations if o.payment_event_id is not None))

            claim_details[claim.internal_id] = {
                "claim": claim,
                "observations": observations,
                "earliest_time": earliest_time,
                "latest_time": latest_time,
                "sources": sources,
                "event_ids": event_ids,
            }

        conflicts: List[EvidenceConflict] = []

        # 1. Analyze PAYMENT_STATUS claims
        status_claims = [
            claim_details[c.internal_id]
            for c in claims
            if c.claim_type == ClaimType.PAYMENT_STATUS.value and c.claim_key == "STATUS"
        ]
        status_conflicts = cls._evaluate_status_consistency(
            db, payment_id, status_claims, eval_time, clock_tolerance_seconds
        )
        conflicts.extend(status_conflicts)

        # 2. Analyze PAYMENT_AMOUNT claims
        amount_claims = [
            claim_details[c.internal_id]
            for c in claims
            if c.claim_type == ClaimType.PAYMENT_AMOUNT.value and c.claim_key == "AMOUNT"
        ]
        amount_conflicts = cls._evaluate_value_consistency(
            db, payment_id, amount_claims, eval_time, "monetary amount"
        )
        conflicts.extend(amount_conflicts)

        # 3. Analyze PAYMENT_CURRENCY claims
        currency_claims = [
            claim_details[c.internal_id]
            for c in claims
            if c.claim_type == ClaimType.PAYMENT_CURRENCY.value and c.claim_key == "CURRENCY"
        ]
        currency_conflicts = cls._evaluate_value_consistency(
            db, payment_id, currency_claims, eval_time, "currency"
        )
        conflicts.extend(currency_conflicts)

        # 4. Analyze ORDER_ASSOCIATION claims
        order_claims = [
            claim_details[c.internal_id]
            for c in claims
            if c.claim_type == ClaimType.ORDER_ASSOCIATION.value
        ]
        order_conflicts = cls._evaluate_order_consistency(
            db, payment_id, order_claims, eval_time
        )
        conflicts.extend(order_conflicts)

        db.flush()
        return conflicts

    @classmethod
    def _evaluate_status_consistency(
        cls,
        db: Session,
        payment_id: str,
        claim_details_list: List[Dict],
        eval_time: datetime,
        clock_tolerance_seconds: float,
    ) -> List[EvidenceConflict]:
        conflicts = []
        n = len(claim_details_list)
        if n < 2:
            return conflicts

        # Sort by earliest observed timestamp
        sorted_items = sorted(claim_details_list, key=lambda x: (x["earliest_time"], x["claim"].internal_id))

        for i in range(n):
            for j in range(i + 1, n):
                item_a = sorted_items[i]
                item_b = sorted_items[j]

                claim_a = item_a["claim"]
                claim_b = item_b["claim"]

                val_a = claim_a.canonical_value
                val_b = claim_b.canonical_value

                if val_a == val_b:
                    continue  # Identical canonical propositions do not conflict

                t_a = item_a["earliest_time"]
                t_b = item_b["earliest_time"]
                time_diff_sec = (t_b - t_a).total_seconds() if t_a and t_b else 0.0

                # Check if within clock skew / network ambiguity window
                if abs(time_diff_sec) <= clock_tolerance_seconds:
                    res = PaymentStateMachine.classify_transition(val_a, val_b)
                    if res["transition_type"] == "CONTRADICTORY_TERMINAL":
                        conflict = cls._record_conflict(
                            db=db,
                            payment_id=payment_id,
                            claim_a=claim_a,
                            claim_b=claim_b,
                            conflict_type=ConflictType.STATE_CONFLICT.value,
                            severity=ConflictSeverity.HIGH.value,
                            detected_at=eval_time,
                            explanation={
                                "what": f"Conflicting terminal states observed at same temporal window ({val_a} vs {val_b})",
                                "why": res["explanation"],
                                "timestamp_a": t_a.isoformat() if t_a else None,
                                "timestamp_b": t_b.isoformat() if t_b else None,
                                "time_delta_seconds": round(time_diff_sec, 3),
                                "sources_a": item_a["sources"],
                                "sources_b": item_b["sources"],
                                "rule": "STATE_CONFLICT_TERMINAL_AMBIGUITY",
                            },
                        )
                        conflicts.append(conflict)
                    else:
                        conflict = cls._record_conflict(
                            db=db,
                            payment_id=payment_id,
                            claim_a=claim_a,
                            claim_b=claim_b,
                            conflict_type=ConflictType.ORDERING_AMBIGUITY.value,
                            severity=ConflictSeverity.INFO.value,
                            detected_at=eval_time,
                            explanation={
                                "what": f"Different statuses observed within clock tolerance window ({val_a} vs {val_b})",
                                "why": f"Time difference ({round(time_diff_sec, 3)}s) is within clock tolerance ({clock_tolerance_seconds}s)",
                                "timestamp_a": t_a.isoformat() if t_a else None,
                                "timestamp_b": t_b.isoformat() if t_b else None,
                                "sources_a": item_a["sources"],
                                "sources_b": item_b["sources"],
                                "rule": "ORDERING_AMBIGUITY_TOLERANCE",
                            },
                        )
                        conflicts.append(conflict)
                else:
                    # Clear chronological sequence: t_a < t_b
                    res = PaymentStateMachine.classify_transition(val_a, val_b)
                    if not res["is_valid"]:
                        conf_type = (
                            ConflictType.STATE_CONFLICT.value
                            if res["transition_type"] == "CONTRADICTORY_TERMINAL"
                            else ConflictType.TEMPORAL_CONFLICT.value
                        )
                        severity = (
                            ConflictSeverity.HIGH.value
                            if res["transition_type"] == "CONTRADICTORY_TERMINAL"
                            else ConflictSeverity.MEDIUM.value
                        )
                        conflict = cls._record_conflict(
                            db=db,
                            payment_id=payment_id,
                            claim_a=claim_a,
                            claim_b=claim_b,
                            conflict_type=conf_type,
                            severity=severity,
                            detected_at=eval_time,
                            explanation={
                                "what": f"Invalid state transition sequence: '{val_a}' at {t_a} -> '{val_b}' at {t_b}",
                                "why": res["explanation"],
                                "transition_type": res["transition_type"],
                                "timestamp_a": t_a.isoformat() if t_a else None,
                                "timestamp_b": t_b.isoformat() if t_b else None,
                                "sources_a": item_a["sources"],
                                "sources_b": item_b["sources"],
                                "rule": "PAYMENT_LIFECYCLE_STATE_MACHINE",
                            },
                        )
                        conflicts.append(conflict)

        return conflicts

    @classmethod
    def _evaluate_value_consistency(
        cls,
        db: Session,
        payment_id: str,
        claim_details_list: List[Dict],
        eval_time: datetime,
        field_name: str,
    ) -> List[EvidenceConflict]:
        conflicts = []
        n = len(claim_details_list)
        if n < 2:
            return conflicts

        for i in range(n):
            for j in range(i + 1, n):
                item_a = claim_details_list[i]
                item_b = claim_details_list[j]

                claim_a = item_a["claim"]
                claim_b = item_b["claim"]

                if claim_a.canonical_value != claim_b.canonical_value:
                    conflict = cls._record_conflict(
                        db=db,
                        payment_id=payment_id,
                        claim_a=claim_a,
                        claim_b=claim_b,
                        conflict_type=ConflictType.VALUE_CONFLICT.value,
                        severity=ConflictSeverity.HIGH.value,
                        detected_at=eval_time,
                        explanation={
                            "what": f"Conflicting {field_name} observed for payment '{payment_id}' ({claim_a.canonical_value} vs {claim_b.canonical_value})",
                            "why": f"A payment cannot simultaneously have multiple distinct values for {field_name}",
                            "timestamp_a": item_a["earliest_time"].isoformat() if item_a["earliest_time"] else None,
                            "timestamp_b": item_b["earliest_time"].isoformat() if item_b["earliest_time"] else None,
                            "sources_a": item_a["sources"],
                            "sources_b": item_b["sources"],
                            "rule": "VALUE_CONSISTENCY_CHECK",
                        },
                    )
                    conflicts.append(conflict)

        return conflicts

    @classmethod
    def _evaluate_order_consistency(
        cls,
        db: Session,
        payment_id: str,
        claim_details_list: List[Dict],
        eval_time: datetime,
    ) -> List[EvidenceConflict]:
        conflicts = []
        n = len(claim_details_list)
        if n < 2:
            return conflicts

        for i in range(n):
            for j in range(i + 1, n):
                item_a = claim_details_list[i]
                item_b = claim_details_list[j]

                claim_a = item_a["claim"]
                claim_b = item_b["claim"]

                if claim_a.canonical_value != claim_b.canonical_value:
                    conflict = cls._record_conflict(
                        db=db,
                        payment_id=payment_id,
                        claim_a=claim_a,
                        claim_b=claim_b,
                        conflict_type=ConflictType.RELATIONSHIP_CONFLICT.value,
                        severity=ConflictSeverity.HIGH.value,
                        detected_at=eval_time,
                        explanation={
                            "what": f"Payment '{payment_id}' associated with multiple conflicting order IDs ({claim_a.canonical_value} vs {claim_b.canonical_value})",
                            "why": "A canonical payment cannot be mapped to multiple distinct orders simultaneously",
                            "timestamp_a": item_a["earliest_time"].isoformat() if item_a["earliest_time"] else None,
                            "timestamp_b": item_b["earliest_time"].isoformat() if item_b["earliest_time"] else None,
                            "sources_a": item_a["sources"],
                            "sources_b": item_b["sources"],
                            "rule": "ORDER_RELATIONSHIP_CONSISTENCY",
                        },
                    )
                    conflicts.append(conflict)

        return conflicts

    @classmethod
    def _record_conflict(
        cls,
        db: Session,
        payment_id: str,
        claim_a: Claim,
        claim_b: Claim,
        conflict_type: str,
        severity: str,
        detected_at: datetime,
        explanation: dict,
    ) -> EvidenceConflict:
        # Pair normalization: ensure lower internal_id is always claim_a_id
        c_a_id = min(claim_a.internal_id, claim_b.internal_id)
        c_b_id = max(claim_a.internal_id, claim_b.internal_id)

        conflict = (
            db.query(EvidenceConflict)
            .filter(
                EvidenceConflict.payment_id == payment_id,
                EvidenceConflict.claim_a_id == c_a_id,
                EvidenceConflict.claim_b_id == c_b_id,
                EvidenceConflict.conflict_type == conflict_type,
                EvidenceConflict.rule_version == cls.RULE_VERSION,
            )
            .first()
        )

        if not conflict:
            conflict = EvidenceConflict(
                payment_id=payment_id,
                claim_a_id=c_a_id,
                claim_b_id=c_b_id,
                conflict_type=conflict_type,
                severity=severity,
                status=ConflictStatus.OPEN.value,
                detected_at=detected_at,
                rule_version=cls.RULE_VERSION,
                explanation=explanation,
            )
            db.add(conflict)
            db.flush()
        else:
            conflict.explanation = explanation
            conflict.severity = severity

        return conflict
