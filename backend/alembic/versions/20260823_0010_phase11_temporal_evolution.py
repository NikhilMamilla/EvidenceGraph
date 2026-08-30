"""Phase 11 — Evidence Temporal Evolution & Change Intelligence

Revision ID: 0010_phase11
Revises: 0009_phase10
Create Date: 2026-08-23

Creates tables:
  1. evidence_state_snapshots
     Denormalised, point-in-time summary of evidence quality dimensions for
     one payment at one specific evaluation time and methodology version.
     Immutable append-only log — rows are never updated after creation.
     The unique constraint on (payment_id, evaluation_time, methodology_version)
     enforces idempotency and prevents duplicate snapshots.

  2. evidence_state_changes
     One row per observable dimension change detected between two consecutive
     EvidenceStateSnapshot records.  References predecessor and successor
     snapshots via FK so that the full before/after context is always
     recoverable.  Optional FKs into evidence_observations and
     evidence_conflicts allow direct causality tracing.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0010_phase11"
down_revision: Union[str, None] = "0009_phase10"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 1. evidence_state_snapshots  (no inbound FKs from phase 11 tables)
    # ------------------------------------------------------------------
    op.create_table(
        "evidence_state_snapshots",
        sa.Column("internal_id", sa.Integer(), autoincrement=True, nullable=False),
        # Identity
        sa.Column("payment_id", sa.String(128), nullable=False),
        sa.Column("evaluation_time", sa.DateTime(timezone=True), nullable=False),
        # Phase 9 linkage
        sa.Column(
            "integrity_snapshot_id",
            sa.Integer(),
            sa.ForeignKey("evidence_integrity_snapshots.internal_id"),
            nullable=False,
        ),
        # Overall result
        sa.Column("overall_integrity_status", sa.String(32), nullable=False),
        # Evidence scope counters
        sa.Column(
            "evidence_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "source_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "claim_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "conflict_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "open_conflict_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        # Dimension status fields
        sa.Column(
            "corroboration_status",
            sa.String(64),
            nullable=False,
            server_default=sa.text("'UNKNOWN'"),
        ),
        sa.Column(
            "independence_status",
            sa.String(64),
            nullable=False,
            server_default=sa.text("'UNKNOWN'"),
        ),
        sa.Column(
            "freshness_status",
            sa.String(32),
            nullable=False,
            server_default=sa.text("'UNKNOWN'"),
        ),
        sa.Column(
            "consistency_status",
            sa.String(64),
            nullable=False,
            server_default=sa.text("'NO_DETECTED_CONFLICT'"),
        ),
        # Methodology
        sa.Column("methodology_version", sa.String(16), nullable=False),
        # Audit
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("internal_id"),
        sa.UniqueConstraint(
            "payment_id",
            "evaluation_time",
            "methodology_version",
            name="uq_evidence_state_snapshot",
        ),
    )

    op.create_index(
        "ix_evidence_state_snapshot_payment_id",
        "evidence_state_snapshots",
        ["payment_id"],
    )
    op.create_index(
        "ix_evidence_state_snapshot_evaluation_time",
        "evidence_state_snapshots",
        ["evaluation_time"],
    )

    # ------------------------------------------------------------------
    # 2. evidence_state_changes  (FKs → evidence_state_snapshots above)
    # ------------------------------------------------------------------
    op.create_table(
        "evidence_state_changes",
        sa.Column("internal_id", sa.Integer(), autoincrement=True, nullable=False),
        # Identity
        sa.Column("change_id", sa.String(36), nullable=False),
        sa.Column("payment_id", sa.String(128), nullable=False),
        # Snapshot references
        sa.Column(
            "previous_snapshot_id",
            sa.Integer(),
            sa.ForeignKey("evidence_state_snapshots.internal_id"),
            nullable=False,
        ),
        sa.Column(
            "current_snapshot_id",
            sa.Integer(),
            sa.ForeignKey("evidence_state_snapshots.internal_id"),
            nullable=False,
        ),
        # Change description
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("change_type", sa.String(64), nullable=False),
        sa.Column("dimension", sa.String(64), nullable=False),
        sa.Column("previous_value", sa.String(256), nullable=True),
        sa.Column("current_value", sa.String(256), nullable=True),
        # Causality
        sa.Column("direct_cause", sa.String(64), nullable=True),
        sa.Column("causality", sa.String(16), nullable=True),
        sa.Column("explanation", sa.Text(), nullable=True),
        sa.Column("magnitude", sa.String(16), nullable=True),
        # Optional Phase 4–8 record linkage
        sa.Column(
            "linked_evidence_id",
            sa.Integer(),
            sa.ForeignKey("evidence_observations.internal_id"),
            nullable=True,
        ),
        sa.Column(
            "linked_conflict_id",
            sa.Integer(),
            sa.ForeignKey("evidence_conflicts.internal_id"),
            nullable=True,
        ),
        # Methodology
        sa.Column("methodology_version", sa.String(16), nullable=True),
        # Audit
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("internal_id"),
        sa.UniqueConstraint("change_id", name="uq_evidence_state_change_id"),
        sa.UniqueConstraint(
            "previous_snapshot_id",
            "current_snapshot_id",
            "change_type",
            "dimension",
            name="uq_evidence_state_change_pair",
        ),
    )

    op.create_index(
        "ix_evidence_state_change_payment_id",
        "evidence_state_changes",
        ["payment_id"],
    )
    op.create_index(
        "ix_evidence_state_change_detected_at",
        "evidence_state_changes",
        ["detected_at"],
    )
    op.create_index(
        "ix_evidence_state_change_dimension",
        "evidence_state_changes",
        ["dimension"],
    )


def downgrade() -> None:
    # Drop in reverse FK order: changes first, then snapshots
    op.drop_index(
        "ix_evidence_state_change_dimension", table_name="evidence_state_changes"
    )
    op.drop_index(
        "ix_evidence_state_change_detected_at", table_name="evidence_state_changes"
    )
    op.drop_index(
        "ix_evidence_state_change_payment_id", table_name="evidence_state_changes"
    )
    op.drop_table("evidence_state_changes")

    op.drop_index(
        "ix_evidence_state_snapshot_evaluation_time",
        table_name="evidence_state_snapshots",
    )
    op.drop_index(
        "ix_evidence_state_snapshot_payment_id",
        table_name="evidence_state_snapshots",
    )
    op.drop_table("evidence_state_snapshots")
