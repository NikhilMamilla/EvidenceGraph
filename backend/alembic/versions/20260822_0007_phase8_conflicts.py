"""Phase 8 — Evidence Conflicts & Resolutions

Revision ID: 0007_phase8
Revises: 0006_phase7
Create Date: 2026-08-22

Creates tables:
  1. evidence_conflicts — Inconsistencies and temporal contradictions
  2. conflict_resolutions — Audit trail of conflict resolutions
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007_phase8"
down_revision: Union[str, None] = "0006_phase7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. evidence_conflicts
    op.create_table(
        "evidence_conflicts",
        sa.Column("internal_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("payment_id", sa.String(length=128), nullable=False),
        sa.Column("claim_a_id", sa.Integer(), nullable=False),
        sa.Column("claim_b_id", sa.Integer(), nullable=False),
        sa.Column("conflict_type", sa.String(length=64), nullable=False),
        sa.Column("severity", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), server_default="OPEN", nullable=False),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("rule_version", sa.String(length=32), server_default="1.0", nullable=False),
        sa.Column("explanation", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["claim_a_id"],
            ["claims.internal_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["claim_b_id"],
            ["claims.internal_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("internal_id"),
        sa.UniqueConstraint(
            "payment_id",
            "claim_a_id",
            "claim_b_id",
            "conflict_type",
            "rule_version",
            name="uq_evidence_conflict_pair",
        ),
    )
    op.create_index("ix_evidence_conflicts_payment_id", "evidence_conflicts", ["payment_id"], unique=False)
    op.create_index("ix_evidence_conflicts_type", "evidence_conflicts", ["conflict_type"], unique=False)
    op.create_index("ix_evidence_conflicts_status", "evidence_conflicts", ["status"], unique=False)

    # 2. conflict_resolutions
    op.create_table(
        "conflict_resolutions",
        sa.Column("internal_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("conflict_id", sa.Integer(), nullable=False),
        sa.Column("resolving_evidence_id", sa.Integer(), nullable=True),
        sa.Column("resolution_type", sa.String(length=64), nullable=False),
        sa.Column("explanation", sa.String(length=512), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("rule_version", sa.String(length=32), server_default="1.0", nullable=False),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["conflict_id"],
            ["evidence_conflicts.internal_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["resolving_evidence_id"],
            ["evidence_observations.internal_id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("internal_id"),
    )
    op.create_index("ix_conflict_resolutions_conflict_id", "conflict_resolutions", ["conflict_id"], unique=False)


def downgrade() -> None:
    op.drop_table("conflict_resolutions")
    op.drop_table("evidence_conflicts")
