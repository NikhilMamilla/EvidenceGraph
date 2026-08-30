"""Phase 10 — Evidence Integrity Decision Traces & Audit Events

Revision ID: 0009_phase10
Revises: 0008_phase9
Create Date: 2026-08-23

Creates tables:
  1. evidence_integrity_traces
     Immutable, tamper-evident decision traces for integrity evaluations.
     One COMPLETED EVALUATION trace per (payment_id, evaluated_at,
     methodology_version) — enforced by a partial unique index.
     CHECK constraints make incomplete terminal states unrepresentable.

  2. integrity_trace_events
     Ordered audit events for trace lifecycles with explicit sequence numbers.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0009_phase10"
down_revision: Union[str, None] = "0008_phase9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "evidence_integrity_traces",
        sa.Column("internal_id", sa.Integer(), autoincrement=True, nullable=False),
        # Identity
        sa.Column("trace_id", sa.String(36), nullable=False),
        sa.Column("trace_type", sa.String(16), nullable=False),
        sa.Column("original_trace_id", sa.String(36), nullable=True),
        sa.Column("payment_id", sa.String(128), nullable=False),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("methodology_version", sa.String(16), nullable=False),
        sa.Column("methodology_snapshot_hash", sa.String(64), nullable=True),
        sa.Column("trigger", sa.String(64), nullable=True),
        # Lifecycle
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("failure_stage", sa.String(64), nullable=True),
        sa.Column("failure_category", sa.String(64), nullable=True),
        sa.Column("failure_detail", sa.Text(), nullable=True),
        # Result
        sa.Column(
            "integrity_snapshot_internal_id",
            sa.Integer(),
            sa.ForeignKey("evidence_integrity_snapshots.internal_id"),
            nullable=True,
        ),
        sa.Column("overall_status", sa.String(32), nullable=True),
        # Cryptographic integrity
        sa.Column("canonical_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("trace_hash", sa.String(64), nullable=True),
        sa.Column("hash_algorithm", sa.String(32), nullable=True),
        sa.Column("canonicalization_version", sa.String(16), nullable=True),
        # Hash chain
        sa.Column("previous_trace_id", sa.String(36), nullable=True),
        sa.Column("previous_trace_hash", sa.String(64), nullable=True),
        # Audit
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("finalized_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("internal_id"),
        sa.UniqueConstraint("trace_id", name="uq_integrity_trace_trace_id"),
        # Transactional finalization safety (no IMPLIES keyword — portable SQL)
        sa.CheckConstraint(
            "(status NOT IN ('COMPLETED', 'FAILED')) OR "
            "(canonical_payload IS NOT NULL AND trace_hash IS NOT NULL "
            "AND hash_algorithm IS NOT NULL AND canonicalization_version IS NOT NULL)",
            name="ck_integrity_trace_finalized_complete",
        ),
        sa.CheckConstraint(
            "(status <> 'COMPLETED') OR "
            "((trace_type = 'EVALUATION') AND integrity_snapshot_internal_id IS NOT NULL "
            "AND overall_status IS NOT NULL) OR "
            "((trace_type = 'REPLAY') AND overall_status IS NOT NULL)",
            name="ck_integrity_trace_completed_has_result",
        ),
        sa.CheckConstraint(
            "(status <> 'FAILED') OR "
            "(failure_stage IS NOT NULL AND failure_category IS NOT NULL)",
            name="ck_integrity_trace_failed_has_failure_info",
        ),
        sa.CheckConstraint(
            "(trace_type <> 'REPLAY') OR (original_trace_id IS NOT NULL)",
            name="ck_integrity_trace_replay_has_original",
        ),
    )

    # Idempotency: at most one COMPLETED EVALUATION trace per identity tuple.
    op.create_index(
        "uq_integrity_trace_evaluation_identity",
        "evidence_integrity_traces",
        ["payment_id", "evaluated_at", "methodology_version"],
        unique=True,
        postgresql_where=sa.text(
            "trace_type = 'EVALUATION' AND status = 'COMPLETED'"
        ),
        sqlite_where=sa.text(
            "trace_type = 'EVALUATION' AND status = 'COMPLETED'"
        ),
    )
    op.create_index(
        "ix_integrity_trace_payment_id",
        "evidence_integrity_traces",
        ["payment_id"],
    )
    op.create_index(
        "ix_integrity_trace_evaluated_at",
        "evidence_integrity_traces",
        ["evaluated_at"],
    )
    op.create_index(
        "ix_integrity_trace_status", "evidence_integrity_traces", ["status"]
    )
    op.create_index(
        "ix_integrity_trace_original_trace_id",
        "evidence_integrity_traces",
        ["original_trace_id"],
    )

    op.create_table(
        "integrity_trace_events",
        sa.Column("internal_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("event_id", sa.String(36), nullable=False),
        sa.Column("trace_id", sa.String(36), nullable=False),
        sa.Column("sequence_number", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actor_type", sa.String(16), nullable=False),
        sa.Column("event_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("internal_id"),
        sa.UniqueConstraint("event_id", name="uq_integrity_trace_event_event_id"),
        sa.UniqueConstraint(
            "trace_id", "sequence_number", name="uq_integrity_trace_event_order"
        ),
        sa.CheckConstraint(
            "actor_type IN ('SYSTEM', 'USER')",
            name="ck_integrity_trace_event_actor",
        ),
    )

    op.create_index(
        "ix_integrity_trace_events_trace_id",
        "integrity_trace_events",
        ["trace_id"],
    )
    op.create_index(
        "ix_integrity_trace_events_type",
        "integrity_trace_events",
        ["event_type"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_integrity_trace_events_type", table_name="integrity_trace_events"
    )
    op.drop_index(
        "ix_integrity_trace_events_trace_id", table_name="integrity_trace_events"
    )
    op.drop_table("integrity_trace_events")

    op.drop_index(
        "ix_integrity_trace_original_trace_id",
        table_name="evidence_integrity_traces",
    )
    op.drop_index(
        "ix_integrity_trace_status", table_name="evidence_integrity_traces"
    )
    op.drop_index(
        "ix_integrity_trace_evaluated_at", table_name="evidence_integrity_traces"
    )
    op.drop_index(
        "ix_integrity_trace_payment_id", table_name="evidence_integrity_traces"
    )
    op.drop_index(
        "uq_integrity_trace_evaluation_identity",
        table_name="evidence_integrity_traces",
    )
    op.drop_table("evidence_integrity_traces")
