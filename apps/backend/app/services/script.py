import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.channel import Channel
from app.db.models.script import Script
from app.schemas.common import PaginatedResponse
from app.schemas.script import ScriptCreate, ScriptUpdate


class ScriptService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_for_user(
        self,
        user_id: str,
        *,
        channel_id: uuid.UUID | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> PaginatedResponse:
        offset = (page - 1) * page_size
        base_q = (
            select(Script)
            .join(Channel, Script.channel_id == Channel.id)
            .where(Channel.owner_id == user_id)
        )
        if channel_id:
            base_q = base_q.where(Script.channel_id == channel_id)

        total = (await self.db.execute(select(func.count()).select_from(base_q.subquery()))).scalar_one()
        rows = (
            await self.db.execute(
                base_q.order_by(Script.created_at.desc()).offset(offset).limit(page_size)
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

    async def create(self, payload: ScriptCreate) -> Script:
        script = Script(**payload.model_dump())
        self.db.add(script)
        await self.db.flush()
        await self.db.refresh(script)
        return script

    async def get_by_id(self, script_id: uuid.UUID) -> Script | None:
        result = await self.db.execute(select(Script).where(Script.id == script_id))
        return result.scalar_one_or_none()

    async def update(self, script_id: uuid.UUID, payload: ScriptUpdate) -> Script | None:
        script = await self.get_by_id(script_id)
        if not script:
            return None
        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(script, field, value)
        await self.db.flush()
        await self.db.refresh(script)
        return script
