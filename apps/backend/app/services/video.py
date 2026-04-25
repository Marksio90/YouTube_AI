import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.channel import Channel
from app.db.models.video import Video
from app.schemas.common import PaginatedResponse
from app.schemas.common import TaskResponse
from app.schemas.video import VideoCreate, VideoRenderRequest, VideoUpdate


class VideoService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_for_user(
        self,
        user_id: str,
        *,
        channel_id: uuid.UUID | None = None,
        status_filter: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> PaginatedResponse:
        offset = (page - 1) * page_size
        base_q = (
            select(Video)
            .join(Channel, Video.channel_id == Channel.id)
            .where(Channel.owner_id == user_id)
        )
        if channel_id:
            base_q = base_q.where(Video.channel_id == channel_id)
        if status_filter:
            base_q = base_q.where(Video.status == status_filter)

        total = (await self.db.execute(select(func.count()).select_from(base_q.subquery()))).scalar_one()
        rows = (
            await self.db.execute(
                base_q.order_by(Video.created_at.desc()).offset(offset).limit(page_size)
            )
        ).scalars().all()

        return PaginatedResponse(
            items=rows,
            total=total,
            page=page,
            page_size=page_size,
            has_next=offset + page_size < total,
            has_prev=page > 1,
        )

    async def create(self, payload: VideoCreate, *, user_id: uuid.UUID) -> Video:
        video = Video(
            channel_id=payload.channel_id,
            title=payload.title,
            description=payload.description,
            visibility=payload.visibility,
            scheduled_at=payload.scheduled_at,
        )
        self.db.add(video)
        await self.db.flush()
        await self.db.refresh(video)
        return video

    async def get_owned(self, video_id: uuid.UUID, *, user_id: uuid.UUID) -> Video | None:
        result = await self.db.execute(
            select(Video)
            .join(Channel, Video.channel_id == Channel.id)
            .where(Video.id == video_id, Channel.owner_id == user_id)
        )
        return result.scalar_one_or_none()

    async def update(
        self, video_id: uuid.UUID, payload: VideoUpdate, *, user_id: uuid.UUID
    ) -> Video | None:
        video = await self.get_owned(video_id, user_id=user_id)
        if not video:
            return None
        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(video, field, value)
        await self.db.flush()
        await self.db.refresh(video)
        return video

    async def enqueue_render(
        self,
        video_id: uuid.UUID,
        payload: VideoRenderRequest,
        *,
        user_id: uuid.UUID,
    ) -> TaskResponse:
        from app.tasks.media import enqueue_render_video

        video = await self.get_owned(video_id, user_id=user_id)
        if not video:
            raise ValueError("Video not found")

        task_id = enqueue_render_video(
            video_id=str(video_id),
            audio_url=payload.audio_url,
            scene_plan=[s.model_dump() for s in payload.scene_plan],
            assets=[a.model_dump() for a in payload.assets],
            engine=payload.engine,
        )
        return TaskResponse(task_id=task_id, status="pending")
