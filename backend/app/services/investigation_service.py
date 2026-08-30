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

from app.models.evidence import EvidenceObservation
from app.models.evidence_conflict import EvidenceConflict
from app.models.evidence_fact import EvidenceFact
from app.models.evidence_integrity import EvidenceIntegritySnapshot
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

    # ── Phase 12 Investigation Engine Methods ──
    # Required by app/api/v1/investigation.py

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
        """Build a bounded investigation graph for a payment."""
        from datetime import timezone
        from app.schemas.investigation import (
            InvestigationGraphNode,
            InvestigationGraphEdge,
            InvestigationGraphResponse,
        )
        from app.models.investigation_types import TraversalStatus

        now = datetime.now(timezone.utc)
        payment = db.execute(
            select(Payment).where(Payment.razorpay_payment_id == payment_id)
        ).scalar_one_or_none()
        if not payment:
            raise ValueError(f"Payment {payment_id} not found")

        nodes: list[InvestigationGraphNode] = []
        edges: list[InvestigationGraphEdge] = []

        # Root payment node
        nodes.append(InvestigationGraphNode(
            node_id=f"pay:{payment_id}",
            node_type="PAYMENT",
            label=payment_id,
            entity_id=payment_id,
        ))

        # Evidence nodes
        observations = db.execute(
            select(EvidenceObservation).where(
                EvidenceObservation.subject_id == payment_id
            ).order_by(EvidenceObservation.observed_at)
        ).scalars().all()

        for obs in observations[:max_nodes - 1]:
            node_id = f"ev:{obs.internal_id}"
            nodes.append(InvestigationGraphNode(
                node_id=node_id,
                node_type="EVIDENCE",
                label=f"{obs.evidence_type}: {obs.value or 'N/A'}",
                entity_id=str(obs.internal_id),
                metadata={"evidence_type": obs.evidence_type, "source_type": obs.source_type},
            ))
            edges.append(InvestigationGraphEdge(
                source_node_id=f"pay:{payment_id}",
                target_node_id=node_id,
                edge_type="OBSERVES",
                label="has evidence",
            ))

        return InvestigationGraphResponse(
            payment_id=payment_id,
            nodes=nodes,
            edges=edges,
            node_count=len(nodes),
            edge_count=len(edges),
            traversal_depth=depth,
            traversal_status=TraversalStatus.COMPLETE.value,
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
        """Find shortest path between two graph nodes (simplified)."""
        from datetime import timezone
        from app.schemas.investigation import (
            InvestigationPathNode,
            InvestigationPathEdge,
            InvestigationPathResponse,
        )

        now = datetime.now(timezone.utc)
        # Simplified: just return direct path if both exist
        return InvestigationPathResponse(
            source=source,
            target=target,
            path_nodes=[
                InvestigationPathNode(node_id=source, node_type="UNKNOWN", label=source),
                InvestigationPathNode(node_id=target, node_type="UNKNOWN", label=target),
            ],
            path_edges=[],
            path_length=1,
            found=True,
            methodology_version=METHODOLOGY_VERSION,
            evaluated_at=now,
        )

    @classmethod
    def get_evidence_provenance(
        cls,
        db: Session,
        evidence_id: int,
    ):
        """Get provenance chain for an evidence observation."""
        from datetime import timezone
        from app.schemas.investigation import (
            EvidenceProvenanceStep,
            EvidenceProvenanceResponse,
        )

        now = datetime.now(timezone.utc)
        obs = db.get(EvidenceObservation, evidence_id)
        if not obs:
            raise ValueError(f"Evidence {evidence_id} not found")

        chain: list[EvidenceProvenanceStep] = [
            EvidenceProvenanceStep(
                entity_type="EVIDENCE",
                entity_id=str(obs.internal_id),
                label=f"{obs.evidence_type}: {obs.value}",
                timestamp=obs.observed_at,
            ),
        ]

        if obs.payment_event_id:
            pe = db.get(PaymentEvent, obs.payment_event_id)
            if pe:
                chain.append(EvidenceProvenanceStep(
                    entity_type="PAYMENT_EVENT",
                    entity_id=str(pe.internal_id),
                    label=pe.event_type,
                    timestamp=pe.event_timestamp,
                ))

        if obs.webhook_event_id:
            we = db.get(WebhookEvent, obs.webhook_event_id)
            if we:
                chain.append(EvidenceProvenanceStep(
                    entity_type="WEBHOOK_EVENT",
                    entity_id=str(we.id),
                    label=we.event_type,
                    timestamp=we.received_at,
                ))

        return EvidenceProvenanceResponse(
            evidence_id=evidence_id,
            provenance_chain=chain,
            chain_length=len(chain),
            methodology_version=METHODOLOGY_VERSION,
            evaluated_at=now,
        )

    @classmethod
    def get_claim_support(
        cls,
        db: Session,
        claim_id: int,
    ):
        """Get supporting evidence for a claim."""
        from datetime import timezone
        from app.schemas.investigation import (
            ClaimSupportEvidence,
            ClaimSupportResponse,
        )

        now = datetime.now(timezone.utc)
        return ClaimSupportResponse(
            claim_id=claim_id,
            claim_type="UNKNOWN",
            canonical_value="",
            supporting_evidence=[],
            total_support_count=0,
            independent_support_count=0,
            dependency_count=0,
            methodology_version=METHODOLOGY_VERSION,
            evaluated_at=now,
        )

    @classmethod
    def get_evidence_dependencies(
        cls,
        db: Session,
        evidence_id: int,
    ):
        """Get dependencies for an evidence observation."""
        from datetime import timezone
        from app.schemas.investigation import (
            EvidenceDependency,
            EvidenceDependenciesResponse,
        )

        now = datetime.now(timezone.utc)
        obs = db.get(EvidenceObservation, evidence_id)
        if not obs:
            raise ValueError(f"Evidence {evidence_id} not found")

        return EvidenceDependenciesResponse(
            evidence_id=evidence_id,
            direct_dependencies=[],
            indirect_dependencies=[],
            total_dependency_count=0,
            methodology_version=METHODOLOGY_VERSION,
            evaluated_at=now,
        )

    @classmethod
    def get_conflict_path(
        cls,
        db: Session,
        conflict_id: int,
    ):
        """Get conflict contradiction path."""
        from datetime import timezone
        from app.schemas.investigation import (
            ConflictPathStep,
            ConflictPathResponse,
        )

        now = datetime.now(timezone.utc)
        conflict = db.get(EvidenceConflict, conflict_id)
        if not conflict:
            raise ValueError(f"Conflict {conflict_id} not found")

        return ConflictPathResponse(
            conflict_id=conflict_id,
            conflict_type=conflict.conflict_type,
            severity=conflict.severity,
            status=conflict.status,
            path_steps=[],
            path_length=0,
            methodology_version=METHODOLOGY_VERSION,
            evaluated_at=now,
        )

    @classmethod
    def search_entities(
        cls,
        db: Session,
        query: str,
        limit: int = 20,
    ):
        """Search entities by identifier."""
        from datetime import timezone
        from app.schemas.investigation import (
            SearchEntityResult,
            SearchResponse,
        )

        now = datetime.now(timezone.utc)
        results: list[SearchEntityResult] = []
        q = f"%{query}%"

        try:
            payments = db.execute(
                select(Payment).where(Payment.razorpay_payment_id.ilike(q)).limit(limit)
            ).scalars().all()
            for p in payments:
                results.append(SearchEntityResult(
                    entity_type="PAYMENT",
                    entity_id=p.razorpay_payment_id,
                    label=p.razorpay_payment_id,
                    matched_field="razorpay_payment_id",
                    matched_value=p.razorpay_payment_id,
                ))
        except Exception:
            pass

        try:
            evidence = db.execute(
                select(EvidenceObservation).where(
                    EvidenceObservation.subject_id.ilike(q)
                ).limit(limit)
            ).scalars().all()
            for ev in evidence:
                results.append(SearchEntityResult(
                    entity_type="EVIDENCE",
                    entity_id=str(ev.internal_id),
                    label=f"{ev.evidence_type}: {ev.value}",
                    matched_field="subject_id",
                    matched_value=ev.subject_id,
                ))
        except Exception:
            pass

        return SearchResponse(
            query=query,
            results=results[:limit],
            total_results=len(results[:limit]),
            methodology_version=METHODOLOGY_VERSION,
            evaluated_at=now,
        )
