"""Monetization — revenue_streams and affiliate_links tables.

Revision ID: 0002_monetization
Revises: 0001_initial_schema
Create Date: 2026-04-24
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0002_monetization"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── Enums ─────────────────────────────────────────────────────────────────
    op.execute(
        "CREATE TYPE revenue_source AS ENUM ('ads', 'affiliate', 'products', 'sponsorship')"
    )
    op.execute(
        "CREATE TYPE affiliate_platform AS ENUM ('amazon', 'impact', 'shareasale', 'cj', 'custom')"
    )

    # ── revenue_streams ───────────────────────────────────────────────────────
    op.create_table(
        "revenue_streams",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "channel_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("channels.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "publication_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("publications.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "source",
            sa.Enum("ads", "affiliate", "products", "sponsorship",
                    name="revenue_source", create_type=False),
            nullable=False,
        ),
        sa.Column("period_start",     sa.Date,            nullable=False),
        sa.Column("period_end",       sa.Date,            nullable=False),
        sa.Column("revenue_usd",      sa.Numeric(14, 4),  nullable=False, server_default="0"),
        sa.Column("impressions",      sa.Integer,         nullable=False, server_default="0"),
        sa.Column("clicks",           sa.Integer,         nullable=False, server_default="0"),
        sa.Column("conversions",      sa.Integer,         nullable=False, server_default="0"),
        sa.Column("rpm",              sa.Float,           nullable=False, server_default="0"),
        sa.Column("cpm",              sa.Float,           nullable=False, server_default="0"),
        sa.Column("commission_rate",  sa.Float,           nullable=True),
        sa.Column("cost_usd",         sa.Numeric(14, 4),  nullable=False, server_default="0"),
        sa.Column("roi_pct",          sa.Float,           nullable=True),
        sa.Column("is_estimated",     sa.Boolean,         nullable=False, server_default="true"),
        sa.Column("notes",            sa.Text,            nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint(
            "channel_id", "publication_id", "source", "period_start",
            name="uq_revenue_channel_pub_source_period",
        ),
    )
    op.create_index("ix_revenue_channel_source", "revenue_streams", ["channel_id", "source"])
    op.create_index("ix_revenue_publication",    "revenue_streams", ["publication_id"])
    op.create_index("ix_revenue_period",         "revenue_streams", ["period_start"])

    # ── affiliate_links ───────────────────────────────────────────────────────
    op.create_table(
        "affiliate_links",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "channel_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("channels.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "publication_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("publications.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "platform",
            sa.Enum("amazon", "impact", "shareasale", "cj", "custom",
                    name="affiliate_platform", create_type=False),
            nullable=False,
        ),
        sa.Column("name",              sa.String(200),    nullable=False),
        sa.Column("destination_url",   sa.Text,           nullable=False),
        sa.Column("slug",              sa.String(100),    nullable=True, unique=True),
        sa.Column("tracking_id",       sa.String(200),    nullable=True),
        sa.Column("commission_type",   sa.String(20),     nullable=False, server_default="percentage"),
        sa.Column("commission_value",  sa.Float,          nullable=False, server_default="0"),
        sa.Column("total_clicks",      sa.Integer,        nullable=False, server_default="0"),
        sa.Column("total_conversions", sa.Integer,        nullable=False, server_default="0"),
        sa.Column("total_revenue_usd", sa.Numeric(14, 4), nullable=False, server_default="0"),
        sa.Column("is_active",         sa.Boolean,        nullable=False, server_default="true"),
        sa.Column("expires_at",        sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_affiliate_channel",  "affiliate_links", ["channel_id"])
    op.create_index("ix_affiliate_platform", "affiliate_links", ["platform"])
    op.create_index("ix_affiliate_active",   "affiliate_links", ["is_active"])


def downgrade() -> None:
    op.drop_table("affiliate_links")
    op.drop_table("revenue_streams")
    op.execute("DROP TYPE IF EXISTS affiliate_platform")
    op.execute("DROP TYPE IF EXISTS revenue_source")
