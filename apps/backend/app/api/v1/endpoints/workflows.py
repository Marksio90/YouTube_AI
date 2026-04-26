"""
Workflow REST API.

Endpoints:
  POST   /workflows                               — trigger a new run
  GET    /workflows                               — list runs (paginated)
  GET    /workflows/{run_id}                      — full run detail with jobs
  GET    /workflows/{run_id}/audit                — append-only audit trail
  PATCH  /workflows/{run_id}/context             — merge keys into context
  POST   /workflows/{run_id}/pause               — pause a running run
  POST   /workflows/{run_id}/resume              — resume a paused run
  POST   /workflows/{run_id}/cancel              — cancel a run
  POST   /workflows/{run_id}/retry               — retry a failed/paused run
  GET    /workflows/{run_id}/jobs                — list all jobs for a run
  GET    /workflows/{run_id}/jobs/{step_id}      — single job detail
  POST   /workflows/{run_id}/jobs/{step_id}/skip     — skip a job
  POST   /workflows/{run_id}/jobs/{step_id}/retry    — retry a job
  POST   /workflows/{run_id}/jobs/{step_id}/inject   — inject manual result
"""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status

from app.api.v1.deps import CurrentUser, DB
from app.core.exceptions import NotFoundError, PermissionDeniedError
from app.db.models.workflow import RunStatus
from app.schemas.common import TaskResponse
from app.schemas.workflow import (
    InjectResultRequest,
    OverrideContextRequest,
    RetryRequest,
    TriggerRequest,
    WorkflowActionResponse,
    WorkflowAuditResponse,
    WorkflowJobRead,
    WorkflowListResponse,
    WorkflowRunRead,
)
from app.services.workflow_service import WorkflowService

router = APIRouter(prefix="/workflows", tags=["workflows"])


def _svc(db: DB) -> WorkflowService:
    return WorkflowService(db)


def _actor(user: CurrentUser) -> str:
    return str(user.id)


# ── Collection ────────────────────────────────────────────────────────────────

@router.post("", response_model=WorkflowActionResponse, status_code=status.HTTP_202_ACCEPTED)
async def trigger_workflow(
    payload:      TriggerRequest,
    current_user: CurrentUser,
    db:           DB,
) -> WorkflowActionResponse:
    """Create a new workflow run and dispatch it to the worker."""
    try:
        run, task_id = await _svc(db).trigger(payload, owner_id=current_user.id)
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    return WorkflowActionResponse(
        status  = run.status.value,
        run_id  = run.id,
        message = f"Pipeline '{payload.pipeline_name}' dispatched",
        task_id = task_id,
    )


@router.get("", response_model=WorkflowListResponse)
async def list_workflows(
    current_user:  CurrentUser,
    db:            DB,
    channel_id:    uuid.UUID | None  = Query(None),
    pipeline_name: str | None        = Query(None),
    status_filter: RunStatus | None  = Query(None, alias="status"),
    page:          int               = Query(1, ge=1),
    page_size:     int               = Query(20, ge=1, le=100),
) -> WorkflowListResponse:
    return await _svc(db).list_runs(
        current_user.id,
        channel_id    = channel_id,
        pipeline_name = pipeline_name,
        status        = status_filter,
        page          = page,
        page_size     = page_size,
    )


# ── Single run ────────────────────────────────────────────────────────────────

