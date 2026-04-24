import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.pipeline import Pipeline, PipelineRun
from app.schemas.common import PaginatedResponse
from app.schemas.pipeline import PipelineCreate


class PipelineService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_for_user(
        self, owner_id: str, *, page: int = 1, page_size: int = 20
    ) -> PaginatedResponse:
        offset = (page - 1) * page_size
        base_q = select(Pipeline).where(Pipeline.owner_id == owner_id)
        total = (await self.db.execute(select(func.count()).select_from(base_q.subquery()))).scalar_one()
        rows = (await self.db.execute(base_q.offset(offset).limit(page_size))).scalars().all()
        return PaginatedResponse(
            items=rows, total=total, page=page, page_size=page_size,
            has_next=offset + page_size < total, has_prev=page > 1,
        )

    async def create(self, payload: PipelineCreate, *, owner_id: uuid.UUID) -> Pipeline:
        pipeline = Pipeline(
            owner_id=owner_id,
            name=payload.name,
            description=payload.description,
            channel_id=payload.channel_id,
            steps=[s.model_dump() for s in payload.steps],
            schedule_cron=payload.schedule_cron,
        )
        self.db.add(pipeline)
        await self.db.flush()
        await self.db.refresh(pipeline)
        return pipeline

    async def get_owned(self, pipeline_id: uuid.UUID, *, owner_id: uuid.UUID) -> Pipeline | None:
        result = await self.db.execute(
            select(Pipeline).where(Pipeline.id == pipeline_id, Pipeline.owner_id == owner_id)
        )
        return result.scalar_one_or_none()

    async def create_run(
        self, pipeline_id: uuid.UUID, *, triggered_by: str, input: dict
    ) -> PipelineRun:
        run = PipelineRun(
            pipeline_id=pipeline_id,
            triggered_by=triggered_by,
            input=input,
        )
        self.db.add(run)
        await self.db.flush()
        await self.db.refresh(run)
        return run

    async def list_runs(
        self, pipeline_id: uuid.UUID, *, page: int = 1, page_size: int = 20
    ) -> PaginatedResponse:
        offset = (page - 1) * page_size
        base_q = select(PipelineRun).where(PipelineRun.pipeline_id == pipeline_id)
        total = (await self.db.execute(select(func.count()).select_from(base_q.subquery()))).scalar_one()
        rows = (
            await self.db.execute(
                base_q.order_by(PipelineRun.created_at.desc()).offset(offset).limit(page_size)
            )
        ).scalars().all()
        return PaginatedResponse(
            items=rows, total=total, page=page, page_size=page_size,
            has_next=offset + page_size < total, has_prev=page > 1,
        )
