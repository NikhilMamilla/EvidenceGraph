"""Phase 4 — Evidence Observations table

Revision ID: 0003_phase4
Revises: fe5fd3d3fd6f
Create Date: 2026-08-22

Creates the evidence_observations table for storing first-class,
immutable evidence records with full provenance and lineage.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_phase4"
down_revision: Union[str, None] = "fe5fd3d3fd6f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "evidence_observations",
        sa.Column("internal_id", sa.Integer(), autoincrement=True, nullable=False),
        # What was observed
        sa.Column("evidence_type", sa.String(length=64), nullable=False),
        # Subject — which entity this observation describes
        sa.Column("subject_type", sa.String(length=32), nullable=False),
        sa.Column("subject_id", sa.String(length=128), nullable=False),
        # Value representation
        sa.Column("value", sa.Text(), nullable=True),
        sa.Column("value_type", sa.String(length=32), nullable=False),
        # Provenance
        sa.Column("source_type", sa.String(length=32), nullable=False),
        sa.Column("source_reference", sa.String(length=128), nullable=True),
        # Time — observation time (NOT processing time)
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=True),
        # Lineage — FK references for traceable evidence chain
        sa.Column("webhook_event_id", sa.Integer(), nullable=True),
        sa.Column("payment_event_id", sa.Integer(), nullable=True),
        # Extraction metadata
        sa.Column("extraction_method", sa.String(length=64), nullable=False),
        sa.Column(
            "extraction_version",
            sa.String(length=16),
            server_default="1.0",
            nullable=False,
        ),
        sa.Column(
            "provenance_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        # Record creation time (NOT the observation time)
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        # No updated_at — evidence records are immutable by design
        # Foreign keys
        sa.ForeignKeyConstraint(
            ["webhook_event_id"],
            ["webhook_events.id"],
            name="fk_evidence_webhook_event",
        ),
        sa.ForeignKeyConstraint(
            ["payment_event_id"],
            ["payment_events.internal_id"],
            name="fk_evidence_payment_event",
        ),
        sa.PrimaryKeyConstraint("internal_id"),
    )

    # Indexes — chosen for actual query patterns
    # Primary: all evidence for a subject (e.g. all evidence for pay_xxx)
    op.create_index(
        "ix_evidence_subject",
        "evidence_observations",
        ["subject_type", "subject_id"],
    )
    # Filter by evidence type
    op.create_index(
        "ix_evidence_type",
        "evidence_observations",
        ["evidence_type"],
    )
    # Filter by source
    op.create_index(
        "ix_evidence_source_type",
        "evidence_observations",
        ["source_type"],
    )
    op.create_index(
        "ix_evidence_source_reference",
        "evidence_observations",
        ["source_reference"],
    )
    # Time-based ordering
    op.create_index(
        "ix_evidence_observed_at",
        "evidence_observations",
        ["observed_at"],
    )
    # Lineage traversal
    op.create_index(
        "ix_evidence_webhook_event_id",
        "evidence_observations",
        ["webhook_event_id"],
    )
    op.create_index(
        "ix_evidence_payment_event_id",
        "evidence_observations",
        ["payment_event_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_evidence_payment_event_id", table_name="evidence_observations")
    op.drop_index("ix_evidence_webhook_event_id", table_name="evidence_observations")
    op.drop_index("ix_evidence_observed_at", table_name="evidence_observations")
    op.drop_index("ix_evidence_source_reference", table_name="evidence_observations")
    op.drop_index("ix_evidence_source_type", table_name="evidence_observations")
    op.drop_index("ix_evidence_type", table_name="evidence_observations")
    op.drop_index("ix_evidence_subject", table_name="evidence_observations")
    op.drop_table("evidence_observations")
