"""
Phase 11 — Evidence Temporal Evolution & Change Intelligence type constants.

Plain Python string constants, NOT database enum types.
Using plain strings avoids Alembic migrations when new values are added.
This matches the project convention established in trace_types.py and integrity_types.py.

All values persisted to the database must come from these classes.
"""

from __future__ import annotations


class ChangeType:
    """
    Type of observable change between two consecutive evidence state snapshots.

    Only includes change types that are genuinely supported by existing
    Phase 6–9 data. No artificial events are generated.
    """

    NEW_EVIDENCE = "NEW_EVIDENCE"
    """A new evidence observation was incorporated since the previous snapshot."""

    EVIDENCE_REMOVED = "EVIDENCE_REMOVED"
    """An evidence observation count decreased since the previous snapshot."""

    EVIDENCE_INVALIDATED = "EVIDENCE_INVALIDATED"
    """An existing observation's valid_until expired."""

    NEW_SOURCE = "NEW_SOURCE"
    """A new distinct source type appeared in the evidence set."""

    SOURCE_LOST = "SOURCE_LOST"
    """A source type that was present is no longer represented."""

    CORROBORATION_INCREASED = "CORROBORATION_INCREASED"
    """Corroboration status improved (e.g. SINGLE_OBSERVATION → STRONGLY_CORROBORATED)."""

    CORROBORATION_DECREASED = "CORROBORATION_DECREASED"
    """Corroboration status degraded."""

    INDEPENDENCE_CHANGED = "INDEPENDENCE_CHANGED"
    """Independence / source-diversity status changed."""

    CONFLICT_CREATED = "CONFLICT_CREATED"
    """A new Phase 8 conflict was detected."""

    CONFLICT_RESOLVED = "CONFLICT_RESOLVED"
    """An existing conflict was resolved."""

    FRESHNESS_CHANGED = "FRESHNESS_CHANGED"
    """Aggregate freshness status changed (may be caused by time passage alone)."""

    INTEGRITY_CHANGED = "INTEGRITY_CHANGED"
    """Overall integrity status changed."""

    METHODOLOGY_CHANGED = "METHODOLOGY_CHANGED"
    """The methodology version changed between the two snapshots."""

    NO_MATERIAL_CHANGE = "NO_MATERIAL_CHANGE"
    """Comparison produced no meaningful difference across any dimension."""


class ChangeDimension:
    """The evidence quality dimension affected by a change."""

    EVIDENCE = "EVIDENCE"
    SOURCE = "SOURCE"
    CLAIM = "CLAIM"
    CORROBORATION = "CORROBORATION"
    INDEPENDENCE = "INDEPENDENCE"
    FRESHNESS = "FRESHNESS"
    CONSISTENCY = "CONSISTENCY"
    INTEGRITY = "INTEGRITY"
    METHODOLOGY = "METHODOLOGY"


class DirectCause:
    """
    The direct cause of an evidence state change.

    UNKNOWN_CAUSE is used when the system cannot establish causality.
    No fake probabilities or confidence scores are assigned.
    """

    NEW_EVIDENCE = "NEW_EVIDENCE"
    """A new observation was incorporated into the evidence scope."""

    EVIDENCE_INVALIDATION = "EVIDENCE_INVALIDATION"
    """An observation's valid_until expired."""

    CONFLICT = "CONFLICT"
    """A new semantic contradiction was detected by Phase 8."""

    CONFLICT_RESOLUTION = "CONFLICT_RESOLUTION"
    """An existing conflict was resolved by subsequent authoritative evidence."""

    TIME_PASSAGE = "TIME_PASSAGE"
    """Evidence aged without new observations being added."""

    SOURCE_CHANGE = "SOURCE_CHANGE"
    """The set of source types contributing evidence changed."""

    METHODOLOGY_CHANGE = "METHODOLOGY_CHANGE"
    """The evaluation methodology version changed."""

    MANUAL_RECOMPUTATION = "MANUAL_RECOMPUTATION"
    """An explicit recomputation was requested via API."""

    UNKNOWN_CAUSE = "UNKNOWN_CAUSE"
    """Causality cannot be established from available data."""


class CausalityLevel:
    """
    How confidently the cause is established.

    No fake probability values. The level is determined by rule, not by score.
    """

    DIRECT = "DIRECT"
    """The cause can be directly established (e.g. evidence count increased)."""

    INFERRED = "INFERRED"
    """The cause is the most likely explanation but cannot be pinned to one record."""

    UNKNOWN = "UNKNOWN"
    """The system cannot establish causality."""


class ChangeMagnitude:
    """
    Optional qualitative magnitude of a change.

    Determined by documented rules only — no arbitrary thresholds.
    NULL is acceptable when magnitude cannot be determined.
    """

    MINOR = "MINOR"
    MODERATE = "MODERATE"
    MAJOR = "MAJOR"
