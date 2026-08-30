"""
Phase 9 — Evidence Integrity Type Constants.

Plain Python string constants, NOT database enum types.
Using plain strings avoids Alembic migrations when new values are added.

All values persisted to the database must come from these classes.
"""

from __future__ import annotations


class IntegrityStatus:
    """
    The overall evidence integrity classification for a payment.

    Determined by rule-based aggregation of the five dimensions.
    This is NOT a fraud score, risk score, or payment approval score.
    It reflects the quality and internal consistency of the evidence itself.
    """

    VERY_STRONG = "VERY_STRONG"
    """All dimensions strong; multiple independent sources; no conflicts detected."""

    STRONG = "STRONG"
    """Evidence is current, from an authoritative source, no open conflicts.
    Source diversity may be limited."""

    LIMITED = "LIMITED"
    """One or more dimensions are limited; no open semantic conflicts."""

    WEAK = "WEAK"
    """Evidence is stale, from a non-primary source, or has significant limitations."""

    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    """No evidence available for evaluation. Cannot assess integrity."""

    UNRESOLVED = "UNRESOLVED"
    """Open semantic conflicts exist (severity > INFO) that have not been resolved.
    Evidence is internally inconsistent."""


class IndependenceStatus:
    """
    Structural source diversity of the evidence set.

    Does NOT claim statistical independence — only structural separation
    between source types and provider events.
    """

    HIGH_SOURCE_DIVERSITY = "HIGH_SOURCE_DIVERSITY"
    """Evidence comes from multiple distinct source types and provider events."""

    LIMITED_SOURCE_DIVERSITY = "LIMITED_SOURCE_DIVERSITY"
    """Evidence comes from more than one event but limited source types."""

    SINGLE_SOURCE = "SINGLE_SOURCE"
    """All evidence originates from a single source type or event."""

    UNKNOWN = "UNKNOWN"
    """Cannot determine source diversity (no structure snapshot available)."""


class CorroborationStatus:
    """
    How well claims are supported across multiple observations and sources.
    """

    STRONGLY_CORROBORATED = "STRONGLY_CORROBORATED"
    """At least one claim is supported by observations from multiple distinct sources
    or events."""

    PARTIALLY_CORROBORATED = "PARTIALLY_CORROBORATED"
    """At least one claim is supported by multiple observations, but all from the
    same source/event."""

    SINGLE_OBSERVATION = "SINGLE_OBSERVATION"
    """All claims are supported by only one observation."""

    UNKNOWN = "UNKNOWN"
    """Cannot determine corroboration (no corroboration records available)."""


class ConsistencyStatus:
    """
    The temporal and semantic consistency state of a payment's evidence.
    """

    NO_DETECTED_CONFLICT = "NO_DETECTED_CONFLICT"
    """No contradiction engine detected any conflict in the evidence.
    This does NOT guarantee consistency — it means no conflict was detected."""

    ORDERING_AMBIGUITY_ONLY = "ORDERING_AMBIGUITY_ONLY"
    """Only INFO-severity ordering ambiguities exist. No semantic contradictions."""

    HAS_OPEN_CONFLICTS = "HAS_OPEN_CONFLICTS"
    """At least one OPEN conflict with severity > INFO exists."""

    UNRESOLVABLE = "UNRESOLVABLE"
    """Conflicts exist that could not be resolved by new evidence."""


# ---------------------------------------------------------------------------
# Methodology versioning
# ---------------------------------------------------------------------------

INTEGRITY_METHODOLOGY_VERSION = "EIS-1.0"
"""
Version identifier for the Evidence Integrity Scoring methodology.

EIS-1.0 characteristics:
  - Rule-based aggregation (no arbitrary numeric weights)
  - Five dimensions: Freshness, Source, Independence, Corroboration, Consistency
  - Status-based overall classification (no numeric score)
  - Fully deterministic given the same inputs and evaluation_time
  - No ML, no LLM, no external decisioning

Increment to EIS-2.0 when:
  - Aggregation rules change
  - New dimensions are added
  - Thresholds are modified
"""
