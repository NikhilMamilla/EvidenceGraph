"""
Phase 18 — Deterministic Evidence Decision Replay & Differential Analysis Domain Types.

Defines deterministic categorical states, change types, and methodology version
constants for decision replay and differential analysis.
"""

from __future__ import annotations

from enum import Enum

REPLAY_METHODOLOGY_V1 = "EDR-1.0"
DIFF_METHODOLOGY_V1 = "EDA-1.0"


class ReplayVerificationStatus(str, Enum):
    """Outcome of comparing a historical decision trace/snapshot with a reconstructed replay."""
    MATCH = "MATCH"
    REPLAY_MISMATCH = "REPLAY_MISMATCH"
    INCOMPLETE = "INCOMPLETE"
    METHODOLOGY_UNAVAILABLE = "METHODOLOGY_UNAVAILABLE"
    PROFILE_UNAVAILABLE = "PROFILE_UNAVAILABLE"


class FactDiffCategory(str, Enum):
    """Classification of an EvidenceFact between two historical evaluation points."""
    ADDED = "ADDED"
    REMOVED = "REMOVED"
    UNCHANGED = "UNCHANGED"
    CHANGED = "CHANGED"
    SUPERSEDED = "SUPERSEDED"


class SourceDiffType(str, Enum):
    """Direction of source diversity change between two historical points."""
    SOURCE_DIVERSITY_INCREASED = "SOURCE_DIVERSITY_INCREASED"
    SOURCE_DIVERSITY_DECREASED = "SOURCE_DIVERSITY_DECREASED"
    NO_SOURCE_CHANGE = "NO_SOURCE_CHANGE"


class CorroborationDiffType(str, Enum):
    """Direction of corroboration and independence change."""
    CORROBORATION_INCREASED = "CORROBORATION_INCREASED"
    CORROBORATION_DECREASED = "CORROBORATION_DECREASED"
    NO_CORROBORATION_CHANGE = "NO_CORROBORATION_CHANGE"


class ConflictDiffType(str, Enum):
    """Status transition of a contradiction between two historical points."""
    CONFLICT_ADDED = "CONFLICT_ADDED"
    CONFLICT_RESOLVED = "CONFLICT_RESOLVED"
    CONFLICT_CHANGED = "CONFLICT_CHANGED"
    NO_CONFLICT_CHANGE = "NO_CONFLICT_CHANGE"


class RequirementDiffType(str, Enum):
    """Transition of a specific evidence requirement in coverage profile."""
    REQUIREMENT_BECAME_PRESENT = "REQUIREMENT_BECAME_PRESENT"
    REQUIREMENT_BECAME_MISSING = "REQUIREMENT_BECAME_MISSING"
    REQUIREMENT_BECAME_CONFLICTED = "REQUIREMENT_BECAME_CONFLICTED"
    REQUIREMENT_BECAME_NOT_APPLICABLE = "REQUIREMENT_BECAME_NOT_APPLICABLE"
    NO_REQUIREMENT_CHANGE = "NO_REQUIREMENT_CHANGE"


class ChangeCategory(str, Enum):
    """Granular classification category for differential evidence analysis."""
    EVIDENCE_ADDED = "EVIDENCE_ADDED"
    EVIDENCE_REMOVED = "EVIDENCE_REMOVED"
    EVIDENCE_CHANGED = "EVIDENCE_CHANGED"
    SOURCE_ADDED = "SOURCE_ADDED"
    SOURCE_REMOVED = "SOURCE_REMOVED"
    CONFLICT_ADDED = "CONFLICT_ADDED"
    CONFLICT_RESOLVED = "CONFLICT_RESOLVED"
    COVERAGE_CHANGED = "COVERAGE_CHANGED"
    RELIABILITY_CHANGED = "RELIABILITY_CHANGED"
    INTEGRITY_CHANGED = "INTEGRITY_CHANGED"
    METHODOLOGY_CHANGED = "METHODOLOGY_CHANGED"
    PROFILE_CHANGED = "PROFILE_CHANGED"
    UNKNOWN_CHANGE = "UNKNOWN_CHANGE"
