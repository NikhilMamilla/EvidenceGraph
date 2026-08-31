"""
Phase 20 — Investigation Command Center Service.

Provides search, filtering, and guided investigation workflows for
operators exploring payment evidence across the platform.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import func, select, desc, or_, text
from sqlalchemy.orm import Session

from app.models.customer_reference import CustomerReference
from app.models.evidence import EvidenceObservation
from app.models.evidence_conflict import EvidenceConflict
from app.models.evidence_fact import EvidenceFact
from app.models.evidence_integrity import EvidenceIntegritySnapshot
from app.models.evidence_relationship import EvidenceRelationship
from app.models.evidence_structure import Claim, EvidenceClaimLink, EvidenceCorroboration
from app.models.evolution_models import EvidenceStateChange
from app.models.investigation_types import (
    HARD_MAX_EDGES,
    HARD_MAX_NODES,
    MAX_TRAVERSAL_DEPTH,
    TraversalStatus,
)
from app.models.order import Order
from app.models.payment import Payment
from app.models.payment_event import PaymentEvent
from app.models.webhook_event import WebhookEvent
from app.schemas.investigation import (
    InvestigationRecommendation,
    InvestigationRecommendationsResponse,
    InvestigationSearchResponse,
    InvestigationSearchResult,
    InvestigationTimelineEvent,
    InvestigationTimelineResponse,
    PaymentInvestigationProfile,
)

logger = logging.getLogger(__name__)

METHODOLOGY_VERSION = "1.0.0"


class InvestigationService:
    """Investigation Command Center — search, profile, timeline, recommendations."""

    @classmethod
    def search(cls, db: Session, query: str, limit: int = 20) -> InvestigationSearchResponse:
        """Full-text search across payments, evidence, conflicts, and facts."""
        start = time.time()
        results: List[InvestigationSearchResult] = []
        q = f"%{query}%"

        # Search Payments
        try:
            payments = db.execute(
                select(Payment).where(
                    or_(
                        Payment.razorpay_payment_id.ilike(q),
                        Payment.status.ilike(q),
                        Payment.payment_method_type.ilike(q),
                    )
                ).limit(limit)
            ).scalars().all()

            for p in payments:
                results.append(InvestigationSearchResult(
                    result_type="PAYMENT",
                    entity_id=p.razorpay_payment_id,
                    title=f"Payment {p.razorpay_payment_id}",
                    subtitle=f"Status: {p.status} | Amount: {p.amount_minor or 'Unknown'} {p.currency or ''}",
                    relevance_score=0.9,
                    payment_id=p.razorpay_payment_id,
                    timestamp=p.first_observed_at,
                ))
        except Exception as e:
            logger.warning("Payment search failed: %s", e)

        # Search Evidence
        try:
            evidence = db.execute(
                select(EvidenceObservation).where(
                    or_(
                        EvidenceObservation.evidence_type.ilike(q),
                        EvidenceObservation.value.ilike(q),
                        EvidenceObservation.subject_id.ilike(q),
                    )
                ).limit(limit)
            ).scalars().all()

            for ev in evidence:
                results.append(InvestigationSearchResult(
                    result_type="EVIDENCE",
                    entity_id=str(ev.internal_id),
                    title=f"Evidence #{ev.internal_id}: {ev.evidence_type}",
                    subtitle=f"Value: {ev.value} | Source: {ev.source_type}",
                    relevance_score=0.7,
                    payment_id=ev.subject_id if ev.subject_type == "payment" else None,
                    timestamp=ev.observed_at,
                ))
        except Exception as e:
            logger.warning("Evidence search failed: %s", e)

        # Search Conflicts
        try:
            conflicts = db.execute(
                select(EvidenceConflict).where(
                    or_(
                        EvidenceConflict.conflict_type.ilike(q),
                        EvidenceConflict.payment_id.ilike(q),
                        EvidenceConflict.severity.ilike(q),
                    )
                ).limit(limit)
            ).scalars().all()

            for c in conflicts:
                results.append(InvestigationSearchResult(
                    result_type="CONFLICT",
                    entity_id=str(c.internal_id),
                    title=f"Conflict #{c.internal_id}: {c.conflict_type}",
                    subtitle=f"Severity: {c.severity} | Status: {c.status}",
                    relevance_score=0.6,
                    payment_id=c.payment_id,
                    timestamp=c.detected_at,
                ))
        except Exception as e:
            logger.warning("Conflict search failed: %s", e)

        # Search Facts
        try:
            facts = db.execute(
                select(EvidenceFact).where(
                    or_(
                        EvidenceFact.fact_type.ilike(q),
                        EvidenceFact.canonical_value.ilike(q),
                        EvidenceFact.payment_id.ilike(q),
                    )
                ).limit(limit)
            ).scalars().all()

            for f in facts:
                results.append(InvestigationSearchResult(
                    result_type="FACT",
                    entity_id=str(f.internal_id),
                    title=f"Fact #{f.internal_id}: {f.fact_type}",
                    subtitle=f"Value: {f.canonical_value} | Status: {f.status}",
                    relevance_score=0.65,
                    payment_id=f.payment_id,
                    timestamp=f.first_observed_at,
                ))
        except Exception as e:
            logger.warning("Fact search failed: %s", e)

        # Sort by relevance
        results.sort(key=lambda r: r.relevance_score, reverse=True)
        results = results[:limit]

        elapsed_ms = (time.time() - start) * 1000

        # Generate suggestions
        suggestions = cls._generate_search_suggestions(db, query)

        return InvestigationSearchResponse(
            query=query,
            results=results,
            total_results=len(results),
            search_time_ms=round(elapsed_ms, 2),
            suggestions=suggestions,
        )

    @classmethod
    def get_payment_profile(
        cls, db: Session, payment_id: str
    ) -> Optional[PaymentInvestigationProfile]:
        """Build a comprehensive investigation profile for a payment."""
        now = datetime.now(timezone.utc)

        payment = db.execute(
            select(Payment).where(Payment.razorpay_payment_id == payment_id)
        ).scalar_one_or_none()

        if not payment:
            return None

        # Evidence summary
        total_evidence = db.execute(
            select(func.count(EvidenceObservation.internal_id)).where(
                EvidenceObservation.subject_id == payment_id
            )
        ).scalar() or 0

        distinct_sources = db.execute(
            select(func.count(func.distinct(EvidenceObservation.source_type))).where(
                EvidenceObservation.subject_id == payment_id
            )
        ).scalar() or 0

        distinct_events = db.execute(
            select(func.count(func.distinct(EvidenceObservation.payment_event_id))).where(
                EvidenceObservation.subject_id == payment_id,
                EvidenceObservation.payment_event_id.isnot(None),
            )
        ).scalar() or 0

        evidence_types_raw = db.execute(
            select(func.distinct(EvidenceObservation.evidence_type)).where(
                EvidenceObservation.subject_id == payment_id
            )
        ).scalars().all()
        evidence_types = [str(t) for t in evidence_types_raw]

        # Conflict summary
        total_conflicts = db.execute(
            select(func.count(EvidenceConflict.internal_id)).where(
                EvidenceConflict.payment_id == payment_id
            )
        ).scalar() or 0

        open_conflicts = db.execute(
            select(func.count(EvidenceConflict.internal_id)).where(
                EvidenceConflict.payment_id == payment_id,
                EvidenceConflict.status == "ACTIVE",
            )
        ).scalar() or 0

        # Coverage
        latest_cov = db.execute(
            select(EvidenceFact).where(
                EvidenceFact.payment_id == payment_id
            ).order_by(desc(EvidenceFact.last_observed_at)).limit(1)
        ).scalars().first()

        # Key facts
        facts = db.execute(
            select(EvidenceFact).where(
                EvidenceFact.payment_id == payment_id
            ).order_by(desc(EvidenceFact.observation_count)).limit(10)
        ).scalars().all()

        key_facts = []
        for f in facts:
            key_facts.append({
                "fact_type": f.fact_type,
                "canonical_value": f.canonical_value,
                "observation_count": f.observation_count,
                "source_count": f.distinct_source_count,
                "status": f.status,
            })

        # Timeline highlights
        recent_events = db.execute(
            select(PaymentEvent)
            .join(Payment, Payment.internal_id == PaymentEvent.payment_id)
            .where(Payment.razorpay_payment_id == payment_id)
            .order_by(desc(PaymentEvent.event_timestamp))
            .limit(10)
        ).scalars().all()

        timeline_highlights = []
        for ev in recent_events:
            timeline_highlights.append({
                "event_type": ev.event_type,
                "timestamp": ev.event_timestamp.isoformat() if ev.event_timestamp else None,
            })

        # Investigation steps
        investigation_steps = []
        anomaly_flags = []

        if total_evidence == 0:
            investigation_steps.append("No evidence observations — investigate extraction pipeline")
            anomaly_flags.append("ZERO_EVIDENCE")

        if open_conflicts > 0:
            investigation_steps.append(f"Resolve {open_conflicts} active evidence conflict(s)")
            anomaly_flags.append("ACTIVE_CONFLICTS")

        if distinct_sources < 2:
            investigation_steps.append("Single-source evidence — gather independent corroboration")
            anomaly_flags.append("SINGLE_SOURCE")

        if total_evidence > 0 and distinct_events == 0:
            investigation_steps.append("Evidence exists but no linked payment events — check lineage")
            anomaly_flags.append("ORPHANED_EVIDENCE")

        if not investigation_steps:
            investigation_steps.append("Evidence profile appears healthy — review key facts for details")

        return PaymentInvestigationProfile(
            payment_id=payment_id,
            payment_status=payment.status,
            amount_minor=payment.amount_minor,
            currency=payment.currency,
            total_evidence=total_evidence,
            distinct_sources=distinct_sources,
            distinct_events=distinct_events,
            evidence_types=evidence_types,
            risk_score=None,
            risk_level=None,
            total_conflicts=total_conflicts,
            open_conflicts=open_conflicts,
            coverage_status=None,
            key_facts=key_facts,
            timeline_highlights=timeline_highlights,
            investigation_steps=investigation_steps,
            anomaly_flags=anomaly_flags,
            evaluated_at=now,
            methodology_version=METHODOLOGY_VERSION,
        )

    @classmethod
    def get_investigation_timeline(
        cls, db: Session, payment_id: str
    ) -> Optional[InvestigationTimelineResponse]:
        """Build a unified chronological investigation timeline."""
        now = datetime.now(timezone.utc)
        events: List[InvestigationTimelineEvent] = []

        payment = db.execute(
            select(Payment).where(Payment.razorpay_payment_id == payment_id)
        ).scalar_one_or_none()

        if not payment:
            return None

        # Payment events
        payment_events = db.execute(
            select(PaymentEvent)
            .join(Payment, Payment.internal_id == PaymentEvent.payment_id)
            .where(Payment.razorpay_payment_id == payment_id)
            .order_by(PaymentEvent.event_timestamp)
        ).scalars().all()

        for pe in payment_events:
            events.append(InvestigationTimelineEvent(
                timestamp=pe.event_timestamp or now,
                event_type="PAYMENT_EVENT",
                category="EVIDENCE",
                severity="INFO",
                title=f"Payment Event: {pe.event_type}",
                description=f"Payment state transition recorded",
                entity_id=str(pe.internal_id),
                metadata={"event_type": pe.event_type},
            ))

        # Evidence observations
        observations = db.execute(
            select(EvidenceObservation).where(
                EvidenceObservation.subject_id == payment_id
            ).order_by(EvidenceObservation.observed_at)
        ).scalars().all()

        for obs in observations:
            events.append(InvestigationTimelineEvent(
                timestamp=obs.observed_at,
                event_type="EVIDENCE_OBSERVED",
                category="EVIDENCE",
                severity="INFO",
                title=f"Evidence: {obs.evidence_type}",
                description=f"Value: {obs.value} ({obs.value_type}) from {obs.source_type}",
                entity_id=str(obs.internal_id),
                metadata={"evidence_type": obs.evidence_type, "source": obs.source_type},
            ))

        # Conflicts
        conflicts = db.execute(
            select(EvidenceConflict).where(
                EvidenceConflict.payment_id == payment_id
            ).order_by(EvidenceConflict.detected_at)
        ).scalars().all()

        for c in conflicts:
            severity = "ALERT" if c.severity in ("HIGH", "CRITICAL") else "WARNING"
            events.append(InvestigationTimelineEvent(
                timestamp=c.detected_at or c.created_at or now,
                event_type="CONFLICT_DETECTED",
                category="CONFLICT",
                severity=severity,
                title=f"Conflict: {c.conflict_type}",
                description=f"Severity: {c.severity} | Status: {c.status}",
                entity_id=str(c.internal_id),
                metadata={"conflict_type": c.conflict_type, "status": c.status},
            ))

        # Facts
        facts = db.execute(
            select(EvidenceFact).where(
                EvidenceFact.payment_id == payment_id
            ).order_by(EvidenceFact.first_observed_at)
        ).scalars().all()

        for f in facts:
            events.append(InvestigationTimelineEvent(
                timestamp=f.first_observed_at or now,
                event_type="FACT_RECONCILED",
                category="EVIDENCE",
                severity="INFO",
                title=f"Fact: {f.fact_type}",
                description=f"Canonical value: {f.canonical_value} from {f.distinct_source_count} sources",
                entity_id=str(f.internal_id),
                metadata={"fact_type": f.fact_type, "status": f.status},
            ))

        # Sort chronologically
        events.sort(key=lambda e: e.timestamp)

        time_range_start = events[0].timestamp if events else None
        time_range_end = events[-1].timestamp if events else None

        return InvestigationTimelineResponse(
            payment_id=payment_id,
            events=events,
            total_events=len(events),
            time_range_start=time_range_start,
            time_range_end=time_range_end,
            methodology_version=METHODOLOGY_VERSION,
        )

    @classmethod
    def get_recommendations(
        cls, db: Session, payment_id: Optional[str] = None
    ) -> InvestigationRecommendationsResponse:
        """Generate actionable investigation recommendations."""
        now = datetime.now(timezone.utc)
        recommendations: List[InvestigationRecommendation] = []

        if payment_id:
            # Payment-specific recommendations
            profile = cls.get_payment_profile(db, payment_id)
            if profile:
                if profile.open_conflicts > 0:
                    recommendations.append(InvestigationRecommendation(
                        recommendation_id=f"REC-{payment_id}-CONFLICTS",
                        priority="HIGH",
                        category="CONFLICT_RESOLUTION",
                        title="Resolve Active Conflicts",
                        description=f"{profile.open_conflicts} active evidence conflicts need resolution",
                        payment_id=payment_id,
                        generated_at=now,
                        methodology_version=METHODOLOGY_VERSION,
                    ))

                if profile.distinct_sources < 2:
                    recommendations.append(InvestigationRecommendation(
                        recommendation_id=f"REC-{payment_id}-SOURCES",
                        priority="MEDIUM",
                        category="EVIDENCE_DIVERSITY",
                        title="Gather Additional Evidence Sources",
                        description="Payment has single-source evidence — cross-reference recommended",
                        payment_id=payment_id,
                        generated_at=now,
                        methodology_version=METHODOLOGY_VERSION,
                    ))

                if profile.total_evidence == 0:
                    recommendations.append(InvestigationRecommendation(
                        recommendation_id=f"REC-{payment_id}-MISSING",
                        priority="URGENT",
                        category="MISSING_EVIDENCE",
                        title="Investigate Missing Evidence",
                        description="No evidence observations found — extraction pipeline may be failing",
                        payment_id=payment_id,
                        generated_at=now,
                        methodology_version=METHODOLOGY_VERSION,
                    ))
        else:
            # System-wide recommendations
            total_payments = db.execute(select(func.count(Payment.internal_id))).scalar() or 0
            total_conflicts = db.execute(
                select(func.count(EvidenceConflict.internal_id)).where(
                    EvidenceConflict.status == "ACTIVE"
                )
            ).scalar() or 0

            if total_conflicts > 0:
                recommendations.append(InvestigationRecommendation(
                    recommendation_id="REC-SYS-CONFLICTS",
                    priority="HIGH",
                    category="SYSTEM_CONFLICTS",
                    title="System-Wide Conflict Resolution",
                    description=f"{total_conflicts} active conflicts across the platform need attention",
                    generated_at=now,
                    methodology_version=METHODOLOGY_VERSION,
                ))

            if total_payments == 0:
                recommendations.append(InvestigationRecommendation(
                    recommendation_id="REC-SYS-NO-DATA",
                    priority="MEDIUM",
                    category="DATA_INGESTION",
                    title="No Payment Data Available",
                    description="Platform has no payments — verify webhook ingestion pipeline",
                    generated_at=now,
                    methodology_version=METHODOLOGY_VERSION,
                ))

        if not recommendations:
            recommendations.append(InvestigationRecommendation(
                recommendation_id="REC-SYS-OK",
                priority="LOW",
                category="HEALTHY",
                title="System Operating Normally",
                description="No immediate investigation actions required",
                generated_at=now,
                methodology_version=METHODOLOGY_VERSION,
            ))

        return InvestigationRecommendationsResponse(
            recommendations=recommendations,
            total_count=len(recommendations),
            evaluated_at=now,
            methodology_version=METHODOLOGY_VERSION,
        )

    @classmethod
    def _generate_search_suggestions(cls, db: Session, query: str) -> list[str]:
        """Generate search suggestions based on available data patterns."""
        suggestions = []
        q = f"%{query[:3]}%"

        # Suggest payment IDs
        try:
            payment_ids = db.execute(
                select(Payment.razorpay_payment_id).where(
                    Payment.razorpay_payment_id.ilike(q)
                ).limit(3)
            ).scalars().all()
            for pid in payment_ids:
                suggestions.append(pid)
        except Exception:
            pass

        # Suggest evidence types
        try:
            ev_types = db.execute(
                select(func.distinct(EvidenceObservation.evidence_type)).where(
                    EvidenceObservation.evidence_type.ilike(q)
                ).limit(3)
            ).scalars().all()
            for et in ev_types:
                suggestions.append(et)
        except Exception:
            pass

        return suggestions[:5]


    # ═══════════════════════════════════════════════════════════════════════
    # Phase 12 — Deterministic Investigation & Graph Query Engine
    # BFS over persisted relational data. No scoring, no fraud labels.
    # Consumed by app/api/v1/investigation.py
    # ═══════════════════════════════════════════════════════════════════════

    # ── node id helpers ──────────────────────────────────────────────────
    @staticmethod
    def _nid(kind: str, ident: Any) -> str:
        return f"{kind}:{ident}"

    # edge relationship_type -> canonical investigation edge label
    _REL_EDGE_MAP = {
        "DEPENDS_ON": "DEPENDS_ON",
        "DERIVED_FROM": "DERIVED_FROM",
        "CORROBORATES": "CORROBORATES",
        "CONTRADICTS": "CONTRADICTS",
        "SAME_EVENT": "DERIVED_FROM",
        "SAME_SOURCE": "CORROBORATES",
        "INDEPENDENCE_CANDIDATE": "CORROBORATES",
    }

    @classmethod
    def _resolve_payment_for_node(cls, db: Session, node_id: str) -> Optional[str]:
        """Best-effort: which payment's graph does this node belong to?"""
        if ":" not in node_id:
            return None
        kind, ident = node_id.split(":", 1)
        if kind == "pay":
            return ident
        if kind == "ev":
            obs = db.get(EvidenceObservation, cls._safe_int(ident))
            if obs and obs.subject_type == "payment":
                return obs.subject_id
            if obs and obs.payment_event_id:
                pe = db.get(PaymentEvent, obs.payment_event_id)
                if pe:
                    p = db.get(Payment, pe.payment_id)
                    return p.razorpay_payment_id if p else None
            return None
        if kind == "claim":
            c = db.get(Claim, cls._safe_int(ident))
            return c.subject_id if c and c.subject_type == "payment" else None
        if kind == "conflict":
            cf = db.get(EvidenceConflict, cls._safe_int(ident))
            return cf.payment_id if cf else None
        if kind == "evt":
            pe = db.get(PaymentEvent, cls._safe_int(ident))
            if pe:
                p = db.get(Payment, pe.payment_id)
                return p.razorpay_payment_id if p else None
            return None
        if kind == "wh":
            we = db.get(WebhookEvent, cls._safe_int(ident))
            return we.payment_id if we else None
        if kind == "order":
            o = db.execute(
                select(Order).where(Order.razorpay_order_id == ident)
            ).scalar_one_or_none()
            if o:
                p = db.execute(
                    select(Payment).where(Payment.order_id == o.internal_id)
                ).scalars().first()
                return p.razorpay_payment_id if p else None
        if kind == "cust":
            cu = db.execute(
                select(CustomerReference).where(
                    CustomerReference.razorpay_customer_id == ident
                )
            ).scalar_one_or_none()
            if cu:
                p = db.execute(
                    select(Payment).where(Payment.customer_id == cu.internal_id)
                ).scalars().first()
                return p.razorpay_payment_id if p else None
        return None

    @staticmethod
    def _safe_int(v: Any) -> int:
        try:
            return int(v)
        except (TypeError, ValueError):
            return -1

    # ── graph construction ───────────────────────────────────────────────
    @classmethod
    def _construct_graph(
        cls,
        db: Session,
        payment_id: str,
        depth: int,
        as_of: Optional[datetime],
        node_type_filter: Optional[set],
        rel_type_filter: Optional[set],
        max_nodes: int,
        max_edges: int,
    ) -> Dict[str, Any]:
        """
        BFS from the payment root over persisted relations.

        Returns dict: nodes (list[dict]), edges (list[dict]), status (TraversalStatus),
        effective_depth (int).
        """
        from app.schemas.investigation import (
            InvestigationGraphEdge,
            InvestigationGraphNode,
        )

        payment = db.execute(
            select(Payment).where(Payment.razorpay_payment_id == payment_id)
        ).scalar_one_or_none()
        if not payment:
            raise ValueError(f"Payment {payment_id} not found")

        depth = max(1, min(depth, MAX_TRAVERSAL_DEPTH))
        max_nodes = max(1, min(max_nodes, HARD_MAX_NODES))
        max_edges = max(1, min(max_edges, HARD_MAX_EDGES))

        nodes: Dict[str, InvestigationGraphNode] = {}
        edges: Dict[tuple, InvestigationGraphEdge] = {}
        status = TraversalStatus.COMPLETE

        def want_node(node_type: str, is_root: bool = False) -> bool:
            if is_root:
                return True
            return node_type_filter is None or node_type in node_type_filter

        def add_node(nid: str, ntype: str, label: str, entity_id: Optional[str],
                     meta: Optional[dict] = None, is_root: bool = False) -> bool:
            nonlocal status
            if not want_node(ntype, is_root):
                return False
            if nid in nodes:
                return True
            if len(nodes) >= max_nodes:
                status = TraversalStatus.TRAVERSAL_LIMIT_REACHED
                return False
            nodes[nid] = InvestigationGraphNode(
                node_id=nid, node_type=ntype, label=label[:120],
                entity_id=str(entity_id) if entity_id is not None else None,
                metadata=meta or {},
            )
            return True

        def add_edge(src: str, tgt: str, etype: str, label: str = "") -> None:
            nonlocal status
            if src not in nodes or tgt not in nodes:
                return
            if rel_type_filter is not None and etype not in rel_type_filter:
                return
            key = (src, tgt, etype)
            if key in edges:
                return
            if len(edges) >= max_edges:
                status = TraversalStatus.TRAVERSAL_LIMIT_REACHED
                return
            edges[key] = InvestigationGraphEdge(
                source_node_id=src, target_node_id=tgt, edge_type=etype, label=label,
            )

        def obs_visible(obs: EvidenceObservation) -> bool:
            if as_of is None:
                return True
            oa = obs.observed_at
            if oa is None:
                return True
            if oa.tzinfo is None:
                oa = oa.replace(tzinfo=timezone.utc)
            return oa <= as_of

        root = cls._nid("pay", payment_id)
        add_node(root, "PAYMENT", payment_id, payment_id, {
            "status": payment.status,
            "amount_minor": payment.amount_minor,
            "currency": payment.currency,
        }, is_root=True)

        # ---- expansion rules per node kind ----
        def expand(nid: str) -> list:
            """Return [(neighbour_nid, added_bool)] — callers enqueue added ones."""
            kind, ident = nid.split(":", 1)
            produced = []

            if kind == "pay":
                p = payment
                if p.order_id:
                    o = db.get(Order, p.order_id)
                    if o:
                        oid = cls._nid("order", o.razorpay_order_id)
                        if add_node(oid, "ORDER", o.razorpay_order_id, o.razorpay_order_id,
                                    {"status": o.status, "amount_minor": o.amount_minor,
                                     "currency": o.currency}):
                            add_edge(nid, oid, "HAS_ORDER", "order")
                            produced.append(oid)
                if p.customer_id:
                    cu = db.get(CustomerReference, p.customer_id)
                    if cu:
                        cid = cls._nid("cust", cu.razorpay_customer_id)
                        if add_node(cid, "CUSTOMER", cu.razorpay_customer_id,
                                    cu.razorpay_customer_id, {}):
                            add_edge(nid, cid, "HAS_CUSTOMER", "customer")
                            produced.append(cid)
                events = db.execute(
                    select(PaymentEvent).where(PaymentEvent.payment_id == p.internal_id)
                    .order_by(PaymentEvent.event_timestamp)
                ).scalars().all()
                for pe in events:
                    eid = cls._nid("evt", pe.internal_id)
                    if add_node(eid, "PAYMENT_EVENT", pe.event_type, pe.internal_id,
                                {"event_type": pe.event_type,
                                 "event_timestamp": pe.event_timestamp.isoformat()
                                 if pe.event_timestamp else None}):
                        add_edge(nid, eid, "HAS_EVENT", "event")
                        produced.append(eid)
                for cf in db.execute(
                    select(EvidenceConflict).where(EvidenceConflict.payment_id == payment_id)
                ).scalars().all():
                    cfid = cls._nid("conflict", cf.internal_id)
                    if add_node(cfid, "CONFLICT", cf.conflict_type, cf.internal_id,
                                {"conflict_type": cf.conflict_type, "severity": cf.severity,
                                 "status": cf.status}):
                        add_edge(nid, cfid, "HAS_CONFLICT", "conflict")
                        produced.append(cfid)
                for sn in db.execute(
                    select(EvidenceIntegritySnapshot).where(
                        EvidenceIntegritySnapshot.payment_id == payment_id
                    )
                ).scalars().all():
                    snid = cls._nid("snap", sn.internal_id)
                    if add_node(snid, "INTEGRITY_SNAPSHOT",
                                getattr(sn, "overall_status", "SNAPSHOT"), sn.internal_id,
                                {"overall_status": getattr(sn, "overall_status", None)}):
                        add_edge(nid, snid, "HAS_INTEGRITY_SNAPSHOT", "integrity")
                        produced.append(snid)
                for ch in db.execute(
                    select(EvidenceStateChange).where(
                        EvidenceStateChange.payment_id == payment_id
                    )
                ).scalars().all():
                    chid = cls._nid("chg", ch.internal_id)
                    if add_node(chid, "STATE_CHANGE", ch.change_type, ch.internal_id,
                                {"change_type": ch.change_type, "dimension": ch.dimension}):
                        add_edge(nid, chid, "HAS_STATE_CHANGE", "state change")
                        produced.append(chid)

            elif kind == "evt":
                pe = db.get(PaymentEvent, cls._safe_int(ident))
                if not pe:
                    return produced
                obs_list = db.execute(
                    select(EvidenceObservation).where(
                        EvidenceObservation.payment_event_id == pe.internal_id
                    )
                ).scalars().all()
                for obs in obs_list:
                    if not obs_visible(obs):
                        continue
                    oid = cls._nid("ev", obs.internal_id)
                    if add_node(oid, "EVIDENCE",
                                f"{obs.evidence_type}: {obs.value or 'N/A'}", obs.internal_id,
                                {"evidence_type": obs.evidence_type,
                                 "source_type": obs.source_type,
                                 "observed_at": obs.observed_at.isoformat()
                                 if obs.observed_at else None}):
                        add_edge(nid, oid, "PRODUCED_EVIDENCE", "produced")
                        produced.append(oid)
                if pe.webhook_event_id:
                    we = db.get(WebhookEvent, pe.webhook_event_id)
                    if we:
                        wid = cls._nid("wh", we.id)
                        if add_node(wid, "WEBHOOK_EVENT", we.event_type, we.id,
                                    {"event_type": we.event_type,
                                     "signature_verified": we.signature_verified,
                                     "received_at": we.received_at.isoformat()
                                     if we.received_at else None}):
                            add_edge(nid, wid, "DERIVED_FROM_WEBHOOK", "webhook")
                            produced.append(wid)

            elif kind == "ev":
                obs = db.get(EvidenceObservation, cls._safe_int(ident))
                if not obs:
                    return produced
                # source node
                if obs.source_type:
                    sid = cls._nid("src", obs.source_type)
                    if add_node(sid, "SOURCE", obs.source_type, obs.source_type, {}):
                        add_edge(nid, sid, "FROM_SOURCE", "source")
                        produced.append(sid)
                # originating webhook
                if obs.webhook_event_id:
                    we = db.get(WebhookEvent, obs.webhook_event_id)
                    if we:
                        wid = cls._nid("wh", we.id)
                        if add_node(wid, "WEBHOOK_EVENT", we.event_type, we.id,
                                    {"event_type": we.event_type,
                                     "signature_verified": we.signature_verified}):
                            add_edge(nid, wid, "DERIVED_FROM_WEBHOOK", "webhook")
                            produced.append(wid)
                # claims supported
                link_rows = db.execute(
                    select(EvidenceClaimLink).where(
                        EvidenceClaimLink.evidence_id == obs.internal_id
                    )
                ).scalars().all()
                for lk in link_rows:
                    cl = db.get(Claim, lk.claim_id)
                    if cl:
                        clid = cls._nid("claim", cl.internal_id)
                        if add_node(clid, "CLAIM",
                                    f"{cl.claim_type}={cl.canonical_value}", cl.internal_id,
                                    {"claim_type": cl.claim_type,
                                     "canonical_value": cl.canonical_value}):
                            add_edge(nid, clid, "SUPPORTS_CLAIM", "supports")
                            produced.append(clid)
                # evidence <-> evidence relationships
                rels = db.execute(
                    select(EvidenceRelationship).where(
                        or_(
                            EvidenceRelationship.source_evidence_id == obs.internal_id,
                            EvidenceRelationship.target_evidence_id == obs.internal_id,
                        )
                    )
                ).scalars().all()
                for rel in rels:
                    other_id = (rel.target_evidence_id
                                if rel.source_evidence_id == obs.internal_id
                                else rel.source_evidence_id)
                    other = db.get(EvidenceObservation, other_id)
                    if not other or not obs_visible(other):
                        continue
                    oid = cls._nid("ev", other.internal_id)
                    if add_node(oid, "EVIDENCE",
                                f"{other.evidence_type}: {other.value or 'N/A'}",
                                other.internal_id,
                                {"evidence_type": other.evidence_type,
                                 "source_type": other.source_type}):
                        etype = cls._REL_EDGE_MAP.get(rel.relationship_type,
                                                     rel.relationship_type)
                        add_edge(nid, oid, etype, rel.relationship_type.lower())
                        produced.append(oid)

            elif kind == "conflict":
                cf = db.get(EvidenceConflict, cls._safe_int(ident))
                if not cf:
                    return produced
                for claim_ref in (cf.claim_a_id, cf.claim_b_id):
                    cl = db.get(Claim, claim_ref)
                    if cl:
                        clid = cls._nid("claim", cl.internal_id)
                        if add_node(clid, "CLAIM",
                                    f"{cl.claim_type}={cl.canonical_value}", cl.internal_id,
                                    {"claim_type": cl.claim_type,
                                     "canonical_value": cl.canonical_value}):
                            add_edge(nid, clid, "INVOLVES_CLAIM", "involves")
                            produced.append(clid)

            return produced

        # ---- BFS ----
        frontier = [(root, 0)]
        visited = {root}
        effective_depth = 0
        while frontier:
            nid, d = frontier.pop(0)
            if d >= depth:
                continue
            for neighbour in expand(nid):
                effective_depth = max(effective_depth, d + 1)
                if neighbour not in visited:
                    visited.add(neighbour)
                    frontier.append((neighbour, d + 1))
            if status == TraversalStatus.TRAVERSAL_LIMIT_REACHED:
                break

        return {
            "nodes": list(nodes.values()),
            "edges": list(edges.values()),
            "status": status,
            "effective_depth": effective_depth or 1,
            "requested_depth": depth,
        }

    @classmethod
    def build_payment_graph(
        cls,
        db: Session,
        payment_id: str,
        depth: int = 2,
        as_of: Optional[datetime] = None,
        node_types: Optional[list] = None,
        relationship_types: Optional[list] = None,
        max_nodes: int = 200,
        max_edges: int = 400,
    ):
        """Build the bounded investigation graph centred on a payment (BFS)."""
        from app.schemas.investigation import InvestigationGraphResponse

        now = datetime.now(timezone.utc)
        ntf = {str(getattr(t, "value", t)) for t in node_types} if node_types else None
        rtf = {str(getattr(t, "value", t)) for t in relationship_types} if relationship_types else None

        g = cls._construct_graph(
            db, payment_id, depth, as_of, ntf, rtf, max_nodes, max_edges
        )
        return InvestigationGraphResponse(
            payment_id=payment_id,
            nodes=g["nodes"],
            edges=g["edges"],
            node_count=len(g["nodes"]),
            edge_count=len(g["edges"]),
            traversal_depth=g["requested_depth"],
            traversal_status=g["status"].value,
            methodology_version=METHODOLOGY_VERSION,
            evaluated_at=now,
        )

    @classmethod
    def find_path(
        cls,
        db: Session,
        source: str,
        target: str,
        max_depth: int = 5,
        as_of: Optional[datetime] = None,
    ):
        """Shortest path between two node ids via BFS over the payment graph."""
        from app.schemas.investigation import (
            InvestigationPathEdge,
            InvestigationPathNode,
            InvestigationPathResponse,
        )

        now = datetime.now(timezone.utc)
        max_depth = max(1, min(max_depth, 10))

        payment_id = cls._resolve_payment_for_node(db, source) \
            or cls._resolve_payment_for_node(db, target)

        empty = InvestigationPathResponse(
            source=source, target=target, path_nodes=[], path_edges=[],
            path_length=0, found=False,
            methodology_version=METHODOLOGY_VERSION, evaluated_at=now,
        )
        if not payment_id:
            return empty

        g = cls._construct_graph(
            db, payment_id, MAX_TRAVERSAL_DEPTH, as_of, None, None,
            HARD_MAX_NODES, HARD_MAX_EDGES,
        )
        nodes_by_id = {n.node_id: n for n in g["nodes"]}
        if source not in nodes_by_id or target not in nodes_by_id:
            return empty
        if source == target:
            n = nodes_by_id[source]
            return InvestigationPathResponse(
                source=source, target=target,
                path_nodes=[InvestigationPathNode(
                    node_id=n.node_id, node_type=n.node_type, label=n.label)],
                path_edges=[], path_length=0, found=True,
                methodology_version=METHODOLOGY_VERSION, evaluated_at=now,
            )

        adj: Dict[str, list] = {}
        for e in g["edges"]:
            adj.setdefault(e.source_node_id, []).append((e.target_node_id, e))
            adj.setdefault(e.target_node_id, []).append((e.source_node_id, e))

        prev: Dict[str, tuple] = {source: (None, None)}
        queue = [(source, 0)]
        found = False
        while queue:
            cur, dist = queue.pop(0)
            if cur == target:
                found = True
                break
            if dist >= max_depth:
                continue
            for nxt, edge in adj.get(cur, []):
                if nxt not in prev:
                    prev[nxt] = (cur, edge)
                    queue.append((nxt, dist + 1))

        if not found:
            return empty

        path_nids = []
        cur = target
        while cur is not None:
            path_nids.append(cur)
            cur = prev[cur][0]
        path_nids.reverse()

        path_nodes = [
            InvestigationPathNode(node_id=nid, node_type=nodes_by_id[nid].node_type,
                                  label=nodes_by_id[nid].label)
            for nid in path_nids
        ]
        path_edges = []
        for nid in path_nids[1:]:
            _, edge = prev[nid]
            if edge is not None:
                path_edges.append(InvestigationPathEdge(
                    source_node_id=edge.source_node_id,
                    target_node_id=edge.target_node_id,
                    edge_type=edge.edge_type,
                ))

        return InvestigationPathResponse(
            source=source, target=target,
            path_nodes=path_nodes, path_edges=path_edges,
            path_length=len(path_edges), found=True,
            methodology_version=METHODOLOGY_VERSION, evaluated_at=now,
        )

    @classmethod
    def get_evidence_provenance(cls, db: Session, evidence_id: int):
        """Upstream chain: Evidence -> PaymentEvent -> WebhookEvent -> Payment."""
        from app.schemas.investigation import (
            EvidenceProvenanceResponse,
            EvidenceProvenanceStep,
        )

        now = datetime.now(timezone.utc)
        obs = db.get(EvidenceObservation, evidence_id)
        if not obs:
            raise ValueError(f"Evidence {evidence_id} not found")

        chain: List[EvidenceProvenanceStep] = [
            EvidenceProvenanceStep(
                entity_type="EVIDENCE", entity_id=str(obs.internal_id),
                label=f"{obs.evidence_type}: {obs.value or 'N/A'}",
                timestamp=obs.observed_at,
                metadata={"source_type": obs.source_type,
                          "extraction_method": obs.extraction_method,
                          "value_type": obs.value_type},
            )
        ]

        pe = db.get(PaymentEvent, obs.payment_event_id) if obs.payment_event_id else None
        if pe:
            chain.append(EvidenceProvenanceStep(
                entity_type="PAYMENT_EVENT", entity_id=str(pe.internal_id),
                label=pe.event_type, timestamp=pe.event_timestamp,
                metadata={"event_type": pe.event_type},
            ))

        we = None
        if obs.webhook_event_id:
            we = db.get(WebhookEvent, obs.webhook_event_id)
        elif pe and pe.webhook_event_id:
            we = db.get(WebhookEvent, pe.webhook_event_id)
        if we:
            chain.append(EvidenceProvenanceStep(
                entity_type="WEBHOOK_EVENT", entity_id=str(we.id),
                label=we.event_type, timestamp=we.received_at,
                metadata={"event_type": we.event_type,
                          "signature_verified": we.signature_verified,
                          "razorpay_event_id": we.razorpay_event_id},
            ))

        # payment tail
        pay = None
        if pe:
            pay = db.get(Payment, pe.payment_id)
        elif obs.subject_type == "payment":
            pay = db.execute(
                select(Payment).where(Payment.razorpay_payment_id == obs.subject_id)
            ).scalar_one_or_none()
        elif we and we.payment_id:
            pay = db.execute(
                select(Payment).where(Payment.razorpay_payment_id == we.payment_id)
            ).scalar_one_or_none()
        if pay:
            chain.append(EvidenceProvenanceStep(
                entity_type="PAYMENT", entity_id=pay.razorpay_payment_id,
                label=pay.razorpay_payment_id, timestamp=pay.first_observed_at,
                metadata={"status": pay.status},
            ))

        return EvidenceProvenanceResponse(
            evidence_id=evidence_id, provenance_chain=chain,
            chain_length=len(chain),
            methodology_version=METHODOLOGY_VERSION, evaluated_at=now,
        )

    @classmethod
    def get_claim_support(cls, db: Session, claim_id: int):
        """Which observations support a claim, and how independent they are."""
        from app.schemas.investigation import (
            ClaimSupportEvidence,
            ClaimSupportResponse,
        )

        now = datetime.now(timezone.utc)
        claim = db.get(Claim, claim_id)
        if not claim:
            raise ValueError(f"Claim {claim_id} not found")

        links = db.execute(
            select(EvidenceClaimLink).where(EvidenceClaimLink.claim_id == claim_id)
        ).scalars().all()

        supporting: List[ClaimSupportEvidence] = []
        seen_sources: set = set()
        obs_ids: List[int] = []
        for lk in links:
            obs = db.get(EvidenceObservation, lk.evidence_id)
            if not obs:
                continue
            obs_ids.append(obs.internal_id)
            source_key = (obs.source_type, obs.source_reference)
            is_independent = source_key not in seen_sources
            if is_independent:
                seen_sources.add(source_key)
            supporting.append(ClaimSupportEvidence(
                evidence_id=obs.internal_id, evidence_type=obs.evidence_type,
                source_type=obs.source_type, value=obs.value,
                is_independent=is_independent, observed_at=obs.observed_at,
            ))

        dependency_count = 0
        if obs_ids:
            dependency_count = db.execute(
                select(func.count(EvidenceRelationship.internal_id)).where(
                    EvidenceRelationship.source_evidence_id.in_(obs_ids),
                    EvidenceRelationship.target_evidence_id.in_(obs_ids),
                    EvidenceRelationship.relationship_type.in_(
                        ["DEPENDS_ON", "DERIVED_FROM", "SAME_EVENT", "SAME_SOURCE"]
                    ),
                )
            ).scalar() or 0

        corr = db.execute(
            select(EvidenceCorroboration).where(EvidenceCorroboration.claim_id == claim_id)
        ).scalars().first()
        independent_count = (
            corr.distinct_sources_count if corr else len(seen_sources)
        )

        return ClaimSupportResponse(
            claim_id=claim_id, claim_type=claim.claim_type,
            canonical_value=claim.canonical_value,
            supporting_evidence=supporting,
            total_support_count=len(supporting),
            independent_support_count=independent_count,
            dependency_count=int(dependency_count),
            methodology_version=METHODOLOGY_VERSION, evaluated_at=now,
        )

    @classmethod
    def get_evidence_dependencies(cls, db: Session, evidence_id: int):
        """Direct (1-hop) and indirect (multi-hop) dependency relationships."""
        from app.schemas.investigation import (
            EvidenceDependenciesResponse,
            EvidenceDependency,
        )

        now = datetime.now(timezone.utc)
        obs = db.get(EvidenceObservation, evidence_id)
        if not obs:
            raise ValueError(f"Evidence {evidence_id} not found")

        dep_types = {"DEPENDS_ON", "DERIVED_FROM", "SAME_EVENT", "SAME_SOURCE"}

        def rels_from(eid: int) -> list:
            return db.execute(
                select(EvidenceRelationship).where(
                    EvidenceRelationship.source_evidence_id == eid
                )
            ).scalars().all()

        direct: List[EvidenceDependency] = []
        direct_targets: set = set()
        for rel in rels_from(evidence_id):
            if rel.relationship_type not in dep_types:
                continue
            direct.append(EvidenceDependency(
                source_evidence_id=rel.source_evidence_id,
                target_evidence_id=rel.target_evidence_id,
                dependency_type=rel.relationship_type,
                description=(rel.provenance_metadata or {}).get(
                    "reason", f"{rel.relationship_type} via {rel.relationship_source}"),
            ))
            direct_targets.add(rel.target_evidence_id)

        indirect: List[EvidenceDependency] = []
        seen = {evidence_id} | direct_targets
        frontier = list(direct_targets)
        hops = 0
        while frontier and hops < MAX_TRAVERSAL_DEPTH:
            hops += 1
            nxt_frontier = []
            for eid in frontier:
                for rel in rels_from(eid):
                    if rel.relationship_type not in dep_types:
                        continue
                    if rel.target_evidence_id in seen:
                        continue
                    indirect.append(EvidenceDependency(
                        source_evidence_id=rel.source_evidence_id,
                        target_evidence_id=rel.target_evidence_id,
                        dependency_type=rel.relationship_type,
                        description=(rel.provenance_metadata or {}).get(
                            "reason", f"indirect {rel.relationship_type}"),
                    ))
                    seen.add(rel.target_evidence_id)
                    nxt_frontier.append(rel.target_evidence_id)
            frontier = nxt_frontier

        return EvidenceDependenciesResponse(
            evidence_id=evidence_id,
            direct_dependencies=direct,
            indirect_dependencies=indirect,
            total_dependency_count=len(direct) + len(indirect),
            methodology_version=METHODOLOGY_VERSION, evaluated_at=now,
        )

    @classmethod
    def get_conflict_path(cls, db: Session, conflict_id: int):
        """Conflict -> claim A / claim B -> the evidence backing each side."""
        from app.schemas.investigation import (
            ConflictPathResponse,
            ConflictPathStep,
        )

        now = datetime.now(timezone.utc)
        cf = db.get(EvidenceConflict, conflict_id)
        if not cf:
            raise ValueError(f"Conflict {conflict_id} not found")

        steps: List[ConflictPathStep] = [
            ConflictPathStep(
                entity_type="CONFLICT", entity_id=str(cf.internal_id),
                label=f"{cf.conflict_type} ({cf.severity})", role="CONFLICT",
                metadata={"status": cf.status, "detected_at":
                          cf.detected_at.isoformat() if cf.detected_at else None},
            )
        ]

        for claim_ref, role in ((cf.claim_a_id, "CLAIM_A"), (cf.claim_b_id, "CLAIM_B")):
            cl = db.get(Claim, claim_ref)
            if not cl:
                continue
            steps.append(ConflictPathStep(
                entity_type="CLAIM", entity_id=str(cl.internal_id),
                label=f"{cl.claim_type}={cl.canonical_value}", role=role,
                metadata={"claim_type": cl.claim_type},
            ))
            links = db.execute(
                select(EvidenceClaimLink).where(EvidenceClaimLink.claim_id == cl.internal_id)
            ).scalars().all()
            for lk in links:
                obs = db.get(EvidenceObservation, lk.evidence_id)
                if not obs:
                    continue
                steps.append(ConflictPathStep(
                    entity_type="EVIDENCE", entity_id=str(obs.internal_id),
                    label=f"{obs.evidence_type}: {obs.value or 'N/A'}",
                    role="EVIDENCE",
                    metadata={"supports_role": role, "source_type": obs.source_type},
                ))

        return ConflictPathResponse(
            conflict_id=conflict_id, conflict_type=cf.conflict_type,
            severity=cf.severity, status=cf.status,
            path_steps=steps, path_length=len(steps),
            methodology_version=METHODOLOGY_VERSION, evaluated_at=now,
        )

    @classmethod
    def search_entities(cls, db: Session, query: str, limit: int = 20):
        """Exact / prefix identifier search across the core entity tables."""
        from app.schemas.investigation import SearchEntityResult, SearchResponse

        now = datetime.now(timezone.utc)
        results: List[SearchEntityResult] = []
        q = f"%{query}%"
        per = max(1, limit)

        def push(rows, etype, id_fn, label_fn, field, val_fn):
            for r in rows:
                results.append(SearchEntityResult(
                    entity_type=etype, entity_id=str(id_fn(r)), label=str(label_fn(r)),
                    matched_field=field, matched_value=str(val_fn(r)),
                ))

        try:
            push(db.execute(select(Payment).where(
                Payment.razorpay_payment_id.ilike(q)).limit(per)).scalars().all(),
                "PAYMENT", lambda r: r.razorpay_payment_id,
                lambda r: f"Payment {r.razorpay_payment_id} ({r.status})",
                "razorpay_payment_id", lambda r: r.razorpay_payment_id)
        except Exception:
            pass
        try:
            push(db.execute(select(Order).where(
                Order.razorpay_order_id.ilike(q)).limit(per)).scalars().all(),
                "ORDER", lambda r: r.razorpay_order_id,
                lambda r: f"Order {r.razorpay_order_id}",
                "razorpay_order_id", lambda r: r.razorpay_order_id)
        except Exception:
            pass
        try:
            push(db.execute(select(CustomerReference).where(
                CustomerReference.razorpay_customer_id.ilike(q)).limit(per)).scalars().all(),
                "CUSTOMER", lambda r: r.razorpay_customer_id,
                lambda r: f"Customer {r.razorpay_customer_id}",
                "razorpay_customer_id", lambda r: r.razorpay_customer_id)
        except Exception:
            pass
        try:
            push(db.execute(select(WebhookEvent).where(or_(
                WebhookEvent.razorpay_event_id.ilike(q),
                WebhookEvent.payment_id.ilike(q),
            )).limit(per)).scalars().all(),
                "WEBHOOK_EVENT", lambda r: r.id,
                lambda r: f"Webhook {r.event_type}",
                "razorpay_event_id", lambda r: r.razorpay_event_id or r.payment_id or "")
        except Exception:
            pass
        try:
            push(db.execute(select(EvidenceObservation).where(or_(
                EvidenceObservation.subject_id.ilike(q),
                EvidenceObservation.evidence_type.ilike(q),
                EvidenceObservation.value.ilike(q),
            )).limit(per)).scalars().all(),
                "EVIDENCE", lambda r: r.internal_id,
                lambda r: f"{r.evidence_type}: {r.value or 'N/A'}",
                "subject_id", lambda r: r.subject_id)
        except Exception:
            pass
        try:
            push(db.execute(select(Claim).where(or_(
                Claim.subject_id.ilike(q),
                Claim.claim_type.ilike(q),
                Claim.canonical_value.ilike(q),
            )).limit(per)).scalars().all(),
                "CLAIM", lambda r: r.internal_id,
                lambda r: f"{r.claim_type}={r.canonical_value}",
                "subject_id", lambda r: r.subject_id)
        except Exception:
            pass

        results = results[:limit]
        return SearchResponse(
            query=query, results=results, total_results=len(results),
            methodology_version=METHODOLOGY_VERSION, evaluated_at=now,
        )
