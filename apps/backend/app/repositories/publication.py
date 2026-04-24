import uuid

from sqlalchemy import func, select

from app.db.models.channel import Channel
from app.db.models.publication import Publication, PublicationStatus
from app.repositories.base import BaseRepository


class PublicationRepository(BaseRepository[Publication]):
    model = Publication

    async def list_for_user(
        self,
        owner_id: uuid.UUID,
        *,
        channel_id: uuid.UUID | None = None,
        status: PublicationStatus | None = None,
        offset: int = 0,
        limit: int = 20,
    ) -> tuple[list[Publication], int]:
        base_q = (
            select(Publication)
            .join(Channel, Publication.channel_id == Channel.id)
            .where(Channel.owner_id == owner_id)
        )
        if channel_id:
            base_q = base_q.where(Publication.channel_id == channel_id)
        if status:
            base_q = base_q.where(Publication.status == status)

        total = (
            await self.db.execute(select(func.count()).select_from(base_q.subquery()))
        ).scalar_one()

        rows = (
            await self.db.execute(
                base_q.order_by(Publication.created_at.desc()).offset(offset).limit(limit)
            )
        ).scalars().all()

        return list(rows), total

    async def get_for_user(
        self, publication_id: uuid.UUID, *, owner_id: uuid.UUID
    ) -> Publication | None:
        result = await self.db.execute(
            select(Publication)
            .join(Channel, Publication.channel_id == Channel.id)
            .where(
                Publication.id == publication_id,
                Channel.owner_id == owner_id,
            )
        )
        return result.scalar_one_or_none()

    async def count_by_status(self, owner_id: uuid.UUID) -> dict[str, int]:
        rows = (
            await self.db.execute(
                select(Publication.status, func.count(Publication.id))
                .join(Channel, Publication.channel_id == Channel.id)
                .where(Channel.owner_id == owner_id)
                .group_by(Publication.status)
            )
        ).all()
        return {str(r[0]): r[1] for r in rows}

    async def top_by_views(
        self, owner_id: uuid.UUID, *, limit: int = 5
    ) -> list[Publication]:
        rows = (
            await self.db.execute(
                select(Publication)
                .join(Channel, Publication.channel_id == Channel.id)
                .where(
                    Channel.owner_id == owner_id,
                    Publication.status == PublicationStatus.published,
                )
                .order_by(Publication.view_count.desc())
                .limit(limit)
            )
        ).scalars().all()
        return list(rows)
