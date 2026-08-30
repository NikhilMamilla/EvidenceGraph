"""
Phase 11 — Evidence State Snapshot Service.

Reads already-persisted Phase 6/7/8/9 data to produce an ``EvidenceStateSnapshot``
— a denormalised, point-in-time summary of evidence quality for a single payment.

Design contracts:
  - NEVER calls ``IntegrityEngine.compute_integrity`` or any other computation
    engine.  The service is strictly a *reader* of existing snapshot data.
  - Idempotent: ``(payment_id, evaluation_time, methodology_version)`` is a
    unique identity triple.  If a snapshot already exists for that triple it
    is returned without creating a duplicate row.
  - Precondition: a Phase 9 ``EvidenceIntegritySnapshot`` for the same identity
    triple MUST exist before ``take_snapshot`` is called.  ``ValueError`` is
    raised if it is absent — the caller is responsible for running the Phase 9
    pipeline first.
  - Race-condition safety: a database-level ``IntegrityError`` on concurrent
    inserts is caught, the session is rolled back to a clean state, and the
    existing row is re-queried and returned.
  - No fraud detection, risk scoring, or ML of any kind.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.evidence_integrity import EvidenceIntegritySnapshot
from app.models.evidence_structure import Claim, EvidenceStructureSnapshot
from app.models.evolution_models import EvidenceStateSnapshot
from app.models.integrity_types import INTEGRITY_METHODOLOGY_VERSION

logger = logging.getLogger(__name__)


class EvidenceStateSnapshotService:
    """
    Creates ``EvidenceStateSnapshot`` rows by projecting Phase 9 integrity
    snapshot data into a flat, diff-friendly record.

    All methods are classmethods — the class carries no instance state.
    """

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    @classmethod
    def take_snapshot(
        cls,
        db: Session,
        payment_id: str,
        evaluation_time: datetime,
        methodology_version: str = INTEGRITY_METHODOLOGY_VERSION,
    ) -> EvidenceStateSnapshot:
        """
        Read from existing Phase 9 data and create (or return) an
        ``EvidenceStateSnapshot``.

        Parameters
        ----------
        db : Session
            SQLAlchemy session.  Caller controls the transaction.
        payment_id : str
            The payment ID to snapshot.
        evaluation_time : datetime
            Timezone-aware UTC temporal anchor.  Only evidence observed at or
            before this instant is reflected in the snapshot.
        methodology_version : str
            Methodology version string used for the Phase 9 evaluation.
            Defaults to ``INTEGRITY_METHODOLOGY_VERSION``.

        Returns
        -------
        EvidenceStateSnapshot
            The created or existing snapshot (flushed to session, not committed).

        Raises
        ------
        ValueError
            If no Phase 9 ``EvidenceIntegritySnapshot`` exists for the same
            identity triple.  The caller must run Phase 9 first.
        """
        start = time.perf_counter()

        # ------------------------------------------------------------------
        # Idempotency check — return existing row if already present
        # ------------------------------------------------------------------
        existing = db.execute(
            select(EvidenceStateSnapshot).where(
                EvidenceStateSnapshot.payment_id == payment_id,
                EvidenceStateSnapshot.evaluation_time == evaluation_time,
                EvidenceStateSnapshot.methodology_version == methodology_version,
            )
        ).scalar_one_or_none()

        if existing is not None:
            logger.debug(
                "Evolution snapshot already exists — returning existing",
                extra={
                    "payment_id": payment_id,
                    "evaluation_time": evaluation_time.isoformat(),
                    "methodology_version": methodology_version,
                },
            )
            return existing

        # ------------------------------------------------------------------
        # Load the Phase 9 integrity snapshot (precondition)
        # ------------------------------------------------------------------
        integrity_snapshot = db.execute(
            select(EvidenceIntegritySnapshot).where(
                EvidenceIntegritySnapshot.payment_id == payment_id,
                EvidenceIntegritySnapshot.evaluated_at == evaluation_time,
                EvidenceIntegritySnapshot.methodology_version == methodology_version,
            )
        ).scalar_one_or_none()

        if integrity_snapshot is None:
            raise ValueError(
                f"No Phase 9 EvidenceIntegritySnapshot found for payment_id={payment_id!r} "
                f"evaluated_at={evaluation_time.isoformat()} "
                f"methodology_version={methodology_version!r}. "
                "Run Phase 9 integrity computation before calling take_snapshot."
            )

        # ------------------------------------------------------------------
        # Read scalar fields directly from the integrity snapshot
        # ------------------------------------------------------------------
        corroboration_status = cls._extract_result_status(
            integrity_snapshot.corroboration_result, default="UNKNOWN"
        )
        independence_status = cls._extract_result_status(
            integrity_snapshot.independence_result, default="UNKNOWN"
        )
        freshness_status = cls._resolve_freshness_status(integrity_snapshot)
        consistency_status = cls._extract_result_status(
            integrity_snapshot.consistency_result, default="NO_DETECTED_CONFLICT"
        )
        claim_count = cls._resolve_claim_count(db, payment_id, evaluation_time)

        # ------------------------------------------------------------------
        # Build and persist the new snapshot
        # ------------------------------------------------------------------
        snapshot = EvidenceStateSnapshot(
            payment_id=payment_id,
            evaluation_time=evaluation_time,
            integrity_snapshot_id=integrity_snapshot.internal_id,
            overall_integrity_status=integrity_snapshot.overall_status,
            evidence_count=integrity_snapshot.evidence_count,
            source_count=integrity_snapshot.source_count,
            claim_count=claim_count,
            conflict_count=integrity_snapshot.conflict_count,
            open_conflict_count=integrity_snapshot.open_conflict_count,
            corroboration_status=corroboration_status,
            independence_status=independence_status,
            freshness_status=freshness_status,
            consistency_status=consistency_status,
            methodology_version=methodology_version,
        )

        try:
            db.add(snapshot)
            db.flush()
        except IntegrityError:
            db.rollback()
            # Race condition: another process created the same snapshot concurrently.
            # Re-query and return the winning row.
            existing = db.execute(
                select(EvidenceStateSnapshot).where(
                    EvidenceStateSnapshot.payment_id == payment_id,
                    EvidenceStateSnapshot.evaluation_time == evaluation_time,
                    EvidenceStateSnapshot.methodology_version == methodology_version,
                )
            ).scalar_one()
            logger.debug(
                "Evolution snapshot race — returning row created by concurrent process",
                extra={
                    "payment_id": payment_id,
                    "evaluation_time": evaluation_time.isoformat(),
                    "methodology_version": methodology_version,
                },
            )
            return existing

        duration_ms = round((time.perf_counter() - start) * 1000, 2)
        logger.info(
            "Evidence state snapshot created",
            extra={
                "payment_id": payment_id,
                "evaluation_time": evaluation_time.isoformat(),
                "methodology_version": methodology_version,
                "overall_integrity_status": snapshot.overall_integrity_status,
                "evidence_count": snapshot.evidence_count,
                "claim_count": snapshot.claim_count,
                "snapshot_internal_id": snapshot.internal_id,
                "creation_duration_ms": duration_ms,
            },
        )

        return snapshot

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @classmethod
    def _resolve_freshness_status(
        cls, integrity_snapshot: EvidenceIntegritySnapshot
    ) -> str:
        """
        Extract the aggregate freshness status string from the Phase 9
        ``freshness_result`` JSONB field.

        Returns ``"UNKNOWN"`` if ``freshness_result`` is ``None``, not a
        dict, or does not contain a ``"status"`` key.
        """
        return cls._extract_result_status(
            integrity_snapshot.freshness_result, default="UNKNOWN"
        )

    @classmethod
    def _resolve_claim_count(
        cls,
        db: Session,
        payment_id: str,
        evaluation_time: datetime,
    ) -> int:
        """
        Return the number of distinct canonical claims for the payment at
        ``evaluation_time``.

        Primary source:
            The most recent ``EvidenceStructureSnapshot.distinct_claims``
            whose ``evaluated_at`` is at or before ``evaluation_time``.

        Fallback (no structure snapshot):
            Count ``Claim`` records whose subject is the payment that were
            created at or before ``evaluation_time``.
        """
        # Primary: latest EvidenceStructureSnapshot at or before evaluation_time
        structure_snapshot = db.execute(
            select(EvidenceStructureSnapshot).where(
                EvidenceStructureSnapshot.payment_id == payment_id,
                EvidenceStructureSnapshot.evaluated_at <= evaluation_time,
            ).order_by(EvidenceStructureSnapshot.evaluated_at.desc())
        ).scalars().first()

        if structure_snapshot is not None:
            logger.debug(
                "Resolved claim_count from EvidenceStructureSnapshot",
                extra={
                    "payment_id": payment_id,
                    "structure_snapshot_id": structure_snapshot.internal_id,
                    "distinct_claims": structure_snapshot.distinct_claims,
                },
            )
            return structure_snapshot.distinct_claims

        # Fallback: count Claim records for this payment
        from app.models.evidence_structure import EvidenceClaimLink
        from app.models.evidence import EvidenceObservation
        from app.models.evidence_types import SubjectType

        claim_count = (
            db.query(Claim.internal_id)
            .join(EvidenceClaimLink, EvidenceClaimLink.claim_id == Claim.internal_id)
            .join(
                EvidenceObservation,
                EvidenceObservation.internal_id == EvidenceClaimLink.evidence_id,
            )
            .filter(
                EvidenceObservation.subject_type == SubjectType.PAYMENT,
                EvidenceObservation.subject_id == payment_id,
                EvidenceObservation.observed_at <= evaluation_time,
            )
            .distinct()
            .count()
        )

        logger.debug(
            "Resolved claim_count from Claim table (no structure snapshot found)",
            extra={
                "payment_id": payment_id,
                "claim_count": claim_count,
            },
        )
        return claim_count

    # ------------------------------------------------------------------
    # Internal utility
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_result_status(
        result: dict | None,
        default: str,
    ) -> str:
        """
        Safely extract ``result["status"]`` from a JSONB dimension result dict.

        Returns ``default`` if:
          - ``result`` is ``None``
          - ``result`` is not a dict
          - ``"status"`` key is absent
          - The ``"status"`` value is ``None`` or an empty string
        """
        if not isinstance(result, dict):
            return default
        status = result.get("status")
        if not status:
            return default
        return str(status)
