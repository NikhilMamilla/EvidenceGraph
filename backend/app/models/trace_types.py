"""
Phase 10 — Evidence Integrity Decision Trace type constants.

Plain Python string constants, NOT database enum types.
Using plain strings avoids Alembic migrations when new values are added.

All values persisted to the database must come from these classes.
"""

from __future__ import annotations


class TraceStatus:
    """
    Lifecycle state of an EvidenceIntegrityTrace.

    An incomplete trace (EVALUATION_STARTED) must never be presented as
    a completed evaluation. FAILED traces are auditable failure records,
    never masquerade as completed evaluations.
    """

    EVALUATION_STARTED = "EVALUATION_STARTED"
    """Inputs are being captured. No hash exists yet. Not a finished evaluation."""

    COMPLETED = "COMPLETED"
    """Evaluation finished, canonical payload hashed, trace finalized and immutable."""

    FAILED = "FAILED"
    """Evaluation failed. The failure record itself is finalized and hashed."""


class TraceType:
    """
    What kind of evaluation this trace represents.

    EVALUATION traces form the payment's authoritative historical chain.
    REPLAY traces record re-executions of an original evaluation and never
    join the evaluation chain nor mutate the original trace.
    """

    EVALUATION = "EVALUATION"
    REPLAY = "REPLAY"


class ExclusionReason:
    """
    Why a candidate evidence observation was NOT included in an evaluation.

    Candidate evidence is never silently discarded — every exclusion is
    recorded with one of these reasons.
    """

    OBSERVED_AFTER_EVALUATION_TIME = "OBSERVED_AFTER_EVALUATION_TIME"
    """The observation's observed_at is after the evaluation_time anchor."""

    UNRELATED_PAYMENT = "UNRELATED_PAYMENT"
    """The observation does not describe the evaluated payment subject."""

    INVALIDATED = "INVALIDATED"
    """The observation's validity ended (valid_until <= evaluation_time)."""

    OUTSIDE_EVALUATION_SCOPE = "OUTSIDE_EVALUATION_SCOPE"
    """The observation relates to a different subject type (e.g. order-scoped
    evidence reached via lineage) that the integrity scope does not cover."""


class InclusionStatus:
    """Inclusion status of candidate evidence in a trace."""

    INCLUDED = "INCLUDED"
    EXCLUDED = "EXCLUDED"


class ActorType:
    """Who performed the action recorded by an audit event."""

    SYSTEM = "SYSTEM"
    USER = "USER"


class TraceEventType:
    """
    Ordered audit events emitted during the trace lifecycle.

    Events are persisted with a per-trace monotonic sequence_number so
    logical execution order survives any insertion-order ambiguity.
    """

    EVALUATION_STARTED = "EVALUATION_STARTED"
    EVIDENCE_SELECTED = "EVIDENCE_SELECTED"
    EVIDENCE_EXCLUDED = "EVIDENCE_EXCLUDED"
    QUALITY_MEASURED = "QUALITY_MEASURED"
    STRUCTURE_MEASURED = "STRUCTURE_MEASURED"
    CONSISTENCY_ANALYZED = "CONSISTENCY_ANALYZED"
    RULE_EXECUTED = "RULE_EXECUTED"
    INTEGRITY_COMPUTED = "INTEGRITY_COMPUTED"
    TRACE_FINALIZED = "TRACE_FINALIZED"
    EVALUATION_FAILED = "EVALUATION_FAILED"


# ---------------------------------------------------------------------------
# Versioning
# ---------------------------------------------------------------------------

TRACE_SCHEMA_VERSION = "TRC-1.0"
"""
Version of the decision trace schema (structure of the canonical payload).
Increment when the auditable content layout changes incompatibly.
"""

HASH_ALGORITHM = "SHA-256"
"""Hash algorithm used for trace digests. Recorded on every trace row."""

CANONICALIZATION_VERSION = "CG-1.0"
"""
Version of the canonical serialization rules used before hashing.

CG-1.0 rules (see app/services/trace_canonicalization.py):
  - Objects: keys sorted lexicographically (Unicode code point order)
  - Arrays: element order preserved
  - Strings: JSON escaping, non-ASCII escaped (ensure_ascii)
  - Timestamps: RFC3339 UTC with microsecond precision, 'Z' suffix
  - Numbers: integers as-is; floats via shortest round-trip repr;
    integral floats normalized to integers; NaN/Infinity forbidden
  - Nulls: preserved explicitly
  - Separators: ',' and ':' without whitespace; UTF-8 encoded bytes hashed
"""

HASH_DOMAIN = "evidencegraph.integrity_trace.v1"
"""
Domain separation string prepended into every canonical payload so that
trace hashes can never collide with hashes from other subsystems.
"""
