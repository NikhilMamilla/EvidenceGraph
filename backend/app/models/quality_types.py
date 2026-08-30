"""
Evidence quality taxonomy constants — Phase 6.

Plain Python string constants, NOT database enum types.
Using plain strings avoids Alembic migrations when new values are added.

All values persisted to the database must come from these classes.
"""

from __future__ import annotations


class FreshnessState:
    """
    The temporal freshness classification of an evidence observation.

    Determined by comparing the observation's `observed_at` timestamp
    against a configured policy for that evidence type at a specific
    evaluation time. These are labels, not scores.
    """

    CURRENT = "CURRENT"
    """Within the configured 'current' window — the evidence is recent."""

    AGING = "AGING"
    """Past the 'current' threshold but not yet stale — approaching stale."""

    STALE = "STALE"
    """Past the configured 'stale' threshold — evidence may be outdated."""

    UNKNOWN = "UNKNOWN"
    """Cannot determine freshness: observed_at is null, or a future timestamp
    was provided that is after the evaluation_time (handled safely)."""


class HistoricalReliabilityStatus:
    """
    The readiness of historical reliability data for a given evidence type.

    This is NOT a numerical reliability score. In Phase 6 we do not have
    sufficient outcome data to assign meaningful numerical reliabilities.
    These values represent our honest current state.
    """

    NO_OUTCOME_DATA = "NO_OUTCOME_DATA"
    """No outcomes have been recorded that could be correlated with this
    evidence type. Cannot begin reliability assessment."""

    INSUFFICIENT_SAMPLE = "INSUFFICIENT_SAMPLE"
    """Outcomes exist but not enough to produce a statistically meaningful
    reliability estimate for this evidence type."""

    AVAILABLE = "AVAILABLE"
    """Sufficient historical outcome data exists to compute reliability.
    Reserved for future phases when outcome recording is implemented."""


class SourceDirectness:
    """
    How directly the source of this evidence represents the underlying fact.

    Distinct from historical reliability. Directness is a structural property
    of the evidence provenance chain, not a track record.
    """

    DIRECT = "DIRECT"
    """The evidence value was observed directly from an authoritative provider
    source (e.g. Razorpay webhook payload field)."""

    DERIVED = "DERIVED"
    """The evidence value was derived from a direct observation (e.g.
    a payment amount computed from a canonical payment record that was
    itself derived from a webhook)."""

    INFERRED = "INFERRED"
    """The evidence value was inferred by EvidenceGraph through logic
    (e.g. a payment is implicitly captured if both payment.captured=true
    and payment.status=captured)."""


class AuthorityLevel:
    """
    How authoritative the source of evidence is for the claimed fact.

    Authority is structural — it represents the position of the source
    in the evidence chain. It does NOT imply zero error rate.
    """

    PRIMARY = "PRIMARY"
    """The source is the authoritative originator of this fact
    (e.g. Razorpay is primary authority for Razorpay payment status)."""

    SECONDARY = "SECONDARY"
    """The source is a trusted relay (e.g. our own verified database
    derived from a primary provider)."""

    TERTIARY = "TERTIARY"
    """The source is two or more hops from the primary authority."""


# -------------------------------------------------------------------------
# Methodology versioning
# -------------------------------------------------------------------------

FRESHNESS_METHODOLOGY_VERSION = "1.0"
"""Version of the freshness calculation logic.
Increment when thresholds or logic change so that historical snapshots
remain fully explainable by their version alone."""

SOURCE_QUALITY_METHODOLOGY_VERSION = "1.0"
"""Version of the source quality classification logic."""

RELIABILITY_METHODOLOGY_VERSION = "1.0"
"""Version of the historical reliability assessment logic."""
