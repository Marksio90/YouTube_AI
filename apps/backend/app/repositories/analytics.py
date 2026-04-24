import uuid
from datetime import date

from sqlalchemy import func, select

from app.db.models.analytics import AnalyticsSnapshot, SnapshotType
from app.db.models.channel import Channel
from app.repositories.base import BaseRepository


class AnalyticsRepository(BaseRepository[AnalyticsSnapshot]):
    model = AnalyticsSnapshot

    async def get_channel_range(
        self,
        channel_id: uuid.UUID,
        *,
        date_from: date,
        date_to: date,
    ) -> list[AnalyticsSnapshot]:
        rows = (
            await self.db.execute(
                select(AnalyticsSnapshot)
                .where(
                    AnalyticsSnapshot.channel_id == channel_id,
                    AnalyticsSnapshot.snapshot_type == SnapshotType.channel,
                    AnalyticsSnapshot.snapshot_date >= date_from,
                    AnalyticsSnapshot.snapshot_date <= date_to,
                )
                .order_by(AnalyticsSnapshot.snapshot_date.asc())
            )
        ).scalars().all()
        return list(rows)

    async def get_publication_range(
        self,
        publication_id: uuid.UUID,
        *,
        date_from: date,
        date_to: date,
    ) -> list[AnalyticsSnapshot]:
        rows = (
            await self.db.execute(
                select(AnalyticsSnapshot)
                .where(
                    AnalyticsSnapshot.publication_id == publication_id,
                    AnalyticsSnapshot.snapshot_type == SnapshotType.publication,
                    AnalyticsSnapshot.snapshot_date >= date_from,
                    AnalyticsSnapshot.snapshot_date <= date_to,
                )
                .order_by(AnalyticsSnapshot.snapshot_date.asc())
            )
        ).scalars().all()
        return list(rows)

    async def aggregate_for_user(
        self,
        owner_id: uuid.UUID,
        *,
        date_from: date,
        date_to: date,
    ) -> dict:
        row = (
            await self.db.execute(
                select(
                    func.sum(AnalyticsSnapshot.views).label("total_views"),
                    func.sum(AnalyticsSnapshot.watch_time_hours).label("total_watch_time_hours"),
                    func.sum(AnalyticsSnapshot.revenue_usd).label("total_revenue_usd"),
                    func.sum(AnalyticsSnapshot.subscribers_gained).label("subscribers_gained"),
                    func.sum(AnalyticsSnapshot.subscribers_lost).label("subscribers_lost"),
                    func.avg(AnalyticsSnapshot.rpm).label("avg_rpm"),
                    func.avg(AnalyticsSnapshot.ctr).label("avg_ctr"),
                )
                .join(Channel, AnalyticsSnapshot.channel_id == Channel.id)
                .where(
                    Channel.owner_id == owner_id,
                    AnalyticsSnapshot.snapshot_type == SnapshotType.channel,
                    AnalyticsSnapshot.snapshot_date >= date_from,
                    AnalyticsSnapshot.snapshot_date <= date_to,
                )
            )
        ).mappings().one()

        return {
            "total_views": int(row["total_views"] or 0),
            "total_watch_time_hours": float(row["total_watch_time_hours"] or 0),
            "total_revenue_usd": float(row["total_revenue_usd"] or 0),
            "subscribers_gained": int(row["subscribers_gained"] or 0),
            "subscribers_lost": int(row["subscribers_lost"] or 0),
            "avg_rpm": float(row["avg_rpm"] or 0),
            "avg_ctr": float(row["avg_ctr"] or 0),
        }

    async def upsert_channel_snapshot(
        self, channel_id: uuid.UUID, snapshot_date: date, data: dict
    ) -> AnalyticsSnapshot:
        existing = (
            await self.db.execute(
                select(AnalyticsSnapshot).where(
                    AnalyticsSnapshot.channel_id == channel_id,
                    AnalyticsSnapshot.snapshot_date == snapshot_date,
                    AnalyticsSnapshot.snapshot_type == SnapshotType.channel,
                    AnalyticsSnapshot.publication_id.is_(None),
                )
            )
        ).scalar_one_or_none()

        if existing:
            for k, v in data.items():
                setattr(existing, k, v)
            return await self.save(existing)

        snapshot = AnalyticsSnapshot(
            channel_id=channel_id,
            snapshot_date=snapshot_date,
            snapshot_type=SnapshotType.channel,
            **data,
        )
        return await self.save(snapshot)
