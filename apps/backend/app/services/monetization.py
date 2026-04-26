"""
MonetizationService — revenue aggregation, ROI, and affiliate tracking.

Mock logic
──────────
When no RevenueStream rows exist for a channel/period, the service
generates deterministic mock data derived from AnalyticsSnapshot records.
This keeps the UI functional before real payment integrations are wired.

Mock formulas
─────────────
  ads:       snapshot.rpm × snapshot.watch_time_hours           (matches YT Studio)
  affiliate: views × 0.002 (click rate) × 0.05 (cvr) × 12.50  ($12.50 avg commission)
  products:  views × 0.0005 × 29.00                            ($29 avg product price)

Production path
───────────────
  1. Ads:        pull from YouTube Analytics API (already partially in sync_channel task)
  2. Affiliate:  webhook from Impact/Amazon/ShareASale → POST /monetization/webhooks/{platform}
  3. Products:   Gumroad/Lemon Squeezy webhook → POST /monetization/webhooks/products
  4. Sponsorship: manual entry via API

All revenue goes through upsert_stream() regardless of source.
Real data sets is_estimated=False.
"""
from __future__ import annotations

import hashlib
import uuid
from datetime import date, timedelta
from typing import Any

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.analytics import AnalyticsSnapshot
from app.db.models.channel import Channel
from app.db.models.monetization import (
    AffiliateLink,
    AffiliatePlatform,
    RevenueSource,
    RevenueStream,
)
from app.db.models.publication import Publication
from app.schemas.monetization import (
    AffiliateLinkCreate,
    AffiliateLinkUpdate,
    ChannelRevenueOverview,
    PublicationRevenueOverview,
    RevenueBySource,
    RevenueStreamCreate,
    ROISummary,
)

log = structlog.get_logger(__name__)

# ── Mock constants (swap for real when integrations live) ─────────────────────
_MOCK_AFF_CLICK_RATE  = 0.002   # 0.2% of viewers click affiliate link
_MOCK_AFF_CVR         = 0.05    # 5% click → purchase
_MOCK_AFF_COMMISSION  = 12.50   # avg $12.50 commission per conversion
_MOCK_PROD_RATE       = 0.0005  # 0.05% of viewers buy product
_MOCK_PROD_AOV        = 29.00   # avg $29 product price


def _mock_seed(channel_id: uuid.UUID, suffix: str) -> float:
    """Deterministic float 0-1 derived from channel_id + suffix."""
    raw = hashlib.md5(f"{channel_id}:{suffix}".encode()).hexdigest()
    return int(raw[:8], 16) / 0xFFFFFFFF


# ── Service ───────────────────────────────────────────────────────────────────

