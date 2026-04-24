import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.db.models.script import Script
from app.repositories.channel import ChannelRepository
from app.repositories.script import ScriptRepository
from app.schemas.common import PaginatedResponse, TaskResponse
from app.schemas.script import ScriptCreate, ScriptGenerateRequest, ScriptUpdate


class ScriptService:
    def __init__(self, db: AsyncSession) -> None:
        self.repo = ScriptRepository(db)
        self.channel_repo = ChannelRepository(db)

    async def list_for_user(
        self,
        owner_id: uuid.UUID,
        *,
        channel_id: uuid.UUID | None = None,
        brief_id: uuid.UUID | None = None,
        status: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> PaginatedResponse:
        from app.db.models.script import ScriptStatus
        offset = (page - 1) * page_size
        status_enum = ScriptStatus(status) if status else None
        rows, total = await self.repo.list_for_user(
            owner_id,
            channel_id=channel_id,
            brief_id=brief_id,
            status=status_enum,
            offset=offset,
            limit=page_size,
        )
        return PaginatedResponse(
            items=rows, total=total, page=page, page_size=page_size,
            has_next=offset + page_size < total, has_prev=page > 1,
        )

    async def create(self, payload: ScriptCreate, *, owner_id: uuid.UUID) -> Script:
        channel = await self.channel_repo.get_owned(payload.channel_id, owner_id=owner_id)
        if not channel:
            raise NotFoundError("Channel not found or access denied")
        script = Script(**payload.model_dump())
        return await self.repo.save(script)

    async def get_for_user(self, script_id: uuid.UUID, *, owner_id: uuid.UUID) -> Script:
        script = await self.repo.get(script_id)
        if not script:
            raise NotFoundError(f"Script {script_id} not found")
        channel = await self.channel_repo.get_owned(script.channel_id, owner_id=owner_id)
        if not channel:
            raise NotFoundError(f"Script {script_id} not found")
        return script

    async def update(
        self, script_id: uuid.UUID, payload: ScriptUpdate, *, owner_id: uuid.UUID
    ) -> Script:
        script = await self.get_for_user(script_id, owner_id=owner_id)
        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(script, field, value)
        return await self.repo.save(script)

    async def delete(self, script_id: uuid.UUID, *, owner_id: uuid.UUID) -> None:
        script = await self.get_for_user(script_id, owner_id=owner_id)
        await self.repo.delete(script)

    async def generate(
        self, payload: ScriptGenerateRequest, *, owner_id: uuid.UUID
    ) -> TaskResponse:
        from app.tasks.ai import enqueue_generate_script
        channel = await self.channel_repo.get_owned(payload.channel_id, owner_id=owner_id)
        if not channel:
            raise NotFoundError("Channel not found or access denied")
        task_id = enqueue_generate_script(
            channel_id=str(payload.channel_id),
            topic=payload.topic,
            tone=payload.tone,
            target_duration_seconds=payload.target_duration_seconds,
            keywords=payload.keywords,
            additional_context=payload.additional_context,
        )
        return TaskResponse(task_id=task_id, status="pending")

    async def status_summary(self, owner_id: uuid.UUID) -> dict[str, int]:
        return await self.repo.count_by_status(owner_id)
