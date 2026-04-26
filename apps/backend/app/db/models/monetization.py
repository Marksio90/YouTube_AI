"""
Monetization models — revenue tracking, affiliate links, campaigns.

Revenue sources
───────────────
  ads        YouTube AdSense RPM × watch hours
  affiliate  click × conversion_rate × commission_usd
  products   placeholder for digital/physical product sales
  sponsorship placeholder for brand deals

Affiliate system
────────────────
  AffiliateLink           trackable link; can belong to a Campaign
  Campaign                groups links by channel + niche; tracks targets vs actuals
  PublicationAffiliateLink  junction: many publications ↔ many links + per-video counters
  AffiliateLinkClick      event log for time-series click analytics (mock and real)
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
from sqlalchemy.dialects.postgresql import ARRAY, UUID
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


class CampaignStatus(str, enum.Enum):
    draft     = "draft"
    active    = "active"
    paused    = "paused"
    completed = "completed"
    archived  = "archived"


# ── RevenueStream ─────────────────────────────────────────────────────────────

class RevenueStream(Base, UUIDMixin, TimestampMixin):
    """
    Aggregated revenue per (channel, publication?, period, source).

    Channel-level: publication_id = NULL, covers all publications.
    Publication-level: publication_id set, single video breakdown.
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

    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end:   Mapped[date] = mapped_column(Date, nullable=False)

    revenue_usd:   Mapped[float] = mapped_column(Numeric(14, 4), nullable=False, default=0.0)
    impressions:   Mapped[int]   = mapped_column(Integer,        nullable=False, default=0)
    clicks:        Mapped[int]   = mapped_column(Integer,        nullable=False, default=0)
    conversions:   Mapped[int]   = mapped_column(Integer,        nullable=False, default=0)

    rpm:  Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    cpm:  Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    commission_rate: Mapped[float | None] = mapped_column(Float, nullable=True)

    cost_usd: Mapped[float] = mapped_column(Numeric(14, 4), nullable=False, default=0.0)
    roi_pct: Mapped[float | None] = mapped_column(Float, nullable=True)

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


# ── Campaign ──────────────────────────────────────────────────────────────────

class Campaign(Base, UUIDMixin, TimestampMixin):
    """
    Groups affiliate links by channel and niche.

    Tracks targets vs. actuals for clicks, conversions, and revenue.
    topic_ids is a denormalized ARRAY of topic UUIDs (not a FK join) so it
    survives topic deletion without cascading.
    """

    __tablename__ = "affiliate_campaigns"
    __table_args__ = (
        Index("ix_campaign_channel", "channel_id"),
        Index("ix_campaign_status", "status"),
    )

    channel_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("channels.id", ondelete="CASCADE"),
        nullable=False,
    )

    name:        Mapped[str]          = mapped_column(String(200), nullable=False)
    description: Mapped[str | None]   = mapped_column(Text, nullable=True)
    status:      Mapped[CampaignStatus] = mapped_column(
        Enum(CampaignStatus, name="campaign_status"),
        nullable=False,
        default=CampaignStatus.draft,
        index=True,
    )

    # Niche + topic mapping
    niche_tags: Mapped[list[str]] = mapped_column(
        ARRAY(String(100)), nullable=False, default=list,
        comment="Niche labels e.g. ['finance', 'investing']",
    )
    topic_ids: Mapped[list[str]] = mapped_column(
        ARRAY(String(36)), nullable=False, default=list,
        comment="Denormalized topic UUIDs for fast lookup",
    )

    # Schedule
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ends_at:   Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Targets
    target_clicks:      Mapped[int | None]   = mapped_column(Integer, nullable=True)
    target_conversions: Mapped[int | None]   = mapped_column(Integer, nullable=True)
    target_revenue_usd: Mapped[float | None] = mapped_column(Numeric(14, 4), nullable=True)
    budget_usd:         Mapped[float | None] = mapped_column(Numeric(14, 4), nullable=True)

    # Aggregated actuals (updated on each click/conversion event)
    total_clicks:      Mapped[int]   = mapped_column(Integer,        nullable=False, default=0)
    total_conversions: Mapped[int]   = mapped_column(Integer,        nullable=False, default=0)
    total_revenue_usd: Mapped[float] = mapped_column(Numeric(14, 4), nullable=False, default=0.0)

    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    channel: Mapped["Channel"] = relationship("Channel")
    links: Mapped[list["AffiliateLink"]] = relationship(
        "AffiliateLink", back_populates="campaign", lazy="select"
    )

    @property
    def clicks_pct(self) -> float | None:
        if self.target_clicks and self.target_clicks > 0:
            return round(self.total_clicks / self.target_clicks * 100, 1)
        return None

    @property
    def revenue_pct(self) -> float | None:
        target = float(self.target_revenue_usd) if self.target_revenue_usd else None
        if target and target > 0:
            return round(float(self.total_revenue_usd) / target * 100, 1)
        return None

    def __repr__(self) -> str:
        return f"<Campaign {self.name!r} [{self.status.value}]>"


