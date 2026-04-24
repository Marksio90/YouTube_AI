import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.db.models.brief import Brief
from app.repositories.brief import BriefRepository
from app.repositories.channel import ChannelRepository
from app.schemas.brief import BriefCreate, BriefUpdate
from app.schemas.common import PaginatedResponse, TaskResponse


class BriefService:
    def __init__(self, db: AsyncSession) -> None:
        self.repo = BriefRepository(db)
        self.channel_repo = ChannelRepository(db)

    async def list_for_user(
        self,
        owner_id: uuid.UUID,
        *,
        channel_id: uuid.UUID | None = None,
        topic_id: uuid.UUID | None = None,
        status: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> PaginatedResponse:
        from app.db.models.brief import BriefStatus
        offset = (page - 1) * page_size
        status_enum = BriefStatus(status) if status else None
        rows, total = await self.repo.list_for_user(
            owner_id,
            channel_id=channel_id,
            topic_id=topic_id,
            status=status_enum,
            offset=offset,
            limit=page_size,
        )
        return PaginatedResponse(
            items=rows, total=total, page=page, page_size=page_size,
            has_next=offset + page_size < total, has_prev=page > 1,
        )

    async def create(self, payload: BriefCreate, *, owner_id: uuid.UUID) -> Brief:
        channel = await self.channel_repo.get_owned(payload.channel_id, owner_id=owner_id)
        if not channel:
            raise NotFoundError("Channel not found or access denied")
        brief = Brief(**payload.model_dump())
        return await self.repo.save(brief)

    async def get_for_user(self, brief_id: uuid.UUID, *, owner_id: uuid.UUID) -> Brief:
        brief = await self.repo.get(brief_id)
        if not brief:
            raise NotFoundError(f"Brief {brief_id} not found")
        channel = await self.channel_repo.get_owned(brief.channel_id, owner_id=owner_id)
        if not channel:
            raise NotFoundError(f"Brief {brief_id} not found")
        return brief

    async def update(
        self, brief_id: uuid.UUID, payload: BriefUpdate, *, owner_id: uuid.UUID
    ) -> Brief:
        brief = await self.get_for_user(brief_id, owner_id=owner_id)
        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(brief, field, value)
        return await self.repo.save(brief)

    async def delete(self, brief_id: uuid.UUID, *, owner_id: uuid.UUID) -> None:
        brief = await self.get_for_user(brief_id, owner_id=owner_id)
        await self.repo.delete(brief)

    async def generate_from_topic(
        self, channel_id: uuid.UUID, topic_id: uuid.UUID, *, owner_id: uuid.UUID
    ) -> TaskResponse:
        from app.tasks.ai import enqueue_generate_brief
        channel = await self.channel_repo.get_owned(channel_id, owner_id=owner_id)
        if not channel:
            raise NotFoundError("Channel not found or access denied")
        task_id = enqueue_generate_brief(
            channel_id=str(channel_id), topic_id=str(topic_id)
        )
        return TaskResponse(task_id=task_id, status="pending")

    async def status_summary(self, owner_id: uuid.UUID) -> dict[str, int]:
        return await self.repo.count_by_status(owner_id)
