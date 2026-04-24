import uuid

from sqlalchemy import func, select

from app.db.models.channel import Channel
from app.db.models.script import Script, ScriptStatus
from app.repositories.base import BaseRepository


class ScriptRepository(BaseRepository[Script]):
    model = Script

    async def list_for_user(
        self,
        owner_id: uuid.UUID,
        *,
        channel_id: uuid.UUID | None = None,
        brief_id: uuid.UUID | None = None,
        status: ScriptStatus | None = None,
        offset: int = 0,
        limit: int = 20,
    ) -> tuple[list[Script], int]:
        base_q = (
            select(Script)
            .join(Channel, Script.channel_id == Channel.id)
            .where(Channel.owner_id == owner_id)
        )
        if channel_id:
            base_q = base_q.where(Script.channel_id == channel_id)
        if brief_id:
            base_q = base_q.where(Script.brief_id == brief_id)
        if status:
            base_q = base_q.where(Script.status == status)

        total = (
            await self.db.execute(select(func.count()).select_from(base_q.subquery()))
        ).scalar_one()

        rows = (
            await self.db.execute(
                base_q.order_by(Script.created_at.desc()).offset(offset).limit(limit)
            )
        ).scalars().all()

        return list(rows), total

    async def count_by_status(self, owner_id: uuid.UUID) -> dict[str, int]:
        rows = (
            await self.db.execute(
                select(Script.status, func.count(Script.id))
                .join(Channel, Script.channel_id == Channel.id)
                .where(Channel.owner_id == owner_id)
                .group_by(Script.status)
            )
        ).all()
        return {str(r[0]): r[1] for r in rows}
