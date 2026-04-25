"""Affiliate system — Campaign, PublicationAffiliateLink, AffiliateLinkClick tables.

Adds new columns to affiliate_links (campaign_id, niche_tags, avg_order_value_usd).

Revision ID: 0009_affiliate_campaigns
Revises: 0008_optimization_reports
Create Date: 2026-04-25
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0009_affiliate_campaigns"
down_revision = "0008_optimization_reports"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── campaign_status enum ──────────────────────────────────────────────────
    op.execute(
        "CREATE TYPE campaign_status AS ENUM "
        "('draft', 'active', 'paused', 'completed', 'archived')"
    )

    # ── affiliate_campaigns ───────────────────────────────────────────────────
    op.create_table(
        "affiliate_campaigns",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "channel_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("channels.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "status",
            postgresql.ENUM(
                "draft", "active", "paused", "completed", "archived",
                name="campaign_status",
                create_type=False,
            ),
            nullable=False,
            server_default="draft",
        ),
        sa.Column(
            "niche_tags",
            postgresql.ARRAY(sa.String(100)),
            nullable=False,
            server_default="{}",
        ),
        sa.Column(
            "topic_ids",
            postgresql.ARRAY(sa.String(36)),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("target_clicks", sa.Integer(), nullable=True),
        sa.Column("target_conversions", sa.Integer(), nullable=True),
        sa.Column("target_revenue_usd", sa.Numeric(14, 4), nullable=True),
        sa.Column("budget_usd", sa.Numeric(14, 4), nullable=True),
        sa.Column("total_clicks", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_conversions", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_revenue_usd", sa.Numeric(14, 4), nullable=False, server_default="0"),
        sa.Column("notes", sa.Text(), nullable=True),
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
    )
    op.create_index("ix_campaign_channel", "affiliate_campaigns", ["channel_id"])
    op.create_index("ix_campaign_status", "affiliate_campaigns", ["status"])

    # ── new columns on affiliate_links ────────────────────────────────────────
    op.add_column(
        "affiliate_links",
        sa.Column(
            "campaign_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("affiliate_campaigns.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "affiliate_links",
        sa.Column(
            "niche_tags",
            postgresql.ARRAY(sa.String(100)),
            nullable=False,
            server_default="{}",
        ),
    )
    op.add_column(
        "affiliate_links",
        sa.Column(
            "avg_order_value_usd",
            sa.Float(),
            nullable=False,
            server_default="50.0",
        ),
    )
    op.create_index("ix_affiliate_campaign", "affiliate_links", ["campaign_id"])

    # ── publication_affiliate_links ───────────────────────────────────────────
    op.create_table(
        "publication_affiliate_links",
        sa.Column(
            "publication_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("publications.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "link_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("affiliate_links.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "campaign_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("affiliate_campaigns.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("description_text", sa.String(500), nullable=True),
        sa.Column("clicks", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("conversions", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("revenue_usd", sa.Numeric(14, 4), nullable=False, server_default="0"),
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
        sa.UniqueConstraint("publication_id", "link_id", name="uq_pub_affiliate_link"),
    )
    op.create_index("ix_pub_aff_publication", "publication_affiliate_links", ["publication_id"])
    op.create_index("ix_pub_aff_link", "publication_affiliate_links", ["link_id"])
    op.create_index("ix_pub_aff_campaign", "publication_affiliate_links", ["campaign_id"])

    # ── affiliate_link_clicks ─────────────────────────────────────────────────
    op.create_table(
        "affiliate_link_clicks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "link_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("affiliate_links.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "publication_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("publications.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "campaign_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("affiliate_campaigns.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "clicked_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("is_mock", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column(
            "estimated_revenue_usd",
            sa.Numeric(14, 6),
            nullable=False,
            server_default="0",
        ),
    )
    op.create_index("ix_click_link_id", "affiliate_link_clicks", ["link_id"])
    op.create_index("ix_click_clicked_at", "affiliate_link_clicks", ["clicked_at"])
    op.create_index("ix_click_publication", "affiliate_link_clicks", ["publication_id"])


def downgrade() -> None:
    op.drop_table("affiliate_link_clicks")
    op.drop_table("publication_affiliate_links")
    op.drop_index("ix_affiliate_campaign", "affiliate_links")
    op.drop_column("affiliate_links", "avg_order_value_usd")
    op.drop_column("affiliate_links", "niche_tags")
    op.drop_column("affiliate_links", "campaign_id")
    op.drop_table("affiliate_campaigns")
    op.execute("DROP TYPE campaign_status")
