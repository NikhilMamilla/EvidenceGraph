"""Phase 7 — Evidence Structure, Claims, Groups & Corroboration

Revision ID: 0006_phase7
Revises: 0005_phase6
Create Date: 2026-08-22

Creates tables:
  1. claims — Canonical propositions about entities
  2. evidence_claim_links — Links between evidence observations and claims
  3. evidence_groups — Clusters of observations sharing structural origin
  4. evidence_group_members — Associations between groups and evidence
  5. evidence_corroborations — Multi-source and temporal corroboration analysis
  6. evidence_structure_snapshots — Overall concentration and structure metrics
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006_phase7"
down_revision: Union[str, None] = "0005_phase6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. claims
    op.create_table(
        "claims",
        sa.Column("internal_id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("subject_type", sa.String(length=64), nullable=False),
        sa.Column("subject_id", sa.String(length=128), nullable=False),
        sa.Column("claim_type", sa.String(length=64), nullable=False),
        sa.Column("claim_key", sa.String(length=128), nullable=False),
        sa.Column("canonical_value", sa.String(length=512), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("internal_id"),
        sa.UniqueConstraint(
            "subject_type",
            "subject_id",
            "claim_type",
            "claim_key",
            "canonical_value",
            name="uq_claim_proposition",
        ),
    )
    op.create_index("ix_claims_subject", "claims", ["subject_type", "subject_id"], unique=False)
    op.create_index("ix_claims_type", "claims", ["claim_type"], unique=False)

    # 2. evidence_claim_links
    op.create_table(
        "evidence_claim_links",
        sa.Column("internal_id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("claim_id", sa.BigInteger(), nullable=False),
        sa.Column("evidence_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["claim_id"],
            ["claims.internal_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["evidence_id"],
            ["evidence_observations.internal_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("internal_id"),
        sa.UniqueConstraint("claim_id", "evidence_id", name="uq_evidence_claim_link"),
    )
    op.create_index("ix_evidence_claim_links_claim_id", "evidence_claim_links", ["claim_id"], unique=False)
    op.create_index("ix_evidence_claim_links_evidence_id", "evidence_claim_links", ["evidence_id"], unique=False)

    # 3. evidence_groups
    op.create_table(
        "evidence_groups",
        sa.Column("internal_id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("payment_id", sa.String(length=128), nullable=False),
        sa.Column("group_type", sa.String(length=64), nullable=False),
        sa.Column("grouping_key", sa.String(length=128), nullable=False),
        sa.Column("rule_version", sa.String(length=32), server_default="1.0", nullable=False),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("internal_id"),
        sa.UniqueConstraint("payment_id", "group_type", "grouping_key", name="uq_evidence_group_key"),
    )
    op.create_index("ix_evidence_groups_payment_id", "evidence_groups", ["payment_id"], unique=False)
    op.create_index("ix_evidence_groups_type", "evidence_groups", ["group_type"], unique=False)

    # 4. evidence_group_members
    op.create_table(
        "evidence_group_members",
        sa.Column("internal_id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("group_id", sa.BigInteger(), nullable=False),
        sa.Column("evidence_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["group_id"],
            ["evidence_groups.internal_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["evidence_id"],
            ["evidence_observations.internal_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("internal_id"),
        sa.UniqueConstraint("group_id", "evidence_id", name="uq_evidence_group_member"),
    )
    op.create_index("ix_evidence_group_members_group_id", "evidence_group_members", ["group_id"], unique=False)
    op.create_index("ix_evidence_group_members_evidence_id", "evidence_group_members", ["evidence_id"], unique=False)

    # 5. evidence_corroborations
    op.create_table(
        "evidence_corroborations",
        sa.Column("internal_id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("claim_id", sa.BigInteger(), nullable=False),
        sa.Column("payment_id", sa.String(length=128), nullable=False),
        sa.Column("corroboration_type", sa.String(length=64), nullable=False),
        sa.Column("independence_status", sa.String(length=64), nullable=False),
        sa.Column("observation_count", sa.Integer(), server_default="1", nullable=False),
        sa.Column("distinct_sources_count", sa.Integer(), server_default="1", nullable=False),
        sa.Column("distinct_events_count", sa.Integer(), server_default="1", nullable=False),
        sa.Column("methodology_version", sa.String(length=32), server_default="1.0", nullable=False),
        sa.Column("details", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["claim_id"],
            ["claims.internal_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("internal_id"),
    )
    op.create_index("ix_evidence_corroborations_claim_id", "evidence_corroborations", ["claim_id"], unique=False)
    op.create_index("ix_evidence_corroborations_payment_id", "evidence_corroborations", ["payment_id"], unique=False)

    # 6. evidence_structure_snapshots
    op.create_table(
        "evidence_structure_snapshots",
        sa.Column("internal_id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("payment_id", sa.String(length=128), nullable=False),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("total_observations", sa.Integer(), nullable=False),
        sa.Column("distinct_claims", sa.Integer(), nullable=False),
        sa.Column("distinct_sources", sa.Integer(), nullable=False),
        sa.Column("distinct_events", sa.Integer(), nullable=False),
        sa.Column("distinct_groups", sa.Integer(), nullable=False),
        sa.Column("largest_group_size", sa.Integer(), nullable=False),
        sa.Column("group_hhi", sa.Float(), nullable=False),
        sa.Column("corroborated_claim_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("multi_source_claim_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("methodology_version", sa.String(length=32), server_default="1.0", nullable=False),
        sa.Column("structural_summary", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("internal_id"),
    )
    op.create_index("ix_structure_snapshots_payment_id", "evidence_structure_snapshots", ["payment_id"], unique=False)
    op.create_index("ix_structure_snapshots_evaluated_at", "evidence_structure_snapshots", ["evaluated_at"], unique=False)


def downgrade() -> None:
    op.drop_table("evidence_structure_snapshots")
    op.drop_table("evidence_corroborations")
    op.drop_table("evidence_group_members")
    op.drop_table("evidence_groups")
    op.drop_table("evidence_claim_links")
    op.drop_table("claims")
