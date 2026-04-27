from __future__ import annotations

import uuid

import structlog
from fastapi import APIRouter, Query, status

from app.api.v1.deps import CurrentUser, DB
from app.db.models.brief import BriefStatus
from app.schemas.brief import BriefCreate, BriefGenerateRequest, BriefRead, BriefUpdate
from app.schemas.common import PaginatedResponse, TaskResponse
from app.services.brief import BriefService

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/briefs", tags=["briefs"])

DEFAULT_PAGE = 1
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100


@router.get(
    "",
    response_model=PaginatedResponse[BriefRead],
    summary="List briefs owned by the current user",
)
async def list_briefs(
    current_user: CurrentUser,
    db: DB,
    channel_id: uuid.UUID | None = Query(default=None),
    topic_id: uuid.UUID | None = Query(default=None),
    status_filter: BriefStatus | None = Query(default=None, alias="status"),
    page: int = Query(DEFAULT_PAGE, ge=1),
    page_size: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
) -> PaginatedResponse[BriefRead]:
    service = BriefService(db)

    return await service.list_for_user(
        current_user.id,
        channel_id=channel_id,
        topic_id=topic_id,
        status=status_filter,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/status-summary",
    response_model=dict[str, int],
    summary="Get brief count grouped by status",
)
async def brief_status_summary(
    current_user: CurrentUser,
    db: DB,
) -> dict[str, int]:
    service = BriefService(db)
    return await service.status_summary(current_user.id)


@router.post(
    "",
    response_model=BriefRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a brief manually",
)
async def create_brief(
    payload: BriefCreate,
    current_user: CurrentUser,
    db: DB,
) -> BriefRead:
    service = BriefService(db)

    try:
        brief = await service.create(payload, owner_id=current_user.id)
        await db.commit()
        await db.refresh(brief)
    except Exception:
        await db.rollback()
        logger.exception(
            "briefs.create_failed",
            owner_id=str(current_user.id),
            channel_id=str(payload.channel_id),
            topic_id=str(payload.topic_id) if payload.topic_id else None,
        )
        raise

    logger.info(
        "briefs.created",
        owner_id=str(current_user.id),
        brief_id=str(brief.id),
        channel_id=str(brief.channel_id),
        topic_id=str(brief.topic_id) if brief.topic_id else None,
    )

    return BriefRead.model_validate(brief)


@router.post(
    "/generate",
    response_model=TaskResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Queue AI brief generation from a topic",
)
async def generate_brief(
    payload: BriefGenerateRequest,
    current_user: CurrentUser,
    db: DB,
) -> TaskResponse:
    service = BriefService(db)

    task = await service.generate_from_topic(
        payload.channel_id,
        payload.topic_id,
        owner_id=current_user.id,
    )

    if payload.additional_instructions:
        logger.info(
            "briefs.generate_requested_with_additional_instructions",
            owner_id=str(current_user.id),
            channel_id=str(payload.channel_id),
            topic_id=str(payload.topic_id),
            additional_instructions_length=len(payload.additional_instructions),
            task_id=task.task_id,
        )
    else:
        logger.info(
            "briefs.generate_requested",
            owner_id=str(current_user.id),
            channel_id=str(payload.channel_id),
            topic_id=str(payload.topic_id),
            task_id=task.task_id,
        )

    return task


@router.get(
    "/{brief_id}",
    response_model=BriefRead,
    summary="Get a brief by id",
)
async def get_brief(
    brief_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
) -> BriefRead:
    service = BriefService(db)
    brief = await service.get_for_user(brief_id, owner_id=current_user.id)

    return BriefRead.model_validate(brief)


@router.patch(
    "/{brief_id}",
    response_model=BriefRead,
    summary="Update a brief",
)
async def update_brief(
    brief_id: uuid.UUID,
    payload: BriefUpdate,
    current_user: CurrentUser,
    db: DB,
) -> BriefRead:
    service = BriefService(db)

    try:
        brief = await service.update(brief_id, payload, owner_id=current_user.id)
        await db.commit()
        await db.refresh(brief)
    except Exception:
        await db.rollback()
        logger.exception(
            "briefs.update_failed",
            owner_id=str(current_user.id),
            brief_id=str(brief_id),
        )
        raise

    logger.info(
        "briefs.updated",
        owner_id=str(current_user.id),
        brief_id=str(brief.id),
        status=str(brief.status),
    )

    return BriefRead.model_validate(brief)


@router.delete(
    "/{brief_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a brief",
)
async def delete_brief(
    brief_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
) -> None:
    service = BriefService(db)

    try:
        await service.delete(brief_id, owner_id=current_user.id)
        await db.commit()
    except Exception:
        await db.rollback()
        logger.exception(
            "briefs.delete_failed",
            owner_id=str(current_user.id),
            brief_id=str(brief_id),
        )
        raise

    logger.info(
        "briefs.deleted",
        owner_id=str(current_user.id),
        brief_id=str(brief_id),
    )
