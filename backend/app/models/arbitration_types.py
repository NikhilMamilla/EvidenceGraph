"""
Phase 17 — Evidence Conflict Arbitration & Resolution Engine Domain Types.

Defines deterministic categorical states for arbitration verdicts, precedence
factors, and methodology version constants. No numerical scores.
"""

from enum import Enum

ARBITRATION_METHODOLOGY_V1 = "ECA-1.0"


class ArbitrationOutcome(str, Enum):
    """
    Deterministic verdict produced by the arbitration engine for a conflict pair.

    CLAIM_A_PREVAILS  — Claim A is the authoritative assertion; Claim B is superseded.
    CLAIM_B_PREVAILS  — Claim B is the authoritative assertion; Claim A is superseded.
    IRRECONCILABLE    — Both claims satisfy equally strong precedence criteria;
                        neither can be deterministically preferred.
    INSUFFICIENT_DATA — Arbitration cannot proceed because one or both claims
                        lack the minimum evidence required for comparison.
    NOT_APPLICABLE    — Conflict type does not support arbitration
                        (e.g., ORDERING_AMBIGUITY is not a semantic contradiction).
    """
    CLAIM_A_PREVAILS = "CLAIM_A_PREVAILS"
    CLAIM_B_PREVAILS = "CLAIM_B_PREVAILS"
    IRRECONCILABLE = "IRRECONCILABLE"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class PrecedenceFactor(str, Enum):
    """
    Which precedence dimension caused the arbitration outcome.

    Evaluated in strict priority order:
      1. SOURCE_AUTHORITY      — Provider-signed > authenticated internal > unverified.
      2. TEMPORAL_PRIMACY      — Earlier first_observed_at wins (oldest = original signal).
      3. CORROBORATION_COUNT   — More distinct source types = stronger.
      4. RELIABILITY_CEILING   — Higher ReliabilityState (Phase 16) wins.
      5. RECENCY               — Later last_observed_at wins (still being confirmed).
      6. STRUCTURAL_INTEGRITY  — CANONICAL_FACT > PARTIAL > MALFORMED.
    """
    SOURCE_AUTHORITY = "SOURCE_AUTHORITY"
    TEMPORAL_PRIMACY = "TEMPORAL_PRIMACY"
    CORROBORATION_COUNT = "CORROBORATION_COUNT"
    RELIABILITY_CEILING = "RELIABILITY_CEILING"
    RECENCY = "RECENCY"
    STRUCTURAL_INTEGRITY = "STRUCTURAL_INTEGRITY"
    NONE_APPLICABLE = "NONE_APPLICABLE"


class SourceAuthorityRank(int, Enum):
    """
    Ordinal authority rank for source types. Higher = more authoritative.
    Used in SOURCE_AUTHORITY dimension. Integer comparison is valid.
    """
    UNKNOWN = 0
    UNVERIFIED = 1
    VERIFIED_INTERNAL = 2
    VERIFIED_PROVIDER = 3


class ReliabilityRank(int, Enum):
    """
    Ordinal rank for ReliabilityState values. Higher = more reliable.
    Used in RELIABILITY_CEILING dimension. Integer comparison is valid.
    """
    UNKNOWN = 0
    UNRELIABLE = 1
    LIMITED = 2
    MODERATE = 3
    HIGH = 4


class StructuralRank(int, Enum):
    """
    Ordinal rank for StructuralReliability values. Higher = better structure.
    Used in STRUCTURAL_INTEGRITY dimension. Integer comparison is valid.
    """
    UNKNOWN = 0
    MALFORMED = 1
    PARTIAL_OBSERVATION = 2
    CANONICAL_FACT = 3


class ArbitrationConflictCategory(str, Enum):
    """
    Grouping of conflict types by whether they are arbitrable.
    """
    ARBITRABLE = "ARBITRABLE"         # STATE_CONFLICT, VALUE_CONFLICT, RELATIONSHIP_CONFLICT
    TEMPORAL_ONLY = "TEMPORAL_ONLY"   # TEMPORAL_CONFLICT — may be resolved by primacy only
    NON_ARBITRABLE = "NON_ARBITRABLE"  # ORDERING_AMBIGUITY — clock skew, not a true conflict
