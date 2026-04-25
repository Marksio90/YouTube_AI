import uuid

from fastapi import APIRouter, Query, status

from app.api.v1.deps import CurrentUser, DB
from app.schemas.common import PaginatedResponse, TaskResponse
from app.schemas.publication import PublicationCreate, PublicationRead, PublicationUpdate, PublishPipelineRequest
from app.services.publication import PublicationService

router = APIRouter(prefix="/publications", tags=["publications"])


@router.get("", response_model=PaginatedResponse[PublicationRead])
async def list_publications(
    current_user: CurrentUser,
    db: DB,
    channel_id: uuid.UUID | None = None,
    status: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> PaginatedResponse[PublicationRead]:
    svc = PublicationService(db)
    return await svc.list_for_user(
        current_user.id,
        channel_id=channel_id,
        status=status,
        page=page,
        page_size=page_size,
    )


@router.post("", response_model=PublicationRead, status_code=status.HTTP_201_CREATED)
async def create_publication(
    payload: PublicationCreate, current_user: CurrentUser, db: DB
) -> PublicationRead:
    svc = PublicationService(db)
    pub = await svc.create(payload, owner_id=current_user.id)
    return PublicationRead.model_validate(pub)


@router.get("/{publication_id}", response_model=PublicationRead)
async def get_publication(
    publication_id: uuid.UUID, current_user: CurrentUser, db: DB
) -> PublicationRead:
    svc = PublicationService(db)
    pub = await svc.get_for_user(publication_id, owner_id=current_user.id)
    return PublicationRead.model_validate(pub)


@router.patch("/{publication_id}", response_model=PublicationRead)
async def update_publication(
    publication_id: uuid.UUID,
    payload: PublicationUpdate,
    current_user: CurrentUser,
    db: DB,
) -> PublicationRead:
    svc = PublicationService(db)
    pub = await svc.update(publication_id, payload, owner_id=current_user.id)
    return PublicationRead.model_validate(pub)


@router.delete("/{publication_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_publication(
    publication_id: uuid.UUID, current_user: CurrentUser, db: DB
) -> None:
    svc = PublicationService(db)
    await svc.delete(publication_id, owner_id=current_user.id)


@router.post("/{publication_id}/publish", response_model=TaskResponse)
async def publish(
    publication_id: uuid.UUID, current_user: CurrentUser, db: DB
) -> TaskResponse:
    svc = PublicationService(db)
    return await svc.enqueue_publish(publication_id, owner_id=current_user.id)


@router.post("/{publication_id}/publish-pipeline", response_model=TaskResponse)
async def publish_pipeline(
    publication_id: uuid.UUID,
    payload: PublishPipelineRequest,
    current_user: CurrentUser,
    db: DB,
) -> TaskResponse:
    svc = PublicationService(db)
    return await svc.enqueue_publish_pipeline(publication_id, payload, owner_id=current_user.id)
