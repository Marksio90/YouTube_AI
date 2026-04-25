"""
Digital products — Product, ProductLink (pub↔product junction), ProductSale event log.

Product types
─────────────
  ebook        PDF / digital book
  course       video/text course (Teachable, Kajabi, etc.)
  template     Notion, Figma, spreadsheet, etc.
  software     app, plugin, script
  membership   recurring community / content access
  bundle       multiple products grouped
  other        catch-all

Platforms
─────────
  gumroad / lemon_squeezy / payhip / teachable / podia / custom

Revenue flow
────────────
  ProductSale  event log  →  ProductLink.{sales,revenue_usd}  (per-video)
                          →  Product.{total_sales,total_revenue_usd}  (lifetime)
"""
from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.db.models.channel import Channel
    from app.db.models.publication import Publication


class ProductType(str, enum.Enum):
    ebook      = "ebook"
    course     = "course"
    template   = "template"
    software   = "software"
    membership = "membership"
    bundle     = "bundle"
    other      = "other"


class ProductPlatform(str, enum.Enum):
    gumroad       = "gumroad"
    lemon_squeezy = "lemon_squeezy"
    payhip        = "payhip"
    teachable     = "teachable"
    podia         = "podia"
    custom        = "custom"


# ── Product ───────────────────────────────────────────────────────────────────

class Product(Base, UUIDMixin, TimestampMixin):
    """
    A digital product owned by a channel.

    Attached to publications via ProductLink (many-to-many).
    Lifetime sales and revenue counters updated on each ProductSale event.
    """

    __tablename__ = "products"
    __table_args__ = (
        Index("ix_product_channel", "channel_id"),
        Index("ix_product_type", "product_type"),
        Index("ix_product_platform", "platform"),
        Index("ix_product_active", "is_active"),
    )

    channel_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("channels.id", ondelete="CASCADE"),
        nullable=False,
    )

    name:        Mapped[str]           = mapped_column(String(200), nullable=False)
    description: Mapped[str | None]    = mapped_column(Text, nullable=True)
    product_type: Mapped[ProductType]  = mapped_column(
        Enum(ProductType, name="product_type"),
        nullable=False,
        default=ProductType.other,
    )
    platform: Mapped[ProductPlatform]  = mapped_column(
        Enum(ProductPlatform, name="product_platform"),
        nullable=False,
        default=ProductPlatform.custom,
    )

    # Pricing
    price_usd:     Mapped[float]       = mapped_column(Float, nullable=False, default=0.0)
    currency:      Mapped[str]         = mapped_column(String(3), nullable=False, default="USD")

    # URLs
    sales_page_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    checkout_url:   Mapped[str | None] = mapped_column(Text, nullable=True)
    thumbnail_url:  Mapped[str | None] = mapped_column(Text, nullable=True)

    # Niche matching (same pattern as AffiliateLink)
    niche_tags: Mapped[list[str]] = mapped_column(
        ARRAY(String(100)), nullable=False, default=list,
    )

    # Lifetime counters (denormalized for fast reads)
    total_sales:       Mapped[int]   = mapped_column(Integer,        nullable=False, default=0)
    total_revenue_usd: Mapped[float] = mapped_column(Numeric(14, 4), nullable=False, default=0.0)

    is_active:   Mapped[bool]            = mapped_column(Boolean, nullable=False, default=True)
    is_featured: Mapped[bool]            = mapped_column(Boolean, nullable=False, default=False)
    launched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    channel:    Mapped["Channel"]                = relationship("Channel")
    pub_links:  Mapped[list["ProductLink"]]      = relationship(
        "ProductLink", back_populates="product", lazy="select"
    )

    @property
    def revenue_per_sale(self) -> float:
        if self.total_sales > 0:
            return round(float(self.total_revenue_usd) / self.total_sales, 4)
        return self.price_usd

    def __repr__(self) -> str:
        return f"<Product {self.name!r} [{self.product_type.value}] ${self.price_usd}>"


# ── ProductLink ───────────────────────────────────────────────────────────────

class ProductLink(Base, TimestampMixin):
    """
    Many-to-many junction: publications ↔ products.

    Tracks per-video sales and revenue independently from
    the lifetime counters on Product.
    """

    __tablename__ = "product_links"
    __table_args__ = (
        UniqueConstraint("publication_id", "product_id", name="uq_product_link"),
        Index("ix_product_link_pub", "publication_id"),
        Index("ix_product_link_product", "product_id"),
    )

    publication_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("publications.id", ondelete="CASCADE"),
        primary_key=True,
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("products.id", ondelete="CASCADE"),
        primary_key=True,
    )

    position:         Mapped[int]        = mapped_column(Integer, nullable=False, default=0)
    description_text: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Per-video counters
    clicks:      Mapped[int]   = mapped_column(Integer,        nullable=False, default=0)
    sales:       Mapped[int]   = mapped_column(Integer,        nullable=False, default=0)
    revenue_usd: Mapped[float] = mapped_column(Numeric(14, 4), nullable=False, default=0.0)

    publication: Mapped["Publication"]  = relationship("Publication")
    product:     Mapped["Product"]      = relationship("Product", back_populates="pub_links")

    @property
    def cvr(self) -> float | None:
        if self.clicks > 0:
            return round(self.sales / self.clicks, 4)
        return None

    def __repr__(self) -> str:
        return f"<ProductLink pub={self.publication_id} product={self.product_id}>"


# ── ProductSale ───────────────────────────────────────────────────────────────

class ProductSale(Base, UUIDMixin):
    """
    Time-series sale event log.

    One row per sale.  is_mock=True for seeded demo data.
    Used for daily/weekly sales trend charts and revenue reporting.
    """

    __tablename__ = "product_sales"
    __table_args__ = (
        Index("ix_product_sale_product", "product_id"),
        Index("ix_product_sale_pub", "publication_id"),
        Index("ix_product_sale_sold_at", "sold_at"),
    )

    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
    )
    publication_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("publications.id", ondelete="SET NULL"),
        nullable=True,
    )

    sold_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    amount_usd: Mapped[float] = mapped_column(
        Numeric(14, 4), nullable=False, default=0.0,
        comment="Actual sale amount (price at time of purchase)",
    )
    is_mock: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    product: Mapped["Product"] = relationship("Product")

    def __repr__(self) -> str:
        return f"<ProductSale product={self.product_id} ${float(self.amount_usd):.2f} at={self.sold_at}>"
