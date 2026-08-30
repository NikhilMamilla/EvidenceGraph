"""Phase 6 — Evidence Quality tables

Revision ID: 0005_phase6
Revises: 0004_phase5
Create Date: 2026-08-22

Creates three tables:
  1. evidence_source_profiles — source type metadata (authority, directness)
  2. evidence_quality_snapshots — point-in-time quality measurements
  3. evidence_evaluations — outcome recording infrastructure (skeleton)

And seeds the initial EvidenceSourceProfile rows for all known source types.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005_phase6"
down_revision: Union[str, None] = "0004_phase5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # -----------------------------------------------------------------------
    # 1. evidence_source_profiles
    # -----------------------------------------------------------------------
    op.create_table(
        "evidence_source_profiles",
        sa.Column("internal_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("source_type", sa.String(length=64), nullable=False),
        sa.Column("authority_level", sa.String(length=32), nullable=False),
        sa.Column("default_directness", sa.String(length=32), nullable=False),
        sa.Column("description", sa.String(length=512), nullable=True),
        sa.Column("methodology_version", sa.String(length=16), server_default="1.0", nullable=False),
        sa.Column("profile_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("internal_id"),
        sa.UniqueConstraint("source_type", name="uq_source_profile_type"),
    )
    op.create_index("ix_source_profile_type", "evidence_source_profiles", ["source_type"])

    # -----------------------------------------------------------------------
    # 2. evidence_quality_snapshots
    # -----------------------------------------------------------------------
    op.create_table(
        "evidence_quality_snapshots",
        sa.Column("internal_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("evidence_id", sa.Integer(), nullable=False),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=False),
        # Freshness
        sa.Column("age_seconds", sa.Numeric(precision=18, scale=3), nullable=True),
        sa.Column("freshness_state", sa.String(length=16), nullable=False),
        sa.Column("freshness_policy_key", sa.String(length=64), nullable=False),
        sa.Column("freshness_methodology_version", sa.String(length=16), server_default="1.0", nullable=False),
        # Source quality
        sa.Column("source_type", sa.String(length=64), nullable=False),
        sa.Column("source_directness", sa.String(length=32), nullable=False),
        sa.Column("source_authority_level", sa.String(length=32), nullable=False),
        sa.Column("source_methodology_version", sa.String(length=16), server_default="1.0", nullable=False),
        # Historical reliability
        sa.Column("historical_reliability_status", sa.String(length=32), nullable=False),
        sa.Column("reliability_sample_count", sa.Integer(), nullable=True),
        sa.Column("reliability_methodology_version", sa.String(length=16), server_default="1.0", nullable=False),
        # Provenance
        sa.Column("snapshot_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("internal_id"),
        sa.ForeignKeyConstraint(
            ["evidence_id"],
            ["evidence_observations.internal_id"],
            name="fk_quality_snapshot_evidence",
            ondelete="RESTRICT",
        ),
    )
    op.create_index("ix_quality_snapshot_evidence_id", "evidence_quality_snapshots", ["evidence_id"])
    op.create_index("ix_quality_snapshot_evaluated_at", "evidence_quality_snapshots", ["evaluated_at"])
    op.create_index("ix_quality_snapshot_freshness_state", "evidence_quality_snapshots", ["freshness_state"])

    # -----------------------------------------------------------------------
    # 3. evidence_evaluations  (outcome infrastructure skeleton)
    # -----------------------------------------------------------------------
    op.create_table(
        "evidence_evaluations",
        sa.Column("internal_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("evidence_id", sa.Integer(), nullable=False),
        sa.Column("evaluation_type", sa.String(length=64), nullable=False),
        sa.Column("evaluation_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("outcome_reference", sa.String(length=256), nullable=True),
        sa.Column("result", sa.String(length=64), nullable=True),
        sa.Column("availability_status", sa.String(length=32), nullable=False),
        sa.Column("methodology_version", sa.String(length=16), server_default="1.0", nullable=False),
        sa.Column("evaluation_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("internal_id"),
        sa.ForeignKeyConstraint(
            ["evidence_id"],
            ["evidence_observations.internal_id"],
            name="fk_evaluation_evidence",
            ondelete="RESTRICT",
        ),
    )
    op.create_index("ix_evidence_evaluation_evidence_id", "evidence_evaluations", ["evidence_id"])
    op.create_index("ix_evidence_evaluation_type", "evidence_evaluations", ["evaluation_type"])

    # -----------------------------------------------------------------------
    # Seed initial source profiles
    # These are structural facts, not numerical trust scores.
    # -----------------------------------------------------------------------
    op.execute(
        sa.text(
            """
            INSERT INTO evidence_source_profiles
                (source_type, authority_level, default_directness, description, methodology_version)
            VALUES
                ('RAZORPAY_WEBHOOK', 'PRIMARY', 'DIRECT',
                 'Verified Razorpay webhook payload. Primary authority for Razorpay payment facts. '
                 'Direct: the value is taken verbatim from the provider event payload.',
                 '1.0'),
                ('RAZORPAY_API', 'PRIMARY', 'DIRECT',
                 'Response from a direct Razorpay REST API call. Primary authority. '
                 'Direct: fetched on-demand from the provider.',
                 '1.0'),
                ('INTERNAL_SYSTEM', 'SECONDARY', 'DERIVED',
                 'Evidence derived by EvidenceGraph from verified provider data. '
                 'Secondary authority — one hop from the provider.',
                 '1.0')
            ON CONFLICT (source_type) DO NOTHING
            """
        )
    )


def downgrade() -> None:
    op.drop_index("ix_evidence_evaluation_type", table_name="evidence_evaluations")
    op.drop_index("ix_evidence_evaluation_evidence_id", table_name="evidence_evaluations")
    op.drop_table("evidence_evaluations")

    op.drop_index("ix_quality_snapshot_freshness_state", table_name="evidence_quality_snapshots")
    op.drop_index("ix_quality_snapshot_evaluated_at", table_name="evidence_quality_snapshots")
    op.drop_index("ix_quality_snapshot_evidence_id", table_name="evidence_quality_snapshots")
    op.drop_table("evidence_quality_snapshots")

    op.drop_index("ix_source_profile_type", table_name="evidence_source_profiles")
    op.drop_table("evidence_source_profiles")
