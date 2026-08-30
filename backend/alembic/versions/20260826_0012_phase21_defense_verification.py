"""Phase 21 — Defense Verification Evaluation Foundation

Revision ID: phase21_defense
Revises: phase13_reconciliation
Create Date: 2026-08-26
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "phase21_defense"
down_revision = "0011_phase13"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Defense Cases
    op.create_table(
        "defense_cases",
        sa.Column("internal_id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("case_id", sa.String(64), nullable=False, unique=True, index=True),
        sa.Column("dispute_category", sa.String(64), nullable=False),
        sa.Column("dispute_reason", sa.Text, nullable=False),
        sa.Column("case_description", sa.Text, nullable=False),
        sa.Column("payment_reference", sa.String(64), nullable=True),
        sa.Column("order_reference", sa.String(64), nullable=True),
        sa.Column("dataset_version", sa.String(32), nullable=False),
        sa.Column("case_source", sa.String(32), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="CREATED"),
        sa.Column("evaluation_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    # Defense Claims
    op.create_table(
        "defense_claims",
        sa.Column("internal_id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("claim_id", sa.String(64), nullable=False, unique=True, index=True),
        sa.Column("case_id", sa.String(64), nullable=False, index=True),
        sa.Column("claim_text", sa.Text, nullable=False),
        sa.Column("claim_type", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    # Defense Evidence Links
    op.create_table(
        "defense_evidence_links",
        sa.Column("internal_id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("claim_id", sa.String(64), nullable=False, index=True),
        sa.Column("evidence_observation_id", sa.Integer, nullable=False, index=True),
        sa.Column("link_type", sa.String(32), nullable=False),
        sa.Column("relevance_score", sa.Float, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    # Evaluation Labels
    op.create_table(
        "evaluation_labels",
        sa.Column("internal_id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("case_id", sa.String(64), nullable=False, index=True),
        sa.Column("claim_id", sa.String(64), nullable=False, index=True),
        sa.Column("dataset_version", sa.String(32), nullable=False),
        sa.Column("label_type", sa.String(16), nullable=False),
        sa.Column("label", sa.String(32), nullable=False),
        sa.Column("methodology_version", sa.String(64), nullable=True),
        sa.Column("labeler_id", sa.String(64), nullable=True),
        sa.Column("rationale", sa.Text, nullable=True),
        sa.Column("supporting_evidence_ids", postgresql.JSONB, nullable=True),
        sa.Column("contradicting_evidence_ids", postgresql.JSONB, nullable=True),
        sa.Column("missing_requirement_ids", postgresql.JSONB, nullable=True),
        sa.Column("label_confidence", sa.Float, nullable=True),
        sa.Column("metadata_json", postgresql.JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    # Evaluation Datasets
    op.create_table(
        "evaluation_datasets",
        sa.Column("internal_id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("dataset_version", sa.String(32), nullable=False, unique=True, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("total_cases", sa.Integer, nullable=False, server_default="0"),
        sa.Column("source_counts", postgresql.JSONB, nullable=True),
        sa.Column("label_counts", postgresql.JSONB, nullable=True),
        sa.Column("split_counts", postgresql.JSONB, nullable=True),
        sa.Column("dataset_fingerprint", sa.String(128), nullable=True),
        sa.Column("is_frozen", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("frozen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("methodology_version", sa.String(64), nullable=True),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("metadata_json", postgresql.JSONB, nullable=True),
    )

    # Evaluation Runs
    op.create_table(
        "evaluation_runs",
        sa.Column("internal_id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("run_id", sa.String(64), nullable=False, unique=True, index=True),
        sa.Column("dataset_version", sa.String(32), nullable=False),
        sa.Column("methodology_version", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="RUNNING"),
        sa.Column("total_cases", sa.Integer, nullable=False, server_default="0"),
        sa.Column("evaluated_cases", sa.Integer, nullable=False, server_default="0"),
        sa.Column("correct_predictions", sa.Integer, nullable=False, server_default="0"),
        sa.Column("confusion_matrix", postgresql.JSONB, nullable=True),
        sa.Column("metrics", postgresql.JSONB, nullable=True),
        sa.Column("error_cases", postgresql.JSONB, nullable=True),
        sa.Column("results_fingerprint", sa.String(128), nullable=True),
        sa.Column("dataset_fingerprint", sa.String(128), nullable=True),
        sa.Column("run_metadata", postgresql.JSONB, nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("evaluation_runs")
    op.drop_table("evaluation_datasets")
    op.drop_table("evaluation_labels")
    op.drop_table("defense_evidence_links")
    op.drop_table("defense_claims")
    op.drop_table("defense_cases")
