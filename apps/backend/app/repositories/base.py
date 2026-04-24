from typing import Any, Generic, TypeVar
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.db.base import Base

ModelT = TypeVar("ModelT", bound=Base)


class BaseRepository(Generic[ModelT]):
    """
    Generic async repository. Subclasses must set `model` as a class variable.

    Provides: get, get_or_raise, list (with count), save, delete.
    Domain-specific filters are added in concrete subclasses.
    """

    model: type[ModelT]

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get(self, id: UUID | str) -> ModelT | None:
        result = await self.db.execute(select(self.model).where(self.model.id == id))
        return result.scalar_one_or_none()

    async def get_or_raise(self, id: UUID | str) -> ModelT:
        obj = await self.get(id)
        if obj is None:
            raise NotFoundError(f"{self.model.__tablename__} {id} not found")
        return obj

    async def list(
        self,
        *where: Any,
        order_by: Any = None,
        offset: int = 0,
        limit: int = 20,
    ) -> tuple[list[ModelT], int]:
        base_q = select(self.model)
        if where:
            base_q = base_q.where(*where)

        total = (
            await self.db.execute(select(func.count()).select_from(base_q.subquery()))
        ).scalar_one()

        q = base_q.offset(offset).limit(limit)
        if order_by is not None:
            q = q.order_by(order_by)

        rows = (await self.db.execute(q)).scalars().all()
        return list(rows), total

    async def save(self, obj: ModelT) -> ModelT:
        self.db.add(obj)
        await self.db.flush()
        await self.db.refresh(obj)
        return obj

    async def delete(self, obj: ModelT) -> None:
        await self.db.delete(obj)
        await self.db.flush()

    async def count(self, *where: Any) -> int:
        q = select(func.count()).select_from(self.model)
        if where:
            q = q.where(*where)
        return (await self.db.execute(q)).scalar_one()
