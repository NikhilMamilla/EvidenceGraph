"""Phase 2: webhook ingestion schema

Revision ID: 0001_phase2
Revises:
Create Date: 2026-08-21

Tables created:
  - webhook_events      : verified Razorpay webhook events (immutable raw payload)
  - payment_references  : minimal payment state derived from events
  - order_references    : minimal order state for event correlation
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_phase2"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # webhook_events — immutable record of every verified Razorpay event
    # ------------------------------------------------------------------
    op.create_table(
        "webhook_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("razorpay_event_id", sa.String(128), nullable=True),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("event_timestamp", sa.DateTime(timezone=True), nullable=True),
        sa.Column("signature_verified", sa.Boolean(), nullable=False, default=False),
        sa.Column(
            "processing_status",
            sa.String(32),
            nullable=False,
            server_default="RECEIVED",
        ),
        # Raw verified payload — immutable, never mutated
        sa.Column("raw_payload", postgresql.JSONB(), nullable=False),
        # SHA-256 hex digest of raw payload bytes for integrity checks
        sa.Column("payload_hash", sa.String(64), nullable=False),
        # Extracted convenience fields (denormalised from raw_payload)
        sa.Column("payment_id", sa.String(64), nullable=True),
        sa.Column("order_id", sa.String(64), nullable=True),
        sa.Column("account_id", sa.String(128), nullable=True),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("processing_error", sa.Text(), nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now(), onupdate=sa.func.now()),
    )
    # Idempotency: one logical record per Razorpay event ID
    op.create_index(
        "uq_webhook_events_razorpay_event_id",
        "webhook_events",
        ["razorpay_event_id"],
        unique=True,
        postgresql_where=sa.text("razorpay_event_id IS NOT NULL"),
    )
    op.create_index("ix_webhook_events_event_type", "webhook_events", ["event_type"])
    op.create_index("ix_webhook_events_payment_id", "webhook_events", ["payment_id"])
    op.create_index("ix_webhook_events_order_id", "webhook_events", ["order_id"])
    op.create_index("ix_webhook_events_processing_status",
                    "webhook_events", ["processing_status"])
    op.create_index("ix_webhook_events_received_at", "webhook_events", ["received_at"])

    # ------------------------------------------------------------------
    # payment_references — minimal payment state derived from events
    # ------------------------------------------------------------------
    op.create_table(
        "payment_references",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("razorpay_payment_id", sa.String(64), nullable=False, unique=True),
        sa.Column("razorpay_order_id", sa.String(64), nullable=True),
        sa.Column("latest_status", sa.String(32), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("last_updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("event_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
    )
    op.create_index(
        "ix_payment_references_razorpay_payment_id",
        "payment_references",
        ["razorpay_payment_id"],
    )
    op.create_index(
        "ix_payment_references_razorpay_order_id",
        "payment_references",
        ["razorpay_order_id"],
    )

    # ------------------------------------------------------------------
    # order_references — minimal order state for event correlation
    # ------------------------------------------------------------------
    op.create_table(
        "order_references",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("razorpay_order_id", sa.String(64), nullable=False, unique=True),
        sa.Column("latest_status", sa.String(32), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("last_updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("event_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
    )
    op.create_index(
        "ix_order_references_razorpay_order_id",
        "order_references",
        ["razorpay_order_id"],
    )


def downgrade() -> None:
    op.drop_table("order_references")
    op.drop_table("payment_references")
    op.drop_table("webhook_events")
