"""
Phase 14 — Evidence Lineage & Causal Explanation Engine.

Assembles a complete, authoritative, bidirectional lineage chain from real
database records. Every edge is backed by an actual FK or documented
DERIVED_TEMPORAL linkage. No relationships are fabricated.

Architecture:
  - Three root-level entry points: payment lineage, trace lineage, fact lineage.
  - One path-search entry point for arbitrary source→target traversal.
  - Pure read-only: no writes, no side effects.
  - Sanitized outputs: no raw payloads, no webhook secrets, no credentials.
  - Safety limits: max_nodes, max_depth, query timeout (via bounded loops).

Documented lineage gaps (no FK exists — explicitly recorded as LineageGap):
  1. EvidenceFact → Claim: no direct FK. Bridged via ObservationFactLink +
     EvidenceClaimLink. Linkage type: DERIVED_TEMPORAL (SAME_PAYMENT path).
  2. EvidenceConflict → EvidenceIntegritySnapshot: no FK. Joined via payment_id
     + evaluated_at temporal window. Linkage: DERIVED_TEMPORAL.
  3. EvidenceQualitySnapshot → EvidenceIntegritySnapshot: no FK. Joined via
     evidence_id → observation → payment_id + time. Linkage: DERIVED_TEMPORAL.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.evidence import EvidenceObservation
from app.models.evidence_conflict import EvidenceConflict
from app.models.evidence_fact import EvidenceFact
from app.models.evidence_integrity import EvidenceIntegritySnapshot
from app.models.evidence_quality import EvidenceQualitySnapshot
from app.models.evidence_reconciliation import EvidenceReconciliation
from app.models.evidence_structure import (
    Claim,
    EvidenceClaimLink,
    EvidenceCorroboration,
    EvidenceStructureSnapshot,
)
from app.models.evolution_models import EvidenceStateChange, EvidenceStateSnapshot
from app.models.integrity_trace import EvidenceIntegrityTrace
from app.models.lineage_types import (
    LINEAGE_MAX_DEPTH_DEFAULT,
    LINEAGE_MAX_DEPTH_HARD_LIMIT,
    LINEAGE_MAX_NODES_DEFAULT,
    LINEAGE_MAX_NODES_HARD_LIMIT,
    LINEAGE_METHODOLOGY_VERSION,
    CausalRole,
    ExplanationLevel,
    LineageCompleteness,
    LineageEdgeType,
    LineageNodeType,
    LinkageType,
    TraversalDirection,
)
from app.models.observation_fact_link import ObservationFactLink
from app.models.payment import Payment
from app.models.payment_event import PaymentEvent
from app.models.reconciliation_types import ReconciliationResult
from app.models.webhook_event import WebhookEvent
from app.schemas.lineage import (
    EvaluationContext,
    FactLineageResponse,
    LineageEdge,
    LineageExplanation,
    LineageGap,
    LineageNode,
    LineagePathResponse,
    LineageSummary,
    PaymentLineageResponse,
    TraceLineageResponse,
)


# ---------------------------------------------------------------------------
# Internal data-collection helpers
# ---------------------------------------------------------------------------

def _node_id(node_type: str, entity_id: Any) -> str:
    """Build a stable composite node_id string."""
    return f"{node_type}:{entity_id}"


def _safe_meta(d: Dict[str, Any]) -> Dict[str, Any]:
    """Strip any key that looks like it could contain sensitive data."""
    _SENSITIVE = {
        "raw_payload", "payload", "signature", "secret", "password",
        "api_key", "webhook_secret", "cvv", "pin", "otp", "token",
        "auth", "credential", "key", "razorpay_webhook_secret",
    }
    return {k: v for k, v in d.items() if k.lower() not in _SENSITIVE}


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Node builders — each wraps one DB record type
# ---------------------------------------------------------------------------

def _webhook_node(we: WebhookEvent) -> LineageNode:
    return LineageNode(
        node_id=_node_id(LineageNodeType.WEBHOOK_EVENT, we.id),
        node_type=LineageNodeType.WEBHOOK_EVENT,
        entity_id=str(we.id),
        label=f"Webhook #{we.id} ({we.event_type})",
        timestamp=we.received_at,
        metadata=_safe_meta({
            "event_type": we.event_type,
            "razorpay_event_id": we.razorpay_event_id,
            "signature_verified": we.signature_verified,
            "payment_id": we.payment_id,
        }),
    )


def _payment_event_node(pe: PaymentEvent) -> LineageNode:
    return LineageNode(
        node_id=_node_id(LineageNodeType.PAYMENT_EVENT, pe.internal_id),
        node_type=LineageNodeType.PAYMENT_EVENT,
        entity_id=str(pe.internal_id),
        label=f"PaymentEvent #{pe.internal_id} ({pe.event_type})",
        timestamp=pe.event_timestamp or pe.created_at,
        metadata=_safe_meta({
            "event_type": pe.event_type,
            "webhook_event_id": pe.webhook_event_id,
        }),
    )


def _payment_node(p: Payment) -> LineageNode:
    return LineageNode(
        node_id=_node_id(LineageNodeType.PAYMENT, p.razorpay_payment_id),
        node_type=LineageNodeType.PAYMENT,
        entity_id=p.razorpay_payment_id,
        label=f"Payment {p.razorpay_payment_id}",
        timestamp=p.first_observed_at,
        metadata=_safe_meta({
            "status": p.status,
            "currency": p.currency,
            "captured": p.captured,
        }),
    )


def _observation_node(obs: EvidenceObservation) -> LineageNode:
    return LineageNode(
        node_id=_node_id(LineageNodeType.OBSERVATION, obs.internal_id),
        node_type=LineageNodeType.OBSERVATION,
        entity_id=str(obs.internal_id),
        label=f"Observation #{obs.internal_id} ({obs.evidence_type})",
        timestamp=obs.observed_at,
        metadata=_safe_meta({
            "evidence_type": obs.evidence_type,
            "source_type": obs.source_type,
            "extraction_method": obs.extraction_method,
            "extraction_version": obs.extraction_version,
            "subject_type": obs.subject_type,
            "subject_id": obs.subject_id,
            "webhook_event_id": obs.webhook_event_id,
            "payment_event_id": obs.payment_event_id,
        }),
    )


def _fact_node(fact: EvidenceFact) -> LineageNode:
    return LineageNode(
        node_id=_node_id(LineageNodeType.FACT, fact.internal_id),
        node_type=LineageNodeType.FACT,
        entity_id=str(fact.internal_id),
        label=f"Fact #{fact.internal_id} ({fact.fact_type})",
        timestamp=fact.first_observed_at,
        metadata=_safe_meta({
            "fact_type": fact.fact_type,
            "status": fact.status,
            "observation_count": fact.observation_count,
            "distinct_source_count": fact.distinct_source_count,
            "methodology_version": fact.methodology_version,
            "canonical_value": fact.canonical_value,
        }),
    )


def _claim_node(claim: Claim) -> LineageNode:
    return LineageNode(
        node_id=_node_id(LineageNodeType.CLAIM, claim.internal_id),
        node_type=LineageNodeType.CLAIM,
        entity_id=str(claim.internal_id),
        label=f"Claim #{claim.internal_id} ({claim.claim_type})",
        timestamp=claim.created_at,
        metadata=_safe_meta({
            "claim_type": claim.claim_type,
            "claim_key": claim.claim_key,
            "canonical_value": claim.canonical_value,
            "subject_type": claim.subject_type,
            "subject_id": claim.subject_id,
        }),
    )


def _corroboration_node(corr: EvidenceCorroboration) -> LineageNode:
    return LineageNode(
        node_id=_node_id(LineageNodeType.CORROBORATION, corr.internal_id),
        node_type=LineageNodeType.CORROBORATION,
        entity_id=str(corr.internal_id),
        label=f"Corroboration #{corr.internal_id} ({corr.corroboration_type})",
        timestamp=corr.created_at,
        metadata=_safe_meta({
            "corroboration_type": corr.corroboration_type,
            "independence_status": corr.independence_status,
            "observation_count": corr.observation_count,
            "distinct_sources_count": corr.distinct_sources_count,
            "distinct_events_count": corr.distinct_events_count,
        }),
    )


def _conflict_node(conflict: EvidenceConflict) -> LineageNode:
    return LineageNode(
        node_id=_node_id(LineageNodeType.CONFLICT, conflict.internal_id),
        node_type=LineageNodeType.CONFLICT,
        entity_id=str(conflict.internal_id),
        label=f"Conflict #{conflict.internal_id} ({conflict.conflict_type})",
        timestamp=conflict.detected_at,
        metadata=_safe_meta({
            "conflict_type": conflict.conflict_type,
            "severity": conflict.severity,
            "status": conflict.status,
            "rule_version": conflict.rule_version,
        }),
    )


def _quality_node(qs: EvidenceQualitySnapshot) -> LineageNode:
    return LineageNode(
        node_id=_node_id(LineageNodeType.QUALITY_SNAPSHOT, qs.internal_id),
        node_type=LineageNodeType.QUALITY_SNAPSHOT,
        entity_id=str(qs.internal_id),
        label=f"QualitySnapshot #{qs.internal_id}",
        timestamp=qs.evaluated_at if hasattr(qs, "evaluated_at") else qs.created_at,
        metadata=_safe_meta({
            "evidence_id": qs.evidence_id,
        }),
    )


def _integrity_snapshot_node(snap: EvidenceIntegritySnapshot) -> LineageNode:
    dims: List[str] = []
    for d in ["freshness_result", "source_result", "independence_result",
              "corroboration_result", "consistency_result"]:
        if getattr(snap, d, None):
            dims.append(d.replace("_result", "").upper())
    return LineageNode(
        node_id=_node_id(LineageNodeType.INTEGRITY_SNAPSHOT, snap.internal_id),
        node_type=LineageNodeType.INTEGRITY_SNAPSHOT,
        entity_id=str(snap.internal_id),
        label=f"IntegritySnapshot #{snap.internal_id} ({snap.overall_status})",
        timestamp=snap.evaluated_at,
        metadata=_safe_meta({
            "overall_status": snap.overall_status,
            "methodology_version": snap.methodology_version,
            "evidence_count": snap.evidence_count,
            "source_count": snap.source_count,
            "conflict_count": snap.conflict_count,
            "open_conflict_count": snap.open_conflict_count,
            "dimensions": dims,
        }),
    )


def _trace_node(trace: EvidenceIntegrityTrace) -> LineageNode:
    return LineageNode(
        node_id=_node_id(LineageNodeType.INTEGRITY_TRACE, trace.trace_id),
        node_type=LineageNodeType.INTEGRITY_TRACE,
        entity_id=trace.trace_id,
        label=f"IntegrityTrace {trace.trace_id[:8]}… ({trace.overall_status})",
        timestamp=trace.evaluated_at,
        metadata=_safe_meta({
            "trace_type": trace.trace_type,
            "status": trace.status,
            "overall_status": trace.overall_status,
            "methodology_version": trace.methodology_version,
            "trace_hash": trace.trace_hash,
            "hash_algorithm": trace.hash_algorithm,
            "canonicalization_version": trace.canonicalization_version,
        }),
    )


def _state_snapshot_node(ss: EvidenceStateSnapshot) -> LineageNode:
    return LineageNode(
        node_id=_node_id(LineageNodeType.STATE_SNAPSHOT, ss.internal_id),
        node_type=LineageNodeType.STATE_SNAPSHOT,
        entity_id=str(ss.internal_id),
        label=f"StateSnapshot #{ss.internal_id} ({ss.overall_integrity_status})",
        timestamp=ss.evaluation_time,
        metadata=_safe_meta({
            "overall_integrity_status": ss.overall_integrity_status,
            "corroboration_status": ss.corroboration_status,
            "consistency_status": ss.consistency_status,
            "freshness_status": ss.freshness_status,
            "independence_status": ss.independence_status,
            "evidence_count": ss.evidence_count,
        }),
    )


def _state_change_node(sc: EvidenceStateChange) -> LineageNode:
    return LineageNode(
        node_id=_node_id(LineageNodeType.STATE_CHANGE, sc.change_id),
        node_type=LineageNodeType.STATE_CHANGE,
        entity_id=sc.change_id,
        label=f"StateChange ({sc.dimension}: {sc.previous_value} → {sc.current_value})",
        timestamp=sc.detected_at,
        metadata=_safe_meta({
            "change_type": sc.change_type,
            "dimension": sc.dimension,
            "previous_value": sc.previous_value,
            "current_value": sc.current_value,
            "causality": sc.causality,
            "direct_cause": sc.direct_cause,
            "magnitude": sc.magnitude,
        }),
    )


def _reconciliation_node(rec: EvidenceReconciliation) -> LineageNode:
    return LineageNode(
        node_id=_node_id(LineageNodeType.RECONCILIATION, rec.internal_id),
        node_type=LineageNodeType.RECONCILIATION,
        entity_id=str(rec.internal_id),
        label=f"Reconciliation #{rec.internal_id} ({rec.result})",
        timestamp=rec.evaluated_at,
        metadata=_safe_meta({
            "result": rec.result,
            "rule_id": rec.rule_id,
            "rule_version": rec.rule_version,
            "explanation": rec.explanation,
            "fact_id": rec.fact_id,
        }),
    )


# ---------------------------------------------------------------------------
# Lineage Assembler
# ---------------------------------------------------------------------------

class LineageAssembler:
    """
    Mutable accumulator for nodes, edges, and gaps during lineage assembly.
    Deduplicates by node_id to prevent duplicate entries when multiple
    observations share the same webhook event.
    """

    def __init__(self, max_nodes: int = LINEAGE_MAX_NODES_DEFAULT) -> None:
        self._nodes: Dict[str, LineageNode] = {}
        self._edges: List[LineageEdge] = []
        self._gaps: List[LineageGap] = []
        self._edge_keys: Set[Tuple[str, str, str]] = set()
        self.max_nodes = min(max_nodes, LINEAGE_MAX_NODES_HARD_LIMIT)
        self.truncated = False

    def add_node(self, node: LineageNode) -> bool:
        """Add node; returns False if max_nodes reached (truncation)."""
        if node.node_id in self._nodes:
            return True  # already present — dedup
        if len(self._nodes) >= self.max_nodes:
            self.truncated = True
            return False
        self._nodes[node.node_id] = node
        return True

    def add_edge(self, edge: LineageEdge) -> None:
        key = (edge.source_node_id, edge.target_node_id, edge.edge_type)
        if key not in self._edge_keys:
            self._edge_keys.add(key)
            self._edges.append(edge)

    def add_gap(self, gap: LineageGap) -> None:
        self._gaps.append(gap)

    def has_node(self, node_id: str) -> bool:
        return node_id in self._nodes

    @property
    def nodes(self) -> List[LineageNode]:
        return list(self._nodes.values())

    @property
    def edges(self) -> List[LineageEdge]:
        return self._edges

    @property
    def gaps(self) -> List[LineageGap]:
        return self._gaps


# ---------------------------------------------------------------------------
# Core traversal helpers
# ---------------------------------------------------------------------------

def _load_observations_for_payment(
    db: Session,
    payment_id: str,
    as_of: Optional[datetime],
) -> List[EvidenceObservation]:
    """Batch-load all observations for a payment, filtered by as_of."""
    q = select(EvidenceObservation).where(
        EvidenceObservation.subject_type == "payment",
        EvidenceObservation.subject_id == payment_id,
    ).order_by(EvidenceObservation.observed_at.asc())
    if as_of is not None:
        q = q.where(EvidenceObservation.observed_at <= as_of)
    return db.execute(q).scalars().all()


def _load_webhook_events_for_ids(
    db: Session,
    ids: List[int],
) -> Dict[int, WebhookEvent]:
    if not ids:
        return {}
    rows = db.execute(
        select(WebhookEvent).where(WebhookEvent.id.in_(ids))
    ).scalars().all()
    return {r.id: r for r in rows}


def _load_payment_events_for_webhook_ids(
    db: Session,
    webhook_ids: List[int],
) -> Dict[int, PaymentEvent]:
    """Map webhook_event_id → PaymentEvent (unique per webhook)."""
    if not webhook_ids:
        return {}
    rows = db.execute(
        select(PaymentEvent).where(PaymentEvent.webhook_event_id.in_(webhook_ids))
    ).scalars().all()
    return {r.webhook_event_id: r for r in rows}


def _load_fact_links_for_obs(
    db: Session,
    obs_ids: List[int],
) -> Dict[int, List[ObservationFactLink]]:
    """obs_id → list of ObservationFactLink rows."""
    if not obs_ids:
        return {}
    rows = db.execute(
        select(ObservationFactLink).where(ObservationFactLink.observation_id.in_(obs_ids))
    ).scalars().all()
    result: Dict[int, List[ObservationFactLink]] = {}
    for r in rows:
        result.setdefault(r.observation_id, []).append(r)
    return result


def _load_facts_for_ids(
    db: Session,
    fact_ids: List[int],
) -> Dict[int, EvidenceFact]:
    if not fact_ids:
        return {}
    rows = db.execute(
        select(EvidenceFact).where(EvidenceFact.internal_id.in_(fact_ids))
    ).scalars().all()
    return {r.internal_id: r for r in rows}


def _load_claim_links_for_obs(
    db: Session,
    obs_ids: List[int],
) -> Dict[int, List[EvidenceClaimLink]]:
    """obs_id → list of EvidenceClaimLink rows."""
    if not obs_ids:
        return {}
    rows = db.execute(
        select(EvidenceClaimLink).where(EvidenceClaimLink.evidence_id.in_(obs_ids))
    ).scalars().all()
    result: Dict[int, List[EvidenceClaimLink]] = {}
    for r in rows:
        result.setdefault(r.evidence_id, []).append(r)
    return result


def _load_claims_for_ids(
    db: Session,
    claim_ids: List[int],
) -> Dict[int, Claim]:
    if not claim_ids:
        return {}
    rows = db.execute(
        select(Claim).where(Claim.internal_id.in_(claim_ids))
    ).scalars().all()
    return {r.internal_id: r for r in rows}


def _load_corroborations_for_claims(
    db: Session,
    claim_ids: List[int],
) -> Dict[int, EvidenceCorroboration]:
    """claim_id → EvidenceCorroboration (one-to-one)."""
    if not claim_ids:
        return {}
    rows = db.execute(
        select(EvidenceCorroboration).where(EvidenceCorroboration.claim_id.in_(claim_ids))
    ).scalars().all()
    return {r.claim_id: r for r in rows}


def _load_conflicts_for_claims(
    db: Session,
    claim_ids: List[int],
) -> List[EvidenceConflict]:
    """All conflicts involving any of the given claim_ids."""
    if not claim_ids:
        return []
    from sqlalchemy import or_
    rows = db.execute(
        select(EvidenceConflict).where(
            or_(
                EvidenceConflict.claim_a_id.in_(claim_ids),
                EvidenceConflict.claim_b_id.in_(claim_ids),
            )
        )
    ).scalars().all()
    return list(rows)


def _load_quality_snapshots_for_obs(
    db: Session,
    obs_ids: List[int],
    as_of: Optional[datetime],
) -> Dict[int, EvidenceQualitySnapshot]:
    """obs_id → most recent quality snapshot at/before as_of."""
    if not obs_ids:
        return {}
    q = select(EvidenceQualitySnapshot).where(
        EvidenceQualitySnapshot.evidence_id.in_(obs_ids)
    )
    if as_of is not None:
        # evaluated_at or created_at depending on model
        if hasattr(EvidenceQualitySnapshot, "evaluated_at"):
            q = q.where(EvidenceQualitySnapshot.evaluated_at <= as_of)
    rows = db.execute(q).scalars().all()
    # Keep only the most recent per obs_id
    result: Dict[int, EvidenceQualitySnapshot] = {}
    for r in rows:
        existing = result.get(r.evidence_id)
        ts = getattr(r, "evaluated_at", None) or r.created_at
        existing_ts = (
            getattr(existing, "evaluated_at", None) or existing.created_at
            if existing else None
        )
        if existing is None or (existing_ts and ts and ts > existing_ts):
            result[r.evidence_id] = r
    return result


def _load_integrity_snapshot(
    db: Session,
    payment_id: str,
    as_of: Optional[datetime],
) -> Optional[EvidenceIntegritySnapshot]:
    """Most recent completed integrity snapshot at/before as_of."""
    q = select(EvidenceIntegritySnapshot).where(
        EvidenceIntegritySnapshot.payment_id == payment_id
    ).order_by(EvidenceIntegritySnapshot.evaluated_at.desc())
    if as_of is not None:
        q = q.where(EvidenceIntegritySnapshot.evaluated_at <= as_of)
    return db.execute(q.limit(1)).scalar_one_or_none()


def _load_trace_for_snapshot(
    db: Session,
    snapshot_internal_id: int,
) -> Optional[EvidenceIntegrityTrace]:
    """FK: evidence_integrity_traces.integrity_snapshot_internal_id."""
    return db.execute(
        select(EvidenceIntegrityTrace).where(
            EvidenceIntegrityTrace.integrity_snapshot_internal_id == snapshot_internal_id,
            EvidenceIntegrityTrace.status == "COMPLETED",
        ).order_by(EvidenceIntegrityTrace.created_at.desc()).limit(1)
    ).scalar_one_or_none()


def _load_state_snapshots(
    db: Session,
    payment_id: str,
    as_of: Optional[datetime],
) -> List[EvidenceStateSnapshot]:
    q = select(EvidenceStateSnapshot).where(
        EvidenceStateSnapshot.payment_id == payment_id
    ).order_by(EvidenceStateSnapshot.evaluation_time.asc())
    if as_of is not None:
        q = q.where(EvidenceStateSnapshot.evaluation_time <= as_of)
    return db.execute(q).scalars().all()


def _load_state_changes_for_snapshots(
    db: Session,
    snapshot_ids: List[int],
) -> List[EvidenceStateChange]:
    if not snapshot_ids:
        return []
    from sqlalchemy import or_
    rows = db.execute(
        select(EvidenceStateChange).where(
            or_(
                EvidenceStateChange.previous_snapshot_id.in_(snapshot_ids),
                EvidenceStateChange.current_snapshot_id.in_(snapshot_ids),
            )
        ).order_by(EvidenceStateChange.detected_at.asc())
    ).scalars().all()
    return list(rows)


def _load_reconciliations_for_obs(
    db: Session,
    obs_ids: List[int],
) -> List[EvidenceReconciliation]:
    if not obs_ids:
        return []
    from sqlalchemy import or_
    rows = db.execute(
        select(EvidenceReconciliation).where(
            or_(
                EvidenceReconciliation.observation_a_id.in_(obs_ids),
                EvidenceReconciliation.observation_b_id.in_(obs_ids),
            )
        )
    ).scalars().all()
    return list(rows)


# ---------------------------------------------------------------------------
# Completeness computation
# ---------------------------------------------------------------------------

def _compute_completeness(
    assembler: LineageAssembler,
    has_observations: bool,
    has_facts: bool,
    has_claims: bool,
    has_integrity: bool,
    has_trace: bool,
) -> str:
    """
    COMPLETE: Observations → Facts → Claims → Integrity Snapshot → Trace all exist.
    PARTIAL: Some optional links are missing (no quality snapshot, no state changes, etc.)
    BROKEN: A required step is completely absent.
    """
    if not has_observations:
        return LineageCompleteness.BROKEN
    if not has_integrity:
        return LineageCompleteness.BROKEN
    if not has_facts or not has_claims or not has_trace:
        return LineageCompleteness.PARTIAL
    if assembler.gaps:
        return LineageCompleteness.PARTIAL
    return LineageCompleteness.COMPLETE


# ---------------------------------------------------------------------------
# Explanation generator
# ---------------------------------------------------------------------------

def _build_explanation(
    payment_id: str,
    assembler: LineageAssembler,
    integrity_snapshot: Optional[EvidenceIntegritySnapshot],
    as_of: Optional[datetime],
) -> LineageExplanation:
    """Deterministic explanation from real record values. No LLM."""
    node_types = [n.node_type for n in assembler.nodes]
    n_obs = node_types.count(LineageNodeType.OBSERVATION)
    n_facts = node_types.count(LineageNodeType.FACT)
    n_claims = node_types.count(LineageNodeType.CLAIM)
    n_conflicts = node_types.count(LineageNodeType.CONFLICT)
    n_gaps = len(assembler.gaps)

    status_str = (
        integrity_snapshot.overall_status if integrity_snapshot else "NOT_EVALUATED"
    )
    as_of_str = as_of.isoformat() if as_of else "now"

    summary = (
        f"For payment {payment_id} (as of {as_of_str}): "
        f"{n_obs} observation(s) from the evidence record; "
        f"{n_facts} canonical fact(s) established via Phase 13 reconciliation; "
        f"{n_claims} claim(s) supported by observations; "
        f"{n_conflicts} conflict(s) detected; "
        f"overall integrity status: {status_str}."
    )

    detail_lines: List[str] = []

    # Observation → Fact edges
    for edge in assembler.edges:
        if edge.edge_type == LineageEdgeType.REPRESENTS:
            detail_lines.append(
                f"Observation {edge.source_node_id} was reconciled into "
                f"Fact {edge.target_node_id} ({edge.explanation})."
            )
        elif edge.edge_type == LineageEdgeType.RECONCILED_INTO:
            detail_lines.append(
                f"Reconciliation {edge.source_node_id} resolved to "
                f"Fact {edge.target_node_id} ({edge.explanation})."
            )

    # Conflicts
    for edge in assembler.edges:
        if edge.edge_type == LineageEdgeType.CONFLICTED_BY:
            detail_lines.append(
                f"Claim {edge.source_node_id} is involved in "
                f"conflict {edge.target_node_id} ({edge.explanation})."
            )

    # State changes
    for edge in assembler.edges:
        if edge.edge_type == LineageEdgeType.STATE_TRANSITION:
            detail_lines.append(
                f"State transition from {edge.source_node_id} to "
                f"{edge.target_node_id} recorded."
            )

    # Integrity
    for edge in assembler.edges:
        if edge.edge_type == LineageEdgeType.EVALUATED_BY:
            detail_lines.append(
                f"Integrity snapshot {edge.source_node_id} was evaluated and "
                f"recorded in trace {edge.target_node_id}."
            )

    # Gaps
    for gap in assembler.gaps:
        detail_lines.append(
            f"LINEAGE GAP at '{gap.location}': expected {gap.expected_edge_type} "
            f"— {gap.reason}."
        )

    return LineageExplanation(summary=summary, detail_lines=detail_lines)


# ---------------------------------------------------------------------------
# Lineage summary builder
# ---------------------------------------------------------------------------

def _build_summary(assembler: LineageAssembler) -> LineageSummary:
    node_types = [n.node_type for n in assembler.nodes]
    # Distinct sources from observation nodes
    source_types: Set[str] = set()
    for n in assembler.nodes:
        if n.node_type == LineageNodeType.OBSERVATION:
            st = n.metadata.get("source_type")
            if st:
                source_types.add(st)

    dims: List[str] = []
    for n in assembler.nodes:
        if n.node_type == LineageNodeType.INTEGRITY_SNAPSHOT:
            dims = n.metadata.get("dimensions", [])
            break

    return LineageSummary(
        fact_count=node_types.count(LineageNodeType.FACT),
        observation_count=node_types.count(LineageNodeType.OBSERVATION),
        source_count=len(source_types),
        conflict_count=node_types.count(LineageNodeType.CONFLICT),
        claim_count=node_types.count(LineageNodeType.CLAIM),
        dimension_count=len(dims),
        affected_dimensions=dims,
        has_integrity_trace=LineageNodeType.INTEGRITY_TRACE in node_types,
        has_state_changes=LineageNodeType.STATE_CHANGE in node_types,
    )


# ---------------------------------------------------------------------------
# Main public entry points
# ---------------------------------------------------------------------------

def build_payment_lineage(
    db: Session,
    payment_id: str,
    as_of: Optional[datetime] = None,
    max_nodes: int = LINEAGE_MAX_NODES_DEFAULT,
    max_depth: int = LINEAGE_MAX_DEPTH_DEFAULT,
) -> PaymentLineageResponse:
    """
    Build forward lineage for a payment: from provider events to integrity trace.

    Uses FK-backed traversal wherever possible.
    Documents gaps where no FK exists.
    Excludes future evidence when as_of is specified.
    """
    now = _now_utc()
    assembler = LineageAssembler(max_nodes=min(max_nodes, LINEAGE_MAX_NODES_HARD_LIMIT))

    # 1. Load Payment
    payment = db.execute(
        select(Payment).where(Payment.razorpay_payment_id == payment_id)
    ).scalar_one_or_none()

    if payment:
        p_node = _payment_node(payment)
        assembler.add_node(p_node)

    # 2. Load all observations (batch)
    observations = _load_observations_for_payment(db, payment_id, as_of)
    obs_ids = [o.internal_id for o in observations]
    obs_map: Dict[int, EvidenceObservation] = {o.internal_id: o for o in observations}

    for obs in observations:
        if not assembler.add_node(_observation_node(obs)):
            break

    # 3. Load WebhookEvents for observations (batch via FK)
    webhook_ids = [o.webhook_event_id for o in observations if o.webhook_event_id is not None]
    webhook_map = _load_webhook_events_for_ids(db, list(set(webhook_ids)))

    for we in webhook_map.values():
        assembler.add_node(_webhook_node(we))

    # 4. Load PaymentEvents for webhooks (batch via FK)
    payment_event_map = _load_payment_events_for_webhook_ids(db, list(webhook_map.keys()))
    for pe in payment_event_map.values():
        assembler.add_node(_payment_event_node(pe))

    # 5. Load ObservationFactLinks → EvidenceFacts (batch)
    fact_links_by_obs = _load_fact_links_for_obs(db, obs_ids)
    all_fact_ids = list({
        link.fact_id
        for links in fact_links_by_obs.values()
        for link in links
    })
    facts_map = _load_facts_for_ids(db, all_fact_ids)

    for fact in facts_map.values():
        assembler.add_node(_fact_node(fact))

    # 6. Load EvidenceClaimLinks → Claims (batch)
    claim_links_by_obs = _load_claim_links_for_obs(db, obs_ids)
    all_claim_ids = list({
        link.claim_id
        for links in claim_links_by_obs.values()
        for link in links
    })
    claims_map = _load_claims_for_ids(db, all_claim_ids)

    for claim in claims_map.values():
        assembler.add_node(_claim_node(claim))

    # 7. Load Corroborations (batch via claim FK)
    corroborations = _load_corroborations_for_claims(db, all_claim_ids)
    for corr in corroborations.values():
        assembler.add_node(_corroboration_node(corr))

    # 8. Load Conflicts (batch — conflicts reference claims)
    conflicts = _load_conflicts_for_claims(db, all_claim_ids)
    for conflict in conflicts:
        assembler.add_node(_conflict_node(conflict))

    # 9. Load Quality Snapshots (batch)
    quality_map = _load_quality_snapshots_for_obs(db, obs_ids, as_of)
    for qs in quality_map.values():
        assembler.add_node(_quality_node(qs))

    # 10. Load Integrity Snapshot (temporal query — documented DERIVED_TEMPORAL gap)
    integrity_snapshot = _load_integrity_snapshot(db, payment_id, as_of)
    if integrity_snapshot:
        assembler.add_node(_integrity_snapshot_node(integrity_snapshot))

        # 11. Load Integrity Trace (FK: integrity_snapshot_internal_id)
        trace = _load_trace_for_snapshot(db, integrity_snapshot.internal_id)
        if trace:
            assembler.add_node(_trace_node(trace))
        else:
            assembler.add_gap(LineageGap(
                location="IntegritySnapshot → IntegrityTrace",
                expected_edge_type=LineageEdgeType.EVALUATED_BY,
                reason="No COMPLETED EvidenceIntegrityTrace found for this integrity snapshot.",
                detected_at=now,
            ))
    else:
        assembler.add_gap(LineageGap(
            location=f"Payment {payment_id} → IntegritySnapshot",
            expected_edge_type=LineageEdgeType.CONTRIBUTES_TO,
            reason="No EvidenceIntegritySnapshot exists for this payment at/before the requested time.",
            detected_at=now,
        ))

    # 12. Load State Snapshots and Changes (Phase 11)
    state_snapshots = _load_state_snapshots(db, payment_id, as_of)
    ss_ids = [ss.internal_id for ss in state_snapshots]
    for ss in state_snapshots:
        assembler.add_node(_state_snapshot_node(ss))

    state_changes = _load_state_changes_for_snapshots(db, ss_ids)
    for sc in state_changes:
        assembler.add_node(_state_change_node(sc))

    # 13. Load Reconciliation records (Phase 13)
    reconciliations = _load_reconciliations_for_obs(db, obs_ids)
    for rec in reconciliations:
        assembler.add_node(_reconciliation_node(rec))

    # -----------------------------------------------------------------------
    # Build edges
    # -----------------------------------------------------------------------
    _build_forward_edges(
        assembler=assembler,
        payment=payment,
        observations=observations,
        webhook_map=webhook_map,
        payment_event_map=payment_event_map,
        fact_links_by_obs=fact_links_by_obs,
        facts_map=facts_map,
        claim_links_by_obs=claim_links_by_obs,
        claims_map=claims_map,
        corroborations=corroborations,
        conflicts=conflicts,
        quality_map=quality_map,
        integrity_snapshot=integrity_snapshot,
        state_snapshots=state_snapshots,
        state_changes=state_changes,
        reconciliations=reconciliations,
        now=now,
    )

    # -----------------------------------------------------------------------
    # Completeness & explanation
    # -----------------------------------------------------------------------
    node_types = [n.node_type for n in assembler.nodes]
    completeness = _compute_completeness(
        assembler,
        has_observations=bool(observations),
        has_facts=bool(all_fact_ids),
        has_claims=bool(all_claim_ids),
        has_integrity=integrity_snapshot is not None,
        has_trace=LineageNodeType.INTEGRITY_TRACE in node_types,
    )

    explanation = _build_explanation(payment_id, assembler, integrity_snapshot, as_of)
    summary = _build_summary(assembler)

    return PaymentLineageResponse(
        payment_id=payment_id,
        nodes=assembler.nodes,
        edges=assembler.edges,
        gaps=assembler.gaps,
        completeness=completeness,
        summary=summary,
        explanation=explanation,
        evaluation_context=EvaluationContext(
            as_of=as_of,
            methodology_version=LINEAGE_METHODOLOGY_VERSION,
            truncated=assembler.truncated,
            node_count=len(assembler.nodes),
            edge_count=len(assembler.edges),
            gap_count=len(assembler.gaps),
        ),
    )


def _build_forward_edges(
    assembler: LineageAssembler,
    payment: Optional[Payment],
    observations: List[EvidenceObservation],
    webhook_map: Dict[int, WebhookEvent],
    payment_event_map: Dict[int, PaymentEvent],
    fact_links_by_obs: Dict[int, List[ObservationFactLink]],
    facts_map: Dict[int, EvidenceFact],
    claim_links_by_obs: Dict[int, List[EvidenceClaimLink]],
    claims_map: Dict[int, Claim],
    corroborations: Dict[int, EvidenceCorroboration],
    conflicts: List[EvidenceConflict],
    quality_map: Dict[int, EvidenceQualitySnapshot],
    integrity_snapshot: Optional[EvidenceIntegritySnapshot],
    state_snapshots: List[EvidenceStateSnapshot],
    state_changes: List[EvidenceStateChange],
    reconciliations: List[EvidenceReconciliation],
    now: datetime,
) -> None:
    """Build all edges using only authenticated relationships."""

    # WebhookEvent → PaymentEvent (FK: payment_events.webhook_event_id)
    for wid, pe in payment_event_map.items():
        we_nid = _node_id(LineageNodeType.WEBHOOK_EVENT, wid)
        pe_nid = _node_id(LineageNodeType.PAYMENT_EVENT, pe.internal_id)
        if assembler.has_node(we_nid) and assembler.has_node(pe_nid):
            assembler.add_edge(LineageEdge(
                source_node_id=we_nid,
                target_node_id=pe_nid,
                edge_type=LineageEdgeType.TRIGGERED,
                causal_role=CausalRole.DIRECT_CAUSE,
                linkage_type=LinkageType.FOREIGN_KEY,
                explanation=f"PaymentEvent #{pe.internal_id} was created from WebhookEvent #{wid} (FK: payment_events.webhook_event_id).",
            ))

    # WebhookEvent → Observation (FK: evidence_observations.webhook_event_id)
    for obs in observations:
        obs_nid = _node_id(LineageNodeType.OBSERVATION, obs.internal_id)
        if obs.webhook_event_id and obs.webhook_event_id in webhook_map:
            we_nid = _node_id(LineageNodeType.WEBHOOK_EVENT, obs.webhook_event_id)
            if assembler.has_node(we_nid) and assembler.has_node(obs_nid):
                assembler.add_edge(LineageEdge(
                    source_node_id=we_nid,
                    target_node_id=obs_nid,
                    edge_type=LineageEdgeType.PRODUCED,
                    causal_role=CausalRole.DIRECT_CAUSE,
                    linkage_type=LinkageType.FOREIGN_KEY,
                    explanation=f"Observation #{obs.internal_id} was extracted from WebhookEvent #{obs.webhook_event_id} (FK: evidence_observations.webhook_event_id).",
                ))

        # Observation → Fact (via ObservationFactLink FK)
        for link in fact_links_by_obs.get(obs.internal_id, []):
            fact = facts_map.get(link.fact_id)
            if not fact:
                continue
            fact_nid = _node_id(LineageNodeType.FACT, fact.internal_id)
            if assembler.has_node(obs_nid) and assembler.has_node(fact_nid):
                assembler.add_edge(LineageEdge(
                    source_node_id=obs_nid,
                    target_node_id=fact_nid,
                    edge_type=LineageEdgeType.REPRESENTS,
                    causal_role=CausalRole.DERIVED_FROM,
                    linkage_type=LinkageType.FOREIGN_KEY,
                    explanation=f"Observation #{obs.internal_id} is linked to Fact #{fact.internal_id} via ObservationFactLink (observation_fact_links.observation_id FK).",
                ))

        # Observation → Claim (via EvidenceClaimLink FK)
        for link in claim_links_by_obs.get(obs.internal_id, []):
            claim = claims_map.get(link.claim_id)
            if not claim:
                continue
            claim_nid = _node_id(LineageNodeType.CLAIM, claim.internal_id)
            if assembler.has_node(obs_nid) and assembler.has_node(claim_nid):
                assembler.add_edge(LineageEdge(
                    source_node_id=obs_nid,
                    target_node_id=claim_nid,
                    edge_type=LineageEdgeType.SUPPORTS,
                    causal_role=CausalRole.CONTRIBUTING_INPUT,
                    linkage_type=LinkageType.FOREIGN_KEY,
                    explanation=f"Observation #{obs.internal_id} supports Claim #{claim.internal_id} via EvidenceClaimLink (evidence_claim_links.evidence_id FK).",
                ))

        # Observation → QualitySnapshot (FK: evidence_quality_snapshots.evidence_id)
        qs = quality_map.get(obs.internal_id)
        if qs:
            qs_nid = _node_id(LineageNodeType.QUALITY_SNAPSHOT, qs.internal_id)
            if assembler.has_node(obs_nid) and assembler.has_node(qs_nid):
                assembler.add_edge(LineageEdge(
                    source_node_id=obs_nid,
                    target_node_id=qs_nid,
                    edge_type=LineageEdgeType.MEASURED_BY,
                    causal_role=CausalRole.CONTEXT,
                    linkage_type=LinkageType.FOREIGN_KEY,
                    explanation=f"Observation #{obs.internal_id} was quality-measured in QualitySnapshot #{qs.internal_id}.",
                ))

    # Claim → Corroboration (FK: evidence_corroborations.claim_id)
    for claim_id, corr in corroborations.items():
        claim_nid = _node_id(LineageNodeType.CLAIM, claim_id)
        corr_nid = _node_id(LineageNodeType.CORROBORATION, corr.internal_id)
        if assembler.has_node(claim_nid) and assembler.has_node(corr_nid):
            assembler.add_edge(LineageEdge(
                source_node_id=claim_nid,
                target_node_id=corr_nid,
                edge_type=LineageEdgeType.CORROBORATED_BY,
                causal_role=CausalRole.CORROBORATION_INPUT,
                linkage_type=LinkageType.FOREIGN_KEY,
                explanation=f"Claim #{claim_id} has corroboration analysis #{corr.internal_id} (evidence_corroborations.claim_id FK).",
            ))

    # Claim ← EvidenceConflict (FK: evidence_conflicts.claim_a_id / claim_b_id)
    for conflict in conflicts:
        conflict_nid = _node_id(LineageNodeType.CONFLICT, conflict.internal_id)
        if not assembler.has_node(conflict_nid):
            continue
        for claim_id_attr in [conflict.claim_a_id, conflict.claim_b_id]:
            claim_nid = _node_id(LineageNodeType.CLAIM, claim_id_attr)
            if assembler.has_node(claim_nid):
                assembler.add_edge(LineageEdge(
                    source_node_id=claim_nid,
                    target_node_id=conflict_nid,
                    edge_type=LineageEdgeType.CONFLICTED_BY,
                    causal_role=CausalRole.CONFLICT_INPUT,
                    linkage_type=LinkageType.FOREIGN_KEY,
                    explanation=f"Claim #{claim_id_attr} is involved in Conflict #{conflict.internal_id} (evidence_conflicts.claim_a/b_id FK).",
                ))

    # EvidenceIntegritySnapshot → IntegrityTrace (FK)
    if integrity_snapshot:
        snap_nid = _node_id(LineageNodeType.INTEGRITY_SNAPSHOT, integrity_snapshot.internal_id)
        # Find trace node
        for n in assembler.nodes:
            if n.node_type == LineageNodeType.INTEGRITY_TRACE:
                if assembler.has_node(snap_nid):
                    assembler.add_edge(LineageEdge(
                        source_node_id=snap_nid,
                        target_node_id=n.node_id,
                        edge_type=LineageEdgeType.EVALUATED_BY,
                        causal_role=CausalRole.CONTRIBUTING_INPUT,
                        linkage_type=LinkageType.FOREIGN_KEY,
                        explanation=f"IntegritySnapshot #{integrity_snapshot.internal_id} is referenced by trace {n.entity_id[:8]}… (evidence_integrity_traces.integrity_snapshot_internal_id FK).",
                    ))

    # EvidenceStateSnapshot → EvidenceIntegritySnapshot (FK: integrity_snapshot_id)
    for ss in state_snapshots:
        ss_nid = _node_id(LineageNodeType.STATE_SNAPSHOT, ss.internal_id)
        snap_nid = _node_id(LineageNodeType.INTEGRITY_SNAPSHOT, ss.integrity_snapshot_id)
        if assembler.has_node(ss_nid) and assembler.has_node(snap_nid):
            assembler.add_edge(LineageEdge(
                source_node_id=ss_nid,
                target_node_id=snap_nid,
                edge_type=LineageEdgeType.MIRRORS,
                causal_role=CausalRole.DERIVED_FROM,
                linkage_type=LinkageType.FOREIGN_KEY,
                explanation=f"StateSnapshot #{ss.internal_id} mirrors IntegritySnapshot #{ss.integrity_snapshot_id} (evidence_state_snapshots.integrity_snapshot_id FK).",
            ))

    # EvidenceStateChange → previous + current snapshots (FK)
    for sc in state_changes:
        sc_nid = _node_id(LineageNodeType.STATE_CHANGE, sc.change_id)
        if not assembler.has_node(sc_nid):
            continue
        prev_nid = _node_id(LineageNodeType.STATE_SNAPSHOT, sc.previous_snapshot_id)
        curr_nid = _node_id(LineageNodeType.STATE_SNAPSHOT, sc.current_snapshot_id)
        if assembler.has_node(prev_nid) and assembler.has_node(curr_nid):
            assembler.add_edge(LineageEdge(
                source_node_id=prev_nid,
                target_node_id=sc_nid,
                edge_type=LineageEdgeType.STATE_TRANSITION,
                causal_role=CausalRole.CONTRIBUTING_INPUT,
                linkage_type=LinkageType.FOREIGN_KEY,
                explanation=f"StateChange {sc.change_id[:8]}… detected between snapshots #{sc.previous_snapshot_id} and #{sc.current_snapshot_id}.",
            ))
            assembler.add_edge(LineageEdge(
                source_node_id=sc_nid,
                target_node_id=curr_nid,
                edge_type=LineageEdgeType.STATE_TRANSITION,
                causal_role=CausalRole.DIRECT_CAUSE if sc.causality == "DIRECT" else CausalRole.CONTRIBUTING_INPUT,
                linkage_type=LinkageType.FOREIGN_KEY,
                explanation=f"StateChange {sc.change_id[:8]}… led to StateSnapshot #{sc.current_snapshot_id}.",
            ))

        # StateChange → linked observation (FK: linked_evidence_id) if DIRECT
        if sc.linked_evidence_id:
            obs_nid = _node_id(LineageNodeType.OBSERVATION, sc.linked_evidence_id)
            if assembler.has_node(obs_nid):
                assembler.add_edge(LineageEdge(
                    source_node_id=obs_nid,
                    target_node_id=sc_nid,
                    edge_type=LineageEdgeType.CAUSED_STATE_CHANGE,
                    causal_role=CausalRole.DIRECT_CAUSE,
                    linkage_type=LinkageType.FOREIGN_KEY,
                    explanation=f"Observation #{sc.linked_evidence_id} directly caused StateChange {sc.change_id[:8]}… (evidence_state_changes.linked_evidence_id FK).",
                ))

    # Reconciliation → Fact (FK: evidence_reconciliations.fact_id when SAME_FACT)
    for rec in reconciliations:
        rec_nid = _node_id(LineageNodeType.RECONCILIATION, rec.internal_id)
        if not assembler.has_node(rec_nid):
            continue
        if rec.result == ReconciliationResult.SAME_FACT and rec.fact_id:
            fact_nid = _node_id(LineageNodeType.FACT, rec.fact_id)
            if assembler.has_node(fact_nid):
                assembler.add_edge(LineageEdge(
                    source_node_id=rec_nid,
                    target_node_id=fact_nid,
                    edge_type=LineageEdgeType.RECONCILED_INTO,
                    causal_role=CausalRole.DERIVED_FROM,
                    linkage_type=LinkageType.FOREIGN_KEY,
                    explanation=f"Reconciliation #{rec.internal_id} (rule: {rec.rule_id}) resolved observations into Fact #{rec.fact_id}.",
                ))


# ---------------------------------------------------------------------------
# Trace lineage (reverse direction)
# ---------------------------------------------------------------------------

def build_trace_lineage(
    db: Session,
    trace_id: str,
    max_nodes: int = LINEAGE_MAX_NODES_DEFAULT,
) -> TraceLineageResponse:
    """
    Reverse lineage: starting from an IntegrityTrace, walk backward to provider events.
    """
    now = _now_utc()
    assembler = LineageAssembler(max_nodes=min(max_nodes, LINEAGE_MAX_NODES_HARD_LIMIT))

    # 1. Load trace
    trace = db.execute(
        select(EvidenceIntegrityTrace).where(
            EvidenceIntegrityTrace.trace_id == trace_id
        )
    ).scalar_one_or_none()

    if trace is None:
        return TraceLineageResponse(
            trace_id=trace_id,
            payment_id="",
            nodes=[],
            edges=[],
            gaps=[LineageGap(
                location="TraceLineage entry point",
                expected_edge_type=LineageEdgeType.EVALUATED_BY,
                reason=f"EvidenceIntegrityTrace with trace_id={trace_id} not found.",
                detected_at=now,
            )],
            completeness=LineageCompleteness.BROKEN,
            summary=LineageSummary(),
            explanation=LineageExplanation(
                summary=f"Trace {trace_id} not found.",
                detail_lines=[],
            ),
            evaluation_context=EvaluationContext(
                methodology_version=LINEAGE_METHODOLOGY_VERSION,
                truncated=False,
                node_count=0,
                edge_count=0,
                gap_count=1,
            ),
        )

    payment_id = trace.payment_id
    as_of = trace.evaluated_at
    assembler.add_node(_trace_node(trace))

    # 2. Load IntegritySnapshot (FK from trace)
    integrity_snapshot: Optional[EvidenceIntegritySnapshot] = None
    if trace.integrity_snapshot_internal_id:
        integrity_snapshot = db.execute(
            select(EvidenceIntegritySnapshot).where(
                EvidenceIntegritySnapshot.internal_id == trace.integrity_snapshot_internal_id
            )
        ).scalar_one_or_none()

    if integrity_snapshot:
        assembler.add_node(_integrity_snapshot_node(integrity_snapshot))
        snap_nid = _node_id(LineageNodeType.INTEGRITY_SNAPSHOT, integrity_snapshot.internal_id)
        trace_nid = _node_id(LineageNodeType.INTEGRITY_TRACE, trace.trace_id)
        assembler.add_edge(LineageEdge(
            source_node_id=snap_nid,
            target_node_id=trace_nid,
            edge_type=LineageEdgeType.EVALUATED_BY,
            causal_role=CausalRole.CONTRIBUTING_INPUT,
            linkage_type=LinkageType.FOREIGN_KEY,
            explanation=f"IntegrityTrace {trace_id[:8]}… evaluated snapshot #{integrity_snapshot.internal_id}.",
        ))

    # 3. Now build the rest using the forward payment lineage helper
    observations = _load_observations_for_payment(db, payment_id, as_of)
    obs_ids = [o.internal_id for o in observations]
    obs_map = {o.internal_id: o for o in observations}

    for obs in observations:
        assembler.add_node(_observation_node(obs))

    webhook_ids = [o.webhook_event_id for o in observations if o.webhook_event_id]
    webhook_map = _load_webhook_events_for_ids(db, list(set(webhook_ids)))
    for we in webhook_map.values():
        assembler.add_node(_webhook_node(we))

    payment_event_map = _load_payment_events_for_webhook_ids(db, list(webhook_map.keys()))
    for pe in payment_event_map.values():
        assembler.add_node(_payment_event_node(pe))

    fact_links_by_obs = _load_fact_links_for_obs(db, obs_ids)
    all_fact_ids = list({l.fact_id for ls in fact_links_by_obs.values() for l in ls})
    facts_map = _load_facts_for_ids(db, all_fact_ids)
    for fact in facts_map.values():
        assembler.add_node(_fact_node(fact))

    claim_links_by_obs = _load_claim_links_for_obs(db, obs_ids)
    all_claim_ids = list({l.claim_id for ls in claim_links_by_obs.values() for l in ls})
    claims_map = _load_claims_for_ids(db, all_claim_ids)
    for claim in claims_map.values():
        assembler.add_node(_claim_node(claim))

    corroborations = _load_corroborations_for_claims(db, all_claim_ids)
    for corr in corroborations.values():
        assembler.add_node(_corroboration_node(corr))

    conflicts = _load_conflicts_for_claims(db, all_claim_ids)
    for conflict in conflicts:
        assembler.add_node(_conflict_node(conflict))

    quality_map = _load_quality_snapshots_for_obs(db, obs_ids, as_of)
    for qs in quality_map.values():
        assembler.add_node(_quality_node(qs))

    state_snapshots = _load_state_snapshots(db, payment_id, as_of)
    ss_ids = [ss.internal_id for ss in state_snapshots]
    for ss in state_snapshots:
        assembler.add_node(_state_snapshot_node(ss))

    state_changes = _load_state_changes_for_snapshots(db, ss_ids)
    for sc in state_changes:
        assembler.add_node(_state_change_node(sc))

    reconciliations = _load_reconciliations_for_obs(db, obs_ids)
    for rec in reconciliations:
        assembler.add_node(_reconciliation_node(rec))

    _build_forward_edges(
        assembler=assembler,
        payment=None,
        observations=observations,
        webhook_map=webhook_map,
        payment_event_map=payment_event_map,
        fact_links_by_obs=fact_links_by_obs,
        facts_map=facts_map,
        claim_links_by_obs=claim_links_by_obs,
        claims_map=claims_map,
        corroborations=corroborations,
        conflicts=conflicts,
        quality_map=quality_map,
        integrity_snapshot=integrity_snapshot,
        state_snapshots=state_snapshots,
        state_changes=state_changes,
        reconciliations=reconciliations,
        now=now,
    )

    node_types = [n.node_type for n in assembler.nodes]
    completeness = _compute_completeness(
        assembler,
        has_observations=bool(observations),
        has_facts=bool(all_fact_ids),
        has_claims=bool(all_claim_ids),
        has_integrity=integrity_snapshot is not None,
        has_trace=True,
    )

    explanation = _build_explanation(payment_id, assembler, integrity_snapshot, as_of)
    summary = _build_summary(assembler)

    return TraceLineageResponse(
        trace_id=trace_id,
        payment_id=payment_id,
        nodes=assembler.nodes,
        edges=assembler.edges,
        gaps=assembler.gaps,
        completeness=completeness,
        summary=summary,
        explanation=explanation,
        evaluation_context=EvaluationContext(
            as_of=as_of,
            methodology_version=LINEAGE_METHODOLOGY_VERSION,
            truncated=assembler.truncated,
            node_count=len(assembler.nodes),
            edge_count=len(assembler.edges),
            gap_count=len(assembler.gaps),
        ),
    )


# ---------------------------------------------------------------------------
# Fact lineage
# ---------------------------------------------------------------------------

def build_fact_lineage(
    db: Session,
    fact_id: int,
    as_of: Optional[datetime] = None,
) -> FactLineageResponse:
    """
    Lineage centered on a single EvidenceFact:
    Observations → Fact → Claims → IntegritySnapshot (if found).
    """
    now = _now_utc()
    assembler = LineageAssembler()

    fact = db.execute(
        select(EvidenceFact).where(EvidenceFact.internal_id == fact_id)
    ).scalar_one_or_none()

    if fact is None:
        return FactLineageResponse(
            fact_id=fact_id,
            payment_id="",
            nodes=[],
            edges=[],
            gaps=[LineageGap(
                location="Fact entry point",
                expected_edge_type=LineageEdgeType.REPRESENTS,
                reason=f"EvidenceFact #{fact_id} not found.",
                detected_at=now,
            )],
            completeness=LineageCompleteness.BROKEN,
            summary=LineageSummary(),
            explanation=LineageExplanation(
                summary=f"Fact #{fact_id} not found.",
                detail_lines=[],
            ),
            evaluation_context=EvaluationContext(
                methodology_version=LINEAGE_METHODOLOGY_VERSION,
                gap_count=1,
            ),
        )

    payment_id = fact.payment_id
    assembler.add_node(_fact_node(fact))

    # Observations via ObservationFactLink (FK)
    links = db.execute(
        select(ObservationFactLink).where(ObservationFactLink.fact_id == fact_id)
    ).scalars().all()
    obs_ids = [l.observation_id for l in links]

    q = select(EvidenceObservation).where(EvidenceObservation.internal_id.in_(obs_ids))
    if as_of is not None:
        q = q.where(EvidenceObservation.observed_at <= as_of)
    observations = db.execute(q).scalars().all()

    for obs in observations:
        assembler.add_node(_observation_node(obs))

    obs_id_set = [o.internal_id for o in observations]

    # WebhookEvents
    webhook_ids = [o.webhook_event_id for o in observations if o.webhook_event_id]
    webhook_map = _load_webhook_events_for_ids(db, list(set(webhook_ids)))
    for we in webhook_map.values():
        assembler.add_node(_webhook_node(we))

    # Claims (via EvidenceClaimLink on observations)
    claim_links_by_obs = _load_claim_links_for_obs(db, obs_id_set)
    all_claim_ids = list({l.claim_id for ls in claim_links_by_obs.values() for l in ls})
    claims_map = _load_claims_for_ids(db, all_claim_ids)
    for claim in claims_map.values():
        assembler.add_node(_claim_node(claim))

    # Integrity snapshot
    integrity_snapshot = _load_integrity_snapshot(db, payment_id, as_of)
    if integrity_snapshot:
        assembler.add_node(_integrity_snapshot_node(integrity_snapshot))

    # Reconciliations for these observations
    reconciliations = _load_reconciliations_for_obs(db, obs_id_set)
    for rec in reconciliations:
        assembler.add_node(_reconciliation_node(rec))

    # Edges
    fact_nid = _node_id(LineageNodeType.FACT, fact.internal_id)
    for obs in observations:
        obs_nid = _node_id(LineageNodeType.OBSERVATION, obs.internal_id)
        assembler.add_edge(LineageEdge(
            source_node_id=obs_nid,
            target_node_id=fact_nid,
            edge_type=LineageEdgeType.REPRESENTS,
            causal_role=CausalRole.DERIVED_FROM,
            linkage_type=LinkageType.FOREIGN_KEY,
            explanation=f"Observation #{obs.internal_id} linked to Fact #{fact_id} via ObservationFactLink.",
        ))
        if obs.webhook_event_id and obs.webhook_event_id in webhook_map:
            we_nid = _node_id(LineageNodeType.WEBHOOK_EVENT, obs.webhook_event_id)
            assembler.add_edge(LineageEdge(
                source_node_id=we_nid,
                target_node_id=obs_nid,
                edge_type=LineageEdgeType.PRODUCED,
                causal_role=CausalRole.DIRECT_CAUSE,
                linkage_type=LinkageType.FOREIGN_KEY,
                explanation=f"Observation #{obs.internal_id} extracted from WebhookEvent #{obs.webhook_event_id}.",
            ))
        for link in claim_links_by_obs.get(obs.internal_id, []):
            claim = claims_map.get(link.claim_id)
            if not claim:
                continue
            claim_nid = _node_id(LineageNodeType.CLAIM, claim.internal_id)
            assembler.add_edge(LineageEdge(
                source_node_id=obs_nid,
                target_node_id=claim_nid,
                edge_type=LineageEdgeType.SUPPORTS,
                causal_role=CausalRole.CONTRIBUTING_INPUT,
                linkage_type=LinkageType.FOREIGN_KEY,
                explanation=f"Observation #{obs.internal_id} supports Claim #{claim.internal_id}.",
            ))

    if integrity_snapshot:
        snap_nid = _node_id(LineageNodeType.INTEGRITY_SNAPSHOT, integrity_snapshot.internal_id)
        for claim in claims_map.values():
            claim_nid = _node_id(LineageNodeType.CLAIM, claim.internal_id)
            if assembler.has_node(claim_nid) and assembler.has_node(snap_nid):
                assembler.add_edge(LineageEdge(
                    source_node_id=claim_nid,
                    target_node_id=snap_nid,
                    edge_type=LineageEdgeType.CONTRIBUTES_TO,
                    causal_role=CausalRole.CONTRIBUTING_INPUT,
                    linkage_type=LinkageType.DERIVED_TEMPORAL,
                    explanation=f"Claim #{claim.internal_id} contributes to IntegritySnapshot #{integrity_snapshot.internal_id} (derived via payment_id match — no direct FK).",
                ))

    for rec in reconciliations:
        rec_nid = _node_id(LineageNodeType.RECONCILIATION, rec.internal_id)
        if rec.result == ReconciliationResult.SAME_FACT and rec.fact_id == fact_id:
            assembler.add_edge(LineageEdge(
                source_node_id=rec_nid,
                target_node_id=fact_nid,
                edge_type=LineageEdgeType.RECONCILED_INTO,
                causal_role=CausalRole.DERIVED_FROM,
                linkage_type=LinkageType.FOREIGN_KEY,
                explanation=f"Reconciliation #{rec.internal_id} (rule: {rec.rule_id}) merged observations into Fact #{fact_id}.",
            ))

    node_types = [n.node_type for n in assembler.nodes]
    completeness = _compute_completeness(
        assembler,
        has_observations=bool(observations),
        has_facts=True,
        has_claims=bool(all_claim_ids),
        has_integrity=integrity_snapshot is not None,
        has_trace=False,
    )
    if completeness == LineageCompleteness.COMPLETE and not assembler.has_node(
        _node_id(LineageNodeType.INTEGRITY_TRACE, "")
    ):
        completeness = LineageCompleteness.PARTIAL

    explanation = _build_explanation(payment_id, assembler, integrity_snapshot, as_of)
    summary = _build_summary(assembler)

    return FactLineageResponse(
        fact_id=fact_id,
        payment_id=payment_id,
        nodes=assembler.nodes,
        edges=assembler.edges,
        gaps=assembler.gaps,
        completeness=completeness,
        summary=summary,
        explanation=explanation,
        evaluation_context=EvaluationContext(
            as_of=as_of,
            methodology_version=LINEAGE_METHODOLOGY_VERSION,
            truncated=assembler.truncated,
            node_count=len(assembler.nodes),
            edge_count=len(assembler.edges),
            gap_count=len(assembler.gaps),
        ),
    )


# ---------------------------------------------------------------------------
# Path search
# ---------------------------------------------------------------------------

def find_lineage_path(
    db: Session,
    source_type: str,
    source_id: str,
    target_type: str,
    target_id: str,
    max_depth: int = LINEAGE_MAX_DEPTH_DEFAULT,
    as_of: Optional[datetime] = None,
) -> LineagePathResponse:
    """
    BFS path search from a source entity to a target entity.
    Uses bounded traversal (max_depth). Returns found=False if unreachable.
    """
    max_depth = min(max_depth, LINEAGE_MAX_DEPTH_HARD_LIMIT)

    # We use the payment lineage as the search space when source is a payment
    # For other combinations, we extract from the relevant payment
    payment_id: Optional[str] = None

    if source_type == LineageNodeType.PAYMENT:
        payment_id = source_id
    elif target_type == LineageNodeType.PAYMENT:
        payment_id = target_id

    if not payment_id:
        # Try to resolve payment from trace
        if source_type == LineageNodeType.INTEGRITY_TRACE:
            trace = db.execute(
                select(EvidenceIntegrityTrace).where(
                    EvidenceIntegrityTrace.trace_id == source_id
                )
            ).scalar_one_or_none()
            if trace:
                payment_id = trace.payment_id
        elif target_type == LineageNodeType.INTEGRITY_TRACE:
            trace = db.execute(
                select(EvidenceIntegrityTrace).where(
                    EvidenceIntegrityTrace.trace_id == target_id
                )
            ).scalar_one_or_none()
            if trace:
                payment_id = trace.payment_id

    if not payment_id:
        return LineagePathResponse(
            found=False,
            source_type=source_type,
            source_id=source_id,
            target_type=target_type,
            target_id=target_id,
            path=[],
            edges=[],
            depth=0,
            truncated=False,
            explanation=f"Cannot resolve payment_id from {source_type}:{source_id} or {target_type}:{target_id}.",
        )

    # Build full payment lineage as the search space
    full_lineage = build_payment_lineage(db, payment_id, as_of=as_of, max_nodes=LINEAGE_MAX_NODES_HARD_LIMIT)

    # Build adjacency for BFS
    adjacency: Dict[str, List[Tuple[str, LineageEdge]]] = {}
    for edge in full_lineage.edges:
        adjacency.setdefault(edge.source_node_id, []).append((edge.target_node_id, edge))
        # Also allow backward traversal
        adjacency.setdefault(edge.target_node_id, []).append((edge.source_node_id, edge))

    nodes_by_id: Dict[str, LineageNode] = {n.node_id: n for n in full_lineage.nodes}

    # Source and target node_ids
    src_nid = _node_id(source_type, source_id)
    tgt_nid = _node_id(target_type, target_id)

    if src_nid not in nodes_by_id or tgt_nid not in nodes_by_id:
        return LineagePathResponse(
            found=False,
            source_type=source_type,
            source_id=source_id,
            target_type=target_type,
            target_id=target_id,
            path=[],
            edges=[],
            depth=0,
            truncated=full_lineage.evaluation_context.truncated,
            explanation=f"Source node {src_nid} or target node {tgt_nid} not found in payment lineage.",
        )

    # BFS
    from collections import deque
    queue: deque = deque([(src_nid, [src_nid], [])])
    visited: Set[str] = {src_nid}
    found_path: Optional[List[str]] = None
    found_edges: List[LineageEdge] = []
    truncated = False

    while queue:
        current, path, edges_so_far = queue.popleft()
        if len(path) > max_depth:
            truncated = True
            break
        if current == tgt_nid:
            found_path = path
            found_edges = edges_so_far
            break
        for neighbor, edge in adjacency.get(current, []):
            if neighbor not in visited:
                visited.add(neighbor)
                queue.append((neighbor, path + [neighbor], edges_so_far + [edge]))

    if found_path:
        path_nodes = [nodes_by_id[nid] for nid in found_path if nid in nodes_by_id]
        return LineagePathResponse(
            found=True,
            source_type=source_type,
            source_id=source_id,
            target_type=target_type,
            target_id=target_id,
            path=path_nodes,
            edges=found_edges,
            depth=len(found_path) - 1,
            truncated=truncated,
            explanation=f"Path found from {source_type}:{source_id} to {target_type}:{target_id} in {len(found_path) - 1} step(s).",
        )
    else:
        return LineagePathResponse(
            found=False,
            source_type=source_type,
            source_id=source_id,
            target_type=target_type,
            target_id=target_id,
            path=[],
            edges=[],
            depth=0,
            truncated=truncated,
            explanation=f"No path found from {source_type}:{source_id} to {target_type}:{target_id} within depth {max_depth}.",
        )
