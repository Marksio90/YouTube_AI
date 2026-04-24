import uuid

from fastapi import APIRouter, HTTPException, Query, status

from app.api.v1.deps import CurrentUser, DB
from app.schemas.common import PaginatedResponse, TaskResponse
from app.schemas.video import VideoCreate, VideoRead, VideoUpdate
from app.services.video import VideoService

router = APIRouter(prefix="/videos", tags=["videos"])


@router.get("", response_model=PaginatedResponse[VideoRead])
async def list_videos(
    current_user: CurrentUser,
    db: DB,
    channel_id: uuid.UUID | None = None,
    status: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> PaginatedResponse[VideoRead]:
    svc = VideoService(db)
    return await svc.list_for_user(
        str(current_user.id),
        channel_id=channel_id,
        status_filter=status,
        page=page,
        page_size=page_size,
    )


@router.post("", response_model=VideoRead, status_code=201)
async def create_video(payload: VideoCreate, current_user: CurrentUser, db: DB) -> VideoRead:
    svc = VideoService(db)
    video = await svc.create(payload, user_id=current_user.id)
    return VideoRead.model_validate(video)


@router.get("/{video_id}", response_model=VideoRead)
async def get_video(video_id: uuid.UUID, current_user: CurrentUser, db: DB) -> VideoRead:
    svc = VideoService(db)
    video = await svc.get_owned(video_id, user_id=current_user.id)
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    return VideoRead.model_validate(video)


@router.patch("/{video_id}", response_model=VideoRead)
async def update_video(
    video_id: uuid.UUID, payload: VideoUpdate, current_user: CurrentUser, db: DB
) -> VideoRead:
    svc = VideoService(db)
    video = await svc.update(video_id, payload, user_id=current_user.id)
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    return VideoRead.model_validate(video)


@router.post("/{video_id}/publish", response_model=TaskResponse)
async def publish_video(video_id: uuid.UUID, current_user: CurrentUser, db: DB) -> TaskResponse:
    from app.tasks.youtube import upload_video_task

    svc = VideoService(db)
    video = await svc.get_owned(video_id, user_id=current_user.id)
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")

    task = upload_video_task.delay(str(video_id))
    return TaskResponse(task_id=task.id, status="pending")
