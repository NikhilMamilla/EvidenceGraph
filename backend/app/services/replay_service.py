"""
Phase 10 — Decision-trace replay engine.

Re-executes the authoritative Phase 9 computation for an ORIGINAL evaluation's
exact context — (payment_id, evaluation_time, methodology_version) and the
evidence scope implied by them — using the SAME engine implementation that
produced the original result, then compares the replayed computation against
the original trace's canonical content.

Hard contracts:
  - The ORIGINAL trace is NEVER modified. Replay reads it; nothing writes to
    it. If a durable record of the replay is desired, a separate REPLAY-type
    trace is created (own trace_id, own hash, never joins the payment chain).
  - Comparison identifies the FIRST meaningful difference by category, not a
    bare MISMATCH: methodology, evidence set, measurements, relationships,
    conflicts, rule outputs, or final result.
  - A MISMATCH is not an error: it means the world changed since the original
    evaluation (e.g. new evidence arrived), or the stored history was altered.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.integrity_trace import EvidenceIntegrityTrace
from app.models.trace_types import ActorType, TraceStatus, TraceType
from app.services.integrity_engine import IntegrityEngine
from app.services.integrity_trace_service import IntegrityTraceService
from app.services.trace_canonicalization import canonicalize

logger = logging.getLogger(__name__)


class ReplayNotPossibleError(ValueError):
    """Raised when a trace cannot be replayed (missing, failed, or wrong type)."""


class ReplayService:
    """Replays evaluations recorded in decision traces and diffs the results."""

    # Priority order for locating the FIRST meaningful difference.
    _COMPARISON_PLAN: tuple[tuple[tuple[str, ...], str], ...] = (
        (("methodology",), "METHODOLOGY_CHANGED"),
        (("evidence_inputs", "excluded_evidence"), "EVIDENCE_SET_CHANGED"),
        (("quality_measurements",), "MEASUREMENT_CHANGED"),
        (("structural_measurements", "corroboration"), "RELATIONSHIP_CHANGED"),
        (("consistency",), "CONFLICT_CHANGED"),
        (("rule_executions",), "RULE_OUTPUT_CHANGED"),
        (("intermediate_results",), "RULE_OUTPUT_CHANGED"),
        (
            (
                "evaluation_context",
                "counts",
                "final_result",
                "explanation_lines",
                "limitations",
            ),
            "FINAL_RESULT_CHANGED",
        ),
    )

    @classmethod
    def replay_trace(
        cls,
        db: Session,
        trace_id: str,
        actor_type: str = ActorType.USER,
    ) -> dict:
        """
        Replay one COMPLETED EVALUATION trace.

        Returns a dict with:
            original_trace_id, replay_trace_id,
            original_result, replay_result,
            comparison_result (MATCH | MISMATCH),
            first_difference (category + paths) | None,
            differences (per-category summary)

        Raises ReplayNotPossibleError when the trace cannot be replayed.
        """
        original = IntegrityTraceService.get_by_trace_id(db, trace_id)
        if original is None:
            raise ReplayNotPossibleError(f"Trace '{trace_id}' does not exist.")
        if original.trace_type != TraceType.EVALUATION:
            raise ReplayNotPossibleError(
                f"Trace '{trace_id}' is a {original.trace_type} trace; "
                "only EVALUATION traces can be replayed."
            )
        if original.status == TraceStatus.FAILED:
            raise ReplayNotPossibleError(
                f"Trace '{trace_id}' records a FAILED evaluation; "
                "there is no result to replay."
            )
        if original.status != TraceStatus.COMPLETED:
            raise ReplayNotPossibleError(
                f"Trace '{trace_id}' is not finalized (status="
                f"{original.status}); wait for completion before replaying."
            )

        original_content = (original.canonical_payload or {}).get("content") or {}

        # ------------------------------------------------------------------
        # Re-execute the authoritative computation in the ORIGINAL context.
        # Reads current database state; writes nothing except the new
        # REPLAY trace created below.
        # ------------------------------------------------------------------
        replay_trace = IntegrityTraceService._start_trace(
            db=db,
            payment_id=original.payment_id,
            evaluation_time=original.evaluated_at,
            methodology_version=original.methodology_version,
            trace_type=TraceType.REPLAY,
            original_trace_id=original.trace_id,
            trigger="REPLAY_REQUEST",
            actor_type=actor_type,
        )

        capture: dict = {}
        try:
            IntegrityEngine._execute_computation(
                db=db,
                payment_id=original.payment_id,
                evaluation_time=original.evaluated_at,
                methodology_version=original.methodology_version,
                capture=capture,
            )
        except Exception as exc:
            IntegrityTraceService._finalize_failed(
                db=db,
                trace=replay_trace,
                capture=capture,
                exc=exc,
                stage="REPLAY_EXECUTION",
                actor_type=actor_type,
            )
            raise ReplayNotPossibleError(
                f"Replay execution failed: {type(exc).__name__}"
            ) from exc

        replayed_content = IntegrityTraceService._build_content(capture)

        # ------------------------------------------------------------------
        # Compare (normalized) contents.
        # ------------------------------------------------------------------
        differences = cls._diff_contents(original_content, replayed_content)
        first_difference = cls._first_difference(differences)
        comparison_result = "MATCH" if not differences else "MISMATCH"

        replay_comparison = {
            "original_trace_id": original.trace_id,
            "comparison_result": comparison_result,
            "first_difference": first_difference,
            "differences": differences,
            "replayed_at": datetime.now(tz=timezone.utc),
        }

        IntegrityTraceService._finalize_completed(
            db=db,
            trace=replay_trace,
            capture=capture,
            snapshot=None,
            actor_type=actor_type,
            content_extra={"replay_comparison": replay_comparison},
        )

        logger.info(
            "Decision trace replay finished",
            extra={
                "trace_id": replay_trace.trace_id,
                "original_trace_id": original.trace_id,
                "payment_id": original.payment_id,
                "methodology_version": original.methodology_version,
                "evaluation_time": original.evaluated_at.isoformat(),
                "replay_status": comparison_result,
            },
        )

        return {
            "original_trace_id": original.trace_id,
            "original_payment_id": original.payment_id,
            "evaluated_at": original.evaluated_at,
            "methodology_version": original.methodology_version,
            "replay_trace_id": replay_trace.trace_id,
            "original_result": (original_content.get("final_result") or {}).get(
                "overall_status"
            ),
            "replay_result": replayed_content["final_result"]["overall_status"],
            "comparison_result": comparison_result,
            "first_difference": first_difference,
            "differences": differences,
        }

    # ------------------------------------------------------------------
    # Diff machinery
    # ------------------------------------------------------------------

    @classmethod
    def _diff_contents(
        cls, original: dict, replayed: dict
    ) -> list[dict]:
        """
        Compare every planned content section; return per-category differences
        with concrete JSON-style paths. Sections absent from both sides match.

        Both sides are canonicalized first so raw datetimes from a live
        capture compare equal to the stored canonical string forms.
        """
        original = canonicalize(original)
        replayed = canonicalize(replayed)

        differences: list[dict] = []
        seen_categories: set[str] = set()

        for keys, category in cls._COMPARISON_PLAN:
            for key in keys:
                left = cls._normalize_section(key, original.get(key))
                right = cls._normalize_section(key, replayed.get(key))
                if left == right:
                    continue
                paths = cls._diff_paths(left, right, prefix=key)
                if category in seen_categories:
                    for diff in differences:
                        if diff["category"] == category:
                            diff["sections"].append(key)
                            diff["paths"].extend(paths)
                    continue
                seen_categories.add(category)
                differences.append(
                    {
                        "category": category,
                        "sections": [key],
                        "paths": paths[:20],
                    }
                )
        return differences

    @staticmethod
    def _first_difference(differences: list[dict]) -> dict | None:
        return differences[0] if differences else None

    @staticmethod
    def _normalize_section(section: str, value):
        """
        Remove legitimately non-comparable fields before equality checks.

        - final_result.integrity_snapshot_internal_id: the original references
          its persisted snapshot; a replay persists nothing, so this field is
          identity metadata, not audit content.
        """
        if section == "final_result" and isinstance(value, dict):
            cleaned = dict(value)
            cleaned.pop("integrity_snapshot_internal_id", None)
            return cleaned
        return value

    @classmethod
    def _diff_paths(cls, left, right, prefix: str, limit: int = 20) -> list[str]:
        """Collect up to `limit` concrete differing paths between two values."""
        paths: list[str] = []

        def walk(l, r, path: str) -> None:
            if len(paths) >= limit:
                return
            if l == r:
                return
            if isinstance(l, dict) and isinstance(r, dict):
                for key in sorted(set(l.keys()) | set(r.keys())):
                    walk(l.get(key), r.get(key), f"{path}.{key}")
                    if len(paths) >= limit:
                        return
            elif isinstance(l, list) and isinstance(r, list):
                max_len = max(len(l), len(r))
                for i in range(max_len):
                    walk(
                        l[i] if i < len(l) else "<absent>",
                        r[i] if i < len(r) else "<absent>",
                        f"{path}[{i}]",
                    )
                    if len(paths) >= limit:
                        return
            else:
                paths.append(path)

        walk(left, right, prefix)
        if not paths and left != right:
            paths.append(prefix)
        return paths