@router.get("/{run_id}", response_model=WorkflowRunRead)
async def get_workflow(
    run_id:       uuid.UUID,
    current_user: CurrentUser,
    db:           DB,
) -> WorkflowRunRead:
    try:
        run = await _svc(db).get_run(run_id, owner_id=current_user.id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except PermissionDeniedError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    return WorkflowRunRead.model_validate(run)


@router.get("/{run_id}/audit", response_model=WorkflowAuditResponse)
async def get_audit_trail(
    run_id:       uuid.UUID,
    current_user: CurrentUser,
    db:           DB,
    limit:        int = Query(200, ge=1, le=1000),
) -> WorkflowAuditResponse:
    try:
        return await _svc(db).get_audit(run_id, current_user.id, limit=limit)
    except (NotFoundError, PermissionDeniedError) as exc:
        code = 404 if isinstance(exc, NotFoundError) else 403
        raise HTTPException(status_code=code, detail=str(exc))


@router.patch("/{run_id}/context", response_model=WorkflowRunRead)
async def patch_context(
    run_id:       uuid.UUID,
    payload:      OverrideContextRequest,
    current_user: CurrentUser,
    db:           DB,
) -> WorkflowRunRead:
    try:
        run = await _svc(db).patch_context(run_id, _actor(current_user), payload.updates)
    except (NotFoundError, PermissionDeniedError) as exc:
        code = 404 if isinstance(exc, NotFoundError) else 403
        raise HTTPException(status_code=code, detail=str(exc))
    return WorkflowRunRead.model_validate(run)


# ── Lifecycle actions ─────────────────────────────────────────────────────────

@router.post("/{run_id}/pause", response_model=WorkflowActionResponse)
async def pause_workflow(
    run_id: uuid.UUID, current_user: CurrentUser, db: DB
) -> WorkflowActionResponse:
    try:
        run = await _svc(db).pause(run_id, _actor(current_user))
    except (NotFoundError, PermissionDeniedError, ValueError) as exc:
        code = 404 if isinstance(exc, NotFoundError) else (403 if isinstance(exc, PermissionDeniedError) else 409)
        raise HTTPException(status_code=code, detail=str(exc))
    return WorkflowActionResponse(status=run.status.value, run_id=run.id, message="Paused")


@router.post("/{run_id}/resume", response_model=WorkflowActionResponse)
async def resume_workflow(
    run_id: uuid.UUID, current_user: CurrentUser, db: DB
) -> WorkflowActionResponse:
    try:
        run, task_id = await _svc(db).resume(run_id, _actor(current_user))
    except (NotFoundError, PermissionDeniedError, ValueError) as exc:
        code = 404 if isinstance(exc, NotFoundError) else (403 if isinstance(exc, PermissionDeniedError) else 409)
        raise HTTPException(status_code=code, detail=str(exc))
    return WorkflowActionResponse(
        status=run.status.value, run_id=run.id, message="Resumed", task_id=task_id
    )


@router.post("/{run_id}/cancel", response_model=WorkflowActionResponse)
async def cancel_workflow(
    run_id: uuid.UUID, current_user: CurrentUser, db: DB
) -> WorkflowActionResponse:
    try:
        run = await _svc(db).cancel(run_id, _actor(current_user))
    except (NotFoundError, PermissionDeniedError, ValueError) as exc:
        code = 404 if isinstance(exc, NotFoundError) else (403 if isinstance(exc, PermissionDeniedError) else 409)
        raise HTTPException(status_code=code, detail=str(exc))
    return WorkflowActionResponse(status=run.status.value, run_id=run.id, message="Cancelled")


@router.post("/{run_id}/retry", response_model=WorkflowActionResponse)
async def retry_workflow(
    run_id:       uuid.UUID,
    payload:      RetryRequest,
    current_user: CurrentUser,
    db:           DB,
) -> WorkflowActionResponse:
    try:
        run, task_id = await _svc(db).retry_run(run_id, _actor(current_user), payload)
    except (NotFoundError, PermissionDeniedError, ValueError) as exc:
        code = 404 if isinstance(exc, NotFoundError) else (403 if isinstance(exc, PermissionDeniedError) else 409)
        raise HTTPException(status_code=code, detail=str(exc))
    return WorkflowActionResponse(
        status=run.status.value, run_id=run.id, message="Retrying", task_id=task_id
    )


# ── Job endpoints ─────────────────────────────────────────────────────────────

@router.get("/{run_id}/jobs", response_model=list[WorkflowJobRead])
async def list_jobs(
    run_id:       uuid.UUID,
    current_user: CurrentUser,
    db:           DB,
) -> list[WorkflowJobRead]:
    try:
        run = await _svc(db).get_run(run_id, owner_id=current_user.id)
    except (NotFoundError, PermissionDeniedError) as exc:
        code = 404 if isinstance(exc, NotFoundError) else 403
        raise HTTPException(status_code=code, detail=str(exc))
    return [WorkflowJobRead.model_validate(j) for j in run.jobs]


@router.get("/{run_id}/jobs/{step_id}", response_model=WorkflowJobRead)
async def get_job(
    run_id:       uuid.UUID,
    step_id:      str,
    current_user: CurrentUser,
    db:           DB,
) -> WorkflowJobRead:
    from app.repositories.workflow import WorkflowJobRepository
    try:
        await _svc(db).get_run(run_id, owner_id=current_user.id)  # auth check
        job = await WorkflowJobRepository(db).get_by_step_or_raise(run_id, step_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except PermissionDeniedError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    return WorkflowJobRead.model_validate(job)


@router.post("/{run_id}/jobs/{step_id}/skip", response_model=WorkflowJobRead)
async def skip_job(
    run_id:       uuid.UUID,
    step_id:      str,
    current_user: CurrentUser,
    db:           DB,
) -> WorkflowJobRead:
    try:
        job = await _svc(db).skip_job(run_id, step_id, _actor(current_user))
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except (PermissionDeniedError, ValueError) as exc:
        code = 403 if isinstance(exc, PermissionDeniedError) else 409
        raise HTTPException(status_code=code, detail=str(exc))
    return WorkflowJobRead.model_validate(job)


@router.post("/{run_id}/jobs/{step_id}/retry", response_model=WorkflowActionResponse)
async def retry_job(
    run_id:       uuid.UUID,
    step_id:      str,
    current_user: CurrentUser,
    db:           DB,
) -> WorkflowActionResponse:
    try:
        job, task_id = await _svc(db).retry_job(run_id, step_id, _actor(current_user))
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except (PermissionDeniedError, ValueError) as exc:
        code = 403 if isinstance(exc, PermissionDeniedError) else 409
        raise HTTPException(status_code=code, detail=str(exc))
    return WorkflowActionResponse(
        status  = job.status.value,
        run_id  = run_id,
        message = f"Job '{step_id}' reset and run re-dispatched",
        task_id = task_id,
    )


@router.post("/{run_id}/jobs/{step_id}/inject", response_model=WorkflowJobRead)
async def inject_result(
    run_id:       uuid.UUID,
    step_id:      str,
    payload:      InjectResultRequest,
    current_user: CurrentUser,
    db:           DB,
) -> WorkflowJobRead:
    """
    Manually mark a job as completed with a provided output dict.
    Use this to bypass a failing step when you have the result already.
    """
    try:
        job = await _svc(db).inject_result(run_id, step_id, _actor(current_user), payload)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except (PermissionDeniedError, ValueError) as exc:
        code = 403 if isinstance(exc, PermissionDeniedError) else 409
        raise HTTPException(status_code=code, detail=str(exc))
    return WorkflowJobRead.model_validate(job)
