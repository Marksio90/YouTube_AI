import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.db.models.publication import Publication, PublicationStatus
from app.repositories.channel import ChannelRepository
from app.repositories.publication import PublicationRepository
from app.schemas.common import PaginatedResponse, TaskResponse
from app.schemas.publication import PublicationCreate, PublicationUpdate, PublishPipelineRequest


class PublicationService:
    def __init__(self, db: AsyncSession) -> None:
        self.repo = PublicationRepository(db)
        self.channel_repo = ChannelRepository(db)

    async def list_for_user(
        self,
        owner_id: uuid.UUID,
        *,
        channel_id: uuid.UUID | None = None,
        status: PublicationStatus | None = None,
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

    async def create(self, payload: PublicationCreate, *, owner_id: uuid.UUID) -> Publication:
        channel = await self.channel_repo.get_owned(payload.channel_id, owner_id=owner_id)
        if not channel:
            raise NotFoundError("Channel not found or access denied")
        pub = Publication(**payload.model_dump())
        return await self.repo.save(pub)

    async def get_for_user(
        self, publication_id: uuid.UUID, *, owner_id: uuid.UUID
    ) -> Publication:
        pub = await self.repo.get_for_user(publication_id, owner_id=owner_id)
        if not pub:
            raise NotFoundError(f"Publication {publication_id} not found")
        return pub

    async def update(
        self,
        publication_id: uuid.UUID,
        payload: PublicationUpdate,
        *,
        owner_id: uuid.UUID,
    ) -> Publication:
        pub = await self.get_for_user(publication_id, owner_id=owner_id)
        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(pub, field, value)
        return await self.repo.save(pub)

    async def delete(self, publication_id: uuid.UUID, *, owner_id: uuid.UUID) -> None:
        pub = await self.get_for_user(publication_id, owner_id=owner_id)
        await self.repo.delete(pub)

    async def enqueue_publish(
        self, publication_id: uuid.UUID, *, owner_id: uuid.UUID
    ) -> TaskResponse:
        from app.tasks.youtube import enqueue_upload
        pub = await self.get_for_user(publication_id, owner_id=owner_id)
        task_id = enqueue_upload(publication_id=str(pub.id))
        return TaskResponse(task_id=task_id, status="pending")


    async def enqueue_publish_pipeline(
        self,
        publication_id: uuid.UUID,
        payload: PublishPipelineRequest,
        *,
        owner_id: uuid.UUID,
    ) -> TaskResponse:
        from app.tasks.youtube import enqueue_publish_pipeline

        pub = await self.get_for_user(publication_id, owner_id=owner_id)
        task_id = enqueue_publish_pipeline(
            publication_id=str(pub.id),
            media_url=payload.media_url,
            audio_url=payload.audio_url,
            thumbnail_url=payload.thumbnail_url or pub.thumbnail_url,
            title=payload.title or pub.title,
            description=payload.description if payload.description is not None else pub.description,
            tags=payload.tags or pub.tags,
            visibility=payload.visibility or str(pub.visibility),
        )
        return TaskResponse(task_id=task_id, status="pending")

    async def status_summary(self, owner_id: uuid.UUID) -> dict[str, int]:
        return await self.repo.count_by_status(owner_id)

    async def top_by_views(self, owner_id: uuid.UUID, *, limit: int = 5) -> list[Publication]:
        return await self.repo.top_by_views(owner_id, limit=limit)
