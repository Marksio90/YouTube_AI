from __future__ import annotations

import uuid
from typing import Any

import structlog
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

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/pipelines", tags=["pipelines"])

DEFAULT_PAGE = 1
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100


async def _get_owned_pipeline(
    *,
    service: PipelineService,
    pipeline_id: uuid.UUID,
    owner_id: uuid.UUID,
):
    pipeline = await service.get_owned(pipeline_id, owner_id=owner_id)
    if not pipeline:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Pipeline not found",
        )
    return pipeline


def _enqueue_pipeline_run(run_id: uuid.UUID) -> str:
    try:
        from app.tasks.pipeline import run_pipeline_task
    except ModuleNotFoundError as exc:
        logger.error(
            "pipelines.task_module_missing",
            run_id=str(run_id),
            expected_module="app.tasks.pipeline",
            expected_task="run_pipeline_task",
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Pipeline worker task is not available",
        ) from exc

    task = run_pipeline_task.delay(str(run_id))
    return task.id


@router.get(
    "",
    response_model=PaginatedResponse[PipelineRead],
    summary="List pipelines owned by the current user",
)
async def list_pipelines(
    current_user: CurrentUser,
    db: DB,
    page: int = Query(DEFAULT_PAGE, ge=1),
    page_size: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
) -> PaginatedResponse[PipelineRead]:
    service = PipelineService(db)

    return await service.list_for_user(
        current_user.id,
        page=page,
        page_size=page_size,
    )


@router.post(
    "",
    response_model=PipelineRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a pipeline",
)
async def create_pipeline(
    payload: PipelineCreate,
    current_user: CurrentUser,
    db: DB,
) -> PipelineRead:
    service = PipelineService(db)

    try:
        pipeline = await service.create(payload, owner_id=current_user.id)
        await db.commit()
        await db.refresh(pipeline)
    except Exception:
        await db.rollback()
        logger.exception(
            "pipelines.create_failed",
            owner_id=str(current_user.id),
            name=payload.name,
            channel_id=str(payload.channel_id) if payload.channel_id else None,
            step_count=len(payload.steps),
        )
        raise

    logger.info(
        "pipelines.created",
        pipeline_id=str(pipeline.id),
        owner_id=str(current_user.id),
        channel_id=str(pipeline.channel_id) if pipeline.channel_id else None,
        step_count=len(pipeline.steps or []),
    )

    return PipelineRead.model_validate(pipeline)


@router.get(
    "/{pipeline_id}",
    response_model=PipelineRead,
    summary="Get a pipeline",
)
async def get_pipeline(
    pipeline_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
) -> PipelineRead:
    service = PipelineService(db)
    pipeline = await _get_owned_pipeline(
        service=service,
        pipeline_id=pipeline_id,
        owner_id=current_user.id,
    )

    return PipelineRead.model_validate(pipeline)


@router.post(
    "/{pipeline_id}/trigger",
    response_model=TaskResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Trigger a pipeline run",
)
async def trigger_pipeline(
    pipeline_id: uuid.UUID,
    payload: PipelineTriggerRequest,
    current_user: CurrentUser,
    db: DB,
) -> TaskResponse:
    service = PipelineService(db)

    await _get_owned_pipeline(
        service=service,
        pipeline_id=pipeline_id,
        owner_id=current_user.id,
    )

    try:
        run = await service.create_run(
            pipeline_id,
            triggered_by=str(current_user.id),
            input=payload.input,
        )
        await db.commit()
        await db.refresh(run)
    except Exception:
        await db.rollback()
        logger.exception(
            "pipelines.run_create_failed",
            pipeline_id=str(pipeline_id),
            owner_id=str(current_user.id),
        )
        raise

    task_id = _enqueue_pipeline_run(run.id)

    logger.info(
        "pipelines.run_queued",
        pipeline_id=str(pipeline_id),
        run_id=str(run.id),
        owner_id=str(current_user.id),
        task_id=task_id,
    )

    return TaskResponse(task_id=task_id, status="pending")


@router.get(
    "/{pipeline_id}/runs",
    response_model=PaginatedResponse[PipelineRunRead],
    summary="List runs for a pipeline",
)
async def list_runs(
    pipeline_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
    page: int = Query(DEFAULT_PAGE, ge=1),
    page_size: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
) -> PaginatedResponse[PipelineRunRead]:
    service = PipelineService(db)

    await _get_owned_pipeline(
        service=service,
        pipeline_id=pipeline_id,
        owner_id=current_user.id,
    )

    return await service.list_runs(
        pipeline_id,
        page=page,
        page_size=page_size,
    )