class MonetizationService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    # ── Streams ───────────────────────────────────────────────────────────────

    async def upsert_stream(self, payload: RevenueStreamCreate) -> RevenueStream:
        """Insert or update a revenue stream. Computes ROI automatically."""
        existing = (
            await self._db.execute(
                select(RevenueStream).where(
                    RevenueStream.channel_id    == payload.channel_id,
                    RevenueStream.publication_id == payload.publication_id,
                    RevenueStream.source        == payload.source,
                    RevenueStream.period_start  == payload.period_start,
                )
            )
        ).scalar_one_or_none()

        roi = (
            round(float(payload.revenue_usd) / float(payload.cost_usd) * 100, 2)
            if payload.cost_usd > 0
            else None
        )

        if existing:
            for k, v in payload.model_dump(exclude={"channel_id"}).items():
                setattr(existing, k, v)
            existing.roi_pct = roi
            return existing

        stream = RevenueStream(
            **payload.model_dump(),
            roi_pct=roi,
        )
        self._db.add(stream)
        await self._db.flush()
        return stream

    async def list_streams(
        self,
        channel_id: uuid.UUID,
        *,
        source: RevenueSource | None = None,
        publication_id: uuid.UUID | None = None,
        period_start: date | None = None,
        period_end: date | None = None,
        limit: int = 100,
    ) -> list[RevenueStream]:
        q = select(RevenueStream).where(RevenueStream.channel_id == channel_id)
        if source:
            q = q.where(RevenueStream.source == source)
        if publication_id:
            q = q.where(RevenueStream.publication_id == publication_id)
        if period_start:
            q = q.where(RevenueStream.period_start >= period_start)
        if period_end:
            q = q.where(RevenueStream.period_end <= period_end)
        q = q.order_by(RevenueStream.period_start.desc()).limit(limit)
        return list((await self._db.execute(q)).scalars().all())

    # ── Channel revenue overview ───────────────────────────────────────────────

    async def channel_overview(
        self,
        channel_id: uuid.UUID,
        *,
        period_start: date,
        period_end: date,
    ) -> ChannelRevenueOverview:
        streams = await self.list_streams(
            channel_id, period_start=period_start, period_end=period_end
        )

        if not streams:
            streams = await self._generate_mock_streams(
                channel_id, period_start=period_start, period_end=period_end
            )

        total_rev  = sum(float(s.revenue_usd) for s in streams)
        total_cost = sum(float(s.cost_usd) for s in streams)

        by_source = _aggregate_by_source(streams, total_rev)

        overall_roi = (
            round(total_rev / total_cost * 100, 2) if total_cost > 0 else None
        )

        top_streams = sorted(streams, key=lambda s: float(s.revenue_usd), reverse=True)[:10]

        return ChannelRevenueOverview(
            channel_id=channel_id,
            period_start=period_start,
            period_end=period_end,
            total_revenue_usd=round(total_rev, 4),
            total_cost_usd=round(total_cost, 4),
            overall_roi_pct=overall_roi,
            by_source=by_source,
            top_streams=top_streams,
        )

    # ── Publication revenue overview ──────────────────────────────────────────

    async def publication_overview(
        self,
        publication_id: uuid.UUID,
        *,
        owner_id: uuid.UUID,
        organization_id: uuid.UUID | None,
    ) -> PublicationRevenueOverview | None:
        publication = await self._get_owned_publication(
            publication_id,
            owner_id=owner_id,
            organization_id=organization_id,
        )
        if not publication:
            return None

        channel_id = publication.channel_id
        streams = await self.list_streams(channel_id, publication_id=publication_id)

        if not streams:
            streams = await self._generate_mock_pub_streams(
                channel_id=channel_id, publication_id=publication_id
            )

        total_rev  = sum(float(s.revenue_usd) for s in streams)
        total_cost = sum(float(s.cost_usd) for s in streams)
        roi = round(total_rev / total_cost * 100, 2) if total_cost > 0 else None

        return PublicationRevenueOverview(
            publication_id=publication_id,
            channel_id=channel_id,
            total_revenue_usd=round(total_rev, 4),
            total_cost_usd=round(total_cost, 4),
            roi_pct=roi,
            by_source=_aggregate_by_source(streams, total_rev),
            streams=streams,
        )

    # ── ROI summary ───────────────────────────────────────────────────────────

    async def roi_summary(
        self,
        channel_id: uuid.UUID,
        *,
        period_start: date,
        period_end: date,
    ) -> ROISummary:
        streams = await self.list_streams(
            channel_id, period_start=period_start, period_end=period_end
        )
        if not streams:
            streams = await self._generate_mock_streams(
                channel_id, period_start=period_start, period_end=period_end
            )

        total_rev  = sum(float(s.revenue_usd) for s in streams)
        total_cost = sum(float(s.cost_usd) for s in streams)
        overall_roi = round(total_rev / total_cost * 100, 2) if total_cost > 0 else None

        # Per-publication breakdown
        pub_ids = {s.publication_id for s in streams if s.publication_id}
        pub_revenue: dict[uuid.UUID, float] = {}
        pub_cost:    dict[uuid.UUID, float] = {}
        for s in streams:
            if s.publication_id:
                pub_revenue[s.publication_id] = (
                    pub_revenue.get(s.publication_id, 0) + float(s.revenue_usd)
                )
                pub_cost[s.publication_id] = (
                    pub_cost.get(s.publication_id, 0) + float(s.cost_usd)
                )

        pub_roi: dict[uuid.UUID, float | None] = {
            pid: (
                round(pub_revenue[pid] / pub_cost[pid] * 100, 2)
                if pub_cost.get(pid, 0) > 0
                else None
            )
            for pid in pub_ids
        }

        ranked = sorted(
            [(pid, r) for pid, r in pub_roi.items() if r is not None],
            key=lambda x: x[1],
            reverse=True,
        )
        best_id  = ranked[0][0]  if ranked else None
        worst_id = ranked[-1][0] if ranked else None

        num_videos = len(pub_ids) or 1

        return ROISummary(
            channel_id=channel_id,
            period_start=period_start,
            period_end=period_end,
            total_revenue_usd=round(total_rev, 4),
            total_cost_usd=round(total_cost, 4),
            roi_pct=overall_roi,
            revenue_per_video=round(total_rev / num_videos, 4),
            cost_per_video=round(total_cost / num_videos, 4),
            best_publication_id=best_id,
            best_publication_roi=pub_roi.get(best_id) if best_id else None,
            worst_publication_id=worst_id,
            worst_publication_roi=pub_roi.get(worst_id) if worst_id else None,
        )

    # ── Affiliate links ───────────────────────────────────────────────────────

    async def list_affiliate_links(
        self,
        channel_id: uuid.UUID,
        *,
        active_only: bool = True,
        limit: int = 100,
    ) -> list[AffiliateLink]:
        q = select(AffiliateLink).where(AffiliateLink.channel_id == channel_id)
        if active_only:
            q = q.where(AffiliateLink.is_active.is_(True))
        q = q.order_by(AffiliateLink.total_revenue_usd.desc()).limit(limit)
        return list((await self._db.execute(q)).scalars().all())

    async def create_affiliate_link(
        self, payload: AffiliateLinkCreate
    ) -> AffiliateLink:
        link = AffiliateLink(**payload.model_dump())
        self._db.add(link)
        await self._db.flush()
        return link

    async def update_affiliate_link(
        self,
        link_id: uuid.UUID,
        payload: AffiliateLinkUpdate,
        *,
        owner_id: uuid.UUID,
        organization_id: uuid.UUID | None,
    ) -> AffiliateLink | None:
        link = await self._get_owned_affiliate_link(
            link_id,
            owner_id=owner_id,
            organization_id=organization_id,
        )
        if not link:
            return None
        for k, v in payload.model_dump(exclude_none=True).items():
            setattr(link, k, v)
        return link

    async def record_click(
        self,
        link_id: uuid.UUID,
        *,
        owner_id: uuid.UUID,
        organization_id: uuid.UUID | None,
    ) -> AffiliateLink | None:
        """Increment click counter. Called by short-link redirect handler."""
        link = await self._get_owned_affiliate_link(
            link_id,
            owner_id=owner_id,
            organization_id=organization_id,
        )
        if link:
            link.total_clicks += 1
        return link

    async def record_conversion(
        self,
        link_id: uuid.UUID,
        revenue_usd: float,
        *,
        owner_id: uuid.UUID,
        organization_id: uuid.UUID | None,
    ) -> AffiliateLink | None:
        """Increment conversion counter + cumulative revenue."""
        link = await self._get_owned_affiliate_link(
            link_id,
            owner_id=owner_id,
            organization_id=organization_id,
        )
        if link:
            link.total_conversions += 1
            link.total_revenue_usd = float(link.total_revenue_usd) + revenue_usd
        return link

    async def _get_owned_publication(
        self,
        publication_id: uuid.UUID,
        *,
        owner_id: uuid.UUID,
        organization_id: uuid.UUID | None,
    ) -> Publication | None:
        q = (
            select(Publication)
            .join(Channel, Publication.channel_id == Channel.id)
            .where(
                Publication.id == publication_id,
                Channel.owner_id == owner_id,
            )
        )
        if organization_id is not None:
            q = q.where(Channel.organization_id == organization_id)
        return (await self._db.execute(q)).scalar_one_or_none()

    async def _get_owned_affiliate_link(
        self,
        link_id: uuid.UUID,
        *,
        owner_id: uuid.UUID,
        organization_id: uuid.UUID | None,
    ) -> AffiliateLink | None:
        q = (
            select(AffiliateLink)
            .join(Channel, AffiliateLink.channel_id == Channel.id)
            .where(
                AffiliateLink.id == link_id,
                Channel.owner_id == owner_id,
            )
        )
        if organization_id is not None:
            q = q.where(Channel.organization_id == organization_id)
        return (await self._db.execute(q)).scalar_one_or_none()

    # ── Mock generation ───────────────────────────────────────────────────────

    async def _generate_mock_streams(
        self,
        channel_id: uuid.UUID,
        *,
        period_start: date,
        period_end: date,
    ) -> list[RevenueStream]:
        """
        Build in-memory (not persisted) RevenueStream objects from
        AnalyticsSnapshot data for the given window.

        These are ephemeral — flushed only if caller commits.
        Call upsert_stream() to persist real data.
        """
        snapshots = (
            await self._db.execute(
                select(AnalyticsSnapshot).where(
                    AnalyticsSnapshot.channel_id == channel_id,
                    AnalyticsSnapshot.snapshot_date >= period_start,
                    AnalyticsSnapshot.snapshot_date <= period_end,
                    AnalyticsSnapshot.publication_id.is_(None),
                )
            )
        ).scalars().all()

        if not snapshots:
            return _mock_streams_from_seed(channel_id, period_start, period_end)

        total_views      = sum(s.views for s in snapshots)
        total_watch_h    = sum(s.watch_time_hours for s in snapshots)
        total_revenue    = sum(float(s.revenue_usd) for s in snapshots)
        avg_rpm          = (
            sum(s.rpm for s in snapshots) / len(snapshots) if snapshots else 2.5
        )

        seed = _mock_seed(channel_id, "cost")
        prod_cost = total_revenue * (0.3 + seed * 0.4)   # 30–70% of revenue

        streams: list[RevenueStream] = []

        # Ads stream
        streams.append(RevenueStream(
            channel_id=channel_id,
            publication_id=None,
            source=RevenueSource.ads,
            period_start=period_start,
            period_end=period_end,
            revenue_usd=round(total_revenue, 4),
            impressions=sum(s.impressions for s in snapshots),
            clicks=0,
            conversions=0,
            rpm=round(avg_rpm, 4),
            cpm=round(avg_rpm * 0.8, 4),
            cost_usd=round(prod_cost, 4),
            roi_pct=round(total_revenue / prod_cost * 100, 2) if prod_cost > 0 else None,
            is_estimated=True,
        ))

        # Affiliate stream
        aff_clicks = int(total_views * _MOCK_AFF_CLICK_RATE)
        aff_convs  = int(aff_clicks * _MOCK_AFF_CVR)
        aff_rev    = round(aff_convs * _MOCK_AFF_COMMISSION, 4)
        streams.append(RevenueStream(
            channel_id=channel_id,
            publication_id=None,
            source=RevenueSource.affiliate,
            period_start=period_start,
            period_end=period_end,
            revenue_usd=aff_rev,
            impressions=0,
            clicks=aff_clicks,
            conversions=aff_convs,
            commission_rate=_MOCK_AFF_COMMISSION,
            cost_usd=0.0,
            roi_pct=None,
            is_estimated=True,
        ))

        # Products stream (placeholder)
        prod_units = int(total_views * _MOCK_PROD_RATE)
        prod_rev   = round(prod_units * _MOCK_PROD_AOV, 4)
        streams.append(RevenueStream(
            channel_id=channel_id,
            publication_id=None,
            source=RevenueSource.products,
            period_start=period_start,
            period_end=period_end,
            revenue_usd=prod_rev,
            impressions=0,
            clicks=prod_units,
            conversions=prod_units,
            cost_usd=round(prod_rev * 0.35, 4),  # 35% COGS placeholder
            roi_pct=round(prod_rev / (prod_rev * 0.35) * 100, 2) if prod_rev > 0 else None,
            is_estimated=True,
        ))

        return streams

    async def _generate_mock_pub_streams(
        self,
        channel_id: uuid.UUID,
        publication_id: uuid.UUID,
    ) -> list[RevenueStream]:
        snapshots = (
            await self._db.execute(
                select(AnalyticsSnapshot).where(
                    AnalyticsSnapshot.publication_id == publication_id,
                )
            )
        ).scalars().all()

        if not snapshots:
            return []

        period_start = min(s.snapshot_date for s in snapshots)
        period_end   = max(s.snapshot_date for s in snapshots)
        total_views  = sum(s.views for s in snapshots)
        total_rev    = sum(float(s.revenue_usd) for s in snapshots)
        avg_rpm      = sum(s.rpm for s in snapshots) / len(snapshots)

        seed      = _mock_seed(channel_id, str(publication_id))
        prod_cost = total_rev * (0.25 + seed * 0.5)

        streams: list[RevenueStream] = []

        streams.append(RevenueStream(
            channel_id=channel_id,
            publication_id=publication_id,
            source=RevenueSource.ads,
            period_start=period_start,
            period_end=period_end,
            revenue_usd=round(total_rev, 4),
            rpm=round(avg_rpm, 4),
            cpm=round(avg_rpm * 0.8, 4),
            cost_usd=round(prod_cost, 4),
            roi_pct=round(total_rev / prod_cost * 100, 2) if prod_cost > 0 else None,
            is_estimated=True,
        ))

        aff_clicks = int(total_views * _MOCK_AFF_CLICK_RATE)
        aff_convs  = int(aff_clicks * _MOCK_AFF_CVR)
        aff_rev    = round(aff_convs * _MOCK_AFF_COMMISSION, 4)
        streams.append(RevenueStream(
            channel_id=channel_id,
            publication_id=publication_id,
            source=RevenueSource.affiliate,
            period_start=period_start,
            period_end=period_end,
            revenue_usd=aff_rev,
            clicks=aff_clicks,
            conversions=aff_convs,
            commission_rate=_MOCK_AFF_COMMISSION,
            is_estimated=True,
        ))

        return streams


