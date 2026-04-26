"""
AffiliateService — Campaign CRUD, video attachment, click tracking, revenue estimation.

Click tracking
──────────────
  record_click()  logs to AffiliateLinkClick, bumps counters on AffiliateLink
                  and (if given) PublicationAffiliateLink, and Campaign.
  generate_mock_clicks()  seeds a link with realistic time-series events
                           for dev / demo purposes.

Revenue estimation
──────────────────
  estimate_revenue()  project 30d revenue = clicks × cvr × commission
  campaign_report()   full Campaign snapshot with per-link breakdown
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import structlog
from sqlalchemy import delete, func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.monetization import (
    AffiliateConversionIdempotency,
    AffiliateLink,
    AffiliateLinkClick,
    AffiliateSecurityAudit,
    AffiliateTrackingNonce,
    AffiliatePlatform,
    Campaign,
    CampaignStatus,
    PublicationAffiliateLink,
    RevenueSource,
)
from app.db.models.publication import Publication

log = structlog.get_logger(__name__)


class AffiliateService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    # ── Campaign CRUD ─────────────────────────────────────────────────────────

    async def list_campaigns(
        self,
        channel_id: uuid.UUID,
        *,
        status: CampaignStatus | None = None,
        limit: int = 50,
    ) -> list[Campaign]:
        q = select(Campaign).where(Campaign.channel_id == channel_id)
        if status:
            q = q.where(Campaign.status == status)
        q = q.order_by(Campaign.created_at.desc()).limit(limit)
        return list((await self._db.execute(q)).scalars().all())

    async def get_campaign(self, campaign_id: uuid.UUID) -> Campaign | None:
        return (
            await self._db.execute(
                select(Campaign).where(Campaign.id == campaign_id)
            )
        ).scalar_one_or_none()

    async def create_campaign(self, *, channel_id: uuid.UUID, data: dict[str, Any]) -> Campaign:
        campaign = Campaign(channel_id=channel_id, **data)
        self._db.add(campaign)
        await self._db.flush()
        return campaign

    async def update_campaign(
        self, campaign_id: uuid.UUID, data: dict[str, Any]
    ) -> Campaign | None:
        campaign = await self.get_campaign(campaign_id)
        if not campaign:
            return None
        for k, v in data.items():
            setattr(campaign, k, v)
        return campaign

    async def delete_campaign(self, campaign_id: uuid.UUID) -> bool:
        campaign = await self.get_campaign(campaign_id)
        if not campaign:
            return False
        await self._db.delete(campaign)
        return True

    # ── AffiliateLink CRUD ────────────────────────────────────────────────────

    async def list_links(
        self,
        channel_id: uuid.UUID,
        *,
        campaign_id: uuid.UUID | None = None,
        active_only: bool = True,
        limit: int = 100,
    ) -> list[AffiliateLink]:
        q = select(AffiliateLink).where(AffiliateLink.channel_id == channel_id)
        if campaign_id:
            q = q.where(AffiliateLink.campaign_id == campaign_id)
        if active_only:
            q = q.where(AffiliateLink.is_active.is_(True))
        q = q.order_by(AffiliateLink.total_revenue_usd.desc()).limit(limit)
        return list((await self._db.execute(q)).scalars().all())

    async def get_link(self, link_id: uuid.UUID) -> AffiliateLink | None:
        return (
            await self._db.execute(
                select(AffiliateLink).where(AffiliateLink.id == link_id)
            )
        ).scalar_one_or_none()

    async def create_link(self, *, channel_id: uuid.UUID, data: dict[str, Any]) -> AffiliateLink:
        link = AffiliateLink(channel_id=channel_id, **data)
        self._db.add(link)
        await self._db.flush()
        return link

    async def update_link(
        self, link_id: uuid.UUID, data: dict[str, Any]
    ) -> AffiliateLink | None:
        link = await self.get_link(link_id)
        if not link:
            return None
        for k, v in data.items():
            setattr(link, k, v)
        return link

    # ── Video attachment ──────────────────────────────────────────────────────

    async def attach_link_to_publication(
        self,
        *,
        publication_id: uuid.UUID,
        link_id: uuid.UUID,
        campaign_id: uuid.UUID | None = None,
        position: int = 0,
        description_text: str | None = None,
    ) -> PublicationAffiliateLink:
        existing = (
            await self._db.execute(
                select(PublicationAffiliateLink).where(
                    PublicationAffiliateLink.publication_id == publication_id,
                    PublicationAffiliateLink.link_id == link_id,
                )
            )
        ).scalar_one_or_none()

        if existing:
            existing.position = position
            if description_text is not None:
                existing.description_text = description_text
            if campaign_id is not None:
                existing.campaign_id = campaign_id
            return existing

        pal = PublicationAffiliateLink(
            publication_id=publication_id,
            link_id=link_id,
            campaign_id=campaign_id,
            position=position,
            description_text=description_text,
        )
        self._db.add(pal)
        await self._db.flush()
        return pal

    async def detach_link_from_publication(
        self, *, publication_id: uuid.UUID, link_id: uuid.UUID
    ) -> bool:
        result = await self._db.execute(
            delete(PublicationAffiliateLink).where(
                PublicationAffiliateLink.publication_id == publication_id,
                PublicationAffiliateLink.link_id == link_id,
            )
        )
        return result.rowcount > 0

    async def list_publication_links(
        self, publication_id: uuid.UUID
    ) -> list[PublicationAffiliateLink]:
        q = (
            select(PublicationAffiliateLink)
            .where(PublicationAffiliateLink.publication_id == publication_id)
            .order_by(PublicationAffiliateLink.position)
        )
        return list((await self._db.execute(q)).scalars().all())

    # ── Click tracking ────────────────────────────────────────────────────────

    async def record_click(
        self,
        link_id: uuid.UUID,
        *,
        publication_id: uuid.UUID | None = None,
        campaign_id: uuid.UUID | None = None,
        is_mock: bool = False,
        source: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
        fingerprint: str | None = None,
    ) -> AffiliateLinkClick:
        link = await self.get_link(link_id)
        if not link:
            raise ValueError(f"AffiliateLink {link_id} not found")

        estimated_rev = link.commission_per_conversion_usd * link.effective_cvr

        click = AffiliateLinkClick(
            link_id=link_id,
            publication_id=publication_id,
            campaign_id=campaign_id or link.campaign_id,
            source=source,
            ip_address=ip_address,
            user_agent=user_agent,
            fingerprint=fingerprint,
            clicked_at=datetime.now(tz=timezone.utc),
            is_mock=is_mock,
            estimated_revenue_usd=round(estimated_rev, 6),
        )
        self._db.add(click)

        # Bump link lifetime counters
        link.total_clicks += 1

        # Bump per-video counters
        if publication_id:
            pal = (
                await self._db.execute(
                    select(PublicationAffiliateLink).where(
                        PublicationAffiliateLink.publication_id == publication_id,
                        PublicationAffiliateLink.link_id == link_id,
                    )
                )
            ).scalar_one_or_none()
            if pal:
                pal.clicks += 1

        # Bump campaign counters
        if click.campaign_id:
            campaign = await self.get_campaign(click.campaign_id)
            if campaign:
                campaign.total_clicks += 1

        await self._db.flush()
        return click

    async def record_conversion(
        self,
        link_id: uuid.UUID,
        *,
        publication_id: uuid.UUID | None = None,
        revenue_usd: float | None = None,
        idempotency_key: str | None = None,
        source: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
        fingerprint: str | None = None,
    ) -> AffiliateLink | None:
        link = await self.get_link(link_id)
        if not link:
            return None

        actual_rev = revenue_usd if revenue_usd is not None else link.commission_per_conversion_usd

        if idempotency_key:
            existing = (
                await self._db.execute(
                    select(AffiliateConversionIdempotency).where(
                        AffiliateConversionIdempotency.link_id == link_id,
                        AffiliateConversionIdempotency.idempotency_key == idempotency_key,
                    )
                )
            ).scalar_one_or_none()
            if existing:
                return link

            self._db.add(
                AffiliateConversionIdempotency(
                    link_id=link_id,
                    idempotency_key=idempotency_key,
                    publication_id=publication_id,
                    revenue_usd=actual_rev,
                    source=source,
                    ip_address=ip_address,
                    user_agent=user_agent,
                    fingerprint=fingerprint,
                )
            )

        link.total_conversions += 1
        link.total_revenue_usd = float(link.total_revenue_usd) + actual_rev

        if publication_id:
            pal = (
                await self._db.execute(
                    select(PublicationAffiliateLink).where(
                        PublicationAffiliateLink.publication_id == publication_id,
                        PublicationAffiliateLink.link_id == link_id,
                    )
                )
            ).scalar_one_or_none()
            if pal:
                pal.conversions += 1
                pal.revenue_usd = float(pal.revenue_usd) + actual_rev

        if link.campaign_id:
            campaign = await self.get_campaign(link.campaign_id)
            if campaign:
                campaign.total_conversions += 1
                campaign.total_revenue_usd = float(campaign.total_revenue_usd) + actual_rev

        return link

    async def click_rate_limit_exceeded(
        self,
        link_id: uuid.UUID,
        *,
        ip_address: str | None,
        per_ip_limit: int,
        per_link_limit: int,
        window_seconds: int,
    ) -> tuple[bool, str | None]:
        if window_seconds <= 0:
            return False, None

        window_start = datetime.now(tz=timezone.utc) - timedelta(seconds=window_seconds)
        link_count = (
            await self._db.execute(
                select(func.count(AffiliateLinkClick.id)).where(
                    AffiliateLinkClick.link_id == link_id,
                    AffiliateLinkClick.clicked_at >= window_start,
                )
            )
        ).scalar_one()
        if link_count >= per_link_limit:
            return True, "link_rate_limit"

        if ip_address:
            ip_count = (
                await self._db.execute(
                    select(func.count(AffiliateLinkClick.id)).where(
                        AffiliateLinkClick.link_id == link_id,
                        AffiliateLinkClick.ip_address == ip_address,
                        AffiliateLinkClick.clicked_at >= window_start,
                    )
                )
            ).scalar_one()
            if ip_count >= per_ip_limit:
                return True, "ip_rate_limit"

        return False, None

    async def audit_security_event(
        self,
        *,
        event_type: str,
        decision: str,
        link_id: uuid.UUID | None,
        source: str | None,
        ip_address: str | None,
        user_agent: str | None,
        fingerprint: str | None,
        reason: str | None = None,
    ) -> None:
        self._db.add(
            AffiliateSecurityAudit(
                event_type=event_type,
                decision=decision,
                reason=reason,
                link_id=link_id,
                source=source,
                ip_address=ip_address,
                user_agent=user_agent,
                fingerprint=fingerprint,
            )
        )

    async def register_tracking_nonce(
        self,
        *,
        link_id: uuid.UUID,
        event_type: str,
        nonce: str,
    ) -> bool:
        existing = (
            await self._db.execute(
                select(AffiliateTrackingNonce).where(
                    AffiliateTrackingNonce.link_id == link_id,
                    AffiliateTrackingNonce.event_type == event_type,
                    AffiliateTrackingNonce.nonce == nonce,
                )
            )
        ).scalar_one_or_none()
        if existing:
            return False
        self._db.add(
            AffiliateTrackingNonce(
                link_id=link_id,
                event_type=event_type,
                nonce=nonce,
            )
        )
        return True

    # ── Mock click generation ─────────────────────────────────────────────────

    async def generate_mock_clicks(
        self,
        link_id: uuid.UUID,
        *,
        count: int = 30,
        days_back: int = 30,
    ) -> int:
        """Seed `count` mock click events spread over the past `days_back` days."""
        link = await self.get_link(link_id)
        if not link:
            raise ValueError(f"AffiliateLink {link_id} not found")

        now = datetime.now(tz=timezone.utc)
        estimated_rev = link.commission_per_conversion_usd * link.effective_cvr
        clicks: list[AffiliateLinkClick] = []

        for i in range(count):
            # Spread clicks evenly with slight random offset via modulo hash
            offset_hours = int((i / count) * days_back * 24)
            clicked_at = now - timedelta(hours=offset_hours)
            clicks.append(AffiliateLinkClick(
                link_id=link_id,
                publication_id=link.publication_id,
                campaign_id=link.campaign_id,
                clicked_at=clicked_at,
                is_mock=True,
                estimated_revenue_usd=round(estimated_rev, 6),
            ))

        self._db.add_all(clicks)
        link.total_clicks += count

        if link.campaign_id:
            campaign = await self.get_campaign(link.campaign_id)
            if campaign:
                campaign.total_clicks += count

        await self._db.flush()
        return count

    # ── Revenue estimation ────────────────────────────────────────────────────

    async def estimate_revenue(
        self,
        link_id: uuid.UUID,
        *,
        projected_clicks: int | None = None,
        days: int = 30,
    ) -> dict[str, Any]:
        """
        Project revenue for a link over `days` days.

        Uses actual CVR if data exists, otherwise 5% default.
        Uses actual clicks/day rate if history exists, otherwise uses projected_clicks.
        """
        link = await self.get_link(link_id)
        if not link:
            raise ValueError(f"AffiliateLink {link_id} not found")

        # Determine clicks/day rate
        if link.total_clicks > 0:
            # Use actual rate from click log
            oldest_click = (
                await self._db.execute(
                    select(func.min(AffiliateLinkClick.clicked_at)).where(
                        AffiliateLinkClick.link_id == link_id
                    )
                )
            ).scalar_one_or_none()

            if oldest_click:
                age_days = max(
                    1,
                    (datetime.now(tz=timezone.utc) - oldest_click).days,
                )
                clicks_per_day = link.total_clicks / age_days
            else:
                clicks_per_day = link.total_clicks / 30
        elif projected_clicks is not None:
            clicks_per_day = projected_clicks / days
        else:
            clicks_per_day = 10.0  # conservative default

        projected_total_clicks = int(clicks_per_day * days)
        cvr = link.effective_cvr
        projected_conversions = int(projected_total_clicks * cvr)
        commission = link.commission_per_conversion_usd
        projected_revenue = round(projected_conversions * commission, 4)

        return {
            "link_id": str(link_id),
            "link_name": link.name,
            "platform": link.platform.value,
            "days": days,
            "clicks_per_day": round(clicks_per_day, 2),
            "projected_clicks": projected_total_clicks,
            "effective_cvr": round(cvr * 100, 2),
            "projected_conversions": projected_conversions,
            "commission_per_conversion_usd": round(commission, 4),
            "projected_revenue_usd": projected_revenue,
            "confidence": "actual" if link.total_clicks >= 100 else "estimated",
        }

    # ── Campaign report ───────────────────────────────────────────────────────

    async def campaign_report(self, campaign_id: uuid.UUID) -> dict[str, Any]:
        """Full campaign snapshot with per-link breakdown and progress vs targets."""
        campaign = await self.get_campaign(campaign_id)
        if not campaign:
            raise ValueError(f"Campaign {campaign_id} not found")

        links = list(
            (
                await self._db.execute(
                    select(AffiliateLink).where(
                        AffiliateLink.campaign_id == campaign_id
                    )
                )
            ).scalars().all()
        )

        # 7-day click trend from event log
        seven_days_ago = datetime.now(tz=timezone.utc) - timedelta(days=7)
        recent_clicks = (
            await self._db.execute(
                select(func.count(AffiliateLinkClick.id)).where(
                    AffiliateLinkClick.campaign_id == campaign_id,
                    AffiliateLinkClick.clicked_at >= seven_days_ago,
                )
            )
        ).scalar_one_or_none() or 0

        link_rows = []
        for link in links:
            link_rows.append({
                "link_id": str(link.id),
                "name": link.name,
                "platform": link.platform.value,
                "total_clicks": link.total_clicks,
                "total_conversions": link.total_conversions,
                "total_revenue_usd": float(link.total_revenue_usd),
                "effective_cvr_pct": round(link.effective_cvr * 100, 2),
                "commission_per_conversion_usd": round(link.commission_per_conversion_usd, 4),
                "is_active": link.is_active,
            })

        return {
            "campaign_id": str(campaign_id),
            "name": campaign.name,
            "status": campaign.status.value,
            "total_clicks": campaign.total_clicks,
            "total_conversions": campaign.total_conversions,
            "total_revenue_usd": float(campaign.total_revenue_usd),
            "clicks_pct": campaign.clicks_pct,
            "revenue_pct": campaign.revenue_pct,
            "clicks_last_7d": recent_clicks,
            "target_clicks": campaign.target_clicks,
            "target_conversions": campaign.target_conversions,
            "target_revenue_usd": float(campaign.target_revenue_usd) if campaign.target_revenue_usd else None,
            "budget_usd": float(campaign.budget_usd) if campaign.budget_usd else None,
            "links": link_rows,
            "link_count": len(links),
        }

    # ── Click history ─────────────────────────────────────────────────────────

    async def click_history(
        self,
        link_id: uuid.UUID,
        *,
        days: int = 30,
        include_mock: bool = True,
    ) -> list[dict[str, Any]]:
        """Daily click counts for chart rendering."""
        since = datetime.now(tz=timezone.utc) - timedelta(days=days)
        q = select(AffiliateLinkClick).where(
            AffiliateLinkClick.link_id == link_id,
            AffiliateLinkClick.clicked_at >= since,
        )
        if not include_mock:
            q = q.where(AffiliateLinkClick.is_mock.is_(False))
        q = q.order_by(AffiliateLinkClick.clicked_at)
        clicks = list((await self._db.execute(q)).scalars().all())

        # Bucket by day
        buckets: dict[str, int] = {}
        for click in clicks:
            day = click.clicked_at.date().isoformat()
            buckets[day] = buckets.get(day, 0) + 1

        return [{"date": d, "clicks": c} for d, c in sorted(buckets.items())]
