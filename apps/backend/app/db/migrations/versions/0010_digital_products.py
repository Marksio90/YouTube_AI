"""Digital products — Product, ProductLink, ProductSale tables.

Revision ID: 0010_digital_products
Revises: 0009_affiliate_campaigns
Create Date: 2026-04-25
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0010_digital_products"
down_revision = "0009_affiliate_campaigns"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── enums ─────────────────────────────────────────────────────────────────
    op.execute(
        "CREATE TYPE product_type AS ENUM "
        "('ebook', 'course', 'template', 'software', 'membership', 'bundle', 'other')"
    )
    op.execute(
        "CREATE TYPE product_platform AS ENUM "
        "('gumroad', 'lemon_squeezy', 'payhip', 'teachable', 'podia', 'custom')"
    )

    # ── products ──────────────────────────────────────────────────────────────
    op.create_table(
        "products",
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
            "product_type",
            postgresql.ENUM(
                "ebook", "course", "template", "software",
                "membership", "bundle", "other",
                name="product_type", create_type=False,
            ),
            nullable=False,
            server_default="other",
        ),
        sa.Column(
            "platform",
            postgresql.ENUM(
                "gumroad", "lemon_squeezy", "payhip",
                "teachable", "podia", "custom",
                name="product_platform", create_type=False,
            ),
            nullable=False,
            server_default="custom",
        ),
        sa.Column("price_usd", sa.Float(), nullable=False, server_default="0"),
        sa.Column("currency", sa.String(3), nullable=False, server_default="USD"),
        sa.Column("sales_page_url", sa.Text(), nullable=True),
        sa.Column("checkout_url", sa.Text(), nullable=True),
        sa.Column("thumbnail_url", sa.Text(), nullable=True),
        sa.Column(
            "niche_tags",
            postgresql.ARRAY(sa.String(100)),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("total_sales", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_revenue_usd", sa.Numeric(14, 4), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("is_featured", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("launched_at", sa.DateTime(timezone=True), nullable=True),
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
    op.create_index("ix_product_channel",  "products", ["channel_id"])
    op.create_index("ix_product_type",     "products", ["product_type"])
    op.create_index("ix_product_platform", "products", ["platform"])
    op.create_index("ix_product_active",   "products", ["is_active"])

    # ── product_links (junction) ──────────────────────────────────────────────
    op.create_table(
        "product_links",
        sa.Column(
            "publication_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("publications.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "product_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("products.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("description_text", sa.String(500), nullable=True),
        sa.Column("clicks", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("sales", sa.Integer(), nullable=False, server_default="0"),
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
        sa.UniqueConstraint("publication_id", "product_id", name="uq_product_link"),
    )
    op.create_index("ix_product_link_pub",     "product_links", ["publication_id"])
    op.create_index("ix_product_link_product", "product_links", ["product_id"])

    # ── product_sales (event log) ─────────────────────────────────────────────
    op.create_table(
        "product_sales",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "product_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("products.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "publication_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("publications.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "sold_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("amount_usd", sa.Numeric(14, 4), nullable=False, server_default="0"),
        sa.Column("is_mock", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.create_index("ix_product_sale_product", "product_sales", ["product_id"])
    op.create_index("ix_product_sale_pub",     "product_sales", ["publication_id"])
    op.create_index("ix_product_sale_sold_at", "product_sales", ["sold_at"])


def downgrade() -> None:
    op.drop_table("product_sales")
    op.drop_table("product_links")
    op.drop_table("products")
    op.execute("DROP TYPE product_platform")
    op.execute("DROP TYPE product_type")
