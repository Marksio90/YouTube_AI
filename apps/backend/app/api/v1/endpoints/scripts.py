import uuid

from fastapi import APIRouter, Query, status

from app.api.v1.deps import CurrentUser, DB
from app.db.models.script import ScriptStatus
from app.schemas.common import PaginatedResponse, TaskResponse
from app.schemas.script import (
    ScriptAudioGenerateRequest,
    ScriptCreate,
    ScriptGenerateRequest,
    ScriptRead,
    ScriptUpdate,
)
from app.services.script import ScriptService

router = APIRouter(prefix="/scripts", tags=["scripts"])


@router.get("", response_model=PaginatedResponse[ScriptRead])
async def list_scripts(
    current_user: CurrentUser,
    db: DB,
    channel_id: uuid.UUID | None = None,
    brief_id: uuid.UUID | None = None,
    status: ScriptStatus | None = Query(default=None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> PaginatedResponse[ScriptRead]:
    svc = ScriptService(db)
    return await svc.list_for_user(
        current_user.id,
        channel_id=channel_id,
        brief_id=brief_id,
        status=status,
        page=page,
        page_size=page_size,
    )


@router.post("", response_model=ScriptRead, status_code=status.HTTP_201_CREATED)
async def create_script(
    payload: ScriptCreate, current_user: CurrentUser, db: DB
) -> ScriptRead:
    svc = ScriptService(db)
    script = await svc.create(payload, owner_id=current_user.id)
    return ScriptRead.model_validate(script)


@router.post("/generate", response_model=TaskResponse)
async def generate_script(
    payload: ScriptGenerateRequest, current_user: CurrentUser, db: DB
) -> TaskResponse:
    svc = ScriptService(db)
    return await svc.generate(payload, owner_id=current_user.id)


@router.post("/{script_id}/generate-audio", response_model=TaskResponse)
async def generate_script_audio(
    script_id: uuid.UUID,
    payload: ScriptAudioGenerateRequest,
    current_user: CurrentUser,
    db: DB,
) -> TaskResponse:
    svc = ScriptService(db)
    return await svc.generate_audio(script_id, payload, owner_id=current_user.id)


@router.get("/{script_id}", response_model=ScriptRead)
async def get_script(
    script_id: uuid.UUID, current_user: CurrentUser, db: DB
) -> ScriptRead:
    svc = ScriptService(db)
    script = await svc.get_for_user(script_id, owner_id=current_user.id)
    return ScriptRead.model_validate(script)


@router.patch("/{script_id}", response_model=ScriptRead)
async def update_script(
    script_id: uuid.UUID, payload: ScriptUpdate, current_user: CurrentUser, db: DB
) -> ScriptRead:
    svc = ScriptService(db)
    script = await svc.update(script_id, payload, owner_id=current_user.id)
    return ScriptRead.model_validate(script)


@router.delete("/{script_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_script(
    script_id: uuid.UUID, current_user: CurrentUser, db: DB
) -> None:
    svc = ScriptService(db)
    await svc.delete(script_id, owner_id=current_user.id)
