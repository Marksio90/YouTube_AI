import uuid

from sqlalchemy import select

from app.db.models.channel import Channel
from app.db.models.topic import Topic, TopicStatus
from app.repositories.base import BaseRepository


class TopicRepository(BaseRepository[Topic]):
    model = Topic

    async def list_for_channel(
        self,
        channel_id: uuid.UUID,
        *,
        status: TopicStatus | None = None,
        offset: int = 0,
        limit: int = 20,
    ) -> tuple[list[Topic], int]:
        filters = [Topic.channel_id == channel_id]
        if status:
            filters.append(Topic.status == status)
        return await self.list(
            *filters,
            order_by=Topic.created_at.desc(),
            offset=offset,
            limit=limit,
        )

    async def list_for_user(
        self,
        owner_id: uuid.UUID,
        *,
        channel_id: uuid.UUID | None = None,
        status: TopicStatus | None = None,
        offset: int = 0,
        limit: int = 20,
    ) -> tuple[list[Topic], int]:
        base_q = select(Topic).join(Channel, Topic.channel_id == Channel.id).where(
            Channel.owner_id == owner_id
        )
        if channel_id:
            base_q = base_q.where(Topic.channel_id == channel_id)
        if status:
            base_q = base_q.where(Topic.status == status)

        from sqlalchemy import func
        total = (
            await self.db.execute(
                select(func.count()).select_from(base_q.subquery())
            )
        ).scalar_one()

        rows = (
            await self.db.execute(
                base_q.order_by(Topic.created_at.desc()).offset(offset).limit(limit)
            )
        ).scalars().all()

        return list(rows), total

    async def count_by_status(self, owner_id: uuid.UUID) -> dict[str, int]:
        from sqlalchemy import func
        rows = (
            await self.db.execute(
                select(Topic.status, func.count(Topic.id))
                .join(Channel, Topic.channel_id == Channel.id)
                .where(Channel.owner_id == owner_id)
                .group_by(Topic.status)
            )
        ).all()
        return {str(r[0]): r[1] for r in rows}
