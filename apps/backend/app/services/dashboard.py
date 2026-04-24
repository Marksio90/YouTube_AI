import asyncio
import uuid
from datetime import date, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.analytics import AnalyticsRepository
from app.repositories.brief import BriefRepository
from app.repositories.channel import ChannelRepository
from app.repositories.publication import PublicationRepository
from app.repositories.script import ScriptRepository
from app.repositories.topic import TopicRepository
from app.schemas.dashboard import AnalyticsSummary, DashboardSummary, EntityCounts
from app.schemas.publication import PublicationRead


class DashboardService:
    def __init__(self, db: AsyncSession) -> None:
        self.channel_repo = ChannelRepository(db)
        self.topic_repo = TopicRepository(db)
        self.brief_repo = BriefRepository(db)
        self.script_repo = ScriptRepository(db)
        self.publication_repo = PublicationRepository(db)
        self.analytics_repo = AnalyticsRepository(db)

    async def get_summary(self, owner_id: uuid.UUID) -> DashboardSummary:
        date_to = date.today()
        date_from = date_to - timedelta(days=27)

        (
            channels_rows,
            topic_counts,
            brief_counts,
            script_counts,
            pub_counts,
            analytics_agg,
            top_pubs,
        ) = await asyncio.gather(
            self.channel_repo.list_owned(owner_id, limit=1000),
            self.topic_repo.count_by_status(owner_id),
            self.brief_repo.count_by_status(owner_id),
            self.script_repo.count_by_status(owner_id),
            self.publication_repo.count_by_status(owner_id),
            self.analytics_repo.aggregate_for_user(owner_id, date_from=date_from, date_to=date_to),
            self.publication_repo.top_by_views(owner_id, limit=5),
        )

        channels_list, channels_total = channels_rows
        from app.db.models.channel import ChannelStatus
        active_channels = sum(1 for c in channels_list if c.status == ChannelStatus.active)

        return DashboardSummary(
            channels={"total": channels_total, "active": active_channels},
            topics=EntityCounts(
                total=sum(topic_counts.values()),
                by_status=topic_counts,
            ),
            briefs=EntityCounts(
                total=sum(brief_counts.values()),
                by_status=brief_counts,
            ),
            scripts=EntityCounts(
                total=sum(script_counts.values()),
                by_status=script_counts,
            ),
            publications=EntityCounts(
                total=sum(pub_counts.values()),
                by_status=pub_counts,
            ),
            analytics=AnalyticsSummary(
                period_days=28,
                total_views=analytics_agg["total_views"],
                total_revenue_usd=analytics_agg["total_revenue_usd"],
                subscribers_gained=analytics_agg["subscribers_gained"],
                avg_rpm=analytics_agg["avg_rpm"],
                avg_ctr=analytics_agg["avg_ctr"],
            ),
            top_publications=[PublicationRead.model_validate(p) for p in top_pubs],
        )
