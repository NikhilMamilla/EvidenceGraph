"""
Phase 7 Structure & Corroboration Enums.
Defines canonical taxonomies for claims, evidence groups, corroboration types, and independence states.
"""
from enum import Enum


class ClaimType(str, Enum):
    """Canonical proposition types."""
    PAYMENT_STATUS = "PAYMENT_STATUS"
    PAYMENT_AMOUNT = "PAYMENT_AMOUNT"
    PAYMENT_CURRENCY = "PAYMENT_CURRENCY"
    PAYMENT_METHOD = "PAYMENT_METHOD"
    ORDER_ASSOCIATION = "ORDER_ASSOCIATION"
    CUSTOMER_IDENTIFIER = "CUSTOMER_IDENTIFIER"
    PAYMENT_EVENT_OCCURRENCE = "PAYMENT_EVENT_OCCURRENCE"


class GroupType(str, Enum):
    """Structural grouping basis for evidence observations."""
    SAME_WEBHOOK_EVENT = "SAME_WEBHOOK_EVENT"
    SAME_PAYMENT_EVENT = "SAME_PAYMENT_EVENT"
    SAME_SOURCE = "SAME_SOURCE"
    SAME_ORDER = "SAME_ORDER"


class CorroborationType(str, Enum):
    """Classification of corroboration supporting a claim."""
    SINGLE_OBSERVATION = "SINGLE_OBSERVATION"
    SAME_SOURCE_CORROBORATION = "SAME_SOURCE_CORROBORATION"
    MULTI_SOURCE_CORROBORATION = "MULTI_SOURCE_CORROBORATION"
    TEMPORAL_CORROBORATION = "TEMPORAL_CORROBORATION"


class IndependenceStatus(str, Enum):
    """
    Independence classification of evidence supporting a claim or relationship.
    Never declares unconditional statistical independence; indicates structural candidacy.
    """
    INDEPENDENT_CANDIDATE = "INDEPENDENT_CANDIDATE"
    DEPENDENT = "DEPENDENT"
    SAME_SOURCE = "SAME_SOURCE"
    UNKNOWN = "UNKNOWN"
