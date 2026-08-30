"""Phase 13 — Multi-Source Evidence Reconciliation & Evidence Identity

Revision ID: 0011_phase13
Revises: 0010_phase11
Create Date: 2026-08-23

Creates tables:
  1. evidence_facts
     Canonical normalized representation of a real-world payment event or
     attribute observation. Unique constraint on (payment_id, fact_type,
     canonical_value_hash) ensures idempotency. Preserves observation count,
     distinct source count, first/last observed timestamps, and status.

  2. observation_fact_links
     Provenance bridge linking raw EvidenceObservation records to their
     reconciled EvidenceFact without mutating the immutable observations.

  3. evidence_reconciliations
     Immutable, versioned record of every pairwise identity decision between
     two EvidenceObservation records with deterministic ordering
     (obs_a_id < obs_b_id).
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0011_phase13"
down_revision: Union[str, None] = "0010_phase11"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # -------------------------------------------------------------------------
    # 1. Table: evidence_facts
    # -------------------------------------------------------------------------
    op.create_table(
        "evidence_facts",
        sa.Column("internal_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("payment_id", sa.String(length=128), nullable=False),
        sa.Column("fact_type", sa.String(length=64), nullable=False),
        sa.Column("canonical_value", sa.String(length=512), nullable=False),
        sa.Column("canonical_value_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), server_default="ACTIVE", nullable=False),
        sa.Column("first_observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("observation_count", sa.Integer(), server_default="1", nullable=False),
        sa.Column("distinct_source_count", sa.Integer(), server_default="1", nullable=False),
        sa.Column("methodology_version", sa.String(length=16), server_default="1.0", nullable=False),
        sa.Column("fact_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("internal_id"),
        sa.UniqueConstraint(
            "payment_id",
            "fact_type",
            "canonical_value_hash",
            name="uq_evidence_fact_identity",
        ),
    )

    op.create_index(
        "ix_evidence_facts_payment_id",
        "evidence_facts",
        ["payment_id"],
        unique=False,
    )
    op.create_index(
        "ix_evidence_facts_fact_type",
        "evidence_facts",
        ["fact_type"],
        unique=False,
    )
    op.create_index(
        "ix_evidence_facts_status",
        "evidence_facts",
        ["status"],
        unique=False,
    )
    op.create_index(
        "ix_evidence_facts_canonical_value_hash",
        "evidence_facts",
        ["canonical_value_hash"],
        unique=False,
    )
    op.create_index(
        "ix_evidence_facts_first_observed_at",
        "evidence_facts",
        ["first_observed_at"],
        unique=False,
    )

    # -------------------------------------------------------------------------
    # 2. Table: observation_fact_links
    # -------------------------------------------------------------------------
    op.create_table(
        "observation_fact_links",
        sa.Column("internal_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("observation_id", sa.Integer(), nullable=False),
        sa.Column("fact_id", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["observation_id"],
            ["evidence_observations.internal_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["fact_id"],
            ["evidence_facts.internal_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("internal_id"),
        sa.UniqueConstraint(
            "observation_id",
            "fact_id",
            name="uq_observation_fact_link",
        ),
    )

    op.create_index(
        "ix_observation_fact_links_observation_id",
        "observation_fact_links",
        ["observation_id"],
        unique=False,
    )
    op.create_index(
        "ix_observation_fact_links_fact_id",
        "observation_fact_links",
        ["fact_id"],
        unique=False,
    )

    # -------------------------------------------------------------------------
    # 3. Table: evidence_reconciliations
    # -------------------------------------------------------------------------
    op.create_table(
        "evidence_reconciliations",
        sa.Column("internal_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("observation_a_id", sa.Integer(), nullable=False),
        sa.Column("observation_b_id", sa.Integer(), nullable=False),
        sa.Column("result", sa.String(length=32), nullable=False),
        sa.Column("rule_id", sa.String(length=64), nullable=False),
        sa.Column("rule_version", sa.String(length=16), nullable=False),
        sa.Column("explanation", sa.String(length=1024), nullable=False),
        sa.Column("fact_id", sa.Integer(), nullable=True),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["observation_a_id"],
            ["evidence_observations.internal_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["observation_b_id"],
            ["evidence_observations.internal_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["fact_id"],
            ["evidence_facts.internal_id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("internal_id"),
        sa.UniqueConstraint(
            "observation_a_id",
            "observation_b_id",
            "rule_id",
            "rule_version",
            name="uq_evidence_reconciliation_pair",
        ),
    )

    op.create_index(
        "ix_evidence_reconciliations_obs_a",
        "evidence_reconciliations",
        ["observation_a_id"],
        unique=False,
    )
    op.create_index(
        "ix_evidence_reconciliations_obs_b",
        "evidence_reconciliations",
        ["observation_b_id"],
        unique=False,
    )
    op.create_index(
        "ix_evidence_reconciliations_result",
        "evidence_reconciliations",
        ["result"],
        unique=False,
    )
    op.create_index(
        "ix_evidence_reconciliations_fact_id",
        "evidence_reconciliations",
        ["fact_id"],
        unique=False,
    )
    op.create_index(
        "ix_evidence_reconciliations_evaluated_at",
        "evidence_reconciliations",
        ["evaluated_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_table("evidence_reconciliations")
    op.drop_table("observation_fact_links")
    op.drop_table("evidence_facts")
