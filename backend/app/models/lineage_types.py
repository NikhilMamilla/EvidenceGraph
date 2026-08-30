"""
Phase 14 — Evidence Lineage & Causal Explanation Engine: Type Constants.

String constants for lineage node types, edge types, causal roles,
completeness statuses, and linkage types.

Design:
  - Plain string constants (no Enum inheritance) for consistency with the
    rest of EvidenceGraph (Phases 7–13 use the same pattern).
  - No database storage — the lineage is assembled in memory by the
    LineageEngine and returned via API response.
  - Every constant is documented with which actual database relationship
    or rule backs it.
"""

from __future__ import annotations


# ---------------------------------------------------------------------------
# Lineage Node Types
# ---------------------------------------------------------------------------

class LineageNodeType:
    """
    Entity types that can appear as nodes in an evidence lineage graph.

    Every type corresponds to an actual database table row.
    """

    # Phase 2 — Razorpay webhook delivery record
    WEBHOOK_EVENT = "WEBHOOK_EVENT"

    # Phase 3 — Canonical event extracted from a webhook
    PAYMENT_EVENT = "PAYMENT_EVENT"

    # Phase 3 — Canonical payment entity
    PAYMENT = "PAYMENT"

    # Phase 4 — Immutable observation extracted from a provider event
    OBSERVATION = "OBSERVATION"

    # Phase 13 — Canonical real-world fact (reconciled from observations)
    FACT = "FACT"

    # Phase 7 — Canonical proposition asserted by the system (e.g. PAYMENT_STATUS=captured)
    CLAIM = "CLAIM"

    # Phase 7 — Corroboration analysis for a claim
    CORROBORATION = "CORROBORATION"

    # Phase 8 — Detected contradiction between two claims
    CONFLICT = "CONFLICT"

    # Phase 6 — Point-in-time quality measurement for one observation
    QUALITY_SNAPSHOT = "QUALITY_SNAPSHOT"

    # Phase 9 — Integrity evaluation result for a payment at one time
    INTEGRITY_SNAPSHOT = "INTEGRITY_SNAPSHOT"

    # Phase 10 — Tamper-evident audit trace for one evaluation
    INTEGRITY_TRACE = "INTEGRITY_TRACE"

    # Phase 11 — Denormalised evolution snapshot for temporal comparison
    STATE_SNAPSHOT = "STATE_SNAPSHOT"

    # Phase 11 — Detected change between two consecutive state snapshots
    STATE_CHANGE = "STATE_CHANGE"

    # Phase 13 — Pairwise identity decision between two observations
    RECONCILIATION = "RECONCILIATION"


# ---------------------------------------------------------------------------
# Lineage Edge Types
# ---------------------------------------------------------------------------

class LineageEdgeType:
    """
    Directed relationship types between lineage nodes.

    Every edge type must have an authoritative basis:
    either a direct FK or a documented DERIVED_TEMPORAL linkage.
    """

    # WebhookEvent → EvidenceObservation
    # FK: evidence_observations.webhook_event_id → webhook_events.id
    PRODUCED = "PRODUCED"

    # WebhookEvent → PaymentEvent
    # FK: payment_events.webhook_event_id → webhook_events.id
    TRIGGERED = "TRIGGERED"

    # EvidenceObservation → EvidenceFact
    # Via: observation_fact_links.observation_id + observation_fact_links.fact_id
    REPRESENTS = "REPRESENTS"

    # EvidenceObservation → Claim
    # Via: evidence_claim_links.evidence_id → claims.internal_id
    SUPPORTS = "SUPPORTS"

    # EvidenceObservation → EvidenceQualitySnapshot
    # Via: evidence_quality_snapshots.evidence_id FK
    MEASURED_BY = "MEASURED_BY"

    # Claim → EvidenceCorroboration
    # FK: evidence_corroborations.claim_id → claims.internal_id
    CORROBORATED_BY = "CORROBORATED_BY"

    # EvidenceConflict → Claim (both claim_a and claim_b)
    # FK: evidence_conflicts.claim_a_id / claim_b_id → claims.internal_id
    CONFLICTED_BY = "CONFLICTED_BY"

    # EvidenceIntegritySnapshot → EvidenceIntegrityTrace
    # FK: evidence_integrity_traces.integrity_snapshot_internal_id
    EVALUATED_BY = "EVALUATED_BY"

    # EvidenceStateSnapshot → EvidenceIntegritySnapshot
    # FK: evidence_state_snapshots.integrity_snapshot_id
    MIRRORS = "MIRRORS"

    # EvidenceStateChange → EvidenceStateSnapshot (previous and current)
    # FK: evidence_state_changes.previous_snapshot_id / current_snapshot_id
    STATE_TRANSITION = "STATE_TRANSITION"

    # EvidenceStateChange → EvidenceObservation (when causality is DIRECT)
    # FK: evidence_state_changes.linked_evidence_id
    CAUSED_STATE_CHANGE = "CAUSED_STATE_CHANGE"

    # EvidenceReconciliation → EvidenceFact (when result = SAME_FACT)
    # FK: evidence_reconciliations.fact_id
    RECONCILED_INTO = "RECONCILED_INTO"

    # EvidenceConflict → EvidenceIntegritySnapshot (DERIVED linkage)
    # No FK — linked via payment_id match + evaluated_at temporal window
    CONTRIBUTES_TO = "CONTRIBUTES_TO"

    # EvidenceFact → Claim (DERIVED via observation bridge)
    # No direct FK — traced via ObservationFactLink + EvidenceClaimLink
    FACT_SUPPORTS_CLAIM = "FACT_SUPPORTS_CLAIM"


