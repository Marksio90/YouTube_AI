import uuid

from fastapi import APIRouter, Query, status

from app.api.v1.deps import CurrentUser, DB
from app.schemas.brief import BriefCreate, BriefGenerateRequest, BriefRead, BriefUpdate
from app.schemas.common import PaginatedResponse, TaskResponse
from app.services.brief import BriefService

router = APIRouter(prefix="/briefs", tags=["briefs"])


@router.get("", response_model=PaginatedResponse[BriefRead])
async def list_briefs(
    current_user: CurrentUser,
    db: DB,
    channel_id: uuid.UUID | None = None,
    topic_id: uuid.UUID | None = None,
    status: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> PaginatedResponse[BriefRead]:
    svc = BriefService(db)
    return await svc.list_for_user(
        current_user.id,
        channel_id=channel_id,
        topic_id=topic_id,
        status=status,
        page=page,
        page_size=page_size,
    )


@router.post("", response_model=BriefRead, status_code=status.HTTP_201_CREATED)
async def create_brief(
    payload: BriefCreate, current_user: CurrentUser, db: DB
) -> BriefRead:
    svc = BriefService(db)
    brief = await svc.create(payload, owner_id=current_user.id)
    return BriefRead.model_validate(brief)


@router.post("/generate", response_model=TaskResponse)
async def generate_brief(
    payload: BriefGenerateRequest, current_user: CurrentUser, db: DB
) -> TaskResponse:
    svc = BriefService(db)
    return await svc.generate_from_topic(
        payload.channel_id, payload.topic_id, owner_id=current_user.id
    )


@router.get("/{brief_id}", response_model=BriefRead)
async def get_brief(
    brief_id: uuid.UUID, current_user: CurrentUser, db: DB
) -> BriefRead:
    svc = BriefService(db)
    brief = await svc.get_for_user(brief_id, owner_id=current_user.id)
    return BriefRead.model_validate(brief)


@router.patch("/{brief_id}", response_model=BriefRead)
async def update_brief(
    brief_id: uuid.UUID, payload: BriefUpdate, current_user: CurrentUser, db: DB
) -> BriefRead:
    svc = BriefService(db)
    brief = await svc.update(brief_id, payload, owner_id=current_user.id)
    return BriefRead.model_validate(brief)


@router.delete("/{brief_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_brief(
    brief_id: uuid.UUID, current_user: CurrentUser, db: DB
) -> None:
    svc = BriefService(db)
    await svc.delete(brief_id, owner_id=current_user.id)