# ── AffiliateLink ─────────────────────────────────────────────────────────────

class AffiliateLink(Base, UUIDMixin, TimestampMixin):
    """
    Trackable affiliate link.

    Belongs optionally to a Campaign.
    Attached to videos via PublicationAffiliateLink (many-to-many).
    publication_id kept as "primary" video shortcut for backward compat.
    """

    __tablename__ = "affiliate_links"
    __table_args__ = (
        Index("ix_affiliate_channel", "channel_id"),
        Index("ix_affiliate_platform", "platform"),
        Index("ix_affiliate_active", "is_active"),
        Index("ix_affiliate_campaign", "campaign_id"),
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
    campaign_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("affiliate_campaigns.id", ondelete="SET NULL"),
        nullable=True,
    )

    platform: Mapped[AffiliatePlatform] = mapped_column(
        Enum(AffiliatePlatform, name="affiliate_platform"),
        nullable=False,
        default=AffiliatePlatform.custom,
    )

    name:            Mapped[str]        = mapped_column(String(200), nullable=False)
    destination_url: Mapped[str]        = mapped_column(Text, nullable=False)
    slug:            Mapped[str | None] = mapped_column(String(100), nullable=True, unique=True)
    tracking_id:     Mapped[str | None] = mapped_column(String(200), nullable=True)

    # Niche tags for channel/topic matching
    niche_tags: Mapped[list[str]] = mapped_column(
        ARRAY(String(100)), nullable=False, default=list,
    )

    # Commission structure
    commission_type:  Mapped[str]   = mapped_column(String(20), nullable=False, default="percentage")
    commission_value: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    # avg_order_value used for percentage commission revenue estimation
    avg_order_value_usd: Mapped[float] = mapped_column(Float, nullable=False, default=50.0)

    # Lifetime counters
    total_clicks:      Mapped[int]   = mapped_column(Integer,        nullable=False, default=0)
    total_conversions: Mapped[int]   = mapped_column(Integer,        nullable=False, default=0)
    total_revenue_usd: Mapped[float] = mapped_column(Numeric(14, 4), nullable=False, default=0.0)

    is_active:  Mapped[bool]           = mapped_column(Boolean, nullable=False, default=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    channel:     Mapped["Channel"]            = relationship("Channel")
    publication: Mapped["Publication | None"] = relationship("Publication")
    campaign:    Mapped["Campaign | None"]    = relationship("Campaign", back_populates="links")
    pub_links:   Mapped[list["PublicationAffiliateLink"]] = relationship(
        "PublicationAffiliateLink", back_populates="link", lazy="select"
    )

    @property
    def commission_per_conversion_usd(self) -> float:
        if self.commission_type == "fixed":
            return self.commission_value
        return round(self.avg_order_value_usd * self.commission_value / 100, 4)

    @property
    def effective_cvr(self) -> float:
        if self.total_clicks > 0:
            return self.total_conversions / self.total_clicks
        return 0.05  # 5% default

    def __repr__(self) -> str:
        return f"<AffiliateLink {self.name!r} platform={self.platform.value}>"


# ── PublicationAffiliateLink ──────────────────────────────────────────────────

class PublicationAffiliateLink(Base, TimestampMixin):
    """
    Many-to-many junction: publications ↔ affiliate_links.

    Tracks per-video click/conversion/revenue counters independently from
    the lifetime link counters on AffiliateLink.
    """

    __tablename__ = "publication_affiliate_links"
    __table_args__ = (
        UniqueConstraint("publication_id", "link_id", name="uq_pub_affiliate_link"),
        Index("ix_pub_aff_publication", "publication_id"),
        Index("ix_pub_aff_link", "link_id"),
        Index("ix_pub_aff_campaign", "campaign_id"),
    )

    publication_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("publications.id", ondelete="CASCADE"),
        primary_key=True,
    )
    link_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("affiliate_links.id", ondelete="CASCADE"),
        primary_key=True,
    )
    campaign_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("affiliate_campaigns.id", ondelete="SET NULL"),
        nullable=True,
    )

    position:         Mapped[int]          = mapped_column(Integer, nullable=False, default=0)
    description_text: Mapped[str | None]   = mapped_column(String(500), nullable=True)

    # Per-video isolated counters
    clicks:      Mapped[int]   = mapped_column(Integer,        nullable=False, default=0)
    conversions: Mapped[int]   = mapped_column(Integer,        nullable=False, default=0)
    revenue_usd: Mapped[float] = mapped_column(Numeric(14, 4), nullable=False, default=0.0)

    publication: Mapped["Publication"]    = relationship("Publication")
    link:        Mapped["AffiliateLink"]  = relationship("AffiliateLink", back_populates="pub_links")

    def __repr__(self) -> str:
        return f"<PublicationAffiliateLink pub={self.publication_id} link={self.link_id}>"


