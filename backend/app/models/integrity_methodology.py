"""
Phase 9 — Evidence Integrity Methodology Registry.

This module is the single authoritative source for how EIS-1.0
combines evidence quality dimensions into an overall integrity status.

Design principles:
  - No arbitrary numeric weights in EIS-1.0.
  - All aggregation rules are named gates with documented conditions.
  - Rules are evaluated in priority order (top wins).
  - Methodology is versioned — rule changes require a version increment.
  - This is a pure Python dataclass, NOT a SQLAlchemy model.
    The version string is embedded in every EvidenceIntegritySnapshot.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.models.integrity_types import (
    ConsistencyStatus,
    CorroborationStatus,
    IndependenceStatus,
    IntegrityStatus,
)


@dataclass(frozen=True)
class AggregationGate:
    """
    A single named rule in the integrity aggregation pipeline.

    Gates are evaluated in priority order. The first gate whose
    conditions are satisfied determines the overall_status.
    """

    name: str
    """Human-readable name for this gate (used in logging and docs)."""

    result_status: str
    """The IntegrityStatus value assigned when this gate fires."""

    description: str
    """Human-readable explanation of what conditions trigger this gate."""


@dataclass(frozen=True)
class EISMethodologyV1:
    """
    Evidence Integrity Scoring — Version 1.0 (EIS-1.0).

    Aggregation strategy: RULE_BASED
    ----------------------------------
    Gates are evaluated in declared order. The first matching gate
    determines the overall status.

    Gate 1 — INSUFFICIENT_DATA
        Condition: evidence_count == 0
        Reason: There is no evidence to assess.

    Gate 2 — UNRESOLVED
        Condition: open_conflict_count > 0
                   (at least one conflict with severity > INFO and status OPEN)
        Reason: The evidence set contains a detected semantic contradiction
                that has not been resolved. Internal consistency is in question.

    Gate 3 — WEAK
        Condition: ANY of:
          - freshness_status == STALE or UNKNOWN
          - source_authority == TERTIARY
        Reason: The foundational quality of evidence is poor regardless of
                other dimensions.

    Gate 4 — VERY_STRONG
        Condition: ALL of:
          - freshness STRONG (CURRENT or AGING)
          - source STRONG (PRIMARY + DIRECT)
          - independence == HIGH_SOURCE_DIVERSITY
          - corroboration == STRONGLY_CORROBORATED
          - consistency == NO_DETECTED_CONFLICT
        Reason: All dimensions are maximally strong.

    Gate 5 — STRONG
        Condition: ALL of:
          - freshness not STALE
          - source authority PRIMARY or SECONDARY
          - consistency is NO_DETECTED_CONFLICT or ORDERING_AMBIGUITY_ONLY
          - evidence_count >= 1
        Reason: Core quality indicators are strong; minor limitations acceptable.

    Gate 6 — LIMITED
        Condition: Falls through all above gates without matching.
        Reason: At least one dimension is limited but no open conflict exists.

    Fallthrough — LIMITED (default)
        Any state not matched by an earlier gate produces LIMITED.
    """

    version: str = "EIS-1.0"
    aggregation: str = "RULE_BASED"

    # Minimum observations to reach VERY_STRONG
    very_strong_min_observations: int = 2

    # Independence threshold for VERY_STRONG
    very_strong_independence: str = IndependenceStatus.HIGH_SOURCE_DIVERSITY

    # Corroboration threshold for VERY_STRONG
    very_strong_corroboration: str = CorroborationStatus.STRONGLY_CORROBORATED

    # Consistency required for STRONG+
    strong_consistency_allowed: tuple[str, ...] = field(
        default_factory=lambda: (
            ConsistencyStatus.NO_DETECTED_CONFLICT,
            ConsistencyStatus.ORDERING_AMBIGUITY_ONLY,
        )
    )

    gates: tuple[AggregationGate, ...] = field(
        default_factory=lambda: (
            AggregationGate(
                name="INSUFFICIENT_DATA",
                result_status=IntegrityStatus.INSUFFICIENT_DATA,
                description="No evidence observed for this payment.",
            ),
            AggregationGate(
                name="UNRESOLVED",
                result_status=IntegrityStatus.UNRESOLVED,
                description=(
                    "At least one open semantic conflict (severity > INFO) "
                    "exists that has not been resolved."
                ),
            ),
            AggregationGate(
                name="WEAK",
                result_status=IntegrityStatus.WEAK,
                description=(
                    "Evidence is stale or from a non-primary authority level."
                ),
            ),
            AggregationGate(
                name="VERY_STRONG",
                result_status=IntegrityStatus.VERY_STRONG,
                description=(
                    "All dimensions are maximally strong: current evidence, "
                    "primary source, high diversity, strong corroboration, "
                    "no detected conflict."
                ),
            ),
            AggregationGate(
                name="STRONG",
                result_status=IntegrityStatus.STRONG,
                description=(
                    "Evidence is current, from an authoritative source, "
                    "with no open semantic conflicts."
                ),
            ),
            AggregationGate(
                name="LIMITED",
                result_status=IntegrityStatus.LIMITED,
                description=(
                    "One or more dimensions are limited. "
                    "No open semantic conflicts detected."
                ),
            ),
        )
    )

    def describe(self) -> dict:
        """Return a structured description of the methodology for documentation."""
        return {
            "version": self.version,
            "aggregation": self.aggregation,
            "gates": [
                {
                    "name": g.name,
                    "result_status": g.result_status,
                    "description": g.description,
                }
                for g in self.gates
            ],
        }


# Singleton instance used by the integrity engine
EIS_V1 = EISMethodologyV1()
