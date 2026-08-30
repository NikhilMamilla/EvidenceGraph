"""
Phase 10 — Evidence Integrity Decision Trace Service.

Owns the trace lifecycle:

    EVALUATION_STARTED
        → INPUTS CAPTURED (evidence selected / excluded)
        → MEASUREMENTS CAPTURED (quality)
        → STRUCTURAL ANALYSIS CAPTURED
        → CONSISTENCY CAPTURED
        → RULES CAPTURED
        → RESULT CAPTURED
        → HASH GENERATED
    COMPLETED | FAILED   (terminal, immutable, tamper-evident)

Design contracts:
  - The trace records the ACTUAL computation path of the authoritative
    Phase 9 engine via its capture channel. Nothing is recomputed or
    invented here.
  - Finalization is transactional: payload + hash + chain linkage +
    terminal status are written together inside the caller's transaction,
    and database CHECK constraints make incomplete terminal states
    unrepresentable.
  - Completed/failed traces have NO update path. New evaluations create
    new traces; history is never rewritten.
  - Raw webhook payloads, secrets, CVV/PIN/OTP, tokens are never copied
    into traces — only safe derived references to authoritative records.
"""

from __future__ import annotations

import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.evidence_integrity import EvidenceIntegritySnapshot
from app.models.integrity_methodology import EIS_V1
from app.models.integrity_trace import EvidenceIntegrityTrace, IntegrityTraceEvent
from app.models.integrity_types import INTEGRITY_METHODOLOGY_VERSION
from app.models.trace_types import (
    ActorType,
    CANONICALIZATION_VERSION,
    HASH_ALGORITHM,
    HASH_DOMAIN,
    TRACE_SCHEMA_VERSION,
    TraceEventType,
    TraceStatus,
    TraceType,
)
from app.services.integrity_engine import IntegrityEngine
from app.services.trace_canonicalization import (
    canonical_hash,
    canonical_payload_for_storage,
    methodology_snapshot_hash,
)

logger = logging.getLogger(__name__)


