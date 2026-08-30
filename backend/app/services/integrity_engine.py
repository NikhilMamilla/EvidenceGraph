"""
Phase 9 — Evidence Integrity Computation Engine.

Computes a structured, explainable assessment of evidence integrity for a payment
at a specific point in time.

Design principles:
  - Reuses Phase 6 (freshness, source, reliability), Phase 7 (independence,
    corroboration), and Phase 8 (consistency) data — no duplication.
  - Temporal enforcement: only evidence with observed_at <= evaluation_time
    is considered. Future evidence cannot leak into historical calculations.
  - Idempotent: a snapshot for (payment_id, evaluated_at, methodology_version)
    is created at most once.
  - Deterministic: same inputs always produce the same result.
  - No ML, no LLM, no external decisioning.
  - Does NOT produce fraud scores, risk scores, or payment decisions.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.conflict_types import ConflictSeverity, ConflictStatus
from app.models.evidence import EvidenceObservation
from app.models.evidence_conflict import EvidenceConflict
from app.models.evidence_integrity import EvidenceIntegritySnapshot
from app.models.evidence_quality import EvidenceQualitySnapshot
from app.models.evidence_structure import (
    Claim,
    EvidenceClaimLink,
    EvidenceCorroboration,
    EvidenceStructureSnapshot,
)
from app.models.evidence_types import SubjectType
from app.models.integrity_methodology import EISMethodologyV1, EIS_V1
from app.models.integrity_types import (
    INTEGRITY_METHODOLOGY_VERSION,
    ConsistencyStatus,
    CorroborationStatus,
    IndependenceStatus,
    IntegrityStatus,
)
from app.models.payment import Payment
from app.models.quality_types import AuthorityLevel, FreshnessState, SourceDirectness
from app.models.trace_types import ExclusionReason, InclusionStatus
from app.services.trace_canonicalization import methodology_snapshot_hash

logger = logging.getLogger(__name__)

# INFO-severity conflicts do not block STRONG status
_INFO_SEVERITIES = {ConflictSeverity.INFO.value, "INFO"}


class IntegrityEngine:
    """
    Computes Evidence Integrity Snapshots for payments.

    Uses data already persisted by Phase 6, 7, and 8 engines.
    Does NOT re-derive quality or structure from raw evidence —
    it reads the measurement outputs of previous phases.
    """

    @classmethod
    def compute_integrity(
        cls,
        db: Session,
        payment_id: str,
        evaluation_time: datetime,
        methodology_version: str = INTEGRITY_METHODOLOGY_VERSION,
        capture: dict[str, Any] | None = None,
    ) -> EvidenceIntegritySnapshot:
        """
        Compute (or retrieve) the Evidence Integrity Snapshot for a payment.

        If a snapshot already exists for (payment_id, evaluated_at,
        methodology_version), returns it without creating a duplicate.

        Parameters
        ----------
        db : Session
            SQLAlchemy session. Caller controls the transaction.
        payment_id : str
            The Razorpay payment ID to assess.
        evaluation_time : datetime
            Explicit timezone-aware UTC timestamp.
            Only evidence observed at or before this time is included.
        methodology_version : str
            Methodology version string. Defaults to INTEGRITY_METHODOLOGY_VERSION.
        capture : dict, optional
            When provided, the engine records its ACTUAL computation path into
            this dict: evidence scope with exclusions, quality measurements used,
            structural/corroboration/conflict references, per-rule execution
            records, and intermediate results. Phase 10 traces consume this —
            nothing is recomputed or invented downstream.

        Returns
        -------
        EvidenceIntegritySnapshot
            The created or existing snapshot (added to session, not committed).
        """
        if evaluation_time.tzinfo is None:
            raise ValueError("evaluation_time must be timezone-aware UTC.")

        start = time.perf_counter()

        # ------------------------------------------------------------------
        # Idempotency check — return existing snapshot if present
        # ------------------------------------------------------------------
        existing = db.execute(
            select(EvidenceIntegritySnapshot).where(
                EvidenceIntegritySnapshot.payment_id == payment_id,
                EvidenceIntegritySnapshot.evaluated_at == evaluation_time,
                EvidenceIntegritySnapshot.methodology_version == methodology_version,
            )
        ).scalar_one_or_none()

        if existing is not None:
            logger.debug(
                "Integrity snapshot already exists — returning existing",
                extra={
                    "payment_id": payment_id,
                    "evaluated_at": evaluation_time.isoformat(),
                    "methodology_version": methodology_version,
                },
            )
            return existing

        # ------------------------------------------------------------------
        # Execute the authoritative computation (shared with Phase 10 replay)
        # ------------------------------------------------------------------
        result = cls._execute_computation(
            db=db,
            payment_id=payment_id,
            evaluation_time=evaluation_time,
            methodology_version=methodology_version,
            capture=capture,
        )

        # ------------------------------------------------------------------
        # Persist snapshot
        # ------------------------------------------------------------------
        snapshot = EvidenceIntegritySnapshot(
            payment_id=payment_id,
            evaluated_at=evaluation_time,
            methodology_version=methodology_version,
            overall_status=result["overall_status"],
            evidence_count=result["evidence_count"],
            source_count=result["source_count"],
            conflict_count=result["conflict_count"],
            open_conflict_count=result["open_conflict_count"],
            freshness_result=result["freshness_result"],
            source_result=result["source_result"],
            independence_result=result["independence_result"],
            corroboration_result=result["corroboration_result"],
            consistency_result=result["consistency_result"],
            explanation_lines=result["explanation_lines"],
            limitations=result["limitations"],
        )

        try:
            db.add(snapshot)
            db.flush()
        except IntegrityError:
            db.rollback()
            # Race condition — another process created the same snapshot
            existing = db.execute(
                select(EvidenceIntegritySnapshot).where(
                    EvidenceIntegritySnapshot.payment_id == payment_id,
                    EvidenceIntegritySnapshot.evaluated_at == evaluation_time,
                    EvidenceIntegritySnapshot.methodology_version == methodology_version,
                )
            ).scalar_one()
            return existing

        if capture is not None and capture.get("final_result") is not None:
            capture["final_result"]["integrity_snapshot_internal_id"] = (
                snapshot.internal_id
            )

        duration_ms = round((time.perf_counter() - start) * 1000, 2)
        logger.info(
            "Evidence integrity computed",
            extra={
                "payment_id": payment_id,
                "evaluated_at": evaluation_time.isoformat(),
                "methodology_version": methodology_version,
                "evidence_count": result["evidence_count"],
                "source_count": result["source_count"],
                "conflict_count": result["conflict_count"],
                "open_conflict_count": result["open_conflict_count"],
                "overall_status": result["overall_status"],
                "computation_duration_ms": duration_ms,
            },
        )

        return snapshot

    @classmethod
    def _execute_computation(
        cls,
        db: Session,
        payment_id: str,
        evaluation_time: datetime,
        methodology_version: str,
        capture: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Run the full authoritative integrity computation WITHOUT persisting.

        This is the single implementation of the computation path used by:
          - compute_integrity()   (persisting evaluation — Phase 9 behaviour)
          - IntegrityTraceService (decision-trace capture — Phase 10)
          - ReplayService         (re-execution for comparison — Phase 10)

        When `capture` is provided, every stage records exactly what it read
        and produced so a decision trace reflects the ACTUAL computation.
        """
        start_note = time.perf_counter()

        # ------------------------------------------------------------------
        # Gather evidence observations in scope
        # (observed_at <= evaluation_time — temporal isolation enforced in SQL).
        # Candidate exclusions are recorded, never silently discarded.
        # ------------------------------------------------------------------
        included, excluded = cls._scope_candidates(db, payment_id, evaluation_time)
        observations = included
        evidence_count = len(observations)
        evidence_ids = [o.internal_id for o in observations]

        if capture is not None:
            capture.clear()
            capture["evaluation_context"] = cls._build_evaluation_context(
                payment_id, evaluation_time, methodology_version
            )
            capture["evidence_inputs"] = [
                cls._evidence_ref(o, InclusionStatus.INCLUDED) for o in included
            ]
            capture["excluded_evidence"] = [
                {**cls._evidence_ref(o, InclusionStatus.EXCLUDED),
                 "exclusion_reason": reason}
                for o, reason in excluded
            ]

        # ------------------------------------------------------------------
        # Dimension 1 — Freshness (Phase 6 data)
        # ------------------------------------------------------------------
        freshness_result = cls._compute_freshness_dimension(
            db, evidence_ids, evaluation_time
        )

        # ------------------------------------------------------------------
        # Dimension 2 — Source Quality (Phase 6 data)
        # ------------------------------------------------------------------
        source_result = cls._compute_source_dimension(
            db, evidence_ids, evaluation_time
        )

        # ------------------------------------------------------------------
        # Dimension 3 — Independence (Phase 7 structural snapshot)
        # ------------------------------------------------------------------
        independence_result = cls._compute_independence_dimension(
            db, payment_id, evaluation_time
        )

        # ------------------------------------------------------------------
        # Dimension 4 — Corroboration (Phase 7 corroboration records)
        # ------------------------------------------------------------------
        corroboration_result = cls._compute_corroboration_dimension(
            db, payment_id
        )

        # ------------------------------------------------------------------
        # Dimension 5 — Consistency (Phase 8 conflict records)
        # ------------------------------------------------------------------
        conflict_count, open_conflict_count, consistency_result = (
            cls._compute_consistency_dimension(db, payment_id)
        )

        # ------------------------------------------------------------------
        # Source count (for context)
        # ------------------------------------------------------------------
        source_count = cls._count_distinct_sources(observations)

        if capture is not None:
            capture["quality_measurements"] = (
                cls._capture_quality_measurements(db, evidence_ids, evaluation_time)
            )
            capture["structural_measurements"] = (
                cls._capture_structure(db, payment_id, evaluation_time)
            )
            capture["corroboration_measurements"] = (
                cls._capture_corroboration(db, payment_id)
            )
            capture["consistency_measurements"] = (
                cls._capture_conflicts(db, payment_id)
            )

        # ------------------------------------------------------------------
        # Aggregate dimensions → overall status (+ actual rule executions)
        # ------------------------------------------------------------------
        overall_status, rule_executions = cls._aggregate_status_detailed(
            methodology=EIS_V1,
            evidence_count=evidence_count,
            open_conflict_count=open_conflict_count,
            freshness_result=freshness_result,
            source_result=source_result,
            independence_result=independence_result,
            corroboration_result=corroboration_result,
            consistency_result=consistency_result,
        )

        if capture is not None:
            capture["rule_executions"] = rule_executions
            capture["dimension_results"] = {
                "freshness": freshness_result,
                "source": source_result,
                "independence": independence_result,
                "corroboration": corroboration_result,
                "consistency": consistency_result,
            }

        # ------------------------------------------------------------------
        # Build explanation and limitations
        # ------------------------------------------------------------------
        explanation_lines = cls._build_explanation(
            overall_status=overall_status,
            freshness_result=freshness_result,
            source_result=source_result,
            independence_result=independence_result,
            corroboration_result=corroboration_result,
            consistency_result=consistency_result,
            evidence_count=evidence_count,
            open_conflict_count=open_conflict_count,
        )
        limitations = cls._build_limitations(
            freshness_result=freshness_result,
            source_result=source_result,
            independence_result=independence_result,
            corroboration_result=corroboration_result,
        )

        if capture is not None:
            capture["methodology_snapshot"] = EIS_V1.describe()
            capture["methodology_snapshot_hash"] = methodology_snapshot_hash(
                EIS_V1.describe()
            )
            capture["counts"] = {
                "evidence_count": evidence_count,
                "source_count": source_count,
                "conflict_count": conflict_count,
                "open_conflict_count": open_conflict_count,
            }
            capture["final_result"] = {
                "overall_status": overall_status,
                "integrity_snapshot_internal_id": None,  # set after flush by caller
                "score": None,  # EIS-1.0 is status-based; no numeric score exists
            }
            capture["explanation_lines"] = explanation_lines
            capture["limitations"] = limitations
            logger.debug(
                "Integrity computation executed",
                extra={
                    "payment_id": payment_id,
                    "execution_duration_ms": round(
                        (time.perf_counter() - start_note) * 1000, 2
                    ),
                },
            )

        return {
            "overall_status": overall_status,
            "evidence_count": evidence_count,
            "source_count": source_count,
            "conflict_count": conflict_count,
            "open_conflict_count": open_conflict_count,
            "freshness_result": freshness_result,
            "source_result": source_result,
            "independence_result": independence_result,
            "corroboration_result": corroboration_result,
            "consistency_result": consistency_result,
            "explanation_lines": explanation_lines,
            "limitations": limitations,
        }

    # ------------------------------------------------------------------
    # Evidence scope (temporal isolation enforced in SQL)
    # ------------------------------------------------------------------

    @classmethod
    def _scope_candidates(
        cls,
        db: Session,
        payment_id: str,
        evaluation_time: datetime,
    ) -> tuple[list[EvidenceObservation], list[tuple[EvidenceObservation, str]]]:
        """
        Partition candidate evidence observations into (included, excluded).

        Candidates are ALL observations that could plausibly describe this
        payment:
          - observations whose subject IS the payment (any observation time)
          - order-scoped observations linked to this payment's order via
            provenance lineage (they relate to the payment but sit outside
            the payment-subject evaluation scope)

        Exclusion reasons (evaluated in deterministic precedence):
          1. UNRELATED_PAYMENT               subject_id differs from payment_id
          2. OUTSIDE_EVALUATION_SCOPE        subject_type is not 'payment'
          3. OBSERVED_AFTER_EVALUATION_TIME  observed_at > evaluation_time
          4. INVALIDATED                     validity ended at/before
                                             evaluation_time (valid_until set)

        Nothing is silently discarded: every exclusion is returned with its
        reason so Phase 10 traces can record it.
        """
        candidates = db.execute(
            select(EvidenceObservation).where(
                EvidenceObservation.subject_type == SubjectType.PAYMENT,
                EvidenceObservation.subject_id == payment_id,
            )
        ).scalars().all()

        # Order-scoped evidence tied to this payment through provenance lineage.
        payment = db.execute(
            select(Payment).where(Payment.razorpay_payment_id == payment_id)
        ).scalar_one_or_none()
        if payment is not None and payment.order_id:
            from app.models.order import Order

            order = db.get(Order, payment.order_id)
            if order is not None:
                linked_order_obs = db.execute(
                    select(EvidenceObservation).where(
                        EvidenceObservation.subject_type == SubjectType.ORDER,
                        EvidenceObservation.subject_id == order.razorpay_order_id,
                    )
                ).scalars().all()
                candidates.extend(linked_order_obs)

        # Deterministic ordering independent of query plan.
        # Normalize naive DB-loaded timestamps to UTC so comparisons never mix
        # naive and aware datetimes (SQLite drivers return naive values).
        def _utc(value):
            if value is None:
                return None
            if value.tzinfo is None:
                return value.replace(tzinfo=evaluation_time.tzinfo)
            return value

        candidates.sort(
            key=lambda o: (_utc(o.observed_at) or datetime.min.replace(tzinfo=evaluation_time.tzinfo), o.internal_id)
        )

        included: list[EvidenceObservation] = []
        excluded: list[tuple[EvidenceObservation, str]] = []

        for obs in candidates:
            if obs.subject_type != SubjectType.PAYMENT:
                excluded.append((obs, ExclusionReason.OUTSIDE_EVALUATION_SCOPE))
                continue
            if obs.subject_id != payment_id:
                excluded.append((obs, ExclusionReason.UNRELATED_PAYMENT))
                continue
            observed = _utc(obs.observed_at)
            if observed is None or observed > evaluation_time:
                excluded.append((obs, ExclusionReason.OBSERVED_AFTER_EVALUATION_TIME))
                continue
            valid_until = _utc(obs.valid_until)
            if valid_until is not None and valid_until <= evaluation_time:
                excluded.append((obs, ExclusionReason.INVALIDATED))
                continue
            included.append(obs)

        return included, excluded

    @classmethod
    def _get_scoped_observations(
        cls,
        db: Session,
        payment_id: str,
        evaluation_time: datetime,
    ) -> list[EvidenceObservation]:
        """
        Return evidence observations for the payment with
        observed_at <= evaluation_time.

        Temporal isolation is enforced in SQL — not in Python — to prevent
        accidental future-leakage from in-memory filtering bugs.
        """
        return db.execute(
            select(EvidenceObservation).where(
                EvidenceObservation.subject_type == SubjectType.PAYMENT,
                EvidenceObservation.subject_id == payment_id,
                EvidenceObservation.observed_at <= evaluation_time,
            )
        ).scalars().all()

    # ------------------------------------------------------------------
    # Capture helpers (Phase 10 decision-trace support) — these record
    # exactly which persisted measurements the engine consumed. They do
    # NOT recompute any measurement logic.
    # ------------------------------------------------------------------

    @staticmethod
    def _build_evaluation_context(
        payment_id: str,
        evaluation_time: datetime,
        methodology_version: str,
    ) -> dict[str, Any]:
        """Evaluation context recorded verbatim into the trace payload."""
        return {
            "payment_id": payment_id,
            "evaluation_time": evaluation_time,
            "timezone_normalization": "UTC",
            "methodology_version": methodology_version,
        }

    @staticmethod
    def _evidence_ref(obs: EvidenceObservation, inclusion_status: str) -> dict[str, Any]:
        """
        Safe derived reference to an evidence observation.

        Contains metadata only — never raw webhook payloads, secrets, or
        credentials. Authoritative content lives on the referenced record.
        """
        return {
            "evidence_internal_id": obs.internal_id,
            "evidence_type": obs.evidence_type,
            "subject_type": obs.subject_type,
            "subject_id": obs.subject_id,
            "source_type": obs.source_type,
            "source_reference": obs.source_reference,
            "observed_at": obs.observed_at,
            "extraction_version": obs.extraction_version,
            "webhook_event_id": obs.webhook_event_id,
            "payment_event_id": obs.payment_event_id,
            "inclusion_status": inclusion_status,
        }

    @classmethod
    def _capture_quality_measurements(
        cls,
        db: Session,
        evidence_ids: list[int],
        evaluation_time: datetime,
    ) -> list[dict[str, Any]]:
        """Reference the latest Phase 6 quality snapshot per evidence item."""
        if not evidence_ids:
            return []
        rows = db.execute(
            select(EvidenceQualitySnapshot).where(
                EvidenceQualitySnapshot.evidence_id.in_(evidence_ids),
                EvidenceQualitySnapshot.evaluated_at <= evaluation_time,
            )
        ).scalars().all()
        latest_by_evidence: dict[int, EvidenceQualitySnapshot] = {}
        for row in rows:
            eid = row.evidence_id
            if (
                eid not in latest_by_evidence
                or row.evaluated_at > latest_by_evidence[eid].evaluated_at
            ):
                latest_by_evidence[eid] = row
        refs = []
        for eid in sorted(latest_by_evidence.keys()):
            snap = latest_by_evidence[eid]
            refs.append(
                {
                    "evidence_internal_id": eid,
                    "quality_snapshot_internal_id": snap.internal_id,
                    "measured_at": snap.evaluated_at,
                    "freshness_state": snap.freshness_state,
                    "freshness_methodology_version": snap.freshness_methodology_version,
                    "source_authority_level": snap.source_authority_level,
                    "source_directness": snap.source_directness,
                    "source_methodology_version": snap.source_methodology_version,
                    "historical_reliability_status": snap.historical_reliability_status,
                    "reliability_methodology_version": snap.reliability_methodology_version,
                }
            )
        return refs

    @staticmethod
    def _capture_structure(
        db: Session,
        payment_id: str,
        evaluation_time: datetime,
    ) -> dict[str, Any] | None:
        """Reference the Phase 7 structure snapshot the independence dimension uses."""
        snapshot = db.execute(
            select(EvidenceStructureSnapshot).where(
                EvidenceStructureSnapshot.payment_id == payment_id,
                EvidenceStructureSnapshot.evaluated_at <= evaluation_time,
            ).order_by(EvidenceStructureSnapshot.evaluated_at.desc())
        ).scalars().first()
        if snapshot is None:
            return None
        return {
            "structure_snapshot_internal_id": snapshot.internal_id,
            "snapshot_evaluated_at": snapshot.evaluated_at,
            "total_observations": snapshot.total_observations,
            "distinct_claims": snapshot.distinct_claims,
            "distinct_sources": snapshot.distinct_sources,
            "distinct_events": snapshot.distinct_events,
            "distinct_groups": snapshot.distinct_groups,
            "largest_group_size": snapshot.largest_group_size,
            "group_hhi": float(snapshot.group_hhi),
            "corroborated_claim_count": snapshot.corroborated_claim_count,
            "multi_source_claim_count": snapshot.multi_source_claim_count,
            "methodology_version": snapshot.methodology_version,
        }

    @staticmethod
    def _capture_corroboration(db: Session, payment_id: str) -> dict[str, Any]:
        """Reference the Phase 7 corroboration records the dimension consumes."""
        records = db.execute(
            select(EvidenceCorroboration).where(
                EvidenceCorroboration.payment_id == payment_id
            )
        ).scalars().all()
        return {
            "record_internal_ids": sorted(r.internal_id for r in records),
            "total_records": len(records),
            "multi_source_records": sum(
                1 for r in records if r.distinct_sources_count >= 2
            ),
            "multi_observation_records": sum(
                1 for r in records if r.observation_count >= 2
            ),
        }

    @staticmethod
    def _capture_conflicts(db: Session, payment_id: str) -> list[dict[str, Any]]:
        """Reference the Phase 8 conflict records the consistency dimension consumes."""
        conflicts = db.execute(
            select(EvidenceConflict).where(EvidenceConflict.payment_id == payment_id)
        ).scalars().all()
        conflicts.sort(key=lambda c: c.internal_id)
        return [
            {
                "conflict_internal_id": c.internal_id,
                "conflict_type": c.conflict_type,
                "severity": c.severity,
                "status": c.status,
                "detected_at": c.detected_at,
                "rule_version": c.rule_version,
                "claim_a_id": c.claim_a_id,
                "claim_b_id": c.claim_b_id,
            }
            for c in conflicts
        ]

    # ------------------------------------------------------------------
    # Dimension computations
    # ------------------------------------------------------------------

    @classmethod
    def _compute_freshness_dimension(
        cls,
        db: Session,
        evidence_ids: list[int],
        evaluation_time: datetime,
    ) -> dict[str, Any]:
        """
        Freshness dimension — reuses Phase 6 EvidenceQualitySnapshot data.

        Aggregate rule:
          - STRONG  → majority of observations are CURRENT or AGING
          - LIMITED → any STALE observations present
          - UNKNOWN → no quality snapshots available
        """
        if not evidence_ids:
            return {
                "status": "UNKNOWN",
                "reason": "No evidence observations in scope.",
                "inputs": {"evidence_count": 0},
            }

        # Get the most recent quality snapshot for each evidence observation
        # at or before evaluation_time
        rows = db.execute(
            select(EvidenceQualitySnapshot).where(
                EvidenceQualitySnapshot.evidence_id.in_(evidence_ids),
                EvidenceQualitySnapshot.evaluated_at <= evaluation_time,
            )
        ).scalars().all()

        if not rows:
            return {
                "status": "UNKNOWN",
                "reason": "No quality snapshots available for the evidence in scope.",
                "inputs": {"evidence_ids": evidence_ids},
            }

        # Use the most recent snapshot per evidence_id
        latest_by_evidence: dict[int, EvidenceQualitySnapshot] = {}
        for row in rows:
            eid = row.evidence_id
            if eid not in latest_by_evidence or row.evaluated_at > latest_by_evidence[eid].evaluated_at:
                latest_by_evidence[eid] = row

        states = [s.freshness_state for s in latest_by_evidence.values()]
        state_counts = {
            FreshnessState.CURRENT: states.count(FreshnessState.CURRENT),
            FreshnessState.AGING: states.count(FreshnessState.AGING),
            FreshnessState.STALE: states.count(FreshnessState.STALE),
            FreshnessState.UNKNOWN: states.count(FreshnessState.UNKNOWN),
        }
        total = len(states)
        stale_count = state_counts[FreshnessState.STALE]
        current_count = state_counts[FreshnessState.CURRENT] + state_counts[FreshnessState.AGING]

        if stale_count > 0:
            status = "LIMITED"
            reason = (
                f"{stale_count} of {total} evidence observations are stale."
            )
        elif current_count == total:
            status = "STRONG"
            reason = (
                f"All {total} evidence observations are current or aging."
            )
        else:
            status = "LIMITED"
            reason = (
                f"Freshness state is mixed across {total} observations."
            )

        return {
            "status": status,
            "reason": reason,
            "inputs": {
                "evidence_snapshot_count": total,
                "current_count": state_counts[FreshnessState.CURRENT],
                "aging_count": state_counts[FreshnessState.AGING],
                "stale_count": stale_count,
                "unknown_count": state_counts[FreshnessState.UNKNOWN],
            },
        }

    @classmethod
    def _compute_source_dimension(
        cls,
        db: Session,
        evidence_ids: list[int],
        evaluation_time: datetime,
    ) -> dict[str, Any]:
        """
        Source quality dimension — reuses Phase 6 quality snapshots.

        Aggregate rule:
          - STRONG  → dominant authority is PRIMARY + directness DIRECT
          - LIMITED → dominant authority is SECONDARY or directness DERIVED
          - WEAK    → any TERTIARY authority present
          - UNKNOWN → no quality snapshots available
        """
        if not evidence_ids:
            return {
                "status": "UNKNOWN",
                "reason": "No evidence observations in scope.",
                "inputs": {},
            }

        rows = db.execute(
            select(EvidenceQualitySnapshot).where(
                EvidenceQualitySnapshot.evidence_id.in_(evidence_ids),
                EvidenceQualitySnapshot.evaluated_at <= evaluation_time,
            )
        ).scalars().all()

        if not rows:
            return {
                "status": "UNKNOWN",
                "reason": "No quality snapshots available for source assessment.",
                "inputs": {},
            }

        # Use most recent per evidence
        latest_by_evidence: dict[int, EvidenceQualitySnapshot] = {}
        for row in rows:
            eid = row.evidence_id
            if eid not in latest_by_evidence or row.evaluated_at > latest_by_evidence[eid].evaluated_at:
                latest_by_evidence[eid] = row

        authority_levels = [s.source_authority_level for s in latest_by_evidence.values()]
        directness_vals = [s.source_directness for s in latest_by_evidence.values()]

        tertiary_count = authority_levels.count(AuthorityLevel.TERTIARY)
        primary_count = authority_levels.count(AuthorityLevel.PRIMARY)
        secondary_count = authority_levels.count(AuthorityLevel.SECONDARY)
        direct_count = directness_vals.count(SourceDirectness.DIRECT)
        total = len(authority_levels)

        if tertiary_count > 0:
            status = "WEAK"
            reason = (
                f"{tertiary_count} of {total} observations have TERTIARY authority."
            )
        elif primary_count == total and direct_count == total:
            status = "STRONG"
            reason = (
                "All observations originate from a primary authoritative source "
                "with direct provenance."
            )
        elif primary_count + secondary_count == total:
            status = "LIMITED"
            reason = (
                f"{secondary_count} of {total} observations are from a secondary source."
            )
        else:
            status = "LIMITED"
            reason = "Source authority is mixed across observations."

        return {
            "status": status,
            "reason": reason,
            "inputs": {
                "total_observations": total,
                "primary_count": primary_count,
                "secondary_count": secondary_count,
                "tertiary_count": tertiary_count,
                "direct_count": direct_count,
            },
        }

    @classmethod
    def _compute_independence_dimension(
        cls,
        db: Session,
        payment_id: str,
        evaluation_time: datetime,
    ) -> dict[str, Any]:
        """
        Independence dimension — reuses Phase 7 EvidenceStructureSnapshot.

        Uses the most recent structure snapshot at or before evaluation_time.

        Status mapping:
          - HIGH_SOURCE_DIVERSITY  → distinct_sources >= 2 AND distinct_events >= 2
          - LIMITED_SOURCE_DIVERSITY → distinct_sources >= 2 OR distinct_events >= 2
          - SINGLE_SOURCE           → distinct_sources == 1 AND distinct_events == 1
          - UNKNOWN                 → no structure snapshot available
        """
        snapshot = db.execute(
            select(EvidenceStructureSnapshot).where(
                EvidenceStructureSnapshot.payment_id == payment_id,
                EvidenceStructureSnapshot.evaluated_at <= evaluation_time,
            ).order_by(EvidenceStructureSnapshot.evaluated_at.desc())
        ).scalars().first()

        if snapshot is None:
            return {
                "status": IndependenceStatus.UNKNOWN,
                "reason": "No structure snapshot available for independence assessment.",
                "inputs": {},
            }

        distinct_sources = snapshot.distinct_sources
        distinct_events = snapshot.distinct_events
        hhi = float(snapshot.group_hhi) if snapshot.group_hhi is not None else None

        if distinct_sources >= 2 and distinct_events >= 2:
            status = IndependenceStatus.HIGH_SOURCE_DIVERSITY
            reason = (
                f"Evidence comes from {distinct_sources} distinct source types "
                f"across {distinct_events} distinct provider events."
            )
        elif distinct_sources >= 2 or distinct_events >= 2:
            status = IndependenceStatus.LIMITED_SOURCE_DIVERSITY
            reason = (
                f"Evidence spans {distinct_sources} source type(s) and "
                f"{distinct_events} event(s). Some structural diversity exists."
            )
        else:
            status = IndependenceStatus.SINGLE_SOURCE
            reason = (
                "All observations originate from a single source type and event. "
                "Source diversity is minimal."
            )

        return {
            "status": status,
            "reason": reason,
            "inputs": {
                "distinct_sources": distinct_sources,
                "distinct_events": distinct_events,
                "distinct_groups": snapshot.distinct_groups,
                "group_hhi": hhi,
                "total_observations": snapshot.total_observations,
            },
        }

    @classmethod
    def _compute_corroboration_dimension(
        cls,
        db: Session,
        payment_id: str,
    ) -> dict[str, Any]:
        """
        Corroboration dimension — reuses Phase 7 EvidenceCorroboration records.

        Status mapping:
          - STRONGLY_CORROBORATED   → at least one multi-source corroborated claim
          - PARTIALLY_CORROBORATED  → at least one multi-observation claim (same source)
          - SINGLE_OBSERVATION      → all claims have only one observation
          - UNKNOWN                 → no corroboration records available
        """
        records = db.execute(
            select(EvidenceCorroboration).where(
                EvidenceCorroboration.payment_id == payment_id
            )
        ).scalars().all()

        if not records:
            return {
                "status": CorroborationStatus.UNKNOWN,
                "reason": "No corroboration records available for this payment.",
                "inputs": {},
            }

        multi_source = [r for r in records if r.distinct_sources_count >= 2]
        multi_obs = [r for r in records if r.observation_count >= 2]
        total_claims = len(records)

        if multi_source:
            status = CorroborationStatus.STRONGLY_CORROBORATED
            reason = (
                f"{len(multi_source)} of {total_claims} claim(s) are supported "
                f"by observations from multiple distinct sources."
            )
        elif multi_obs:
            status = CorroborationStatus.PARTIALLY_CORROBORATED
            reason = (
                f"{len(multi_obs)} of {total_claims} claim(s) are supported by "
                f"multiple observations from the same source."
            )
        else:
            status = CorroborationStatus.SINGLE_OBSERVATION
            reason = (
                f"All {total_claims} claim(s) are supported by a single observation."
            )

        return {
            "status": status,
            "reason": reason,
            "inputs": {
                "total_claims": total_claims,
                "multi_source_claims": len(multi_source),
                "multi_observation_claims": len(multi_obs),
            },
        }

    @classmethod
    def _compute_consistency_dimension(
        cls,
        db: Session,
        payment_id: str,
    ) -> tuple[int, int, dict[str, Any]]:
        """
        Consistency dimension — reuses Phase 8 EvidenceConflict records.

        Returns (conflict_count, open_conflict_count, dimension_result).

        Status mapping:
          - NO_DETECTED_CONFLICT    → no conflict records
          - ORDERING_AMBIGUITY_ONLY → only INFO-severity conflicts
          - HAS_OPEN_CONFLICTS      → at least one OPEN conflict with severity > INFO
          - UNRESOLVABLE            → UNRESOLVED status conflicts exist
        """
        conflicts = db.execute(
            select(EvidenceConflict).where(
                EvidenceConflict.payment_id == payment_id
            )
        ).scalars().all()

        conflict_count = len(conflicts)

        if conflict_count == 0:
            return 0, 0, {
                "status": ConsistencyStatus.NO_DETECTED_CONFLICT,
                "reason": (
                    "No contradiction was detected in the available evidence. "
                    "This does not guarantee perfect consistency — it means no "
                    "conflict rule was triggered."
                ),
                "inputs": {"conflict_count": 0},
            }

        open_non_info = [
            c for c in conflicts
            if c.status == ConflictStatus.OPEN.value
            and c.severity not in _INFO_SEVERITIES
        ]
        unresolvable = [
            c for c in conflicts
            if c.status == ConflictStatus.UNRESOLVED.value
        ]
        info_only = [
            c for c in conflicts
            if c.severity in _INFO_SEVERITIES
        ]

        open_conflict_count = len(open_non_info)

        if unresolvable:
            status = ConsistencyStatus.UNRESOLVABLE
            reason = (
                f"{len(unresolvable)} conflict(s) could not be resolved by "
                f"subsequent evidence."
            )
        elif open_non_info:
            status = ConsistencyStatus.HAS_OPEN_CONFLICTS
            reason = (
                f"{len(open_non_info)} open semantic conflict(s) detected "
                f"(severity > INFO) that have not been resolved."
            )
        else:
            status = ConsistencyStatus.ORDERING_AMBIGUITY_ONLY
            reason = (
                f"Only ordering ambiguities (INFO-severity) detected "
                f"({len(info_only)} conflict(s)). No semantic contradictions."
            )

        resolved = [c for c in conflicts if c.status == ConflictStatus.RESOLVED.value]

        return conflict_count, open_conflict_count, {
            "status": status,
            "reason": reason,
            "inputs": {
                "conflict_count": conflict_count,
                "open_non_info_count": len(open_non_info),
                "resolved_count": len(resolved),
                "unresolvable_count": len(unresolvable),
                "info_only_count": len(info_only),
            },
        }

    # ------------------------------------------------------------------
    # Aggregation
    # ------------------------------------------------------------------

    @classmethod
    def _aggregate_status(
        cls,
        methodology,
        evidence_count: int,
        open_conflict_count: int,
        freshness_result: dict,
        source_result: dict,
        independence_result: dict,
        corroboration_result: dict,
        consistency_result: dict,
    ) -> str:
        """Apply EIS gates and return only the overall status (compat wrapper)."""
        status, _rules = cls._aggregate_status_detailed(
            methodology=methodology,
            evidence_count=evidence_count,
            open_conflict_count=open_conflict_count,
            freshness_result=freshness_result,
            source_result=source_result,
            independence_result=independence_result,
            corroboration_result=corroboration_result,
            consistency_result=consistency_result,
        )
        return status

    @classmethod
    def _aggregate_status_detailed(
        cls,
        methodology,
        evidence_count: int,
        open_conflict_count: int,
        freshness_result: dict,
        source_result: dict,
        independence_result: dict,
        corroboration_result: dict,
        consistency_result: dict,
    ) -> tuple[str, list[dict[str, Any]]]:
        """
        Apply the methodology's rule-based aggregation gates in priority order.

        Returns (overall_status, rule_execution_records). Every gate that was
        actually evaluated produces one record with its concrete inputs and a
        factual explanation; gates after the firing gate are not executed and
        therefore produce no records (the computation path is short-circuit).
        """
        freshness_status = freshness_result.get("status", "UNKNOWN")
        source_status = source_result.get("status", "UNKNOWN")
        independence_status = independence_result.get("status", IndependenceStatus.UNKNOWN)
        corroboration_status = corroboration_result.get("status", CorroborationStatus.UNKNOWN)
        consistency_status = consistency_result.get("status", ConsistencyStatus.NO_DETECTED_CONFLICT)

        dimension_inputs = {
            "evidence_count": evidence_count,
            "open_conflict_count": open_conflict_count,
            "freshness": freshness_status,
            "source": source_status,
            "independence": independence_status,
            "corroboration": corroboration_status,
            "consistency": consistency_status,
        }

        def _record(order, gate, fired, explanation):
            return {
                "rule_id": f"{methodology.version}.{gate.name}",
                "rule_version": methodology.version,
                "execution_order": order,
                "inputs": dict(dimension_inputs),
                "result": gate.result_status if fired else None,
                "fired": fired,
                "explanation": explanation,
            }

        rules: list[dict[str, Any]] = []
        order = 0

        # Gate 1 — INSUFFICIENT_DATA
        order += 1
        gate = methodology.gates[0]
        if evidence_count == 0:
            rules.append(_record(
                order, gate, True,
                f"Gate fired: {evidence_count} evidence observations were in scope "
                "(no evidence to assess).",
            ))
            return IntegrityStatus.INSUFFICIENT_DATA, rules
        rules.append(_record(
            order, gate, False,
            f"Gate not fired: {evidence_count} evidence observation(s) in scope.",
        ))

        # Gate 2 — UNRESOLVED
        order += 1
        gate = methodology.gates[1]
        if open_conflict_count > 0:
            rules.append(_record(
                order, gate, True,
                f"Gate fired: {open_conflict_count} open conflict(s) with severity "
                "> INFO detected and not resolved.",
            ))
            return IntegrityStatus.UNRESOLVED, rules
        rules.append(_record(
            order, gate, False,
            "Gate not fired: no open semantic conflicts (severity > INFO) detected.",
        ))

        # Gate 3 — WEAK
        order += 1
        gate = methodology.gates[2]
        weak_reasons = []
        if freshness_status == FreshnessState.STALE:
            weak_reasons.append("freshness is STALE")
        if freshness_status == "UNKNOWN":
            weak_reasons.append("freshness could not be determined")
        if source_status == "WEAK":
            weak_reasons.append("source authority includes TERTIARY level")
        if weak_reasons:
            rules.append(_record(
                order, gate, True,
                "Gate fired: " + "; ".join(weak_reasons) + ".",
            ))
            return IntegrityStatus.WEAK, rules
        rules.append(_record(
            order, gate, False,
            "Gate not fired: freshness determined and not stale; no tertiary sources.",
        ))

        # Gate 4 — VERY_STRONG
        order += 1
        gate = methodology.gates[3]
        very_strong_conditions = (
            freshness_status == "STRONG"
            and source_status == "STRONG"
            and independence_status == IndependenceStatus.HIGH_SOURCE_DIVERSITY
            and corroboration_status == CorroborationStatus.STRONGLY_CORROBORATED
            and consistency_status == ConsistencyStatus.NO_DETECTED_CONFLICT
            and evidence_count >= methodology.very_strong_min_observations
        )
        if very_strong_conditions:
            rules.append(_record(
                order, gate, True,
                "Gate fired: all dimensions maximally strong across "
                f"{evidence_count} observations (minimum "
                f"{methodology.very_strong_min_observations}).",
            ))
            return IntegrityStatus.VERY_STRONG, rules
        unmet = []
        if freshness_status != "STRONG":
            unmet.append(f"freshness={freshness_status}")
        if source_status != "STRONG":
            unmet.append(f"source={source_status}")
        if independence_status != IndependenceStatus.HIGH_SOURCE_DIVERSITY:
            unmet.append(f"independence={independence_status}")
        if corroboration_status != CorroborationStatus.STRONGLY_CORROBORATED:
            unmet.append(f"corroboration={corroboration_status}")
        if consistency_status != ConsistencyStatus.NO_DETECTED_CONFLICT:
            unmet.append(f"consistency={consistency_status}")
        if evidence_count < methodology.very_strong_min_observations:
            unmet.append(
                f"evidence_count={evidence_count} < "
                f"{methodology.very_strong_min_observations}"
            )
        rules.append(_record(
            order, gate, False,
            "Gate not fired: " + ", ".join(unmet) + ".",
        ))

        # Gate 5 — STRONG
        order += 1
        gate = methodology.gates[4]
        strong_conditions = (
            freshness_status in ("STRONG", "LIMITED")
            and source_status in ("STRONG", "LIMITED")
            and consistency_status in methodology.strong_consistency_allowed
            and freshness_status != FreshnessState.STALE
        )
        if strong_conditions:
            rules.append(_record(
                order, gate, True,
                "Gate fired: evidence is current, from an authoritative source, "
                "and no open semantic conflicts exist.",
            ))
            return IntegrityStatus.STRONG, rules
        rules.append(_record(
            order, gate, False,
            "Gate not fired: core quality indicators do not meet the STRONG "
            "thresholds.",
        ))

        # Gate 6 (fallthrough) — LIMITED
        order += 1
        gate = methodology.gates[5]
        rules.append(_record(
            order, gate, True,
            "Default gate fired: at least one dimension is limited but no open "
            "semantic conflicts were detected.",
        ))
        return IntegrityStatus.LIMITED, rules

    # ------------------------------------------------------------------
    # Explanation engine
    # ------------------------------------------------------------------

    @classmethod
    def _build_explanation(
        cls,
        overall_status: str,
        freshness_result: dict,
        source_result: dict,
        independence_result: dict,
        corroboration_result: dict,
        consistency_result: dict,
        evidence_count: int,
        open_conflict_count: int,
    ) -> list[str]:
        """
        Build a deterministic, human-readable explanation from actual data values.

        Language rules:
          - Does NOT claim "payment is legitimate" or "this transaction is safe."
          - Does NOT claim fraud, risk, or intent.
          - Uses neutral evidence-quality language only.
        """
        lines = []

        freshness_status = freshness_result.get("status", "UNKNOWN")
        source_status = source_result.get("status", "UNKNOWN")
        independence_status = independence_result.get("status", IndependenceStatus.UNKNOWN)
        corroboration_status = corroboration_result.get("status", CorroborationStatus.UNKNOWN)
        consistency_status = consistency_result.get("status", ConsistencyStatus.NO_DETECTED_CONFLICT)

        # Freshness
        if freshness_status == "STRONG":
            lines.append("Evidence was observed recently.")
        elif freshness_status == "LIMITED":
            stale = freshness_result.get("inputs", {}).get("stale_count", 0)
            if stale:
                lines.append(f"{stale} observation(s) have aged beyond the freshness threshold.")
        elif freshness_status in ("UNKNOWN",):
            lines.append("Freshness could not be determined (no quality measurement available).")

        # Source
        if source_status == "STRONG":
            lines.append("Observations originate from an authoritative primary provider source.")
        elif source_status == "LIMITED":
            lines.append("Some observations originate from a secondary (non-primary) source.")
        elif source_status == "WEAK":
            lines.append("At least one observation originates from a tertiary (non-authoritative) source.")

        # Corroboration
        if corroboration_status == CorroborationStatus.STRONGLY_CORROBORATED:
            mc = corroboration_result.get("inputs", {}).get("multi_source_claims", 0)
            lines.append(
                f"{mc} claim(s) are supported by observations from multiple independent sources."
            )
        elif corroboration_status == CorroborationStatus.PARTIALLY_CORROBORATED:
            lines.append(
                "Claims are supported by multiple observations, but all from the same source."
            )
        elif corroboration_status == CorroborationStatus.SINGLE_OBSERVATION:
            lines.append("Each claim is supported by only one observation.")

        # Consistency
        if consistency_status == ConsistencyStatus.NO_DETECTED_CONFLICT:
            lines.append(
                "No contradiction was detected in the available evidence."
            )
        elif consistency_status == ConsistencyStatus.ORDERING_AMBIGUITY_ONLY:
            lines.append(
                "Minor ordering ambiguities exist, but no semantic contradiction was detected."
            )
        elif consistency_status == ConsistencyStatus.HAS_OPEN_CONFLICTS:
            lines.append(
                f"{open_conflict_count} open semantic conflict(s) detected in the evidence."
            )
        elif consistency_status == ConsistencyStatus.UNRESOLVABLE:
            lines.append("One or more conflicts could not be resolved by subsequent evidence.")

        # Independence — always mention if limited (important caveat)
        if independence_status == IndependenceStatus.SINGLE_SOURCE:
            lines.append(
                "All observations originate from a single provider event, limiting structural diversity."
            )
        elif independence_status == IndependenceStatus.LIMITED_SOURCE_DIVERSITY:
            lines.append(
                "Observations span more than one event but source type diversity is limited."
            )
        elif independence_status == IndependenceStatus.UNKNOWN:
            lines.append("Source diversity could not be assessed (no structure snapshot available).")

        return lines

    # ------------------------------------------------------------------
    # Limitations engine
    # ------------------------------------------------------------------

    @classmethod
    def _build_limitations(
        cls,
        freshness_result: dict,
        source_result: dict,
        independence_result: dict,
        corroboration_result: dict,
    ) -> list[str]:
        """
        Produce an explicit list of limitations in this integrity assessment.

        Uncertainty is a first-class output, not a failure.
        """
        limitations = []

        # Historical reliability is always unavailable in current phases
        limitations.append(
            "Historical reliability data is unavailable: no payment outcome records exist yet."
        )

        independence_status = independence_result.get("status", IndependenceStatus.UNKNOWN)
        if independence_status in (
            IndependenceStatus.SINGLE_SOURCE,
            IndependenceStatus.LIMITED_SOURCE_DIVERSITY,
        ):
            inp = independence_result.get("inputs", {})
            src = inp.get("distinct_sources", 1)
            evt = inp.get("distinct_events", 1)
            limitations.append(
                f"Evidence source diversity is limited "
                f"({src} source type(s), {evt} event(s))."
            )

        corroboration_status = corroboration_result.get("status", CorroborationStatus.UNKNOWN)
        if corroboration_status == CorroborationStatus.UNKNOWN:
            limitations.append(
                "Corroboration could not be assessed (no corroboration records available)."
            )
        elif corroboration_status == CorroborationStatus.SINGLE_OBSERVATION:
            limitations.append(
                "Independent corroboration is absent: each claim has only one supporting observation."
            )

        if independence_result.get("status") == IndependenceStatus.UNKNOWN:
            limitations.append(
                "Independence could not be assessed (no structure snapshot available)."
            )

        return limitations

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _count_distinct_sources(observations: list[EvidenceObservation]) -> int:
        return len({o.source_type for o in observations if o.source_type})
