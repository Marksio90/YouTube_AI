import uuid

from fastapi import APIRouter, Query, status

from app.api.v1.deps import CurrentUser, DB
from app.schemas.channel import ChannelCreate, ChannelRead, ChannelUpdate
from app.schemas.common import PaginatedResponse, TaskResponse
from app.services.channel import ChannelService

router = APIRouter(prefix="/channels", tags=["channels"])


@router.get("", response_model=PaginatedResponse[ChannelRead])
async def list_channels(
    current_user: CurrentUser,
    db: DB,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> PaginatedResponse[ChannelRead]:
    svc = ChannelService(db)
    return await svc.list_for_user(current_user.id, current_user.organization_id, page=page, page_size=page_size)


@router.post("", response_model=ChannelRead, status_code=status.HTTP_201_CREATED)
async def create_channel(
    payload: ChannelCreate, current_user: CurrentUser, db: DB
) -> ChannelRead:
    svc = ChannelService(db)
    channel = await svc.create(payload, owner_id=current_user.id, organization_id=current_user.organization_id)
    return ChannelRead.model_validate(channel)


@router.get("/{channel_id}", response_model=ChannelRead)
async def get_channel(
    channel_id: uuid.UUID, current_user: CurrentUser, db: DB
) -> ChannelRead:
    svc = ChannelService(db)
    channel = await svc.get_owned(channel_id, owner_id=current_user.id, organization_id=current_user.organization_id)
    return ChannelRead.model_validate(channel)


@router.patch("/{channel_id}", response_model=ChannelRead)
async def update_channel(
    channel_id: uuid.UUID, payload: ChannelUpdate, current_user: CurrentUser, db: DB
) -> ChannelRead:
    svc = ChannelService(db)
    channel = await svc.update(channel_id, payload, owner_id=current_user.id, organization_id=current_user.organization_id)
    return ChannelRead.model_validate(channel)


@router.delete("/{channel_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_channel(
    channel_id: uuid.UUID, current_user: CurrentUser, db: DB
) -> None:
    svc = ChannelService(db)
    await svc.delete(channel_id, owner_id=current_user.id, organization_id=current_user.organization_id)


@router.post("/{channel_id}/sync-metrics", response_model=TaskResponse)
async def sync_metrics(
    channel_id: uuid.UUID, current_user: CurrentUser, db: DB
) -> TaskResponse:
    from app.tasks.youtube import enqueue_sync_metrics
    svc = ChannelService(db)
    channel = await svc.get_owned(channel_id, owner_id=current_user.id, organization_id=current_user.organization_id)
    task_id = enqueue_sync_metrics(channel_id=str(channel.id))
    return TaskResponse(task_id=task_id, status="pending")
