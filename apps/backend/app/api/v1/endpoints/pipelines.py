import uuid

from fastapi import APIRouter, HTTPException, Query, status

from app.api.v1.deps import CurrentUser, DB
from app.schemas.common import PaginatedResponse, TaskResponse
from app.schemas.pipeline import (
    PipelineCreate,
    PipelineRead,
    PipelineRunRead,
    PipelineTriggerRequest,
)
from app.services.pipeline import PipelineService

router = APIRouter(prefix="/pipelines", tags=["pipelines"])


@router.get("", response_model=PaginatedResponse[PipelineRead])
async def list_pipelines(
    current_user: CurrentUser,
    db: DB,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> PaginatedResponse[PipelineRead]:
    svc = PipelineService(db)
    return await svc.list_for_user(str(current_user.id), page=page, page_size=page_size)


@router.post("", response_model=PipelineRead, status_code=201)
async def create_pipeline(
    payload: PipelineCreate, current_user: CurrentUser, db: DB
) -> PipelineRead:
    svc = PipelineService(db)
    pipeline = await svc.create(payload, owner_id=current_user.id)
    return PipelineRead.model_validate(pipeline)


@router.get("/{pipeline_id}", response_model=PipelineRead)
async def get_pipeline(
    pipeline_id: uuid.UUID, current_user: CurrentUser, db: DB
) -> PipelineRead:
    svc = PipelineService(db)
    pipeline = await svc.get_owned(pipeline_id, owner_id=current_user.id)
    if not pipeline:
        raise HTTPException(status_code=404, detail="Pipeline not found")
    return PipelineRead.model_validate(pipeline)


@router.post("/{pipeline_id}/trigger", response_model=TaskResponse)
async def trigger_pipeline(
    pipeline_id: uuid.UUID,
    payload: PipelineTriggerRequest,
    current_user: CurrentUser,
    db: DB,
) -> TaskResponse:
    from app.tasks.pipeline import run_pipeline_task

    svc = PipelineService(db)
    pipeline = await svc.get_owned(pipeline_id, owner_id=current_user.id)
    if not pipeline:
        raise HTTPException(status_code=404, detail="Pipeline not found")

    run = await svc.create_run(pipeline_id, triggered_by=str(current_user.id), input=payload.input)
    task = run_pipeline_task.delay(str(run.id))
    return TaskResponse(task_id=task.id, status="pending")


@router.get("/{pipeline_id}/runs", response_model=PaginatedResponse[PipelineRunRead])
async def list_runs(
    pipeline_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> PaginatedResponse[PipelineRunRead]:
    svc = PipelineService(db)
    return await svc.list_runs(pipeline_id, page=page, page_size=page_size)
