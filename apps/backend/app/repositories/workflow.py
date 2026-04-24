"""
Workflow data access layer.

Two repositories:
  WorkflowRunRepository   — CRUD + status queries for workflow runs
  WorkflowJobRepository   — CRUD + override operations for individual jobs

Both follow the BaseRepository contract (get, list, save, delete).
Domain-specific helpers are added as named methods for clarity.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import and_, desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.db.models.workflow import (
    JobStatus,
    RunStatus,
    WorkflowAuditEvent,
    WorkflowJob,
    WorkflowRun,
)
from app.repositories.base import BaseRepository


class WorkflowRunRepository(BaseRepository[WorkflowRun]):
    model = WorkflowRun

    # ── Queries ───────────────────────────────────────────────────────────────

    async def list_for_channel(
        self,
        channel_id: uuid.UUID | str,
        *,
        status:    RunStatus | None = None,
        offset:    int  = 0,
        limit:     int  = 20,
    ) -> tuple[list[WorkflowRun], int]:
        conditions = [WorkflowRun.channel_id == channel_id]
        if status:
            conditions.append(WorkflowRun.status == status)
        return await self.list(
            *conditions,
            order_by=desc(WorkflowRun.created_at),
            offset=offset,
            limit=limit,
        )

    async def list_for_owner(
        self,
        owner_id: uuid.UUID | str,
        *,
        pipeline_name: str | None        = None,
        status:        RunStatus | None  = None,
        channel_id:    uuid.UUID | None  = None,
        offset:        int  = 0,
        limit:         int  = 20,
    ) -> tuple[list[WorkflowRun], int]:
        conditions: list[Any] = [WorkflowRun.owner_id == owner_id]
        if pipeline_name:
            conditions.append(WorkflowRun.pipeline_name == pipeline_name)
        if status:
            conditions.append(WorkflowRun.status == status)
        if channel_id:
            conditions.append(WorkflowRun.channel_id == channel_id)
        return await self.list(
            *conditions,
            order_by=desc(WorkflowRun.created_at),
            offset=offset,
            limit=limit,
        )

    async def get_with_jobs(self, run_id: uuid.UUID | str) -> WorkflowRun | None:
        """Eagerly load jobs alongside the run."""
        from sqlalchemy.orm import selectinload
        result = await self.db.execute(
            select(WorkflowRun)
            .where(WorkflowRun.id == run_id)
            .options(selectinload(WorkflowRun.jobs))
        )
        return result.scalar_one_or_none()

    # ── Status transitions ────────────────────────────────────────────────────

    async def set_status(
        self,
        run: WorkflowRun,
        status: RunStatus,
        *,
        error:        str | None       = None,
        started_at:   datetime | None  = None,
        completed_at: datetime | None  = None,
        paused_at:    datetime | None  = None,
    ) -> WorkflowRun:
        run.status = status
        if error is not None:
            run.error = error
        if started_at is not None:
            run.started_at = started_at
        if completed_at is not None:
            run.completed_at = completed_at
        if paused_at is not None:
            run.paused_at = paused_at
        return await self.save(run)

    # ── Audit trail ───────────────────────────────────────────────────────────

    async def audit_events(
        self,
        run_id: uuid.UUID | str,
        *,
        offset: int = 0,
        limit:  int = 200,
    ) -> list[WorkflowAuditEvent]:
        result = await self.db.execute(
            select(WorkflowAuditEvent)
            .where(WorkflowAuditEvent.run_id == run_id)
            .order_by(WorkflowAuditEvent.occurred_at)
            .offset(offset)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def append_audit_event(
        self,
        *,
        run_id:     uuid.UUID | str,
        event_type: str,
        actor:      str = "system",
        job_id:     uuid.UUID | None = None,
        data:       dict | None      = None,
    ) -> WorkflowAuditEvent:
        event = WorkflowAuditEvent(
            run_id     = run_id,
            job_id     = job_id,
            event_type = event_type,
            actor      = actor,
            data       = data or {},
        )
        self.db.add(event)
        await self.db.flush()
        await self.db.refresh(event)
        return event


class WorkflowJobRepository(BaseRepository[WorkflowJob]):
    model = WorkflowJob

    # ── Queries ───────────────────────────────────────────────────────────────

    async def list_for_run(
        self, run_id: uuid.UUID | str
    ) -> list[WorkflowJob]:
        result = await self.db.execute(
            select(WorkflowJob)
            .where(WorkflowJob.run_id == run_id)
            .order_by(WorkflowJob.created_at)
        )
        return list(result.scalars().all())

    async def get_by_step(
        self, run_id: uuid.UUID | str, step_id: str
    ) -> WorkflowJob | None:
        result = await self.db.execute(
            select(WorkflowJob).where(
                and_(WorkflowJob.run_id == run_id, WorkflowJob.step_id == step_id)
            )
        )
        return result.scalar_one_or_none()

    async def get_by_step_or_raise(
        self, run_id: uuid.UUID | str, step_id: str
    ) -> WorkflowJob:
        job = await self.get_by_step(run_id, step_id)
        if job is None:
            raise NotFoundError(f"Job '{step_id}' not found in run {run_id}")
        return job

    # ── Status transitions ────────────────────────────────────────────────────

    async def set_status(
        self,
        job: WorkflowJob,
        status: JobStatus,
        *,
        error:        str | None       = None,
        output:       dict | None      = None,
        started_at:   datetime | None  = None,
        completed_at: datetime | None  = None,
    ) -> WorkflowJob:
        job.status = status
        if error is not None:
            job.error = error
        if output is not None:
            job.output = output
        if started_at is not None:
            job.started_at = started_at
        if completed_at is not None:
            job.completed_at = completed_at
        return await self.save(job)

    # ── Manual overrides ──────────────────────────────────────────────────────

    async def skip(self, job: WorkflowJob, actor: str) -> WorkflowJob:
        """Manually skip a pending/failed job."""
        job.status          = JobStatus.skipped
        job.is_manual_result = True
        job.manual_actor    = actor
        job.completed_at    = datetime.now(timezone.utc)
        return await self.save(job)

    async def inject_result(
        self, job: WorkflowJob, output: dict, actor: str
    ) -> WorkflowJob:
        """Manually inject a successful result, bypassing execution."""
        job.status           = JobStatus.completed
        job.output           = output
        job.is_manual_result = True
        job.manual_actor     = actor
        job.completed_at     = datetime.now(timezone.utc)
        return await self.save(job)

    async def reset_for_retry(self, job: WorkflowJob) -> WorkflowJob:
        """Reset a failed or skipped job back to pending so the engine re-runs it."""
        job.status       = JobStatus.pending
        job.error        = None
        job.output       = None
        job.attempt      = max(1, job.attempt)
        job.scheduled_at = None
        job.started_at   = None
        job.completed_at = None
        job.retry_after  = None
        return await self.save(job)
