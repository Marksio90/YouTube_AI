from __future__ import annotations

import uuid

import structlog
from fastapi import APIRouter, Query, status

from app.api.v1.deps import CurrentUser, DB
from app.schemas.channel import ChannelCreate, ChannelRead, ChannelUpdate
from app.schemas.common import PaginatedResponse, TaskResponse
from app.services.channel import ChannelService
from app.tasks.youtube import enqueue_sync_metrics

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/channels", tags=["channels"])

DEFAULT_PAGE = 1
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100


@router.get(
    "",
    response_model=PaginatedResponse[ChannelRead],
    summary="List channels owned by the current user",
)
async def list_channels(
    current_user: CurrentUser,
    db: DB,
    page: int = Query(DEFAULT_PAGE, ge=1),
    page_size: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
) -> PaginatedResponse[ChannelRead]:
    service = ChannelService(db)

    return await service.list_for_user(
        current_user.id,
        current_user.organization_id,
        page=page,
        page_size=page_size,
    )


@router.post(
    "",
    response_model=ChannelRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a channel",
)
async def create_channel(
    payload: ChannelCreate,
    current_user: CurrentUser,
    db: DB,
) -> ChannelRead:
    service = ChannelService(db)

    try:
        channel = await service.create(
            payload,
            owner_id=current_user.id,
            organization_id=current_user.organization_id,
        )
        await db.commit()
        await db.refresh(channel)
    except Exception:
        await db.rollback()
        logger.exception(
            "channels.create_failed",
            owner_id=str(current_user.id),
            organization_id=str(current_user.organization_id),
            name=payload.name,
            handle=payload.handle,
        )
        raise

    logger.info(
        "channels.created",
        channel_id=str(channel.id),
        owner_id=str(current_user.id),
        organization_id=str(current_user.organization_id),
    )

    return ChannelRead.model_validate(channel)


@router.get(
    "/{channel_id}",
    response_model=ChannelRead,
    summary="Get a channel",
)
async def get_channel(
    channel_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
) -> ChannelRead:
    service = ChannelService(db)

    channel = await service.get_owned(
        channel_id,
        owner_id=current_user.id,
        organization_id=current_user.organization_id,
    )

    return ChannelRead.model_validate(channel)


@router.patch(
    "/{channel_id}",
    response_model=ChannelRead,
    summary="Update a channel",
)
async def update_channel(
    channel_id: uuid.UUID,
    payload: ChannelUpdate,
    current_user: CurrentUser,
    db: DB,
) -> ChannelRead:
    service = ChannelService(db)

    try:
        channel = await service.update(
            channel_id,
            payload,
            owner_id=current_user.id,
            organization_id=current_user.organization_id,
        )
        await db.commit()
        await db.refresh(channel)
    except Exception:
        await db.rollback()
        logger.exception(
            "channels.update_failed",
            channel_id=str(channel_id),
            owner_id=str(current_user.id),
            organization_id=str(current_user.organization_id),
        )
        raise

    logger.info(
        "channels.updated",
        channel_id=str(channel.id),
        owner_id=str(current_user.id),
        organization_id=str(current_user.organization_id),
    )

    return ChannelRead.model_validate(channel)


@router.delete(
    "/{channel_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a channel",
)
async def delete_channel(
    channel_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
) -> None:
    service = ChannelService(db)

    try:
        await service.delete(
            channel_id,
            owner_id=current_user.id,
            organization_id=current_user.organization_id,
        )
        await db.commit()
    except Exception:
        await db.rollback()
        logger.exception(
            "channels.delete_failed",
            channel_id=str(channel_id),
            owner_id=str(current_user.id),
            organization_id=str(current_user.organization_id),
        )
        raise

    logger.info(
        "channels.deleted",
        channel_id=str(channel_id),
        owner_id=str(current_user.id),
        organization_id=str(current_user.organization_id),
    )


@router.post(
    "/{channel_id}/sync-metrics",
    response_model=TaskResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Queue YouTube metric synchronization for a channel",
)
async def sync_metrics(
    channel_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
) -> TaskResponse:
    service = ChannelService(db)

    channel = await service.get_owned(
        channel_id,
        owner_id=current_user.id,
        organization_id=current_user.organization_id,
    )

    task_id = enqueue_sync_metrics(channel_id=str(channel.id))

    logger.info(
        "channels.sync_metrics_queued",
        channel_id=str(channel.id),
        owner_id=str(current_user.id),
        organization_id=str(current_user.organization_id),
        task_id=task_id,
    )

    return TaskResponse(task_id=task_id, status="pending")
