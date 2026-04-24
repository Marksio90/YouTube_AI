import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.channel import Channel
from app.schemas.channel import ChannelCreate, ChannelUpdate
from app.schemas.common import PaginatedResponse


class ChannelService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_for_user(
        self, owner_id: str, *, page: int = 1, page_size: int = 20
    ) -> PaginatedResponse:
        offset = (page - 1) * page_size
        base_q = select(Channel).where(Channel.owner_id == owner_id)

        total = (await self.db.execute(select(func.count()).select_from(base_q.subquery()))).scalar_one()
        rows = (await self.db.execute(base_q.offset(offset).limit(page_size))).scalars().all()

        return PaginatedResponse(
            items=rows,
            total=total,
            page=page,
            page_size=page_size,
            has_next=offset + page_size < total,
            has_prev=page > 1,
        )

    async def create(self, payload: ChannelCreate, *, owner_id: uuid.UUID) -> Channel:
        channel = Channel(
            owner_id=owner_id,
            name=payload.name,
            niche=payload.niche,
            handle=payload.handle,
        )
        self.db.add(channel)
        await self.db.flush()
        await self.db.refresh(channel)
        return channel

    async def get_owned(self, channel_id: uuid.UUID, *, owner_id: uuid.UUID) -> Channel | None:
        result = await self.db.execute(
            select(Channel).where(Channel.id == channel_id, Channel.owner_id == owner_id)
        )
        return result.scalar_one_or_none()

    async def update(
        self, channel_id: uuid.UUID, payload: ChannelUpdate, *, owner_id: uuid.UUID
    ) -> Channel | None:
        channel = await self.get_owned(channel_id, owner_id=owner_id)
        if not channel:
            return None
        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(channel, field, value)
        await self.db.flush()
        await self.db.refresh(channel)
        return channel

    async def delete(self, channel_id: uuid.UUID, *, owner_id: uuid.UUID) -> bool:
        channel = await self.get_owned(channel_id, owner_id=owner_id)
        if not channel:
            return False
        await self.db.delete(channel)
        return True
