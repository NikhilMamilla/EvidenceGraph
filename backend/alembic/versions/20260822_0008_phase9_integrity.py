"""Phase 9 — Evidence Integrity Snapshots

Revision ID: 0008_phase9
Revises: 0007_phase8
Create Date: 2026-08-22

Creates tables:
  1. evidence_integrity_snapshots
     Point-in-time assessments of evidence quality and internal consistency.
     Immutable historical records — one row per (payment_id, evaluated_at, methodology_version).
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008_phase9"
down_revision: Union[str, None] = "0007_phase8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "evidence_integrity_snapshots",
        sa.Column("internal_id", sa.Integer(), autoincrement=True, nullable=False),
        # Identity
        sa.Column("payment_id", sa.String(128), nullable=False),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("methodology_version", sa.String(16), nullable=False),
        # Overall result
        sa.Column("overall_status", sa.String(32), nullable=False),
        # Evidence scope
        sa.Column("evidence_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("source_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("conflict_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("open_conflict_count", sa.Integer(), nullable=False, server_default="0"),
        # Dimension results (JSONB — {status, reason, inputs})
        sa.Column("freshness_result", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("source_result", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("independence_result", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("corroboration_result", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("consistency_result", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        # Explanation and limitations
        sa.Column("explanation_lines", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("limitations", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
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
            "evaluated_at",
            "methodology_version",
            name="uq_integrity_snapshot",
        ),
    )

    op.create_index(
        "ix_integrity_snapshot_payment_id",
        "evidence_integrity_snapshots",
        ["payment_id"],
    )
    op.create_index(
        "ix_integrity_snapshot_evaluated_at",
        "evidence_integrity_snapshots",
        ["evaluated_at"],
    )
    op.create_index(
        "ix_integrity_snapshot_overall_status",
        "evidence_integrity_snapshots",
        ["overall_status"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_integrity_snapshot_overall_status",
        table_name="evidence_integrity_snapshots",
    )
    op.drop_index(
        "ix_integrity_snapshot_evaluated_at",
        table_name="evidence_integrity_snapshots",
    )
    op.drop_index(
        "ix_integrity_snapshot_payment_id",
        table_name="evidence_integrity_snapshots",
    )
    op.drop_table("evidence_integrity_snapshots")
