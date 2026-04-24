import uuid
from datetime import date, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.repositories.analytics import AnalyticsRepository
from app.repositories.channel import ChannelRepository
from app.schemas.analytics import (
    AnalyticsAggregate,
    AnalyticsSnapshotCreate,
    AnalyticsSnapshotRead,
)


class AnalyticsService:
    def __init__(self, db: AsyncSession) -> None:
        self.repo = AnalyticsRepository(db)
        self.channel_repo = ChannelRepository(db)

    async def get_channel_aggregate(
        self,
        channel_id: uuid.UUID,
        *,
        owner_id: uuid.UUID,
        days: int = 28,
    ) -> AnalyticsAggregate:
        channel = await self.channel_repo.get_owned(channel_id, owner_id=owner_id)
        if not channel:
            raise NotFoundError("Channel not found or access denied")

        date_to = date.today()
        date_from = date_to - timedelta(days=days - 1)

        agg = await self.repo.aggregate_for_user(
            owner_id, date_from=date_from, date_to=date_to
        )
        snapshots = await self.repo.get_channel_range(
            channel_id, date_from=date_from, date_to=date_to
        )

        return AnalyticsAggregate(
            channel_id=channel_id,
            date_from=date_from,
            date_to=date_to,
            total_views=agg["total_views"],
            total_watch_time_hours=agg["total_watch_time_hours"],
            total_revenue_usd=agg["total_revenue_usd"],
            subscribers_gained=agg["subscribers_gained"],
            subscribers_lost=agg["subscribers_lost"],
            net_subscribers=agg["subscribers_gained"] - agg["subscribers_lost"],
            avg_rpm=agg["avg_rpm"],
            avg_ctr=agg["avg_ctr"],
            daily_snapshots=[AnalyticsSnapshotRead.model_validate(s) for s in snapshots],
        )

    async def get_publication_snapshots(
        self,
        publication_id: uuid.UUID,
        *,
        date_from: date,
        date_to: date,
    ) -> list[AnalyticsSnapshotRead]:
        snapshots = await self.repo.get_publication_range(
            publication_id, date_from=date_from, date_to=date_to
        )
        return [AnalyticsSnapshotRead.model_validate(s) for s in snapshots]

    async def upsert_snapshot(
        self, payload: AnalyticsSnapshotCreate, *, owner_id: uuid.UUID
    ) -> AnalyticsSnapshotRead:
        channel = await self.channel_repo.get_owned(payload.channel_id, owner_id=owner_id)
        if not channel:
            raise NotFoundError("Channel not found or access denied")

        data = payload.model_dump(exclude={"channel_id", "snapshot_date", "snapshot_type"})
        snapshot = await self.repo.upsert_channel_snapshot(
            payload.channel_id, payload.snapshot_date, data
        )
        return AnalyticsSnapshotRead.model_validate(snapshot)
