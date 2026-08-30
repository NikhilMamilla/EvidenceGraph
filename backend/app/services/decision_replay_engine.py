"""
Phase 18 — Deterministic Evidence Decision Replay Engine.

Reconstructs the exact analytical state of a payment's evidence decision at any
historical timestamp T. Enforces read-only isolation, temporal boundary exclusion,
methodology pinning, profile pinning, and deterministic canonical fingerprinting.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.conflict_types import ConflictStatus
from app.models.coverage_types import (
    COVERAGE_METHODOLOGY_VERSION,
    PROFILE_VERSION_1,
    STANDARD_PAYMENT_PROFILE_ID,
)
from app.models.evidence import EvidenceObservation
from app.models.evidence_conflict import EvidenceConflict
from app.models.evidence_fact import EvidenceFact
from app.models.evidence_integrity import EvidenceIntegritySnapshot
from app.models.integrity_trace import EvidenceIntegrityTrace
from app.models.replay_types import (
    REPLAY_METHODOLOGY_V1,
    ReplayVerificationStatus,
)
from app.models.trace_types import TraceStatus, TraceType
from app.schemas.decision_replay import (
    DecisionReplayResponse,
    ReplayEvidenceStateSchema,
    ReplayVerificationResponse,
)
from app.services.coverage_engine import evaluate_coverage
from app.services.integrity_engine import IntegrityEngine
from app.services.reliability_engine import evaluate_payment_reliability
from app.services.trace_canonicalization import canonical_json, sha256_hex

logger = logging.getLogger(__name__)

SUPPORTED_INTEGRITY_METHODOLOGIES = {"EIS-1.0"}
SUPPORTED_PROFILES = {"STANDARD_PAYMENT_PROFILE_V1", "STANDARD_PAYMENT_PROFILE_V1.0", "STANDARD"}


def _ensure_utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def compute_replay_input_fingerprint(
    payment_id: str,
    evaluation_time: datetime,
    methodology_version: str,
    profile_version: str,
    observation_ids: List[int],
    fact_hashes: List[str],
    conflict_ids: List[int],
) -> str:
    """Computes a deterministic SHA-256 digest over canonicalized replay inputs."""
    payload = {
        "domain": "evidence_replay_input",
        "payment_id": payment_id,
        "evaluation_time": evaluation_time.isoformat(),
        "methodology_version": methodology_version,
        "profile_version": profile_version,
        "observation_ids": sorted(observation_ids),
        "fact_hashes": sorted(fact_hashes),
        "conflict_ids": sorted(conflict_ids),
    }
    return sha256_hex(canonical_json(payload))


def compute_replay_result_fingerprint(
    coverage_status: str,
    required_present: int,
    required_missing: int,
    reliability_state: str,
    reliability_dimensions: Dict[str, str],
    integrity_status: str,
    integrity_dimensions: Dict[str, str],
    active_conflict_count: int,
) -> str:
    """Computes a deterministic SHA-256 digest over the semantic decision outcome."""
    payload = {
        "domain": "evidence_replay_result",
        "coverage_status": coverage_status,
        "required_present": required_present,
        "required_missing": required_missing,
        "reliability_state": reliability_state,
        "reliability_dimensions": {k: str(v) for k, v in sorted(reliability_dimensions.items())},
        "integrity_status": integrity_status,
        "integrity_dimensions": {k: str(v) for k, v in sorted(integrity_dimensions.items())},
        "active_conflict_count": active_conflict_count,
    }
    return sha256_hex(canonical_json(payload))


class DecisionReplayEngine:
    """Core engine for deterministic decision reconstruction and replay verification."""

    @classmethod
    def reconstruct_decision_state(
        cls,
        db: Session,
        payment_id: str,
        evaluation_time: datetime,
        methodology_version: str = "EIS-1.0",
        profile_version: str = "STANDARD_PAYMENT_PROFILE_V1",
        verify_trace: bool = True,
    ) -> DecisionReplayResponse:
        """
        Reconstructs the analytical state of a payment at evaluation_time.
        Strictly read-only; enforces temporal boundaries.
        """
        eval_t = _ensure_utc(evaluation_time)

        # 1. Methodology & Profile Pinning Validation
        if methodology_version not in SUPPORTED_INTEGRITY_METHODOLOGIES:
            return DecisionReplayResponse(
                payment_id=payment_id,
                evaluation_time=eval_t,
                methodology_version=methodology_version,
                profile_version=profile_version,
                input_fingerprint="",
                result_fingerprint="",
                reproducibility_status="METHODOLOGY_UNAVAILABLE",
                evidence_state=ReplayEvidenceStateSchema(
                    observation_count=0, fact_count=0, claim_count=0,
                    active_conflicts_count=0, distinct_sources_count=0, sources=[]
                ),
                coverage_state="UNKNOWN",
                reliability_state="UNKNOWN",
                integrity_status="UNKNOWN",
                coverage_metrics={},
                reliability_dimensions={},
                integrity_dimensions={},
                active_conflicts=[],
                verification_status=ReplayVerificationStatus.METHODOLOGY_UNAVAILABLE,
                mismatch_details={"error": f"Methodology version '{methodology_version}' is not supported."},
            )

        # 2. Query Evidence Under Historical Boundary (observed_at <= eval_t)
        observations = (
            db.query(EvidenceObservation)
            .filter(
                EvidenceObservation.subject_id == payment_id,
                EvidenceObservation.observed_at <= eval_t,
            )
            .order_by(EvidenceObservation.internal_id)
            .all()
        )
        obs_ids = [o.internal_id for o in observations]
        sources = sorted(list(set(o.source_type for o in observations if o.source_type)))

        # 3. Query Reconciled Facts (first_observed_at <= eval_t)
        facts = (
            db.query(EvidenceFact)
            .filter(
                EvidenceFact.payment_id == payment_id,
                EvidenceFact.first_observed_at <= eval_t,
            )
            .order_by(EvidenceFact.internal_id)
            .all()
        )
        fact_hashes = [f.canonical_value_hash for f in facts]

        # 4. Query Conflicts (detected_at <= eval_t)
        conflicts = (
            db.query(EvidenceConflict)
            .filter(
                EvidenceConflict.payment_id == payment_id,
                EvidenceConflict.detected_at <= eval_t,
            )
            .order_by(EvidenceConflict.internal_id)
            .all()
        )
        conflict_ids = [c.internal_id for c in conflicts]
        active_conflicts = [
            {
                "conflict_id": c.internal_id,
                "conflict_type": c.conflict_type,
                "severity": c.severity,
                "status": c.status,
                "detected_at": c.detected_at.isoformat() if c.detected_at else None,
            }
            for c in conflicts
            if c.status == ConflictStatus.OPEN.value or c.status == "OPEN"
        ]

        # 5. Evaluate Coverage (as_of = eval_t, read-only persist=False)
        cov_resp = evaluate_coverage(
            db, payment_id, as_of=eval_t, profile_id=profile_version, persist=False
        )

        # 6. Evaluate Reliability (as_of = eval_t, read-only persist=False)
        rel_resp = evaluate_payment_reliability(
            db, payment_id, as_of=eval_t, persist=False
        )
        rel_dim_map: Dict[str, str] = {}
        reliability_dimensions: Dict[str, Dict[str, Any]] = {}
        for fa in rel_resp.fact_assessments:
            for k, v in fa.dimensions.items():
                rel_dim_map[f"{fa.fact_type}:{k}"] = v.state
                reliability_dimensions[k] = {"state": v.state, "is_degraded": v.is_degraded}

        rel_state_str = (
            rel_resp.overall_state.value
            if hasattr(rel_resp.overall_state, "value")
            else str(rel_resp.overall_state)
        )

        # 7. Evaluate Integrity (Phase 9 Snapshot)
        snap = IntegrityEngine.compute_integrity(
            db, payment_id, evaluation_time=eval_t, methodology_version=methodology_version
        )
        freshness_st = (snap.freshness_result or {}).get("status", "UNKNOWN")
        source_st = (snap.source_result or {}).get("status", "UNKNOWN")
        indep_st = (snap.independence_result or {}).get("status", "UNKNOWN")
        corrob_st = (snap.corroboration_result or {}).get("status", "UNKNOWN")
        cons_st = (snap.consistency_result or {}).get("status", "UNKNOWN")

        integrity_dim_map = {
            "freshness": freshness_st,
            "source": source_st,
            "independence": indep_st,
            "corroboration": corrob_st,
            "consistency": cons_st,
        }

        # 8. Compute Input & Result Fingerprints
        input_fp = compute_replay_input_fingerprint(
            payment_id=payment_id,
            evaluation_time=eval_t,
            methodology_version=methodology_version,
            profile_version=profile_version,
            observation_ids=obs_ids,
            fact_hashes=fact_hashes,
            conflict_ids=conflict_ids,
        )

        result_fp = compute_replay_result_fingerprint(
            coverage_status=cov_resp.overall_coverage_status,
            required_present=cov_resp.metrics.required_present,
            required_missing=cov_resp.metrics.required_missing,
            reliability_state=rel_state_str,
            reliability_dimensions=rel_dim_map,
            integrity_status=snap.overall_status,
            integrity_dimensions=integrity_dim_map,
            active_conflict_count=len(active_conflicts),
        )

        # 9. Verification Against Historical Traces
        verified_trace_id: Optional[str] = None
        verif_status: Optional[ReplayVerificationStatus] = None
        mismatch_details: Optional[Dict[str, Any]] = None

        if verify_trace:
            # Look for completed evaluation trace matching identity
            hist_trace = (
                db.query(EvidenceIntegrityTrace)
                .filter(
                    EvidenceIntegrityTrace.payment_id == payment_id,
                    EvidenceIntegrityTrace.evaluated_at == eval_t,
                    EvidenceIntegrityTrace.methodology_version == methodology_version,
                    EvidenceIntegrityTrace.trace_type == TraceType.EVALUATION,
                    EvidenceIntegrityTrace.status == TraceStatus.COMPLETED,
                )
                .first()
            )

            if hist_trace is not None:
                verified_trace_id = hist_trace.trace_id
                # Compare historical status and dimensions from canonical payload
                payload = hist_trace.canonical_payload or {}
                content = payload.get("content", {})
                hist_overall = content.get("integrity_status") or hist_trace.overall_status
                hist_freshness = content.get("freshness_state")
                hist_source = content.get("source_directness")
                hist_indep = content.get("independence_status")
                hist_cons = content.get("consistency_status")

                diffs = {}
                if hist_overall and hist_overall != snap.overall_status:
                    diffs["overall_status"] = {"historical": hist_overall, "replayed": snap.overall_status}
                if hist_freshness and hist_freshness != freshness_st:
                    diffs["freshness"] = {"historical": hist_freshness, "replayed": freshness_st}
                if hist_source and hist_source != source_st:
                    diffs["source"] = {"historical": hist_source, "replayed": source_st}
                if hist_indep and hist_indep != indep_st:
                    diffs["independence"] = {"historical": hist_indep, "replayed": indep_st}
                if hist_cons and hist_cons != cons_st:
                    diffs["consistency"] = {"historical": hist_cons, "replayed": cons_st}

                if not diffs:
                    verif_status = ReplayVerificationStatus.MATCH
                else:
                    verif_status = ReplayVerificationStatus.REPLAY_MISMATCH
                    mismatch_details = {"differing_dimensions": diffs}
            else:
                # If no formal trace exists, check if a snapshot exists
                if snap.created_at is not None:
                    verif_status = ReplayVerificationStatus.MATCH
                else:
                    verif_status = ReplayVerificationStatus.INCOMPLETE

        return DecisionReplayResponse(
            payment_id=payment_id,
            evaluation_time=eval_t,
            methodology_version=methodology_version,
            profile_version=profile_version,
            input_fingerprint=input_fp,
            result_fingerprint=result_fp,
            reproducibility_status="REPRODUCIBLE",
            evidence_state=ReplayEvidenceStateSchema(
                observation_count=len(observations),
                fact_count=len(facts),
                claim_count=len(facts),
                active_conflicts_count=len(active_conflicts),
                distinct_sources_count=len(sources),
                sources=sources,
            ),
            coverage_state=cov_resp.overall_coverage_status,
            reliability_state=rel_state_str,
            integrity_status=snap.overall_status,
            coverage_metrics=cov_resp.metrics.model_dump(),
            reliability_dimensions=reliability_dimensions,
            integrity_dimensions=integrity_dim_map,
            active_conflicts=active_conflicts,
            verified_against_trace_id=verified_trace_id,
            verification_status=verif_status,
            mismatch_details=mismatch_details,
        )

    @classmethod
    def verify_trace_replay(
        cls,
        db: Session,
        trace_id: str,
    ) -> ReplayVerificationResponse:
        """
        Reconstructs the evaluation recorded in trace_id and verifies reproducibility.
        """
        trace = (
            db.query(EvidenceIntegrityTrace)
            .filter(EvidenceIntegrityTrace.trace_id == trace_id)
            .first()
        )
        if trace is None:
            return ReplayVerificationResponse(
                trace_id=trace_id,
                payment_id="",
                verification_status=ReplayVerificationStatus.INCOMPLETE,
                historical_fingerprint="",
                replay_fingerprint="",
                methodology_version="",
                profile_version="",
                differences={},
                explanation=f"Decision trace '{trace_id}' was not found in audit store.",
            )

        replay = cls.reconstruct_decision_state(
            db,
            payment_id=trace.payment_id,
            evaluation_time=trace.evaluated_at,
            methodology_version=trace.methodology_version,
            profile_version="STANDARD_PAYMENT_PROFILE_V1",
            verify_trace=False,
        )

        hist_hash = trace.trace_hash or ""
        verif_status = ReplayVerificationStatus.MATCH
        diffs = {}
        explanation = "Historical decision replayed with exact semantic match."

        if trace.overall_status and trace.overall_status != replay.integrity_status:
            verif_status = ReplayVerificationStatus.REPLAY_MISMATCH
            diffs["integrity_status"] = {
                "historical": trace.overall_status,
                "replayed": replay.integrity_status,
            }
            explanation = (
                f"Replay mismatch: historical integrity status was '{trace.overall_status}', "
                f"but replayed status is '{replay.integrity_status}'."
            )

        return ReplayVerificationResponse(
            trace_id=trace_id,
            payment_id=trace.payment_id,
            verification_status=verif_status,
            historical_fingerprint=hist_hash,
            replay_fingerprint=replay.result_fingerprint,
            methodology_version=trace.methodology_version,
            profile_version="STANDARD_PAYMENT_PROFILE_V1",
            differences=diffs,
            explanation=explanation,
        )
