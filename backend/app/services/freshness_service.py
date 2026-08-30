"""
Evidence Freshness Service — Phase 6.

Computes how fresh an evidence observation is at a given evaluation time.

Design principles:
  - Accepts an explicit evaluation_time parameter — NEVER calls datetime.now() internally.
    This makes the service deterministic and trivially testable.
  - Returns raw age (in seconds) and a classified FreshnessState.
  - Thresholds are controlled by a versioned FreshnessPolicy — not hardcoded constants
    scattered through the application.
  - Future timestamps (observed_at > evaluation_time) produce FreshnessState.UNKNOWN,
    not a negative age — handled safely and explicitly.
  - No exponential decay curves. Phase 6 implements the simplest defensible model:
    configurable step thresholds per evidence type with LINEAR age.
  - The decay model constant (NO_DECAY / LINEAR / STEP) is stored on the policy
    for future extension.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import NamedTuple

from app.models.evidence_types import EvidenceType
from app.models.quality_types import (
    FRESHNESS_METHODOLOGY_VERSION,
    FreshnessState,
)


# ---------------------------------------------------------------------------
# Freshness Policy
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class FreshnessPolicy:
    """
    Configures the freshness thresholds for one evidence type.

    Thresholds are in seconds.
    current_threshold_s: age < this → CURRENT
    stale_threshold_s:   age ≥ this → STALE
    Between the two → AGING

    decay_model: one of NO_DECAY, LINEAR, STEP
    In Phase 6 only STEP is implemented.
    """

    policy_key: str
    current_threshold_s: float   # seconds
    stale_threshold_s: float     # seconds
    decay_model: str = "STEP"
    description: str = ""

    def __post_init__(self) -> None:
        if self.current_threshold_s > self.stale_threshold_s:
            raise ValueError(
                f"current_threshold_s ({self.current_threshold_s}) must be ≤ "
                f"stale_threshold_s ({self.stale_threshold_s})"
            )


# ---------------------------------------------------------------------------
# Policy registry
# ---------------------------------------------------------------------------
# All thresholds are configurable. They are NOT arbitrary — they represent
# the team's current best estimate of when evidence of each type may lose
# relevance. If we do not yet have empirical data to support a specific
# decay curve, we use a conservative STEP policy with explicit documentation.

_SECONDS_IN_HOUR = 3600.0
_SECONDS_IN_DAY = 86400.0

# The DEFAULT policy applies to any evidence type without a specific override.
# Reasoning: Razorpay payment events are near-real-time. Evidence produced
# from a webhook is immediately relevant (CURRENT). After 24h without a
# follow-up event, it is aging. After 7 days it is STALE.
_DEFAULT_POLICY = FreshnessPolicy(
    policy_key="DEFAULT",
    current_threshold_s=24 * _SECONDS_IN_HOUR,       # < 24h → CURRENT
    stale_threshold_s=7 * _SECONDS_IN_DAY,            # ≥ 7d  → STALE
    description=(
        "Default policy for Razorpay webhook evidence. "
        "Evidence is CURRENT within 24h, AGING from 24h–7d, STALE after 7d."
    ),
)

# PAYMENT_STATUS can change quickly (e.g. authorized → captured in seconds).
# Its freshness window is narrower.
_PAYMENT_STATUS_POLICY = FreshnessPolicy(
    policy_key="PAYMENT_STATUS",
    current_threshold_s=4 * _SECONDS_IN_HOUR,         # < 4h  → CURRENT
    stale_threshold_s=48 * _SECONDS_IN_HOUR,           # ≥ 48h → STALE
    description=(
        "Payment status evidence ages faster because status transitions "
        "can occur frequently. CURRENT within 4h, AGING 4h–48h, STALE after 48h."
    ),
)

# PAYMENT_AMOUNT and PAYMENT_CURRENCY are immutable for a given payment.
# They don't 'age' in the same sense — but a very old observation may
# still be STALE in the absence of any recent confirmation.
_PAYMENT_AMOUNT_POLICY = FreshnessPolicy(
    policy_key="PAYMENT_AMOUNT",
    current_threshold_s=7 * _SECONDS_IN_DAY,           # < 7d  → CURRENT
    stale_threshold_s=30 * _SECONDS_IN_DAY,            # ≥ 30d → STALE
    description=(
        "Payment amount is immutable after settlement. Freshness window is wider. "
        "CURRENT within 7d, AGING 7d–30d, STALE after 30d."
    ),
)

# PAYMENT_EVENT observations represent that the event happened — immutable facts.
_PAYMENT_EVENT_POLICY = FreshnessPolicy(
    policy_key="PAYMENT_EVENT",
    current_threshold_s=24 * _SECONDS_IN_HOUR,
    stale_threshold_s=7 * _SECONDS_IN_DAY,
    description="Payment event occurrence evidence. Same as default policy.",
)

# Registry: evidence_type → FreshnessPolicy
FRESHNESS_POLICY_REGISTRY: dict[str, FreshnessPolicy] = {
    EvidenceType.PAYMENT_STATUS: _PAYMENT_STATUS_POLICY,
    EvidenceType.PAYMENT_AMOUNT: _PAYMENT_AMOUNT_POLICY,
    EvidenceType.PAYMENT_CURRENCY: _PAYMENT_AMOUNT_POLICY,   # same as amount
    EvidenceType.PAYMENT_EVENT: _PAYMENT_EVENT_POLICY,
    # All others fall through to DEFAULT
}


def get_policy_for_evidence_type(evidence_type: str) -> FreshnessPolicy:
    """Return the FreshnessPolicy for the given evidence type, or DEFAULT."""
    return FRESHNESS_POLICY_REGISTRY.get(evidence_type, _DEFAULT_POLICY)


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------

class FreshnessResult(NamedTuple):
    """
    The output of a freshness measurement.

    All fields are explicit — no hidden state.
    """

    evidence_id: int
    evidence_type: str
    observed_at: datetime | None
    evaluation_time: datetime
    age_seconds: float | None
    """Raw age in seconds. None when FreshnessState is UNKNOWN."""
    freshness_state: FreshnessState
    policy_key: str
    methodology_version: str


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class EvidenceFreshnessService:
    """
    Computes freshness for an EvidenceObservation at an explicit evaluation_time.

    Usage:
        service = EvidenceFreshnessService()
        result = service.measure(observation, evaluation_time=datetime.now(tz=timezone.utc))
    """

    def measure_by_fields(
        self,
        evidence_id: int,
        evidence_type: str,
        observed_at: datetime | None,
        evaluation_time: datetime,
    ) -> FreshnessResult:
        """
        Compute freshness given raw field values.

        Accepts explicit evaluation_time — callers must pass this in.
        Never calls datetime.now() internally.

        Handles:
          - None observed_at → UNKNOWN
          - observed_at after evaluation_time (future timestamp) → UNKNOWN
          - Normal age computation → CURRENT / AGING / STALE
        """
        # Ensure evaluation_time is timezone-aware
        if evaluation_time.tzinfo is None:
            raise ValueError("evaluation_time must be timezone-aware (UTC)")

        policy = get_policy_for_evidence_type(evidence_type)

        # Case 1: No observation timestamp
        if observed_at is None:
            return FreshnessResult(
                evidence_id=evidence_id,
                evidence_type=evidence_type,
                observed_at=None,
                evaluation_time=evaluation_time,
                age_seconds=None,
                freshness_state=FreshnessState.UNKNOWN,
                policy_key=policy.policy_key,
                methodology_version=FRESHNESS_METHODOLOGY_VERSION,
            )

        # Normalize to UTC
        obs_utc = observed_at.astimezone(timezone.utc)
        eval_utc = evaluation_time.astimezone(timezone.utc)

        # Case 2: observed_at is in the future relative to evaluation_time
        if obs_utc > eval_utc:
            return FreshnessResult(
                evidence_id=evidence_id,
                evidence_type=evidence_type,
                observed_at=observed_at,
                evaluation_time=evaluation_time,
                age_seconds=None,
                freshness_state=FreshnessState.UNKNOWN,
                policy_key=policy.policy_key,
                methodology_version=FRESHNESS_METHODOLOGY_VERSION,
            )

        # Case 3: Normal age computation
        age_s = (eval_utc - obs_utc).total_seconds()

        if age_s < policy.current_threshold_s:
            state = FreshnessState.CURRENT
        elif age_s < policy.stale_threshold_s:
            state = FreshnessState.AGING
        else:
            state = FreshnessState.STALE

        return FreshnessResult(
            evidence_id=evidence_id,
            evidence_type=evidence_type,
            observed_at=observed_at,
            evaluation_time=evaluation_time,
            age_seconds=age_s,
            freshness_state=state,
            policy_key=policy.policy_key,
            methodology_version=FRESHNESS_METHODOLOGY_VERSION,
        )

    def measure(self, observation: object, evaluation_time: datetime) -> FreshnessResult:
        """
        Compute freshness for an EvidenceObservation ORM object.
        """
        return self.measure_by_fields(
            evidence_id=observation.internal_id,
            evidence_type=observation.evidence_type,
            observed_at=observation.observed_at,
            evaluation_time=evaluation_time,
        )


# Module-level singleton — stateless, safe to share
freshness_service = EvidenceFreshnessService()
