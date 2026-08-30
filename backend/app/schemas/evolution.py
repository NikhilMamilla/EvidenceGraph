"""
Phase 11 — Evidence Temporal Evolution Pydantic Schemas.

Read-only response schemas for the evolution API endpoints.

Follows the same pattern as schemas/integrity.py:
- ConfigDict(from_attributes=True) for ORM compatibility
- from_snapshot / from_change classmethods for clean construction from ORM objects
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class StateSnapshotItem(BaseModel):
    """
    Trimmed representation of a single EvidenceStateSnapshot for list and
    detail views.

    Maps internal_id → snapshot_id so that API consumers never see the
    database-internal primary key name.
    """

    snapshot_id: int
    payment_id: str
    evaluation_time: datetime
    overall_integrity_status: str
    evidence_count: int
    source_count: int
    claim_count: int
    conflict_count: int
    open_conflict_count: int
    corroboration_status: str
    independence_status: str
    freshness_status: str
    consistency_status: str
    methodology_version: str
    integrity_trace_id: str | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

    @classmethod
    def from_snapshot(cls, snap, integrity_trace_id: str | None = None) -> "StateSnapshotItem":
        """
        Build from an EvidenceStateSnapshot ORM instance.

        The ORM model uses ``internal_id`` as its primary key; this classmethod
        maps that to the public ``snapshot_id`` field so the API surface is
        stable even if the column is renamed in a future migration.

        Args:
            snap: An ``EvidenceStateSnapshot`` ORM instance.
            integrity_trace_id: Optional trace identifier to attach for
                observability.  Not stored on the ORM model itself.

        Returns:
            A fully populated ``StateSnapshotItem``.
        """
        return cls(
            snapshot_id=snap.internal_id,
            payment_id=snap.payment_id,
            evaluation_time=snap.evaluation_time,
            overall_integrity_status=snap.overall_integrity_status,
            evidence_count=snap.evidence_count,
            source_count=snap.source_count,
            claim_count=snap.claim_count,
            conflict_count=snap.conflict_count,
            open_conflict_count=snap.open_conflict_count,
            corroboration_status=snap.corroboration_status,
            independence_status=snap.independence_status,
            freshness_status=snap.freshness_status,
            consistency_status=snap.consistency_status,
            methodology_version=snap.methodology_version,
            integrity_trace_id=integrity_trace_id,
            created_at=snap.created_at,
        )


class StateHistoryResponse(BaseModel):
    """
    Paginated list of EvidenceStateSnapshot records for a single payment.

    Returned by GET /api/v1/payments/{payment_id}/evolution/history.
    """

    payment_id: str
    history: list[StateSnapshotItem]
    total: int


class ChangeItem(BaseModel):
    """
    Representation of a single EvidenceStateChange record for list views.

    Exposes the UUID change_id and human-readable dimension / causality fields.
    The two snapshot FK columns are surfaced as integer IDs matching the
    ``snapshot_id`` field on :class:`StateSnapshotItem`.
    """

    change_id: str
    payment_id: str
    detected_at: datetime
    change_type: str
    dimension: str
    previous_value: str | None = None
    current_value: str | None = None
    direct_cause: str | None = None
    causality: str | None = None
    explanation: str | None = None
    magnitude: str | None = None
    linked_evidence_id: int | None = None
    linked_conflict_id: int | None = None
    methodology_version: str | None = None
    previous_snapshot_id: int
    current_snapshot_id: int

    model_config = ConfigDict(from_attributes=True)

    @classmethod
    def from_change(cls, change) -> "ChangeItem":
        """
        Build from an EvidenceStateChange ORM instance.

        Args:
            change: An ``EvidenceStateChange`` ORM instance.

        Returns:
            A fully populated ``ChangeItem``.
        """
        return cls(
            change_id=change.change_id,
            payment_id=change.payment_id,
            detected_at=change.detected_at,
            change_type=change.change_type,
            dimension=change.dimension,
            previous_value=change.previous_value,
            current_value=change.current_value,
            direct_cause=change.direct_cause,
            causality=change.causality,
            explanation=change.explanation,
            magnitude=change.magnitude,
            linked_evidence_id=change.linked_evidence_id,
            linked_conflict_id=change.linked_conflict_id,
            methodology_version=change.methodology_version,
            previous_snapshot_id=change.previous_snapshot_id,
            current_snapshot_id=change.current_snapshot_id,
        )


class EvidenceChangesResponse(BaseModel):
    """
    Paginated list of EvidenceStateChange records for a single payment.

    Returned by GET /api/v1/payments/{payment_id}/evolution/changes.
    An optional dimension_filter is echoed back so the caller can confirm
    which filter was applied server-side.
    """

    payment_id: str
    changes: list[ChangeItem]
    total: int
    dimension_filter: str | None = None


class ChangeDetailResponse(BaseModel):
    """
    Full detail view of a single EvidenceStateChange record.

    Identical to :class:`ChangeItem` but also includes the ``created_at``
    audit timestamp that is omitted from list views for brevity.

    Returned by GET /api/v1/payments/{payment_id}/evolution/changes/{change_id}.
    """

    change_id: str
    payment_id: str
    detected_at: datetime
    change_type: str
    dimension: str
    previous_value: str | None = None
    current_value: str | None = None
    direct_cause: str | None = None
    causality: str | None = None
    explanation: str | None = None
    magnitude: str | None = None
    linked_evidence_id: int | None = None
    linked_conflict_id: int | None = None
    methodology_version: str | None = None
    previous_snapshot_id: int
    current_snapshot_id: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class RecomputeResponse(BaseModel):
    """
    Result of triggering a fresh integrity evaluation and evolution diff.

    Returned by POST /api/v1/payments/{payment_id}/evolution/recompute.

    Fields:
        payment_id:        The payment that was re-evaluated.
        new_snapshot:      The freshly created state snapshot.
        changes_detected:  All change records produced by the diff against the
                           previous snapshot.  Empty list when no material
                           change was found.
        change_count:      Convenience count — equals ``len(changes_detected)``.
        no_material_change: True when the new snapshot is functionally identical
                            to the previous one (no change records were written).
    """

    payment_id: str
    new_snapshot: StateSnapshotItem
    changes_detected: list[ChangeItem]
    change_count: int
    no_material_change: bool
