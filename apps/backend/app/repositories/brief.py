import uuid

from sqlalchemy import func, select

from app.db.models.brief import Brief, BriefStatus
from app.db.models.channel import Channel
from app.repositories.base import BaseRepository


class BriefRepository(BaseRepository[Brief]):
    model = Brief

    async def list_for_user(
        self,
        owner_id: uuid.UUID,
        *,
        channel_id: uuid.UUID | None = None,
        topic_id: uuid.UUID | None = None,
        status: BriefStatus | None = None,
        offset: int = 0,
        limit: int = 20,
    ) -> tuple[list[Brief], int]:
        base_q = (
            select(Brief)
            .join(Channel, Brief.channel_id == Channel.id)
            .where(Channel.owner_id == owner_id)
        )
        if channel_id:
            base_q = base_q.where(Brief.channel_id == channel_id)
        if topic_id:
            base_q = base_q.where(Brief.topic_id == topic_id)
        if status:
            base_q = base_q.where(Brief.status == status)

        total = (
            await self.db.execute(select(func.count()).select_from(base_q.subquery()))
        ).scalar_one()

        rows = (
            await self.db.execute(
                base_q.order_by(Brief.created_at.desc()).offset(offset).limit(limit)
            )
        ).scalars().all()

        return list(rows), total

    async def count_by_status(self, owner_id: uuid.UUID) -> dict[str, int]:
        rows = (
            await self.db.execute(
                select(Brief.status, func.count(Brief.id))
                .join(Channel, Brief.channel_id == Channel.id)
                .where(Channel.owner_id == owner_id)
                .group_by(Brief.status)
            )
        ).all()
        return {str(r[0]): r[1] for r in rows}
