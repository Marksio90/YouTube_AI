import uuid

from fastapi import APIRouter, Query, status

from app.api.v1.deps import CurrentUser, DB
from app.schemas.common import MessageResponse, PaginatedResponse
from app.schemas.topic import TopicCreate, TopicRead, TopicStatusCount, TopicUpdate
from app.services.topic import TopicService

router = APIRouter(prefix="/topics", tags=["topics"])


@router.get("", response_model=PaginatedResponse[TopicRead])
async def list_topics(
    current_user: CurrentUser,
    db: DB,
    channel_id: uuid.UUID | None = None,
    status: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> PaginatedResponse[TopicRead]:
    svc = TopicService(db)
    return await svc.list_for_user(
        current_user.id,
        channel_id=channel_id,
        status=status,
        page=page,
        page_size=page_size,
    )


@router.post("", response_model=TopicRead, status_code=status.HTTP_201_CREATED)
async def create_topic(
    payload: TopicCreate, current_user: CurrentUser, db: DB
) -> TopicRead:
    svc = TopicService(db)
    topic = await svc.create(payload, owner_id=current_user.id)
    return TopicRead.model_validate(topic)


@router.get("/status-summary", response_model=TopicStatusCount)
async def topic_status_summary(
    current_user: CurrentUser, db: DB
) -> TopicStatusCount:
    svc = TopicService(db)
    counts = await svc.status_summary(current_user.id)
    return TopicStatusCount(**counts)


@router.get("/{topic_id}", response_model=TopicRead)
async def get_topic(
    topic_id: uuid.UUID, current_user: CurrentUser, db: DB
) -> TopicRead:
    svc = TopicService(db)
    topic = await svc.get_for_user(topic_id, owner_id=current_user.id)
    return TopicRead.model_validate(topic)


@router.patch("/{topic_id}", response_model=TopicRead)
async def update_topic(
    topic_id: uuid.UUID, payload: TopicUpdate, current_user: CurrentUser, db: DB
) -> TopicRead:
    svc = TopicService(db)
    topic = await svc.update(topic_id, payload, owner_id=current_user.id)
    return TopicRead.model_validate(topic)


@router.delete("/{topic_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_topic(
    topic_id: uuid.UUID, current_user: CurrentUser, db: DB
) -> None:
    svc = TopicService(db)
    await svc.delete(topic_id, owner_id=current_user.id)