# ── AffiliateLinkClick ────────────────────────────────────────────────────────

class AffiliateLinkClick(Base, UUIDMixin):
    """
    Time-series click event log.

    One row per click event.  Supports both real and mock events
    (is_mock=True when generated by the platform for demo/dev purposes).
    Used for daily/weekly click trend charts.
    """

    __tablename__ = "affiliate_link_clicks"
    __table_args__ = (
        Index("ix_click_link_id", "link_id"),
        Index("ix_click_clicked_at", "clicked_at"),
        Index("ix_click_publication", "publication_id"),
    )

    link_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("affiliate_links.id", ondelete="CASCADE"),
        nullable=False,
    )
    publication_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("publications.id", ondelete="SET NULL"),
        nullable=True,
    )
    campaign_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("affiliate_campaigns.id", ondelete="SET NULL"),
        nullable=True,
    )
    source: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
    fingerprint: Mapped[str | None] = mapped_column(String(256), nullable=True)

    clicked_at:            Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    is_mock:               Mapped[bool]  = mapped_column(Boolean, nullable=False, default=False)
    estimated_revenue_usd: Mapped[float] = mapped_column(
        Numeric(14, 6), nullable=False, default=0.0,
        comment="commission_per_conversion × cvr for this click",
    )

    link: Mapped["AffiliateLink"] = relationship("AffiliateLink")

    def __repr__(self) -> str:
        return f"<AffiliateLinkClick link={self.link_id} at={self.clicked_at}>"


class AffiliateConversionIdempotency(Base, UUIDMixin):
    __tablename__ = "affiliate_conversion_idempotency"
    __table_args__ = (
        UniqueConstraint("link_id", "idempotency_key", name="uq_aff_conversion_link_key"),
        Index("ix_aff_conversion_idempotency_link_id", "link_id"),
    )

    link_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("affiliate_links.id", ondelete="CASCADE"),
        nullable=False,
    )
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    publication_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("publications.id", ondelete="SET NULL"),
        nullable=True,
    )
    revenue_usd: Mapped[float] = mapped_column(Numeric(14, 4), nullable=False, default=0.0)
    source: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
    fingerprint: Mapped[str | None] = mapped_column(String(256), nullable=True)
    processed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class AffiliateSecurityAudit(Base, UUIDMixin):
    __tablename__ = "affiliate_security_audit"
    __table_args__ = (
        Index("ix_aff_security_audit_link_id", "link_id"),
        Index("ix_aff_security_audit_event_time", "event_time"),
    )

    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    decision: Mapped[str] = mapped_column(String(32), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    link_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("affiliate_links.id", ondelete="SET NULL"),
        nullable=True,
    )
    source: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
    fingerprint: Mapped[str | None] = mapped_column(String(256), nullable=True)
    event_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class AffiliateTrackingNonce(Base, UUIDMixin):
    __tablename__ = "affiliate_tracking_nonces"
    __table_args__ = (
        UniqueConstraint("link_id", "event_type", "nonce", name="uq_aff_tracking_nonce"),
        Index("ix_aff_tracking_nonce_event_time", "created_at"),
    )

    link_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("affiliate_links.id", ondelete="CASCADE"),
        nullable=False,
    )
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    nonce: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
