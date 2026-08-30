"""
Phase 15 — Evidence Completeness, Coverage & Missing-Evidence Analysis: Types & Constants.
"""

from __future__ import annotations

# Methodology & Profile Constants
COVERAGE_METHODOLOGY_VERSION = "ECS-1.0"
STANDARD_PAYMENT_PROFILE_ID = "STANDARD_PAYMENT_PROFILE_V1"
PROFILE_VERSION_1 = "1.0"
PROFILE_UNKNOWN = "PROFILE_UNKNOWN"


class RequirementType:
    """Classifies how critical a requirement is for a profile."""
    REQUIRED = "REQUIRED"
    EXPECTED = "EXPECTED"
    OPTIONAL = "OPTIONAL"
    CONDITIONAL = "CONDITIONAL"
    NOT_APPLICABLE = "NOT_APPLICABLE"

    ALL = {REQUIRED, EXPECTED, OPTIONAL, CONDITIONAL, NOT_APPLICABLE}


class CoverageState:
    """The observed status of a specific requirement."""
    PRESENT = "PRESENT"
    MISSING = "MISSING"
    PARTIAL = "PARTIAL"
    CONFLICTED = "CONFLICTED"
    UNKNOWN = "UNKNOWN"
    NOT_APPLICABLE = "NOT_APPLICABLE"

    ALL = {PRESENT, MISSING, PARTIAL, CONFLICTED, UNKNOWN, NOT_APPLICABLE}


class CoverageStatus:
    """Overall coverage status for a payment snapshot."""
    COMPLETE = "COMPLETE"
    SUBSTANTIALLY_COMPLETE = "SUBSTANTIALLY_COMPLETE"
    PARTIAL = "PARTIAL"
    INSUFFICIENT = "INSUFFICIENT"
    UNKNOWN = "UNKNOWN"

    ALL = {COMPLETE, SUBSTANTIALLY_COMPLETE, PARTIAL, INSUFFICIENT, UNKNOWN}


class ProfileStatus:
    ACTIVE = "ACTIVE"
    DEPRECATED = "DEPRECATED"
    EXPERIMENTAL = "EXPERIMENTAL"


class CoverageChangeCause:
    """Causal categories for temporal coverage evolution (Phase 11 integration)."""
    NEW_EVIDENCE = "NEW_EVIDENCE"
    EVIDENCE_INVALIDATION = "EVIDENCE_INVALIDATION"
    TIME_PASSAGE = "TIME_PASSAGE"
    APPLICABILITY_CHANGE = "APPLICABILITY_CHANGE"
    METHODOLOGY_CHANGE = "METHODOLOGY_CHANGE"
    UNKNOWN = "UNKNOWN"
