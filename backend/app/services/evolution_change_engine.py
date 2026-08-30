"""
Phase 11 — Evidence Change Engine.

Compares two ``EvidenceStateSnapshot`` objects, detects material changes across
every evidence quality dimension, determines causality, generates deterministic
human-readable explanations, and persists ``EvidenceStateChange`` records.

Design contracts:
  - All methods are classmethods; the class carries no instance state.
  - ``compare_snapshots`` is a pure function — no DB access, no side effects.
  - ``detect_and_persist_changes`` is idempotent: the DB unique constraint on
    (previous_snapshot_id, current_snapshot_id, change_type, dimension) ensures
    that repeated calls for the same snapshot pair produce no duplicate rows.
  - Race-condition safety: ``IntegrityError`` on concurrent inserts is caught at
    savepoint level; the existing row is re-queried and returned.
  - No fraud detection, risk scoring, ML, LLM, or automated decisions.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.evolution_models import EvidenceStateChange, EvidenceStateSnapshot
from app.models.evolution_types import (
    CausalityLevel,
    ChangeDimension,
    ChangeMagnitude,
    ChangeType,
    DirectCause,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Corroboration ordering — higher index = more corroborated
# ---------------------------------------------------------------------------
_CORROBORATION_ORDER: dict[str, int] = {
    "UNKNOWN": 0,
    "SINGLE_OBSERVATION": 1,
    "PARTIALLY_CORROBORATED": 2,
    "STRONGLY_CORROBORATED": 3,
}

# Freshness ordering — higher index = more fresh (better)
_FRESHNESS_ORDER: dict[str, int] = {
    "UNKNOWN": 0,
    "STALE": 1,
    "AGING": 2,
    "CURRENT": 3,
}

# IntegrityStatus tier ordering — higher index = better integrity
_INTEGRITY_ORDER: dict[str, int] = {
    "INSUFFICIENT_DATA": 0,
    "WEAK": 1,
    "UNRESOLVED": 1,
    "LIMITED": 2,
    "STRONG": 3,
    "VERY_STRONG": 4,
}


class EvidenceChangeEngine:
    """
    Detects and persists evidence state changes between two consecutive
    ``EvidenceStateSnapshot`` records.

    All methods are classmethods — no instance state is held.
    """

    # ------------------------------------------------------------------
    # Public: pure comparison
    # ------------------------------------------------------------------

    @classmethod
    def compare_snapshots(
        cls,
        previous: EvidenceStateSnapshot,
        current: EvidenceStateSnapshot,
    ) -> list[dict]:
        """
        Pure typed diff of two ``EvidenceStateSnapshot`` objects.

        Compares every tracked dimension field and returns a list of dicts
        — one per changed dimension — each containing:

            {
                "dimension":      <ChangeDimension constant>,
                "change_type":    <ChangeType constant>,
                "previous_value": <str>,
                "current_value":  <str>,
            }

        Returns an empty list if no dimension changed.
        Does NOT access the database and has no side effects.
        """
        diffs: list[dict] = []

        # ----------------------------------------------------------------
        # EVIDENCE dimension — evidence_count (int)
        # ----------------------------------------------------------------
        if previous.evidence_count != current.evidence_count:
            if current.evidence_count > previous.evidence_count:
                change_type = ChangeType.NEW_EVIDENCE
            else:
                change_type = ChangeType.EVIDENCE_REMOVED
            diffs.append(
                {
                    "dimension": ChangeDimension.EVIDENCE,
                    "change_type": change_type,
                    "previous_value": str(previous.evidence_count),
                    "current_value": str(current.evidence_count),
                }
            )

        # ----------------------------------------------------------------
        # SOURCE dimension — source_count (int)
        # ----------------------------------------------------------------
        if previous.source_count != current.source_count:
            if current.source_count > previous.source_count:
                change_type = ChangeType.NEW_SOURCE
            else:
                change_type = ChangeType.SOURCE_LOST
            diffs.append(
                {
                    "dimension": ChangeDimension.SOURCE,
                    "change_type": change_type,
                    "previous_value": str(previous.source_count),
                    "current_value": str(current.source_count),
                }
            )

        # ----------------------------------------------------------------
        # CORROBORATION dimension — corroboration_status (ordered string)
        # ----------------------------------------------------------------
        if previous.corroboration_status != current.corroboration_status:
            prev_rank = _CORROBORATION_ORDER.get(previous.corroboration_status, 0)
            curr_rank = _CORROBORATION_ORDER.get(current.corroboration_status, 0)
            if curr_rank > prev_rank:
                change_type = ChangeType.CORROBORATION_INCREASED
            else:
                change_type = ChangeType.CORROBORATION_DECREASED
            diffs.append(
                {
                    "dimension": ChangeDimension.CORROBORATION,
                    "change_type": change_type,
                    "previous_value": previous.corroboration_status,
                    "current_value": current.corroboration_status,
                }
            )

        # ----------------------------------------------------------------
        # INDEPENDENCE dimension — independence_status (string change)
        # ----------------------------------------------------------------
        if previous.independence_status != current.independence_status:
            diffs.append(
                {
                    "dimension": ChangeDimension.INDEPENDENCE,
                    "change_type": ChangeType.INDEPENDENCE_CHANGED,
                    "previous_value": previous.independence_status,
                    "current_value": current.independence_status,
                }
            )

        # ----------------------------------------------------------------
        # FRESHNESS dimension — freshness_status (string change)
        # ----------------------------------------------------------------
        if previous.freshness_status != current.freshness_status:
            diffs.append(
                {
                    "dimension": ChangeDimension.FRESHNESS,
                    "change_type": ChangeType.FRESHNESS_CHANGED,
                    "previous_value": previous.freshness_status,
                    "current_value": current.freshness_status,
                }
            )

        # ----------------------------------------------------------------
        # CONSISTENCY dimension — open_conflict_count (int) + consistency_status
        # ----------------------------------------------------------------
        if previous.open_conflict_count != current.open_conflict_count:
            if current.open_conflict_count > previous.open_conflict_count:
                change_type = ChangeType.CONFLICT_CREATED
            else:
                change_type = ChangeType.CONFLICT_RESOLVED
            diffs.append(
                {
                    "dimension": ChangeDimension.CONSISTENCY,
                    "change_type": change_type,
                    "previous_value": str(previous.open_conflict_count),
                    "current_value": str(current.open_conflict_count),
                }
            )
        elif previous.consistency_status != current.consistency_status:
            # Conflict count unchanged but consistency label changed
            diffs.append(
                {
                    "dimension": ChangeDimension.CONSISTENCY,
                    "change_type": ChangeType.FRESHNESS_CHANGED,
                    "previous_value": previous.consistency_status,
                    "current_value": current.consistency_status,
                }
            )

        # ----------------------------------------------------------------
        # INTEGRITY dimension — overall_integrity_status (string change)
        # ----------------------------------------------------------------
        if previous.overall_integrity_status != current.overall_integrity_status:
            diffs.append(
                {
                    "dimension": ChangeDimension.INTEGRITY,
                    "change_type": ChangeType.INTEGRITY_CHANGED,
                    "previous_value": previous.overall_integrity_status,
                    "current_value": current.overall_integrity_status,
                }
            )

        # ----------------------------------------------------------------
        # METHODOLOGY dimension — methodology_version (string change)
        # ----------------------------------------------------------------
        if previous.methodology_version != current.methodology_version:
            diffs.append(
                {
                    "dimension": ChangeDimension.METHODOLOGY,
                    "change_type": ChangeType.METHODOLOGY_CHANGED,
                    "previous_value": previous.methodology_version,
                    "current_value": current.methodology_version,
                }
            )

        return diffs

    # ------------------------------------------------------------------
    # Public: detect + persist
    # ------------------------------------------------------------------

    @classmethod
    def detect_and_persist_changes(
        cls,
        db: Session,
        payment_id: str,
        previous_snapshot: EvidenceStateSnapshot,
        current_snapshot: EvidenceStateSnapshot,
    ) -> list[EvidenceStateChange]:
        """
        Run ``compare_snapshots``, determine causality, generate explanations,
        compute magnitudes, and persist ``EvidenceStateChange`` records.

        Idempotent: the unique constraint on
        ``(previous_snapshot_id, current_snapshot_id, change_type, dimension)``
        prevents duplicate rows.  Race conditions are handled via savepoint.

        Parameters
        ----------
        db : Session
            SQLAlchemy session.  Caller controls the outer transaction.
        payment_id : str
            The payment ID being analysed.
        previous_snapshot : EvidenceStateSnapshot
            The earlier snapshot.
        current_snapshot : EvidenceStateSnapshot
            The later snapshot.

        Returns
        -------
        list[EvidenceStateChange]
            Persisted change records (empty list if no material change).
        """
        diffs = cls.compare_snapshots(previous_snapshot, current_snapshot)
        if not diffs:
            logger.debug(
                "No material change detected between snapshots",
                extra={
                    "payment_id": payment_id,
                    "previous_snapshot_id": previous_snapshot.internal_id,
                    "current_snapshot_id": current_snapshot.internal_id,
                },
            )
            return []

        now = datetime.now(timezone.utc)
        persisted: list[EvidenceStateChange] = []

        for diff in diffs:
            dimension: str = diff["dimension"]
            change_type: str = diff["change_type"]
            prev_value: str = diff["previous_value"]
            curr_value: str = diff["current_value"]

            direct_cause, causality = cls._determine_cause(
                change_type, previous_snapshot, current_snapshot, db
            )
            explanation = cls._generate_explanation(
                change_type, dimension, prev_value, curr_value, direct_cause
            )
            magnitude = cls._compute_magnitude(change_type, prev_value, curr_value)

            change = EvidenceStateChange(
                change_id=str(uuid.uuid4()),
                payment_id=payment_id,
                previous_snapshot_id=previous_snapshot.internal_id,
                current_snapshot_id=current_snapshot.internal_id,
                detected_at=now,
                change_type=change_type,
                dimension=dimension,
                previous_value=prev_value,
                current_value=curr_value,
                direct_cause=direct_cause,
                causality=causality,
                explanation=explanation,
                magnitude=magnitude,
                methodology_version=current_snapshot.methodology_version,
            )

            # Use a savepoint so a uniqueness race on one dimension doesn't
            # abort the entire outer transaction.
            savepoint = db.begin_nested()
            try:
                db.add(change)
                db.flush()
                savepoint.commit()
                persisted.append(change)
                logger.debug(
                    "Evidence state change persisted",
                    extra={
                        "payment_id": payment_id,
                        "change_id": change.change_id,
                        "dimension": dimension,
                        "change_type": change_type,
                        "direct_cause": direct_cause,
                        "causality": causality,
                        "magnitude": magnitude,
                    },
                )
            except IntegrityError:
                savepoint.rollback()
                # Another process already wrote the same change — re-query it.
                existing = db.execute(
                    select(EvidenceStateChange).where(
                        EvidenceStateChange.previous_snapshot_id
                        == previous_snapshot.internal_id,
                        EvidenceStateChange.current_snapshot_id
                        == current_snapshot.internal_id,
                        EvidenceStateChange.change_type == change_type,
                        EvidenceStateChange.dimension == dimension,
                    )
                ).scalar_one_or_none()
                if existing is not None:
                    persisted.append(existing)
                logger.debug(
                    "Evidence state change race — returning existing record",
                    extra={
                        "payment_id": payment_id,
                        "dimension": dimension,
                        "change_type": change_type,
                    },
                )

        return persisted

    # ------------------------------------------------------------------
    # Private: causality
    # ------------------------------------------------------------------

    @classmethod
    def _determine_cause(
        cls,
        change_type: str,
        prev_snapshot: EvidenceStateSnapshot,
        curr_snapshot: EvidenceStateSnapshot,
        db: Session,
    ) -> tuple[str, str]:
        """
        Return ``(direct_cause, causality_level)`` for a given change type.

        Rules (evaluated in priority order):
          1. evidence_count increased               → NEW_EVIDENCE,        DIRECT
          2. evidence_count unchanged + freshness   → TIME_PASSAGE,        DIRECT
             degraded (current freshness rank < prev)
          3. open_conflict_count increased          → CONFLICT,            DIRECT
          4. open_conflict_count decreased          → CONFLICT_RESOLUTION, DIRECT
          5. methodology_version changed            → METHODOLOGY_CHANGE,  DIRECT
          6. source_count changed                   → SOURCE_CHANGE,       INFERRED
          7. corroboration changed + evidence also  → NEW_EVIDENCE,        INFERRED
             changed (evidence_count differs)
          8. corroboration changed, evidence count  → UNKNOWN_CAUSE,       INFERRED
             the same
          9. Otherwise                              → UNKNOWN_CAUSE,       UNKNOWN
        """
        # Rule 1: evidence count increased
        if curr_snapshot.evidence_count > prev_snapshot.evidence_count:
            return DirectCause.NEW_EVIDENCE, CausalityLevel.DIRECT

        # Rule 2: freshness degraded without new evidence
        if change_type == ChangeType.FRESHNESS_CHANGED:
            prev_rank = _FRESHNESS_ORDER.get(prev_snapshot.freshness_status, 0)
            curr_rank = _FRESHNESS_ORDER.get(curr_snapshot.freshness_status, 0)
            if (
                curr_rank < prev_rank
                and curr_snapshot.evidence_count == prev_snapshot.evidence_count
            ):
                return DirectCause.TIME_PASSAGE, CausalityLevel.DIRECT

        # Rule 3: new open conflict
        if curr_snapshot.open_conflict_count > prev_snapshot.open_conflict_count:
            return DirectCause.CONFLICT, CausalityLevel.DIRECT

        # Rule 4: conflict resolved
        if curr_snapshot.open_conflict_count < prev_snapshot.open_conflict_count:
            return DirectCause.CONFLICT_RESOLUTION, CausalityLevel.DIRECT

        # Rule 5: methodology changed
        if curr_snapshot.methodology_version != prev_snapshot.methodology_version:
            return DirectCause.METHODOLOGY_CHANGE, CausalityLevel.DIRECT

        # Rule 6: source count changed
        if curr_snapshot.source_count != prev_snapshot.source_count:
            return DirectCause.SOURCE_CHANGE, CausalityLevel.INFERRED

        # Rule 7 & 8: corroboration changed
        if change_type in (
            ChangeType.CORROBORATION_INCREASED,
            ChangeType.CORROBORATION_DECREASED,
        ):
            if curr_snapshot.evidence_count != prev_snapshot.evidence_count:
                return DirectCause.NEW_EVIDENCE, CausalityLevel.INFERRED
            return DirectCause.UNKNOWN_CAUSE, CausalityLevel.INFERRED

        # Default
        return DirectCause.UNKNOWN_CAUSE, CausalityLevel.UNKNOWN

    # ------------------------------------------------------------------
    # Private: explanation
    # ------------------------------------------------------------------

    @classmethod
    def _generate_explanation(
        cls,
        change_type: str,
        dimension: str,
        prev_value: str,
        curr_value: str,
        direct_cause: str,
    ) -> str:
        """
        Return a deterministic, human-readable explanation for a change.

        Based only on ``change_type``, ``dimension``, ``prev_value``,
        ``curr_value``, and ``direct_cause``.  No LLM, no invented specifics.
        """
        if change_type == ChangeType.METHODOLOGY_CHANGED:
            return (
                f"The result changed because the evaluation methodology "
                f"changed from {prev_value} to {curr_value}."
            )

        if change_type == ChangeType.FRESHNESS_CHANGED:
            if direct_cause == DirectCause.TIME_PASSAGE:
                return (
                    f"Freshness status degraded from {prev_value} to {curr_value} "
                    f"due to evidence aging over time."
                )
            return f"Freshness status changed from {prev_value} to {curr_value}."

        if change_type == ChangeType.NEW_EVIDENCE:
            return (
                f"Evidence count increased from {prev_value} to {curr_value}, "
                f"indicating new observations were incorporated."
            )

        if change_type == ChangeType.EVIDENCE_REMOVED:
            return (
                f"Evidence count decreased from {prev_value} to {curr_value}."
            )

        if change_type == ChangeType.INTEGRITY_CHANGED:
            return (
                f"Overall integrity status changed from {prev_value} to {curr_value}."
            )

        if change_type == ChangeType.CONFLICT_CREATED:
            return (
                f"A new conflict was detected, changing consistency "
                f"from {prev_value} to {curr_value}."
            )

        if change_type == ChangeType.CONFLICT_RESOLVED:
            return (
                f"A conflict was resolved, improving consistency "
                f"from {prev_value} to {curr_value}."
            )

        if change_type == ChangeType.CORROBORATION_INCREASED:
            return f"Corroboration improved from {prev_value} to {curr_value}."

        if change_type == ChangeType.CORROBORATION_DECREASED:
            return f"Corroboration degraded from {prev_value} to {curr_value}."

        # Default fallback
        return f"{dimension} changed from {prev_value} to {curr_value}."

    # ------------------------------------------------------------------
    # Private: magnitude
    # ------------------------------------------------------------------

    @classmethod
    def _compute_magnitude(
        cls,
        change_type: str,
        prev_value: str,
        curr_value: str,
    ) -> str | None:
        """
        Return ``MINOR``, ``MODERATE``, or ``MAJOR`` for quantifiable changes.

        Returns ``None`` when magnitude cannot be determined.

        Rules:
          FRESHNESS_CHANGED:
            CURRENT → AGING   = MINOR
            AGING   → STALE   = MODERATE
            CURRENT → STALE   = MAJOR
            any other pair    = None

          INTEGRITY_CHANGED:
            tier diff = 1     = MINOR
            tier diff = 2     = MODERATE
            tier diff >= 3    = MAJOR

          NEW_EVIDENCE / EVIDENCE_REMOVED:
            count diff = 1    = MINOR
            count diff 2-4    = MODERATE
            count diff >= 5   = MAJOR

          Otherwise → None
        """
        if change_type == ChangeType.FRESHNESS_CHANGED:
            pair = (prev_value, curr_value)
            if pair == ("CURRENT", "AGING"):
                return ChangeMagnitude.MINOR
            if pair == ("AGING", "STALE"):
                return ChangeMagnitude.MODERATE
            if pair == ("CURRENT", "STALE"):
                return ChangeMagnitude.MAJOR
            return None

        if change_type == ChangeType.INTEGRITY_CHANGED:
            prev_tier = _INTEGRITY_ORDER.get(prev_value)
            curr_tier = _INTEGRITY_ORDER.get(curr_value)
            if prev_tier is None or curr_tier is None:
                return None
            diff = abs(curr_tier - prev_tier)
            if diff == 1:
                return ChangeMagnitude.MINOR
            if diff == 2:
                return ChangeMagnitude.MODERATE
            if diff >= 3:
                return ChangeMagnitude.MAJOR
            return None

        if change_type in (ChangeType.NEW_EVIDENCE, ChangeType.EVIDENCE_REMOVED):
            try:
                diff = abs(int(curr_value) - int(prev_value))
            except (ValueError, TypeError):
                return None
            if diff == 1:
                return ChangeMagnitude.MINOR
            if 2 <= diff <= 4:
                return ChangeMagnitude.MODERATE
            if diff >= 5:
                return ChangeMagnitude.MAJOR
            return None

        return None
