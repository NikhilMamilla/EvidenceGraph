"""Phase 5 — Evidence Relationships table

Revision ID: 0004_phase5
Revises: 0003_phase4
Create Date: 2026-08-22

Creates the evidence_relationships table for storing typed, versioned,
immutable directed edges between EvidenceObservation nodes.

Design:
  - Directed edges: source_evidence_id → target_evidence_id
  - Immutable: no updated_at column
  - Idempotent: UNIQUE(source, target, type) — INSERT ... ON CONFLICT DO NOTHING
  - No self-loops: CHECK(source != target)
  - Full FK integrity to evidence_observations with RESTRICT on delete
    (evidence cannot be deleted while it has relationships)
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004_phase5"
down_revision: Union[str, None] = "0003_phase4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "evidence_relationships",
        # Identity
        sa.Column("internal_id", sa.Integer(), autoincrement=True, nullable=False),
        # Graph edge — directed
        sa.Column("source_evidence_id", sa.Integer(), nullable=False),
        sa.Column("target_evidence_id", sa.Integer(), nullable=False),
        # Relationship classification
        sa.Column("relationship_type", sa.String(length=64), nullable=False),
        sa.Column("relationship_source", sa.String(length=64), nullable=False),
        sa.Column(
            "rule_version",
            sa.String(length=16),
            server_default="1.0",
            nullable=False,
        ),
        # Provenance
        sa.Column(
            "provenance_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        # Record creation time (immutable — no updated_at)
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        # Primary key
        sa.PrimaryKeyConstraint("internal_id"),
        # Foreign keys with RESTRICT — evidence cannot be deleted if referenced
        sa.ForeignKeyConstraint(
            ["source_evidence_id"],
            ["evidence_observations.internal_id"],
            name="fk_relationship_source_evidence",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["target_evidence_id"],
            ["evidence_observations.internal_id"],
            name="fk_relationship_target_evidence",
            ondelete="RESTRICT",
        ),
        # Idempotency: same logical edge cannot be duplicated
        sa.UniqueConstraint(
            "source_evidence_id",
            "target_evidence_id",
            "relationship_type",
            name="uq_evidence_relationship",
        ),
        # No self-loops
        sa.CheckConstraint(
            "source_evidence_id != target_evidence_id",
            name="ck_evidence_relationship_no_self_loop",
        ),
    )

    # Traversal indexes
    op.create_index(
        "ix_relationship_source_id",
        "evidence_relationships",
        ["source_evidence_id"],
    )
    op.create_index(
        "ix_relationship_target_id",
        "evidence_relationships",
        ["target_evidence_id"],
    )
    op.create_index(
        "ix_relationship_type",
        "evidence_relationships",
        ["relationship_type"],
    )


def downgrade() -> None:
    op.drop_index("ix_relationship_type", table_name="evidence_relationships")
    op.drop_index("ix_relationship_target_id", table_name="evidence_relationships")
    op.drop_index("ix_relationship_source_id", table_name="evidence_relationships")
    op.drop_table("evidence_relationships")
