import uuid

from fastapi import APIRouter, HTTPException, Query, status

from app.api.v1.deps import CurrentUser, DB
from app.schemas.common import PaginatedResponse, TaskResponse
from app.schemas.script import ScriptCreate, ScriptGenerateRequest, ScriptRead, ScriptUpdate
from app.services.script import ScriptService

router = APIRouter(prefix="/scripts", tags=["scripts"])


@router.get("", response_model=PaginatedResponse[ScriptRead])
async def list_scripts(
    current_user: CurrentUser,
    db: DB,
    channel_id: uuid.UUID | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> PaginatedResponse[ScriptRead]:
    svc = ScriptService(db)
    return await svc.list_for_user(
        str(current_user.id), channel_id=channel_id, page=page, page_size=page_size
    )


@router.post("", response_model=ScriptRead, status_code=201)
async def create_script(payload: ScriptCreate, current_user: CurrentUser, db: DB) -> ScriptRead:
    svc = ScriptService(db)
    script = await svc.create(payload)
    return ScriptRead.model_validate(script)


@router.post("/generate", response_model=TaskResponse)
async def generate_script(
    payload: ScriptGenerateRequest, current_user: CurrentUser, db: DB
) -> TaskResponse:
    from app.tasks.ai import generate_script_task

    task = generate_script_task.delay(
        channel_id=str(payload.channel_id),
        topic=payload.topic,
        tone=payload.tone,
        target_duration_seconds=payload.target_duration_seconds,
        keywords=payload.keywords,
        additional_context=payload.additional_context,
    )
    return TaskResponse(task_id=task.id, status="pending")


@router.get("/{script_id}", response_model=ScriptRead)
async def get_script(script_id: uuid.UUID, current_user: CurrentUser, db: DB) -> ScriptRead:
    svc = ScriptService(db)
    script = await svc.get_by_id(script_id)
    if not script:
        raise HTTPException(status_code=404, detail="Script not found")
    return ScriptRead.model_validate(script)


@router.patch("/{script_id}", response_model=ScriptRead)
async def update_script(
    script_id: uuid.UUID, payload: ScriptUpdate, current_user: CurrentUser, db: DB
) -> ScriptRead:
    svc = ScriptService(db)
    script = await svc.update(script_id, payload)
    if not script:
        raise HTTPException(status_code=404, detail="Script not found")
    return ScriptRead.model_validate(script)