# ---------------------------------------------------------------------------
# Causal Role
# ---------------------------------------------------------------------------

class CausalRole:
    """
    Semantics of an edge — what role the source node plays relative to the target.

    IMPORTANT: 'DIRECT_CAUSE' is reserved for relationships with an explicit
    FK linkage AND documented causality (e.g. EvidenceStateChange.causality = DIRECT).
    Do not use DIRECT_CAUSE when linkage is only temporal.
    """

    # Source node directly caused the target (FK + documented causality)
    DIRECT_CAUSE = "DIRECT_CAUSE"

    # Source node was one of multiple inputs to the target
    CONTRIBUTING_INPUT = "CONTRIBUTING_INPUT"

    # Target was derived from source (e.g. Fact derived from Observation)
    DERIVED_FROM = "DERIVED_FROM"

    # Source provides context but did not cause the target
    CONTEXT = "CONTEXT"

    # Source is a conflict that reduced the integrity dimension
    CONFLICT_INPUT = "CONFLICT_INPUT"

    # Source is corroboration that supported the integrity dimension
    CORROBORATION_INPUT = "CORROBORATION_INPUT"


# ---------------------------------------------------------------------------
# Lineage Completeness
# ---------------------------------------------------------------------------

class LineageCompleteness:
    """
    Overall completeness assessment for an assembled lineage chain.

    COMPLETE: Every required step in the lineage has an authoritative FK reference.
    PARTIAL: Some optional or contextual links are missing (e.g. no quality snapshot).
    BROKEN: A required FK step cannot be established (e.g. no integrity trace exists).
    """

    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    BROKEN = "BROKEN"


# ---------------------------------------------------------------------------
# Linkage Type
# ---------------------------------------------------------------------------

class LinkageType:
    """
    How a lineage edge was established.

    FOREIGN_KEY: Backed by an actual database FK constraint.
    DERIVED_TEMPORAL: Established via payment_id match + evaluated_at time window.
                      Used where no FK exists (documented gaps).
    SAME_PAYMENT: Joined solely by shared payment_id (weakest linkage — documented).
    """

    FOREIGN_KEY = "FOREIGN_KEY"
    DERIVED_TEMPORAL = "DERIVED_TEMPORAL"
    SAME_PAYMENT = "SAME_PAYMENT"


# ---------------------------------------------------------------------------
# Explanation Levels
# ---------------------------------------------------------------------------

class ExplanationLevel:
    SUMMARY = "SUMMARY"
    DETAILED = "DETAILED"


# ---------------------------------------------------------------------------
# Traversal Direction
# ---------------------------------------------------------------------------

class TraversalDirection:
    FORWARD = "FORWARD"    # Provider event → Integrity trace
    BACKWARD = "BACKWARD"  # Integrity trace → Provider event
    BIDIRECTIONAL = "BIDIRECTIONAL"


# ---------------------------------------------------------------------------
# Safety limits
# ---------------------------------------------------------------------------

LINEAGE_MAX_NODES_DEFAULT = 200
LINEAGE_MAX_NODES_HARD_LIMIT = 500
LINEAGE_MAX_DEPTH_DEFAULT = 8
LINEAGE_MAX_DEPTH_HARD_LIMIT = 10
LINEAGE_METHODOLOGY_VERSION = "LIN-1.0"
