"""Content optimization engine — OptimizationReport table + new rec types.

Revision ID: 0008_optimization_reports
Revises: 0007_thumbnails
Create Date: 2026-04-25
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0008_optimization_reports"
down_revision = "0007_thumbnails"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Extend recommendation_type enum with new types
    op.execute("ALTER TYPE recommendation_type ADD VALUE IF NOT EXISTS 'optimize_title'")
    op.execute("ALTER TYPE recommendation_type ADD VALUE IF NOT EXISTS 'change_format'")
    op.execute("ALTER TYPE recommendation_type ADD VALUE IF NOT EXISTS 'increase_cadence'")

    op.create_table(
        "optimization_reports",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "channel_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("channels.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("period_days", sa.Integer(), nullable=False, server_default="28"),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("task_id", sa.String(64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        # Input metric snapshot
        sa.Column("channel_score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("ctr_period", sa.Float(), nullable=False, server_default="0"),
        sa.Column("ctr_trend_pct", sa.Float(), nullable=False, server_default="0"),
        sa.Column("retention_period", sa.Float(), nullable=False, server_default="0"),
        sa.Column("retention_trend_pct", sa.Float(), nullable=False, server_default="0"),
        sa.Column("watch_time_hours", sa.Float(), nullable=False, server_default="0"),
        sa.Column("watch_time_trend_pct", sa.Float(), nullable=False, server_default="0"),
        sa.Column("views_period", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("views_trend_pct", sa.Float(), nullable=False, server_default="0"),
        # AI outputs
        sa.Column("growth_trajectory", sa.String(20), nullable=False, server_default="new"),
        sa.Column("growth_score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("summary", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "content_recommendations",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
        sa.Column(
            "next_topics",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
        sa.Column(
            "format_suggestions",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
        sa.Column(
            "watch_time_insights",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
        sa.Column(
            "ctr_insights",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
        sa.Column(
            "top_performer_patterns",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("channel_id", "period_days", name="uq_opt_report_channel_period"),
    )

    op.create_index("ix_opt_report_channel_id", "optimization_reports", ["channel_id"])
    op.create_index("ix_opt_report_status", "optimization_reports", ["status"])


def downgrade() -> None:
    op.drop_index("ix_opt_report_status", table_name="optimization_reports")
    op.drop_index("ix_opt_report_channel_id", table_name="optimization_reports")
    op.drop_table("optimization_reports")
    # Enum values cannot be removed in PostgreSQL without recreation — leave as-is
