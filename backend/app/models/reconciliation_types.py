"""
Phase 13 — Multi-Source Evidence Reconciliation & Evidence Identity.

Plain string constants for:
  - FactType       — the normalized real-world event type
  - FactStatus     — lifecycle status of a fact
  - ReconciliationResult — outcome of comparing two observations
  - ReconciliationRule   — the rule that produced the decision

Using plain Python strings, NOT SQLAlchemy/PostgreSQL ENUMs.
Adding new values requires no database migration.
"""

from __future__ import annotations


class FactType:
    """
    Normalized types of real-world payment facts.

    Only includes types that are actually supported by real Razorpay
    webhook data processed by Phase 4 evidence extraction.
    Do not add speculative types.
    """

    # Payment lifecycle events
    PAYMENT_CAPTURED = "PAYMENT_CAPTURED"
    """A payment.captured lifecycle event was observed."""

    PAYMENT_FAILED = "PAYMENT_FAILED"
    """A payment.failed lifecycle event was observed."""

    PAYMENT_AUTHORIZED = "PAYMENT_AUTHORIZED"
    """A payment.authorized lifecycle event was observed."""

    PAYMENT_REFUNDED = "PAYMENT_REFUNDED"
    """A payment.refund.created lifecycle event was observed."""

    # Attribute observations
    PAYMENT_AMOUNT_OBSERVED = "PAYMENT_AMOUNT_OBSERVED"
    """The monetary amount of a payment was observed."""

    PAYMENT_CURRENCY_OBSERVED = "PAYMENT_CURRENCY_OBSERVED"
    """The currency of a payment was observed."""

    PAYMENT_METHOD_OBSERVED = "PAYMENT_METHOD_OBSERVED"
    """The payment method was observed."""

    PAYMENT_STATUS_OBSERVED = "PAYMENT_STATUS_OBSERVED"
    """The status field of a payment was observed."""

    # Relationship observations
    PAYMENT_ORDER_ASSOCIATION = "PAYMENT_ORDER_ASSOCIATION"
    """An observed association between a payment and an order."""


# Mapping from EvidenceType (Phase 4) to FactType (Phase 13)
# Used during reconciliation normalization.
EVIDENCE_TYPE_TO_FACT_TYPE: dict[str, str] = {
    "PAYMENT_AMOUNT": FactType.PAYMENT_AMOUNT_OBSERVED,
    "PAYMENT_CURRENCY": FactType.PAYMENT_CURRENCY_OBSERVED,
    "PAYMENT_STATUS": FactType.PAYMENT_STATUS_OBSERVED,
    "PAYMENT_METHOD": FactType.PAYMENT_METHOD_OBSERVED,
    "PAYMENT_ORDER_RELATIONSHIP": FactType.PAYMENT_ORDER_ASSOCIATION,
    "PAYMENT_EVENT": FactType.PAYMENT_STATUS_OBSERVED,  # fallback; resolved by value
    "ORDER_AMOUNT": FactType.PAYMENT_AMOUNT_OBSERVED,  # order-scoped; separate by subject
    "ORDER_CURRENCY": FactType.PAYMENT_CURRENCY_OBSERVED,
    "ORDER_STATUS": FactType.PAYMENT_STATUS_OBSERVED,
}

# Mapping from Razorpay event_type strings to FactType.
# Used to assign FactType from webhook event_type when evidence_type is PAYMENT_EVENT.
EVENT_TYPE_TO_FACT_TYPE: dict[str, str] = {
    "payment.captured": FactType.PAYMENT_CAPTURED,
    "payment.failed": FactType.PAYMENT_FAILED,
    "payment.authorized": FactType.PAYMENT_AUTHORIZED,
    "refund.created": FactType.PAYMENT_REFUNDED,
    "payment.refund.created": FactType.PAYMENT_REFUNDED,
}

# Lifecycle fact types — these represent distinct state transitions and must
# never be merged with one another even if they share the same payment.
LIFECYCLE_FACT_TYPES: frozenset[str] = frozenset({
    FactType.PAYMENT_CAPTURED,
    FactType.PAYMENT_FAILED,
    FactType.PAYMENT_AUTHORIZED,
    FactType.PAYMENT_REFUNDED,
})


class FactStatus:
    """Lifecycle status of an EvidenceFact."""

    ACTIVE = "ACTIVE"
    """The fact is currently valid and not superseded."""

    SUPERSEDED = "SUPERSEDED"
    """A later fact of the same type represents a more current state."""

    INVALIDATED = "INVALIDATED"
    """The fact was determined to be incorrect by authoritative later evidence."""

    UNRESOLVED = "UNRESOLVED"
    """The fact's validity cannot be determined from available evidence."""


class ReconciliationResult:
    """
    Deterministic outcome of comparing two EvidenceObservations.

    SAME_FACT     — both observations represent the same underlying real-world event.
    DIFFERENT_FACT — observations represent distinct facts (different type or value).
    RELATED_FACT  — observations are causally linked but represent separate events.
    CONFLICTING_FACT — observations assert incompatible values for the same attribute.
    UNKNOWN       — insufficient information to determine identity.
    """

    SAME_FACT = "SAME_FACT"
    DIFFERENT_FACT = "DIFFERENT_FACT"
    RELATED_FACT = "RELATED_FACT"
    CONFLICTING_FACT = "CONFLICTING_FACT"
    UNKNOWN = "UNKNOWN"


class ReconciliationRule:
    """
    Identifies the specific rule that produced a reconciliation decision.
    Every rule has an associated version (RECONCILIATION_RULE_VERSION).
    """

    # Observations originate from the exact same Razorpay provider webhook delivery.
    SAME_PROVIDER_EVENT_V1 = "SAME_PROVIDER_EVENT_V1"

    # Observations originate from the exact same PaymentEvent record.
    SAME_PAYMENT_EVENT_V1 = "SAME_PAYMENT_EVENT_V1"

    # Observations represent different lifecycle events for the same payment.
    DIFFERENT_LIFECYCLE_V1 = "DIFFERENT_LIFECYCLE_V1"

    # Same payment, same attribute, conflicting values.
    CONFLICTING_VALUE_V1 = "CONFLICTING_VALUE_V1"

    # Same payment, same attribute, same value, distinct source mechanisms,
    # timestamps within the reconciliation window.
    SAME_FACT_DIFFERENT_SOURCE_V1 = "SAME_FACT_DIFFERENT_SOURCE_V1"

    # Timestamps are too far apart to confidently assign identity.
    TEMPORAL_AMBIGUITY_V1 = "TEMPORAL_AMBIGUITY_V1"

    # Default fallback — insufficient information.
    INSUFFICIENT_INFORMATION_V1 = "INSUFFICIENT_INFORMATION_V1"


# Version applied to all reconciliation records produced by the current engine.
RECONCILIATION_RULE_VERSION = "1.0"

# Time window (seconds) within which two observations of the same payment attribute
# and value are considered to represent the same underlying occurrence.
# Two observations separated by more than this window → UNKNOWN (not SAME_FACT).
# Rationale: Razorpay webhook retries and API polling within the same provider event
# typically arrive within milliseconds to a few seconds.
# This is a configurable constant; do not hardcode elsewhere.
FACT_RECONCILIATION_WINDOW_SECONDS = 5.0

# Current version of the fact methodology.
FACT_METHODOLOGY_VERSION = "1.0"
