"""
Phase 8 — Contradiction & Temporal Consistency Enums.
"""
from enum import Enum


class ConflictType(str, Enum):
    """Classification of semantic or temporal inconsistency between observations/claims."""
    STATE_CONFLICT = "STATE_CONFLICT"
    VALUE_CONFLICT = "VALUE_CONFLICT"
    RELATIONSHIP_CONFLICT = "RELATIONSHIP_CONFLICT"
    TEMPORAL_CONFLICT = "TEMPORAL_CONFLICT"
    SOURCE_CONFLICT = "SOURCE_CONFLICT"
    ORDERING_AMBIGUITY = "ORDERING_AMBIGUITY"
    UNRESOLVED_CONFLICT = "UNRESOLVED_CONFLICT"


class ConflictSeverity(str, Enum):
    """
    Structural semantic severity of inconsistency.
    Describes degree of semantic conflict, NOT fraud probability or risk score.
    """
    INFO = "INFO"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class ConflictStatus(str, Enum):
    """Lifecycle status of a detected contradiction observation."""
    OPEN = "OPEN"
    RESOLVED = "RESOLVED"
    SUPERSEDED = "SUPERSEDED"
    UNRESOLVED = "UNRESOLVED"


class ResolutionType(str, Enum):
    """Classification of how a conflict was resolved by later evidence."""
    SUPERSEDED_BY_LATER_OBSERVATION = "SUPERSEDED_BY_LATER_OBSERVATION"
    AUTHORITATIVE_SOURCE_OVERRIDE = "AUTHORITATIVE_SOURCE_OVERRIDE"
    ORDERING_CLARIFIED = "ORDERING_CLARIFIED"
