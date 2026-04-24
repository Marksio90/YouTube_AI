"""
RevenueStream  — one record per (channel, publication?, period, source).
AffiliateLink  — trackable affiliate link attached to a channel/publication.

Revenue sources
───────────────
  ads        YouTube AdSense RPM × watch hours
  affiliate  click × conversion_rate × commission_usd
  products   placeholder for digital/physical product sales
  sponsorship placeholder for brand deals

ROI
───
  revenue_usd / cost_usd × 100  (cost = production cost on Publication)
  NULL when cost = 0 or unknown.
"""
from __future__ import annotations

import enum
import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    Date,
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
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.db.models.channel import Channel
    from app.db.models.publication import Publication


# ── Enums ─────────────────────────────────────────────────────────────────────

class RevenueSource(str, enum.Enum):
    ads         = "ads"
    affiliate   = "affiliate"
    products    = "products"
    sponsorship = "sponsorship"


class AffiliatePlatform(str, enum.Enum):
    amazon      = "amazon"
    impact      = "impact"
    shareasale  = "shareasale"
    cj          = "cj"
    custom      = "custom"


# ── RevenueStream ─────────────────────────────────────────────────────────────

class RevenueStream(Base, UUIDMixin, TimestampMixin):
    """
    Aggregated revenue per (channel, publication?, period, source).

    Channel-level: publication_id = NULL, covers all publications.
    Publication-level: publication_id set, single video breakdown.

    For ads: computed from analytics_snapshots (rpm × watch_time_hours).
    For affiliate/products/sponsorship: entered manually or via API.

    period_start / period_end define the revenue window (usually 1 month).
    """

    __tablename__ = "revenue_streams"
    __table_args__ = (
        UniqueConstraint(
            "channel_id", "publication_id", "source", "period_start",
            name="uq_revenue_channel_pub_source_period",
        ),
        Index("ix_revenue_channel_source", "channel_id", "source"),
        Index("ix_revenue_publication", "publication_id"),
        Index("ix_revenue_period", "period_start"),
    )

    channel_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("channels.id", ondelete="CASCADE"),
        nullable=False,
    )
    publication_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("publications.id", ondelete="CASCADE"),
        nullable=True,
    )

    source: Mapped[RevenueSource] = mapped_column(
        Enum(RevenueSource, name="revenue_source"),
        nullable=False,
    )

    # Period window
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end:   Mapped[date] = mapped_column(Date, nullable=False)

    # Revenue figures
    revenue_usd:   Mapped[float] = mapped_column(Numeric(14, 4), nullable=False, default=0.0)
    impressions:   Mapped[int]   = mapped_column(Integer,        nullable=False, default=0)
    clicks:        Mapped[int]   = mapped_column(Integer,        nullable=False, default=0)
    conversions:   Mapped[int]   = mapped_column(Integer,        nullable=False, default=0)

    # Ads-specific
    rpm:  Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    cpm:  Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    # Affiliate-specific
    commission_rate: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Cost for ROI (production cost attributable to this video/period)
    cost_usd: Mapped[float] = mapped_column(Numeric(14, 4), nullable=False, default=0.0)

    # Computed ROI = revenue / cost * 100 (NULL if cost = 0)
    roi_pct: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Data provenance
    is_estimated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    notes: Mapped[str | None]  = mapped_column(Text, nullable=True)

    channel:     Mapped["Channel"]            = relationship("Channel")
    publication: Mapped["Publication | None"] = relationship("Publication")

    def __repr__(self) -> str:
        return (
            f"<RevenueStream {self.source.value} "
            f"ch={self.channel_id} "
            f"${float(self.revenue_usd):.2f} "
            f"[{self.period_start}→{self.period_end}]>"
        )


# ── AffiliateLink ─────────────────────────────────────────────────────────────

class AffiliateLink(Base, UUIDMixin, TimestampMixin):
    """
    Trackable affiliate link.  One link can appear across multiple publications
    (e.g. a recurring Amazon product link).

    Click/conversion data synced from platform APIs (future) or entered
    manually.  slug is used for short-link generation (e.g. /go/{slug}).
    """

    __tablename__ = "affiliate_links"
    __table_args__ = (
        Index("ix_affiliate_channel", "channel_id"),
        Index("ix_affiliate_platform", "platform"),
        Index("ix_affiliate_active", "is_active"),
    )

    channel_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("channels.id", ondelete="CASCADE"),
        nullable=False,
    )
    publication_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("publications.id", ondelete="SET NULL"),
        nullable=True,
    )

    platform: Mapped[AffiliatePlatform] = mapped_column(
        Enum(AffiliatePlatform, name="affiliate_platform"),
        nullable=False,
        default=AffiliatePlatform.custom,
    )

    name:            Mapped[str]          = mapped_column(String(200), nullable=False)
    destination_url: Mapped[str]          = mapped_column(Text, nullable=False)
    slug:            Mapped[str | None]   = mapped_column(String(100), nullable=True, unique=True)
    tracking_id:     Mapped[str | None]   = mapped_column(String(200), nullable=True)

    # Commission structure
    commission_type:  Mapped[str]   = mapped_column(String(20), nullable=False, default="percentage")  # percentage | fixed
    commission_value: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)  # % or $ amount

    # Lifetime performance counters
    total_clicks:      Mapped[int]   = mapped_column(Integer,        nullable=False, default=0)
    total_conversions: Mapped[int]   = mapped_column(Integer,        nullable=False, default=0)
    total_revenue_usd: Mapped[float] = mapped_column(Numeric(14, 4), nullable=False, default=0.0)

    is_active:  Mapped[bool]          = mapped_column(Boolean, nullable=False, default=True)
    expires_at: Mapped[datetime|None] = mapped_column(DateTime(timezone=True), nullable=True)

    channel:     Mapped["Channel"]            = relationship("Channel")
    publication: Mapped["Publication | None"] = relationship("Publication")

    def __repr__(self) -> str:
        return f"<AffiliateLink {self.name} platform={self.platform.value}>"
