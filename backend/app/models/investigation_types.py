"""
Investigation type definitions and constants for Phase 12.

Defines normalized node types, edge relationship types, and investigation
constants for deterministic graph queries and traversals.
No scoring, no risk labels, no fraud signals.
"""

from __future__ import annotations

from enum import Enum


class InvestigationNodeType(str, Enum):
    """Supported graph node types derived from real persisted entities."""

    PAYMENT = "PAYMENT"
    ORDER = "ORDER"
    CUSTOMER = "CUSTOMER"
    WEBHOOK_EVENT = "WEBHOOK_EVENT"
    PAYMENT_EVENT = "PAYMENT_EVENT"
    EVIDENCE = "EVIDENCE"
    CLAIM = "CLAIM"
    SOURCE = "SOURCE"
    CONFLICT = "CONFLICT"
    INTEGRITY_SNAPSHOT = "INTEGRITY_SNAPSHOT"
    STATE_CHANGE = "STATE_CHANGE"
    FACT = "FACT"


class InvestigationEdgeType(str, Enum):
    """Supported graph edge relationship types."""

    HAS_ORDER = "HAS_ORDER"
    HAS_CUSTOMER = "HAS_CUSTOMER"
    HAS_EVENT = "HAS_EVENT"
    HAS_FACT = "HAS_FACT"
    OBSERVES = "OBSERVES"
    FACT_SUPPORTS_CLAIM = "FACT_SUPPORTS_CLAIM"
    PRODUCED_EVIDENCE = "PRODUCED_EVIDENCE"
    DERIVED_FROM_WEBHOOK = "DERIVED_FROM_WEBHOOK"
    SUPPORTS_CLAIM = "SUPPORTS_CLAIM"
    DEPENDS_ON = "DEPENDS_ON"
    DERIVED_FROM = "DERIVED_FROM"
    CORROBORATES = "CORROBORATES"
    CONTRADICTS = "CONTRADICTS"
    HAS_CONFLICT = "HAS_CONFLICT"
    INVOLVES_CLAIM = "INVOLVES_CLAIM"
    HAS_INTEGRITY_SNAPSHOT = "HAS_INTEGRITY_SNAPSHOT"
    HAS_STATE_CHANGE = "HAS_STATE_CHANGE"
    FROM_SOURCE = "FROM_SOURCE"


class TraversalStatus(str, Enum):
    """Indicates if graph traversal completed normally or was bounded by limits."""

    COMPLETE = "COMPLETE"
    TRAVERSAL_LIMIT_REACHED = "TRAVERSAL_LIMIT_REACHED"


# Sensible traversal bounds
DEFAULT_TRAVERSAL_DEPTH = 2
MAX_TRAVERSAL_DEPTH = 5
DEFAULT_MAX_NODES = 200
HARD_MAX_NODES = 500
DEFAULT_MAX_EDGES = 400
HARD_MAX_EDGES = 1000