# ── Private helpers ───────────────────────────────────────────────────────────

def _aggregate_by_source(
    streams: list[RevenueStream], total_rev: float
) -> list[RevenueBySource]:
    agg: dict[str, dict] = {}
    for s in streams:
        src = s.source.value if hasattr(s.source, "value") else str(s.source)
        if src not in agg:
            agg[src] = {"revenue": 0.0, "cost": 0.0}
        agg[src]["revenue"] += float(s.revenue_usd)
        agg[src]["cost"]    += float(s.cost_usd)

    result: list[RevenueBySource] = []
    for src, data in sorted(agg.items(), key=lambda x: x[1]["revenue"], reverse=True):
        rev  = data["revenue"]
        cost = data["cost"]
        result.append(RevenueBySource(
            source=src,           # type: ignore[arg-type]
            revenue_usd=round(rev, 4),
            share_pct=round(rev / total_rev * 100, 2) if total_rev > 0 else 0.0,
            roi_pct=round(rev / cost * 100, 2) if cost > 0 else None,
        ))
    return result


def _mock_streams_from_seed(
    channel_id: uuid.UUID, period_start: date, period_end: date
) -> list[RevenueStream]:
    """Fully synthetic fallback — no real analytics data available."""
    seed = _mock_seed(channel_id, "base")
    base_rev = 200 + seed * 1800   # $200–$2000

    streams = []
    sources_rev = {
        RevenueSource.ads:         base_rev * 0.70,
        RevenueSource.affiliate:   base_rev * 0.20,
        RevenueSource.products:    base_rev * 0.10,
    }
    for source, rev in sources_rev.items():
        cost = rev * (0.25 + _mock_seed(channel_id, source.value) * 0.4)
        streams.append(RevenueStream(
            channel_id=channel_id,
            source=source,
            period_start=period_start,
            period_end=period_end,
            revenue_usd=round(rev, 4),
            cost_usd=round(cost, 4),
            roi_pct=round(rev / cost * 100, 2) if cost > 0 else None,
            is_estimated=True,
        ))
    return streams
