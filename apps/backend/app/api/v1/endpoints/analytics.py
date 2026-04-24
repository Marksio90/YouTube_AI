import uuid
from datetime import date

from fastapi import APIRouter, Query

from app.api.v1.deps import CurrentUser, DB
from app.schemas.analytics import (
    AnalyticsAggregate,
    AnalyticsSnapshotCreate,
    AnalyticsSnapshotRead,
)
from app.schemas.common import TaskResponse
from app.services.analytics import AnalyticsService

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/channels/{channel_id}", response_model=AnalyticsAggregate)
async def channel_analytics(
    channel_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
    days: int = Query(28, ge=1, le=365),
) -> AnalyticsAggregate:
    svc = AnalyticsService(db)
    return await svc.get_channel_aggregate(
        channel_id, owner_id=current_user.id, days=days
    )


@router.get("/publications/{publication_id}", response_model=list[AnalyticsSnapshotRead])
async def publication_analytics(
    publication_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
    date_from: date = Query(...),
    date_to: date = Query(...),
) -> list[AnalyticsSnapshotRead]:
    svc = AnalyticsService(db)
    return await svc.get_publication_snapshots(
        publication_id, date_from=date_from, date_to=date_to
    )


@router.post("/snapshots", response_model=AnalyticsSnapshotRead)
async def upsert_snapshot(
    payload: AnalyticsSnapshotCreate,
    current_user: CurrentUser,
    db: DB,
) -> AnalyticsSnapshotRead:
    svc = AnalyticsService(db)
    return await svc.upsert_snapshot(payload, owner_id=current_user.id)


@router.post("/sync/channels/{channel_id}", response_model=TaskResponse)
async def sync_channel_analytics(
    channel_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
) -> TaskResponse:
    from app.tasks.analytics import enqueue_sync_analytics
    from app.repositories.channel import ChannelRepository
    from app.core.exceptions import NotFoundError
    import datetime

    repo = ChannelRepository(db)
    channel = await repo.get_owned(channel_id, owner_id=current_user.id)
    if not channel:
        raise NotFoundError("Channel not found or access denied")

    task_id = enqueue_sync_analytics(
        channel_id=str(channel_id),
        date_str=datetime.date.today().isoformat(),
    )
    return TaskResponse(task_id=task_id, status="pending")
