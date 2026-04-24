import uuid

from sqlalchemy import select

from app.db.models.channel import Channel, ChannelStatus
from app.repositories.base import BaseRepository


class ChannelRepository(BaseRepository[Channel]):
    model = Channel

    async def list_owned(
        self,
        owner_id: uuid.UUID | str,
        *,
        status: ChannelStatus | None = None,
        offset: int = 0,
        limit: int = 20,
    ) -> tuple[list[Channel], int]:
        filters = [Channel.owner_id == owner_id]
        if status:
            filters.append(Channel.status == status)
        return await self.list(
            *filters,
            order_by=Channel.created_at.desc(),
            offset=offset,
            limit=limit,
        )

    async def get_owned(
        self, channel_id: uuid.UUID, *, owner_id: uuid.UUID
    ) -> Channel | None:
        result = await self.db.execute(
            select(Channel).where(
                Channel.id == channel_id,
                Channel.owner_id == owner_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_by_youtube_id(self, youtube_channel_id: str) -> Channel | None:
        result = await self.db.execute(
            select(Channel).where(Channel.youtube_channel_id == youtube_channel_id)
        )
        return result.scalar_one_or_none()