class IntegrityTraceService:
    """Creates and finalizes Evidence Integrity Decision Traces."""

    # ------------------------------------------------------------------
    # Public entry points
    # ------------------------------------------------------------------

    @classmethod
    def record_evaluation(
        cls,
        db: Session,
        payment_id: str,
        evaluation_time: datetime,
        trigger: str | None = None,
        methodology_version: str = INTEGRITY_METHODOLOGY_VERSION,
        actor_type: str = ActorType.SYSTEM,
    ) -> EvidenceIntegrityTrace | None:
        """
        Run one integrity evaluation and record its decision trace.

        Idempotency: if a COMPLETED EVALUATION trace already exists for the
        identity tuple (payment_id, evaluated_at, methodology_version), that
        existing trace is returned and nothing new is created.

        Legacy note: if an integrity snapshot already exists for the tuple but
        no trace does (data produced before Phase 10 existed), NO trace is
        fabricated — the original computation path cannot be honestly
        reconstructed. Returns None in that case.

        Failures produce auditable FAILED traces, not exceptions.
        """
        if evaluation_time.tzinfo is None:
            raise ValueError("evaluation_time must be timezone-aware UTC.")

        start = time.perf_counter()

        # --------------------------------------------------------------
        # Deduplication (application-level, backed by a DB partial unique
        # index on COMPLETED EVALUATION traces for defense in depth).
        # --------------------------------------------------------------
        existing = cls._find_completed_evaluation(db, payment_id, evaluation_time, methodology_version)
        if existing is not None:
            logger.debug(
                "Integrity trace already exists — returning existing",
                extra={
                    "payment_id": payment_id,
                    "trace_id": existing.trace_id,
                    "evaluated_at": evaluation_time.isoformat(),
                },
            )
            return existing

        legacy_snapshot = db.execute(
            select(EvidenceIntegritySnapshot).where(
                EvidenceIntegritySnapshot.payment_id == payment_id,
                EvidenceIntegritySnapshot.evaluated_at == evaluation_time,
                EvidenceIntegritySnapshot.methodology_version == methodology_version,
            )
        ).scalar_one_or_none()
        if legacy_snapshot is not None:
            logger.warning(
                "Integrity snapshot exists without a decision trace "
                "(pre-Phase-10 data) — refusing to fabricate audit history",
                extra={
                    "payment_id": payment_id,
                    "evaluated_at": evaluation_time.isoformat(),
                    "methodology_version": methodology_version,
                },
            )
            return None

        trace = cls._start_trace(
            db=db,
            payment_id=payment_id,
            evaluation_time=evaluation_time,
            methodology_version=methodology_version,
            trace_type=TraceType.EVALUATION,
            original_trace_id=None,
            trigger=trigger,
            actor_type=actor_type,
        )

        capture: dict[str, Any] = {}
        try:
            snapshot = IntegrityEngine.compute_integrity(
                db=db,
                payment_id=payment_id,
                evaluation_time=evaluation_time,
                methodology_version=methodology_version,
                capture=capture,
            )
            finalized = cls._finalize_completed(
                db=db, trace=trace, capture=capture, snapshot=snapshot, actor_type=actor_type
            )
        except IntegrityError:
            # Concurrent finalization won the partial-unique identity slot.
            # The winner's COMPLETED trace is authoritative; ours must not
            # masquerade as a failure.
            db.rollback()
            winner = cls._find_completed_evaluation(
                db, payment_id, evaluation_time, methodology_version
            )
            if winner is not None:
                return winner
            raise
        except Exception as exc:
            failed = cls._finalize_failed(
                db=db,
                trace=trace,
                capture=capture,
                exc=exc,
                stage=cls._infer_failure_stage(capture),
                actor_type=actor_type,
            )
            logger.error(
                "Evidence integrity evaluation FAILED — failure trace recorded",
                extra={
                    "trace_id": failed.trace_id,
                    "payment_id": payment_id,
                    "failure_stage": failed.failure_stage,
                    "failure_category": failed.failure_category,
                    "trace_status": TraceStatus.FAILED,
                },
                exc_info=True,  # full diagnostics go to internal logs only
            )
            return failed

        duration_ms = round((time.perf_counter() - start) * 1000, 2)
        logger.info(
            "Evidence integrity trace completed",
            extra={
                "trace_id": finalized.trace_id,
                "payment_id": payment_id,
                "methodology_version": methodology_version,
                "evaluation_time": evaluation_time.isoformat(),
                "trace_status": TraceStatus.COMPLETED,
                "overall_status": finalized.overall_status,
                "hash_algorithm": HASH_ALGORITHM,
                "duration_ms": duration_ms,
            },
        )
        return finalized

    # ------------------------------------------------------------------
    # Lifecycle steps
    # ------------------------------------------------------------------

    @classmethod
    def _start_trace(
        cls,
        db: Session,
        payment_id: str,
        evaluation_time: datetime,
        methodology_version: str,
        trace_type: str,
        original_trace_id: str | None,
        trigger: str | None,
        actor_type: str,
    ) -> EvidenceIntegrityTrace:
        trace = EvidenceIntegrityTrace(
            trace_id=cls._new_id(),
            trace_type=trace_type,
            original_trace_id=original_trace_id,
            payment_id=payment_id,
            evaluated_at=evaluation_time,
            methodology_version=methodology_version,
            methodology_snapshot_hash=methodology_snapshot_hash(EIS_V1.describe()),
            trigger=trigger,
            status=TraceStatus.EVALUATION_STARTED,
        )
        db.add(trace)
        db.flush()
        cls._record_event(
            db,
            trace_id=trace.trace_id,
            event_type=TraceEventType.EVALUATION_STARTED,
            metadata_={
                "payment_id": payment_id,
                "methodology_version": methodology_version,
                "trace_type": trace_type,
            },
            actor_type=actor_type,
        )
        return trace

    @classmethod
    def _finalize_completed(
        cls,
        db: Session,
        trace: EvidenceIntegrityTrace,
        capture: dict[str, Any],
        snapshot: EvidenceIntegritySnapshot | None,
        actor_type: str,
        content_extra: dict[str, Any] | None = None,
    ) -> EvidenceIntegrityTrace:
        """
        Finalize a trace as COMPLETED.

        `snapshot` is the persisted Phase 9 snapshot for EVALUATION traces;
        REPLAY traces pass None (they never persist snapshots). Extra audit
        sections (e.g. replay comparisons) are merged into the content before
        hashing via `content_extra` so the stored hash covers exactly what is
        stored.
        """
        content = cls._build_content(capture)
        if content_extra:
            content.update(content_extra)

        cls._record_event(
            db,
            trace_id=trace.trace_id,
            event_type=TraceEventType.EVIDENCE_SELECTED,
            metadata_={"included_count": len(content["evidence_inputs"])},
            actor_type=actor_type,
        )
        if content["excluded_evidence"]:
            reasons = sorted({e["exclusion_reason"] for e in content["excluded_evidence"]})
            cls._record_event(
                db,
                trace_id=trace.trace_id,
                event_type=TraceEventType.EVIDENCE_EXCLUDED,
                metadata_={"excluded_count": len(content["excluded_evidence"]),
                           "reasons": reasons},
                actor_type=actor_type,
            )
        cls._record_event(
            db,
            trace_id=trace.trace_id,
            event_type=TraceEventType.QUALITY_MEASURED,
            metadata_={"measurement_count": len(content["quality_measurements"])},
            actor_type=actor_type,
        )
        if content["structural_measurements"] is not None:
            cls._record_event(
                db,
                trace_id=trace.trace_id,
                event_type=TraceEventType.STRUCTURE_MEASURED,
                metadata_={
                    "structure_snapshot_internal_id":
                        content["structural_measurements"].get(
                            "structure_snapshot_internal_id"
                        ),
                },
                actor_type=actor_type,
            )
        cls._record_event(
            db,
            trace_id=trace.trace_id,
            event_type=TraceEventType.CONSISTENCY_ANALYZED,
            metadata_={
                "conflict_count": len(content["consistency"]["conflicts"]),
            },
            actor_type=actor_type,
        )
        for rule in content["rule_executions"]:
            cls._record_event(
                db,
                trace_id=trace.trace_id,
                event_type=TraceEventType.RULE_EXECUTED,
                metadata_={
                    "rule_id": rule["rule_id"],
                    "execution_order": rule["execution_order"],
                    "fired": rule["fired"],
                    "result": rule["result"],
                },
                actor_type=actor_type,
            )
        cls._record_event(
            db,
            trace_id=trace.trace_id,
            event_type=TraceEventType.INTEGRITY_COMPUTED,
            metadata_={"overall_status": content["final_result"]["overall_status"]},
            actor_type=actor_type,
        )

        # Only EVALUATION traces join the per-payment hash chain.
        previous = (
            cls._previous_finalized_evaluation(db, trace)
            if trace.trace_type == TraceType.EVALUATION
            else None
        )

        envelope = {
            "trace_id": trace.trace_id,
            "trace_type": trace.trace_type,
            "original_trace_id": trace.original_trace_id,
            "payment_id": trace.payment_id,
            "evaluated_at": trace.evaluated_at,
            "methodology_version": trace.methodology_version,
            "methodology_snapshot_hash": trace.methodology_snapshot_hash,
            "status": TraceStatus.COMPLETED,
            "previous_trace_hash": previous.trace_hash if previous else None,
        }

        payload = {
            "hash_domain": HASH_DOMAIN,
            "schema": TRACE_SCHEMA_VERSION,
            "envelope": envelope,
            "content": content,
        }
        # Store the canonicalized structure so the persisted JSONB is exactly
        # what was hashed (raw datetimes become canonical strings here).
        stored_payload = canonical_payload_for_storage(payload)
        text, digest = canonical_hash(stored_payload)

        trace.canonical_payload = stored_payload
        trace.trace_hash = digest
        trace.hash_algorithm = HASH_ALGORITHM
        trace.canonicalization_version = CANONICALIZATION_VERSION
        trace.previous_trace_id = previous.trace_id if previous else None
        trace.previous_trace_hash = previous.trace_hash if previous else None
        trace.overall_status = content["final_result"]["overall_status"]
        if snapshot is not None:
            trace.integrity_snapshot_internal_id = snapshot.internal_id
        trace.status = TraceStatus.COMPLETED
        trace.finalized_at = datetime.now(tz=timezone.utc)
        db.flush()

        cls._record_event(
            db,
            trace_id=trace.trace_id,
            event_type=TraceEventType.TRACE_FINALIZED,
            metadata_={
                "hash_algorithm": HASH_ALGORITHM,
                "canonicalization_version": CANONICALIZATION_VERSION,
                "chain_linked_to": trace.previous_trace_id,
            },
            actor_type=actor_type,
        )
        return trace

    @classmethod
    def _finalize_failed(
        cls,
        db: Session,
        trace: EvidenceIntegrityTrace,
        capture: dict[str, Any],
        exc: Exception,
        stage: str,
        actor_type: str,
    ) -> EvidenceIntegrityTrace:
        """
        Produce an auditable failure record.

        The failure record is itself hashed and chain-linked so failure
        history is as tamper-evident as success history.
        """
        cls._record_event(
            db,
            trace_id=trace.trace_id,
            event_type=TraceEventType.EVALUATION_FAILED,
            metadata_={
                "failure_stage": stage,
                "failure_category": type(exc).__name__,
            },
            actor_type=actor_type,
        )

        context = capture.get("evaluation_context") or {
            "payment_id": trace.payment_id,
            "evaluation_time": trace.evaluated_at,
            "timezone_normalization": "UTC",
            "methodology_version": trace.methodology_version,
        }

        content: dict[str, Any] = {
            "evaluation_context": context,
            "methodology": {
                "version": trace.methodology_version,
                "snapshot_hash": trace.methodology_snapshot_hash,
                "snapshot": EIS_V1.describe(),
            },
            "evidence_inputs": [],
            "excluded_evidence": [],
            "quality_measurements": [],
            "structural_measurements": None,
            "corroboration": {"record_internal_ids": [], "total_records": 0},
            "consistency": {"conflicts": []},
            "rule_executions": [],
            "intermediate_results": {},
            "counts": {},
            "final_result": None,
            "limitations": [
                "Evaluation did not complete — no integrity result was produced.",
            ],
            "explanation_lines": [],
            "failure": {
                "stage": stage,
                "category": type(exc).__name__,
                "detail": str(exc)[:300],
            },
        }

        previous = (
            cls._previous_finalized_evaluation(db, trace)
            if trace.trace_type == TraceType.EVALUATION
            else None
        )
        envelope = {
            "trace_id": trace.trace_id,
            "trace_type": trace.trace_type,
            "original_trace_id": trace.original_trace_id,
            "payment_id": trace.payment_id,
            "evaluated_at": trace.evaluated_at,
            "methodology_version": trace.methodology_version,
            "methodology_snapshot_hash": trace.methodology_snapshot_hash,
            "status": TraceStatus.FAILED,
            "previous_trace_hash": previous.trace_hash if previous else None,
        }

        payload = {
            "hash_domain": HASH_DOMAIN,
            "schema": TRACE_SCHEMA_VERSION,
            "envelope": envelope,
            "content": content,
        }
        stored_payload = canonical_payload_for_storage(payload)
        text, digest = canonical_hash(stored_payload)

        trace.canonical_payload = stored_payload
        trace.trace_hash = digest
        trace.hash_algorithm = HASH_ALGORITHM
        trace.canonicalization_version = CANONICALIZATION_VERSION
        trace.previous_trace_id = previous.trace_id if previous else None
        trace.previous_trace_hash = previous.trace_hash if previous else None
        trace.failure_stage = stage
        trace.failure_category = type(exc).__name__
        trace.failure_detail = str(exc)[:300]
        trace.status = TraceStatus.FAILED
        trace.finalized_at = datetime.now(tz=timezone.utc)
        db.flush()

        cls._record_event(
            db,
            trace_id=trace.trace_id,
            event_type=TraceEventType.TRACE_FINALIZED,
            metadata_={
                "hash_algorithm": HASH_ALGORITHM,
                "canonicalization_version": CANONICALIZATION_VERSION,
                "outcome": TraceStatus.FAILED,
            },
            actor_type=actor_type,
        )
        return trace

    # ------------------------------------------------------------------
    # Canonical content assembly
    # ------------------------------------------------------------------

    @staticmethod
    def _build_content(capture: dict[str, Any]) -> dict[str, Any]:
        """Assemble the auditable content sections from the engine capture."""
        structure = capture.get("structural_measurements")
        conflicts = capture.get("consistency_measurements", [])
        return {
            "evaluation_context": capture.get("evaluation_context"),
            "methodology": {
                "version": capture.get("evaluation_context", {}).get(
                    "methodology_version"
                ),
                "aggregation": EIS_V1.aggregation,
                "snapshot_hash": capture.get("methodology_snapshot_hash"),
                "snapshot": capture.get("methodology_snapshot"),
            },
            "evidence_inputs": capture.get("evidence_inputs", []),
            "excluded_evidence": capture.get("excluded_evidence", []),
            "quality_measurements": capture.get("quality_measurements", []),
            "structural_measurements": structure,
            "corroboration": capture.get("corroboration_measurements"),
            "consistency": {"conflicts": conflicts},
            "rule_executions": capture.get("rule_executions", []),
            "intermediate_results": capture.get("dimension_results"),
            "counts": capture.get("counts"),
            "final_result": capture.get("final_result"),
            "limitations": capture.get("limitations", []),
            "explanation_lines": capture.get("explanation_lines", []),
        }

    @staticmethod
    def _infer_failure_stage(capture: dict[str, Any]) -> str:
        """Best-effort pipeline stage attribution from what was captured."""
        if "final_result" in capture:
            return "RESULT_CAPTURED"
        if "rule_executions" in capture:
            return "RULE_EXECUTION"
        if "dimension_results" in capture:
            return "DIMENSION_COMPUTATION"
        if "quality_measurements" in capture:
            return "MEASUREMENT_CAPTURE"
        if "evidence_inputs" in capture:
            return "INPUT_CAPTURE"
        return "EVALUATION_START"

    # ------------------------------------------------------------------
    # Audit events
    # ------------------------------------------------------------------

    @staticmethod
    def _next_sequence_number(db: Session, trace_id: str) -> int:
        last = db.execute(
            select(IntegrityTraceEvent.sequence_number)
            .where(IntegrityTraceEvent.trace_id == trace_id)
            .order_by(IntegrityTraceEvent.sequence_number.desc())
        ).scalars().first()
        return (last or 0) + 1

    @classmethod
    def _record_event(
        cls,
        db: Session,
        trace_id: str,
        event_type: str,
        metadata_: dict[str, Any] | None = None,
        actor_type: str = ActorType.SYSTEM,
    ) -> IntegrityTraceEvent:
        event = IntegrityTraceEvent(
            event_id=cls._new_id(),
            trace_id=trace_id,
            sequence_number=cls._next_sequence_number(db, trace_id),
            event_type=event_type,
            occurred_at=datetime.now(tz=timezone.utc),
            actor_type=actor_type,
            event_metadata=metadata_,
        )
        db.add(event)
        db.flush()
        return event

    # ------------------------------------------------------------------
    # Lookup helpers
    # ------------------------------------------------------------------

    @staticmethod
    def get_by_trace_id(db: Session, trace_id: str) -> EvidenceIntegrityTrace | None:
        return db.execute(
            select(EvidenceIntegrityTrace).where(
                EvidenceIntegrityTrace.trace_id == trace_id
            )
        ).scalar_one_or_none()

    @staticmethod
    def list_payment_traces(
        db: Session,
        payment_id: str,
        include_replays: bool = False,
    ) -> list[EvidenceIntegrityTrace]:
        stmt = select(EvidenceIntegrityTrace).where(
            EvidenceIntegrityTrace.payment_id == payment_id
        )
        if not include_replays:
            stmt = stmt.where(EvidenceIntegrityTrace.trace_type == TraceType.EVALUATION)
        stmt = stmt.order_by(
            EvidenceIntegrityTrace.evaluated_at.asc(),
            EvidenceIntegrityTrace.internal_id.asc(),
        )
        return list(db.execute(stmt).scalars().all())

    @classmethod
    def _find_completed_evaluation(
        cls,
        db: Session,
        payment_id: str,
        evaluation_time: datetime,
        methodology_version: str,
    ) -> EvidenceIntegrityTrace | None:
        return db.execute(
            select(EvidenceIntegrityTrace).where(
                EvidenceIntegrityTrace.payment_id == payment_id,
                EvidenceIntegrityTrace.evaluated_at == evaluation_time,
                EvidenceIntegrityTrace.methodology_version == methodology_version,
                EvidenceIntegrityTrace.trace_type == TraceType.EVALUATION,
                EvidenceIntegrityTrace.status == TraceStatus.COMPLETED,
            )
        ).scalar_one_or_none()

    @staticmethod
    def _previous_finalized_evaluation(
        db: Session,
        trace: EvidenceIntegrityTrace,
    ) -> EvidenceIntegrityTrace | None:
        """
        The immediately preceding FINALIZED EVALUATION trace for this payment,
        ordered by (evaluated_at, internal_id). REPLAY traces never join the
        evaluation hash chain.
        """
        return db.execute(
            select(EvidenceIntegrityTrace)
            .where(
                EvidenceIntegrityTrace.payment_id == trace.payment_id,
                EvidenceIntegrityTrace.trace_type == TraceType.EVALUATION,
                EvidenceIntegrityTrace.status.in_([TraceStatus.COMPLETED, TraceStatus.FAILED]),
                EvidenceIntegrityTrace.internal_id < trace.internal_id,
            )
            .order_by(
                EvidenceIntegrityTrace.evaluated_at.desc(),
                EvidenceIntegrityTrace.internal_id.desc(),
            )
        ).scalars().first()

    @staticmethod
    def _new_id() -> str:
        return str(uuid.uuid4())
