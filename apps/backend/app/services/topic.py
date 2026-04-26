import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.db.models.topic import Topic, TopicStatus
from app.repositories.channel import ChannelRepository
from app.repositories.topic import TopicRepository
from app.schemas.common import PaginatedResponse
from app.schemas.topic import TopicCreate, TopicUpdate


class TopicService:
    def __init__(self, db: AsyncSession) -> None:
        self.repo = TopicRepository(db)
        self.channel_repo = ChannelRepository(db)

    async def list_for_user(
        self,
        owner_id: uuid.UUID,
        *,
        channel_id: uuid.UUID | None = None,
        status: TopicStatus | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> PaginatedResponse:
        offset = (page - 1) * page_size
        rows, total = await self.repo.list_for_user(
            owner_id, channel_id=channel_id, status=status,
            offset=offset, limit=page_size,
        )
        return PaginatedResponse(
            items=rows, total=total, page=page, page_size=page_size,
            has_next=offset + page_size < total, has_prev=page > 1,
        )

    async def create(self, payload: TopicCreate, *, owner_id: uuid.UUID) -> Topic:
        channel = await self.channel_repo.get_owned(payload.channel_id, owner_id=owner_id)
        if not channel:
            raise NotFoundError("Channel not found or access denied")
        topic = Topic(
            channel_id=payload.channel_id,
            title=payload.title,
            description=payload.description,
            keywords=payload.keywords,
            source=payload.source,
        )
        return await self.repo.save(topic)

    async def get_for_user(self, topic_id: uuid.UUID, *, owner_id: uuid.UUID) -> Topic:
        topic = await self.repo.get(topic_id)
        if not topic:
            raise NotFoundError(f"Topic {topic_id} not found")
        channel = await self.channel_repo.get_owned(topic.channel_id, owner_id=owner_id)
        if not channel:
            raise NotFoundError(f"Topic {topic_id} not found")
        return topic

    async def update(
        self, topic_id: uuid.UUID, payload: TopicUpdate, *, owner_id: uuid.UUID
    ) -> Topic:
        topic = await self.get_for_user(topic_id, owner_id=owner_id)
        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(topic, field, value)
        return await self.repo.save(topic)

    async def delete(self, topic_id: uuid.UUID, *, owner_id: uuid.UUID) -> None:
        topic = await self.get_for_user(topic_id, owner_id=owner_id)
        await self.repo.delete(topic)

    async def status_summary(self, owner_id: uuid.UUID) -> dict[str, int]:
        return await self.repo.count_by_status(owner_id)
