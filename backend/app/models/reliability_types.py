"""
Phase 16 — Evidence Reliability Calibration & Uncertainty Boundaries Domain Types.

Defines deterministic categorical states, dimensions, uncertainty boundaries,
and methodology version constants for evidence reliability evaluation.
"""

from enum import Enum

RELIABILITY_METHODOLOGY_V1 = "ERM-1.0"


class ReliabilityState(str, Enum):
    """Categorical reliability state assigned to an evidence fact or payment."""
    HIGH = "HIGH"
    MODERATE = "MODERATE"
    LIMITED = "LIMITED"
    UNRELIABLE = "UNRELIABLE"
    UNKNOWN = "UNKNOWN"


class SourceReliability(str, Enum):
    """Source authenticity and verification status."""
    VERIFIED_PROVIDER_SOURCE = "VERIFIED_PROVIDER_SOURCE"
    VERIFIED_INTERNAL_SOURCE = "VERIFIED_INTERNAL_SOURCE"
    UNVERIFIED_SOURCE = "UNVERIFIED_SOURCE"
    UNKNOWN_SOURCE = "UNKNOWN_SOURCE"


class ProvenanceReliability(str, Enum):
    """End-to-end lineage and provenance chain completeness."""
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    BROKEN = "BROKEN"
    UNKNOWN = "UNKNOWN"


class IdentityReliability(str, Enum):
    """Fact identity certainty from reconciliation."""
    SAME_PROVIDER_EVENT = "SAME_PROVIDER_EVENT"
    SAME_FACT_DIFFERENT_SOURCE = "SAME_FACT_DIFFERENT_SOURCE"
    TEMPORAL_AMBIGUITY = "TEMPORAL_AMBIGUITY"
    INSUFFICIENT_INFORMATION = "INSUFFICIENT_INFORMATION"
    UNKNOWN = "UNKNOWN"


class TemporalReliability(str, Enum):
    """Temporal ordering, freshness, and clock consistency."""
    TEMPORALLY_SOUND = "TEMPORALLY_SOUND"
    TEMPORALLY_AMBIGUOUS = "TEMPORALLY_AMBIGUOUS"
    TEMPORALLY_INVALID = "TEMPORALLY_INVALID"
    UNKNOWN = "UNKNOWN"


class StructuralReliability(str, Enum):
    """Canonical schema compliance and payload validity."""
    CANONICAL_FACT = "CANONICAL_FACT"
    PARTIAL_OBSERVATION = "PARTIAL_OBSERVATION"
    MALFORMED = "MALFORMED"
    UNKNOWN = "UNKNOWN"


class ContradictionReliability(str, Enum):
    """Contradiction status from Phase 8 consistency evaluation."""
    UNCONTRADICTED = "UNCONTRADICTED"
    CONFLICTED = "CONFLICTED"
    RESOLVED_CONFLICT = "RESOLVED_CONFLICT"
    UNKNOWN = "UNKNOWN"


class DependencyReliability(str, Enum):
    """Evidence origin independence vs replication."""
    INDEPENDENT_CORROBORATION = "INDEPENDENT_CORROBORATION"
    DEPENDENT_REPLICATION = "DEPENDENT_REPLICATION"
    SINGLE_SOURCE = "SINGLE_SOURCE"
    UNKNOWN = "UNKNOWN"


class UncertaintyBoundaryType(str, Enum):
    """Structured uncertainty boundary classification."""
    ESTABLISHED = "ESTABLISHED"
    SUPPORTED = "SUPPORTED"
    UNCERTAIN = "UNCERTAIN"
    CONTRADICTED = "CONTRADICTED"
    NOT_OBSERVED = "NOT_OBSERVED"
    NOT_DETERMINABLE = "NOT_DETERMINABLE"
