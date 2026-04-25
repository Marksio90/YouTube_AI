"""
WorkflowService — orchestrates workflow lifecycle from the API layer.

Responsibilities:
  • Create WorkflowRun rows and kick off Celery execution
  • Expose pause / resume / cancel / retry actions
  • Expose per-job overrides (skip, inject result, retry)
  • Feed audit events back to callers for the history view

The service never touches Celery directly for execution — it delegates to
worker.tasks.workflow.*. It does write audit events directly so the trail
reflects the user's intent even before the worker processes the signal.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.celery import send_task
from app.core.exceptions import NotFoundError, PermissionDeniedError
from app.db.models.workflow import (
    JobStatus,
    RunStatus,
    WorkflowAuditEvent,
    WorkflowJob,
    WorkflowRun,
)
from app.repositories.workflow import WorkflowJobRepository, WorkflowRunRepository
from app.schemas.workflow import (
    InjectResultRequest,
    RetryRequest,
    TriggerRequest,
    WorkflowAuditResponse,
    WorkflowListResponse,
    WorkflowRunRead,
    WorkflowRunSummary,
)

log = structlog.get_logger(__name__)

# Terminal statuses — further transitions require explicit user action
_RUN_TERMINAL = frozenset({RunStatus.completed, RunStatus.cancelled})


class WorkflowService:
    def __init__(self, db: AsyncSession) -> None:
        self._db      = db
        self._run_repo = WorkflowRunRepository(db)
        self._job_repo = WorkflowJobRepository(db)

    # ── Create & trigger ──────────────────────────────────────────────────────

    async def trigger(
        self,
        payload:  TriggerRequest,
        owner_id: uuid.UUID,
    ) -> tuple[WorkflowRun, str]:
        """Create a WorkflowRun and dispatch the Celery execution task."""
        run = WorkflowRun(
            owner_id          = owner_id,
            channel_id        = payload.channel_id,
            pipeline_name     = payload.pipeline_name,
            pipeline_version  = "1.0",
            status            = RunStatus.pending,
            triggered_by      = "api",
            triggered_by_user_id = owner_id,
            context           = payload.context,
        )
        await self._run_repo.save(run)
        await self._run_repo.append_audit_event(
            run_id     = run.id,
            event_type = "run.created",
            actor      = str(owner_id),
            data       = {
                "pipeline": payload.pipeline_name,
                "channel_id": str(payload.channel_id) if payload.channel_id else None,
                "context_keys": list(payload.context.keys()),
            },
        )

        celery_task = send_task(
            task_name="worker.tasks.workflow.run_workflow",
            kwargs={"run_id": str(run.id)},
            queue="default",
        )
        log.info("workflow.triggered", run_id=str(run.id), task_id=celery_task.id)
        return run, celery_task.id

    # ── Read ──────────────────────────────────────────────────────────────────

    async def get_run(
        self, run_id: uuid.UUID, owner_id: uuid.UUID
    ) -> WorkflowRun:
        run = await self._run_repo.get_with_jobs(run_id)
        if run is None:
            raise NotFoundError(f"WorkflowRun {run_id} not found")
        if run.owner_id != owner_id:
            raise PermissionDeniedError("Not your workflow run")
        return run

    async def list_runs(
        self,
        owner_id:  uuid.UUID,
        *,
        channel_id:    uuid.UUID | None  = None,
        pipeline_name: str | None        = None,
        status:        RunStatus | None  = None,
        page:          int  = 1,
        page_size:     int  = 20,
    ) -> WorkflowListResponse:
        offset = (page - 1) * page_size
        runs, total = await self._run_repo.list_for_owner(
            owner_id,
            channel_id    = channel_id,
            pipeline_name = pipeline_name,
            status        = status,
            offset        = offset,
            limit         = page_size,
        )
        return WorkflowListResponse(
            items     = [WorkflowRunSummary.model_validate(r) for r in runs],
            total     = total,
            page      = page,
            page_size = page_size,
            has_next  = offset + page_size < total,
            has_prev  = page > 1,
        )

    async def get_audit(
        self, run_id: uuid.UUID, owner_id: uuid.UUID, *, limit: int = 200
    ) -> WorkflowAuditResponse:
        run = await self._run_repo.get_or_raise(run_id)
        if run.owner_id != owner_id:
            raise PermissionDeniedError("Not your workflow run")
        events = await self._run_repo.audit_events(run_id, limit=limit)
        from app.schemas.workflow import WorkflowAuditEventRead
        return WorkflowAuditResponse(
            run_id = run_id,
            events = [WorkflowAuditEventRead.model_validate(e) for e in events],
            total  = len(events),
        )

    # ── Pause ─────────────────────────────────────────────────────────────────

    async def pause(self, run_id: uuid.UUID, actor: str) -> WorkflowRun:
        run = await self._get_owned_run(run_id, actor)
        if run.status != RunStatus.running:
            raise ValueError(f"Cannot pause a run in status '{run.status.value}'")

        run = await self._run_repo.set_status(
            run, RunStatus.paused, paused_at=_now()
        )
        await self._run_repo.append_audit_event(
            run_id=run_id, event_type="manual.pause", actor=actor,
        )
        log.info("workflow.paused", run_id=str(run_id), actor=actor)
        return run

    # ── Resume ────────────────────────────────────────────────────────────────

    async def resume(self, run_id: uuid.UUID, actor: str) -> tuple[WorkflowRun, str]:
        run = await self._get_owned_run(run_id, actor)
        if run.status != RunStatus.paused:
            raise ValueError(f"Cannot resume a run in status '{run.status.value}'")

        run = await self._run_repo.set_status(run, RunStatus.running)
        await self._run_repo.append_audit_event(
            run_id=run_id, event_type="manual.resume", actor=actor,
        )

        celery_task = send_task(
            task_name="worker.tasks.workflow.resume_workflow",
            kwargs={"run_id": str(run_id)},
            queue="default",
        )
        log.info("workflow.resumed", run_id=str(run_id), actor=actor, task_id=celery_task.id)
        return run, celery_task.id

    # ── Cancel ────────────────────────────────────────────────────────────────

    async def cancel(self, run_id: uuid.UUID, actor: str) -> WorkflowRun:
        run = await self._get_owned_run(run_id, actor)
        if run.status in _RUN_TERMINAL:
            raise ValueError(f"Run already in terminal status '{run.status.value}'")

        run = await self._run_repo.set_status(
            run, RunStatus.cancelled, completed_at=_now()
        )
        await self._run_repo.append_audit_event(
            run_id=run_id, event_type="manual.cancel", actor=actor,
        )
        # Also signal the running Celery task via cancel_workflow
        send_task(
            task_name="worker.tasks.workflow.cancel_workflow",
            kwargs={"run_id": str(run_id), "actor": actor},
            queue="high",
        )
        log.info("workflow.cancelled", run_id=str(run_id), actor=actor)
        return run

    # ── Retry run ─────────────────────────────────────────────────────────────

    async def retry_run(
        self,
        run_id:  uuid.UUID,
        actor:   str,
        payload: RetryRequest,
    ) -> tuple[WorkflowRun, str]:
        run = await self._get_owned_run(run_id, actor)
        if run.status not in (RunStatus.failed, RunStatus.paused):
            raise ValueError(
                f"Can only retry a failed or paused run, not '{run.status.value}'"
            )

        # Reset failed jobs so the engine re-runs them
        jobs = await self._job_repo.list_for_run(run_id)
        for job in jobs:
            if job.status == JobStatus.failed:
                await self._job_repo.reset_for_retry(job)

        if payload.reset_context:
            # Restore context to the original run input (stored in a fresh run)
            run.context = {}

        run = await self._run_repo.set_status(run, RunStatus.running)
        await self._run_repo.append_audit_event(
            run_id=run_id, event_type="manual.retry_run", actor=actor,
            data={"reset_context": payload.reset_context},
        )

        celery_task = send_task(
            task_name="worker.tasks.workflow.run_workflow",
            kwargs={"run_id": str(run_id)},
            queue="default",
        )
        log.info("workflow.retried", run_id=str(run_id), actor=actor, task_id=celery_task.id)
        return run, celery_task.id

    # ── Per-job overrides ─────────────────────────────────────────────────────

    async def skip_job(
        self, run_id: uuid.UUID, step_id: str, actor: str
    ) -> WorkflowJob:
        run = await self._get_owned_run(run_id, actor)
        job = await self._job_repo.get_by_step_or_raise(run_id, step_id)

        if job.status in (JobStatus.completed, JobStatus.cancelled):
            raise ValueError(f"Job '{step_id}' is already in terminal status '{job.status.value}'")

        job = await self._job_repo.skip(job, actor)
        await self._run_repo.append_audit_event(
            run_id=run_id, event_type="manual.skip_job", actor=actor,
            job_id=job.id, data={"step_id": step_id},
        )
        log.info("workflow.job_skipped", run_id=str(run_id), step=step_id, actor=actor)
        return job

    async def retry_job(
        self, run_id: uuid.UUID, step_id: str, actor: str
    ) -> tuple[WorkflowJob, str]:
        run = await self._get_owned_run(run_id, actor)
        job = await self._job_repo.get_by_step_or_raise(run_id, step_id)

        if job.status not in (JobStatus.failed, JobStatus.skipped, JobStatus.cancelled):
            raise ValueError(
                f"Can only retry a failed/skipped job, not '{job.status.value}'"
            )

        job = await self._job_repo.reset_for_retry(job)
        await self._run_repo.append_audit_event(
            run_id=run_id, event_type="manual.retry_job", actor=actor,
            job_id=job.id, data={"step_id": step_id},
        )

        # Ensure the run is in running state, then dispatch engine
        if run.status not in (RunStatus.running,):
            await self._run_repo.set_status(run, RunStatus.running)

        celery_task = send_task(
            task_name="worker.tasks.workflow.run_workflow",
            kwargs={"run_id": str(run_id)},
            queue="default",
        )
        log.info("workflow.job_retried", run_id=str(run_id), step=step_id, actor=actor)
        return job, celery_task.id

    async def inject_result(
        self,
        run_id:  uuid.UUID,
        step_id: str,
        actor:   str,
        payload: InjectResultRequest,
    ) -> WorkflowJob:
        """Manually mark a job as completed with a provided output dict."""
        await self._get_owned_run(run_id, actor)
        job = await self._job_repo.get_by_step_or_raise(run_id, step_id)

        if job.status == JobStatus.running:
            raise ValueError("Cannot inject result into a currently running job")

        job = await self._job_repo.inject_result(job, payload.output, actor)
        await self._run_repo.append_audit_event(
            run_id=run_id, event_type="manual.inject_result", actor=actor,
            job_id=job.id,
            data={"step_id": step_id, "output_keys": list(payload.output.keys())},
        )
        log.info("workflow.result_injected", run_id=str(run_id), step=step_id, actor=actor)
        return job

    async def patch_context(
        self,
        run_id:  uuid.UUID,
        actor:   str,
        updates: dict[str, Any],
    ) -> WorkflowRun:
        """Merge updates into the run's shared context."""
        run = await self._get_owned_run(run_id, actor)
        run.context = {**(run.context or {}), **updates}
        run = await self._run_repo.save(run)
        await self._run_repo.append_audit_event(
            run_id=run_id, event_type="manual.inject_result", actor=actor,
            data={"updated_keys": list(updates.keys())},
        )
        return run

    # ── Internal helpers ──────────────────────────────────────────────────────

    async def _get_owned_run(
        self, run_id: uuid.UUID, actor: str
    ) -> WorkflowRun:
        """Load a run and verify ownership (actor = user UUID string or 'system')."""
        run = await self._run_repo.get_or_raise(run_id)
        if actor != "system" and str(run.owner_id) != actor:
            raise PermissionDeniedError("Not your workflow run")
        return run


def _now() -> datetime:
    return datetime.now(timezone.utc)
