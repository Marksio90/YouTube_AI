"""Compliance — compliance_checks and risk_flags tables.

Revision ID: 0003_compliance
Revises: 0002_monetization
Create Date: 2026-04-24
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0003_compliance"
down_revision = "0002_monetization"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── Enums ─────────────────────────────────────────────────────────────────
    op.execute(
        "CREATE TYPE check_status AS ENUM "
        "('pending', 'running', 'passed', 'flagged', 'blocked', 'error')"
    )
    op.execute(
        "CREATE TYPE check_mode AS ENUM ('rule', 'ai', 'both')"
    )
    op.execute(
        "CREATE TYPE risk_category AS ENUM "
        "('ad_safety', 'copyright_risk', 'factual_risk', 'reused_content', 'ai_disclosure')"
    )
    op.execute(
        "CREATE TYPE risk_severity AS ENUM "
        "('critical', 'high', 'medium', 'low', 'info')"
    )
    op.execute(
        "CREATE TYPE flag_source AS ENUM ('rule', 'ai')"
    )

    # ── compliance_checks ─────────────────────────────────────────────────────
    op.create_table(
        "compliance_checks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),

        sa.Column("channel_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("channels.id", ondelete="CASCADE"), nullable=False),
        sa.Column("script_id",  postgresql.UUID(as_uuid=True), sa.ForeignKey("scripts.id",  ondelete="CASCADE"), nullable=True),
        sa.Column("publication_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("publications.id", ondelete="SET NULL"), nullable=True),

        sa.Column("mode",   sa.Enum("rule", "ai", "both",       name="check_mode"),   nullable=False, server_default="both"),
        sa.Column("status", sa.Enum("pending", "running", "passed", "flagged", "blocked", "error", name="check_status"), nullable=False, server_default="pending"),

        sa.Column("risk_score",      sa.Float, nullable=False, server_default="0"),
        sa.Column("category_scores", postgresql.JSONB, nullable=False, server_default="{}"),

        sa.Column("flag_count",     sa.Integer, nullable=False, server_default="0"),
        sa.Column("critical_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("high_count",     sa.Integer, nullable=False, server_default="0"),

        sa.Column("monetization_eligible",  sa.Boolean, nullable=False, server_default="true"),
        sa.Column("ai_disclosure_required", sa.Boolean, nullable=False, server_default="false"),

        sa.Column("is_overridden",   sa.Boolean, nullable=False, server_default="false"),
        sa.Column("override_by",     sa.String(255), nullable=True),
        sa.Column("override_reason", sa.Text, nullable=True),
        sa.Column("overridden_at",   sa.DateTime(timezone=True), nullable=True),

        sa.Column("started_at",   sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),

        sa.Column("ai_task_ids", postgresql.JSONB, nullable=False, server_default="{}"),
    )

    op.create_index("ix_cc_script",      "compliance_checks", ["script_id"])
    op.create_index("ix_cc_publication", "compliance_checks", ["publication_id"])
    op.create_index("ix_cc_status",      "compliance_checks", ["status"])
    op.create_index("ix_cc_channel",     "compliance_checks", ["channel_id"])

    # ── risk_flags ────────────────────────────────────────────────────────────
    op.create_table(
        "risk_flags",
        sa.Column("id",         postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),

        sa.Column("check_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("compliance_checks.id", ondelete="CASCADE"), nullable=False),

        sa.Column("category", sa.Enum("ad_safety", "copyright_risk", "factual_risk", "reused_content", "ai_disclosure", name="risk_category"), nullable=False),
        sa.Column("severity", sa.Enum("critical", "high", "medium", "low", "info", name="risk_severity"), nullable=False),
        sa.Column("source",   sa.Enum("rule", "ai", name="flag_source"), nullable=False),

        sa.Column("rule_id",    sa.String(100), nullable=False),
        sa.Column("title",      sa.String(300), nullable=False),
        sa.Column("detail",     sa.Text, nullable=False),
        sa.Column("evidence",   sa.Text, nullable=True),
        sa.Column("suggestion", sa.Text, nullable=True),

        sa.Column("text_start", sa.Integer, nullable=True),
        sa.Column("text_end",   sa.Integer, nullable=True),

        sa.Column("is_dismissed", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("dismissed_by", sa.String(255), nullable=True),
        sa.Column("dismissed_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_index("ix_rf_check",    "risk_flags", ["check_id"])
    op.create_index("ix_rf_category", "risk_flags", ["category"])
    op.create_index("ix_rf_severity", "risk_flags", ["severity"])

    # ── compliance_score column on scripts ────────────────────────────────────
    op.add_column(
        "scripts",
        sa.Column("compliance_score", sa.Float, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("scripts", "compliance_score")

    op.drop_index("ix_rf_severity", "risk_flags")
    op.drop_index("ix_rf_category", "risk_flags")
    op.drop_index("ix_rf_check",    "risk_flags")
    op.drop_table("risk_flags")

    op.drop_index("ix_cc_channel",     "compliance_checks")
    op.drop_index("ix_cc_status",      "compliance_checks")
    op.drop_index("ix_cc_publication", "compliance_checks")
    op.drop_index("ix_cc_script",      "compliance_checks")
    op.drop_table("compliance_checks")

    op.execute("DROP TYPE IF EXISTS flag_source")
    op.execute("DROP TYPE IF EXISTS risk_severity")
    op.execute("DROP TYPE IF EXISTS risk_category")
    op.execute("DROP TYPE IF EXISTS check_mode")
    op.execute("DROP TYPE IF EXISTS check_status")
