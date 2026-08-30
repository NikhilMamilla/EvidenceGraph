"""
Evidence Quality Engine — Phase 6.

Coordinates the measurement pipeline:
  Evidence → Freshness → Source → Reliability → QualitySnapshot

Design:
  - Called with an explicit evaluation_time so all measurements are deterministic.
  - Creates EvidenceQualitySnapshot records — never mutates EvidenceObservation.
  - Does NOT produce an Evidence Integrity Score.
  - Supports re-evaluation at a different timestamp to track freshness decay.
  - Logs structured observability fields per measurement.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.evidence import EvidenceObservation
from app.models.evidence_quality import EvidenceQualitySnapshot
from app.models.evidence_types import SubjectType
from app.services.freshness_service import freshness_service
from app.services.reliability_service import reliability_service
from app.services.source_service import source_service

logger = logging.getLogger(__name__)


def measure_evidence_quality(
    observation: EvidenceObservation,
    evaluation_time: datetime,
    db: Session,
) -> EvidenceQualitySnapshot:
    """
    Run the full quality measurement pipeline for one evidence observation.

    Creates and persists an EvidenceQualitySnapshot evaluated at the given time.
    Does NOT commit — the caller controls the transaction boundary.

    Parameters
    ----------
    observation : EvidenceObservation
        The evidence to measure.
    evaluation_time : datetime
        Explicit, timezone-aware UTC timestamp for the evaluation.
        The caller must supply this — the engine never calls datetime.now().
    db : Session
        SQLAlchemy session. The snapshot is added but not committed.

    Returns
    -------
    EvidenceQualitySnapshot
        The created (but not yet committed) snapshot.
    """
    if evaluation_time.tzinfo is None:
        raise ValueError("evaluation_time must be timezone-aware")

    start = time.perf_counter()

    # 1. Freshness measurement
    freshness = freshness_service.measure(observation, evaluation_time)

    # 2. Source quality
    source = source_service.classify(observation)

    # 3. Historical reliability
    reliability = reliability_service.assess(observation, db=db)

    # 4. Build snapshot
    snapshot = EvidenceQualitySnapshot(
        evidence_id=observation.internal_id,
        evaluated_at=evaluation_time,
        # Freshness
        age_seconds=freshness.age_seconds,
        freshness_state=freshness.freshness_state,
        freshness_policy_key=freshness.policy_key,
        freshness_methodology_version=freshness.methodology_version,
        # Source
        source_type=source.source_type,
        source_directness=source.directness,
        source_authority_level=source.authority_level,
        source_methodology_version=source.methodology_version,
        # Reliability
        historical_reliability_status=reliability.status,
        reliability_sample_count=reliability.sample_count,
        reliability_methodology_version=reliability.methodology_version,
        # Provenance metadata
        snapshot_metadata={
            "freshness_explanation": f"Policy: {freshness.policy_key}",
            "source_description": source.description,
            "reliability_explanation": reliability.explanation,
        },
    )

    db.add(snapshot)

    duration_ms = round((time.perf_counter() - start) * 1000, 2)
    logger.info(
        "Evidence quality measured",
        extra={
            "evidence_id": observation.internal_id,
            "evidence_type": observation.evidence_type,
            "measurement_type": "quality_snapshot",
            "evaluation_time": evaluation_time.isoformat(),
            "freshness_state": freshness.freshness_state,
            "age_seconds": freshness.age_seconds,
            "source_type": source.source_type,
            "source_directness": source.directness,
            "historical_reliability_status": reliability.status,
            "freshness_methodology_version": freshness.methodology_version,
            "source_methodology_version": source.methodology_version,
            "reliability_methodology_version": reliability.methodology_version,
            "measurement_duration_ms": duration_ms,
        },
    )

    return snapshot


def measure_quality_for_observations(
    observations: list[EvidenceObservation],
    evaluation_time: datetime,
    db: Session,
) -> list[EvidenceQualitySnapshot]:
    """
    Measure quality for a list of evidence observations.

    Returns a list of snapshots (all added to the session, not committed).
    """
    snapshots = []
    for obs in observations:
        snap = measure_evidence_quality(obs, evaluation_time, db)
        snapshots.append(snap)
    return snapshots


def measure_quality_for_payment(
    payment_subject_id: str,
    evaluation_time: datetime,
    db: Session,
) -> list[EvidenceQualitySnapshot]:
    """
    Load all evidence for a payment and measure quality at evaluation_time.

    Creates new snapshots — does NOT delete old ones. Snapshot history is preserved.
    Used for ad-hoc re-evaluation (e.g. to observe freshness decay).
    Commits after creating all snapshots.
    """
    from sqlalchemy import select

    observations = db.execute(
        select(EvidenceObservation)
        .where(
            EvidenceObservation.subject_type == SubjectType.PAYMENT,
            EvidenceObservation.subject_id == payment_subject_id,
        )
    ).scalars().all()

    snapshots = measure_quality_for_observations(list(observations), evaluation_time, db)
    db.commit()

    logger.info(
        "Payment quality measurement complete",
        extra={
            "payment_subject_id": payment_subject_id,
            "snapshots_created": len(snapshots),
            "evaluation_time": evaluation_time.isoformat(),
        },
    )
    return snapshots
