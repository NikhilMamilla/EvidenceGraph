"""
Phase 9 — Evidence Integrity Pydantic Schemas.

Read-only response schemas for the integrity API.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class DimensionResultSchema(BaseModel):
    """Structured result for a single integrity dimension."""

    status: str = Field(description="Dimension status constant.")
    reason: str = Field(description="One-sentence explanation of the status.")
    inputs: dict[str, Any] = Field(
        default_factory=dict,
        description="The actual data values used to produce this dimension result.",
    )

    model_config = {"from_attributes": True}


class IntegritySnapshotResponse(BaseModel):
    """
    Full Evidence Integrity assessment for a payment.

    Returned by GET /api/v1/payments/{payment_id}/integrity.
    """

    payment_id: str
    evaluated_at: datetime
    methodology_version: str

    overall_status: str = Field(
        description=(
            "Overall evidence integrity classification. "
            "One of: VERY_STRONG, STRONG, LIMITED, WEAK, INSUFFICIENT_DATA, UNRESOLVED."
        )
    )

    evidence_count: int = Field(description="Number of evidence observations in scope.")
    source_count: int = Field(description="Number of distinct source types in scope.")
    conflict_count: int = Field(description="Total detected conflicts.")
    open_conflict_count: int = Field(
        description="Open conflicts with severity > INFO."
    )

    freshness_result: DimensionResultSchema | None = None
    source_result: DimensionResultSchema | None = None
    independence_result: DimensionResultSchema | None = None
    corroboration_result: DimensionResultSchema | None = None
    consistency_result: DimensionResultSchema | None = None

    explanation_lines: list[str] = Field(
        default_factory=list,
        description=(
            "Deterministic, human-readable explanation of the overall status. "
            "Generated from actual data — no LLM, no overclaiming."
        ),
    )
    limitations: list[str] = Field(
        default_factory=list,
        description=(
            "Explicit limitations of this integrity assessment. "
            "Missing information is represented here, not silently assumed."
        ),
    )

    created_at: datetime

    model_config = {"from_attributes": True}

    @classmethod
    def from_snapshot(cls, snap) -> "IntegritySnapshotResponse":
        """Build from an EvidenceIntegritySnapshot ORM instance."""

        def _dim(raw: dict | None) -> DimensionResultSchema | None:
            if raw is None:
                return None
            return DimensionResultSchema(
                status=raw.get("status", "UNKNOWN"),
                reason=raw.get("reason", ""),
                inputs=raw.get("inputs", {}),
            )

        return cls(
            payment_id=snap.payment_id,
            evaluated_at=snap.evaluated_at,
            methodology_version=snap.methodology_version,
            overall_status=snap.overall_status,
            evidence_count=snap.evidence_count,
            source_count=snap.source_count,
            conflict_count=snap.conflict_count,
            open_conflict_count=snap.open_conflict_count,
            freshness_result=_dim(snap.freshness_result),
            source_result=_dim(snap.source_result),
            independence_result=_dim(snap.independence_result),
            corroboration_result=_dim(snap.corroboration_result),
            consistency_result=_dim(snap.consistency_result),
            explanation_lines=snap.explanation_lines or [],
            limitations=snap.limitations or [],
            created_at=snap.created_at,
        )


class IntegrityHistoryItem(BaseModel):
    """Trimmed representation of a historical integrity snapshot for list views."""

    payment_id: str
    evaluated_at: datetime
    methodology_version: str
    overall_status: str
    evidence_count: int
    conflict_count: int
    open_conflict_count: int
    created_at: datetime

    model_config = {"from_attributes": True}

    @classmethod
    def from_snapshot(cls, snap) -> "IntegrityHistoryItem":
        return cls(
            payment_id=snap.payment_id,
            evaluated_at=snap.evaluated_at,
            methodology_version=snap.methodology_version,
            overall_status=snap.overall_status,
            evidence_count=snap.evidence_count,
            conflict_count=snap.conflict_count,
            open_conflict_count=snap.open_conflict_count,
            created_at=snap.created_at,
        )


class IntegrityHistoryResponse(BaseModel):
    """List of historical integrity snapshots for a payment."""

    payment_id: str
    history: list[IntegrityHistoryItem]
    total: int
