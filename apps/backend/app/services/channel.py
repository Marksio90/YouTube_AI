import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.repositories.channel import ChannelRepository
from app.schemas.channel import ChannelCreate, ChannelUpdate
from app.schemas.common import PaginatedResponse


class ChannelService:
    def __init__(self, db: AsyncSession) -> None:
        self.repo = ChannelRepository(db)

    async def list_for_user(
        self,
        owner_id: uuid.UUID,
        organization_id: uuid.UUID | None = None,
        *,
        page: int = 1,
        page_size: int = 20,
    ) -> PaginatedResponse:
        offset = (page - 1) * page_size
        rows, total = await self.repo.list_owned(
            owner_id,
            organization_id,
            offset=offset,
            limit=page_size,
        )
        return PaginatedResponse(
            items=rows,
            total=total,
            page=page,
            page_size=page_size,
            has_next=offset + page_size < total,
            has_prev=page > 1,
        )

    async def create(self, payload: ChannelCreate, *, owner_id: uuid.UUID, organization_id: uuid.UUID):
        from app.db.models.channel import Channel

        if organization_id is None:
            raise NotFoundError("Organization required")

        channel = Channel(
            organization_id=organization_id,
            owner_id=owner_id,
            name=payload.name,
            niche=payload.niche,
            handle=payload.handle,
        )
        return await self.repo.save(channel)

    async def get_owned(
        self,
        channel_id: uuid.UUID,
        *,
        owner_id: uuid.UUID,
        organization_id: uuid.UUID | None = None,
    ):
        channel = await self.repo.get_owned(
            channel_id,
            owner_id=owner_id,
            organization_id=organization_id,
        )
        if not channel:
            raise NotFoundError(f"Channel {channel_id} not found")
        return channel

    async def update(
        self,
        channel_id: uuid.UUID,
        payload: ChannelUpdate,
        *,
        owner_id: uuid.UUID,
        organization_id: uuid.UUID | None = None,
    ):
        channel = await self.get_owned(
            channel_id,
            owner_id=owner_id,
            organization_id=organization_id,
        )
        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(channel, field, value)
        return await self.repo.save(channel)

    async def delete(
        self,
        channel_id: uuid.UUID,
        *,
        owner_id: uuid.UUID,
        organization_id: uuid.UUID | None = None,
    ) -> None:
        channel = await self.get_owned(
            channel_id,
            owner_id=owner_id,
            organization_id=organization_id,
        )
        await self.repo.delete(channel)
