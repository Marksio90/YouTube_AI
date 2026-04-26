"""
WorkflowEngine — the main orchestrator.

Design principles:
  • Stateless: reads from DB at the start of each execution; all state lives in DB
  • Resumable: calling execute() on an already-started run picks up from the
    last completed step — safe to call after worker crash or pause/resume
  • Debuggable: every state transition + event is written to the audit log
  • No external state: context is stored in workflow_runs.context (JSONB)

Execution model:
  1. Load the run (create if needed) and all its WorkflowJob rows
  2. Transition run → running (idempotent if already running)
  3. Iterate steps in topological order
  4. For each step:
     a. Skip if already terminal
     b. Poll DB for pause / cancel signals
     c. Verify dependencies are satisfied
     d. Dispatch Celery task → wait for result (with timeout)
     e. On success: merge output into context, persist
     f. On failure: retry with exponential backoff or apply fail_policy
  5. Set final run status and write audit event

Thread safety: not thread-safe. Call from a single asyncio coroutine.
"""
from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from worker.workflow.audit import AuditLogger
from worker.workflow.context import WorkflowContext
from worker.workflow.definition import PipelineDef, StepDef, get_pipeline
from worker.workflow.exceptions import (
    ContextKeyMissingError,
    JobFailedError,
    JobTimeoutError,
    WorkflowAbortError,
    WorkflowCancelledError,
    WorkflowPausedError,
)
from worker.workflow.jobs import get_job
from worker.workflow.state_machine import validate_job_transition, validate_run_transition
from worker.workflow.types import (
    DEPS_OK_STATES,
    JOB_TERMINAL,
    EventType,
    FailPolicy,
    JobStatus,
    RunStatus,
)

log = structlog.get_logger(__name__)


class WorkflowEngine:
    """
    Stateless orchestrator.  All state persists to PostgreSQL between steps.
    The engine can be safely re-instantiated; it will resume from the DB state.
    """

    def __init__(self, db: AsyncSession) -> None:
        self._db    = db
        self._audit = AuditLogger(db)

    # ── Public entry point ────────────────────────────────────────────────────

    async def execute(self, run_id: str) -> RunStatus:
        """
        Drive a workflow run to completion (or until paused/cancelled/failed).
        Returns the final RunStatus.
        """
        run = await self._load_run(run_id)
        if not run:
            raise ValueError(f"WorkflowRun {run_id!r} not found")

        current_status = RunStatus(run["status"])
        if current_status in (RunStatus.completed, RunStatus.cancelled):
            log.info("workflow.already_terminal", run_id=run_id, status=current_status)
            return current_status

        pipeline = get_pipeline(run["pipeline_name"])
        log_ = log.bind(run_id=run_id, pipeline=pipeline.name)

        # Create WorkflowJob rows for any steps that don't have them yet
        await self._ensure_jobs_exist(run_id, pipeline)

        # Transition pending → running
        if current_status == RunStatus.pending:
            await self._set_run_status(run_id, RunStatus.running, started_at=_now())
            await self._audit.log(
                run_id=run_id, event_type=EventType.run_started,
                data={"pipeline": pipeline.name, "version": pipeline.version},
            )

        # Reset any orphaned scheduled/running jobs from a previous worker crash
        await self._reset_orphaned_jobs(run_id)

        # Load context
        ctx = WorkflowContext(run["context"] or {})

        # Execute steps in topological order
        ordered = pipeline.topological_order()
        log_.info("workflow.executing", steps=[s.step_id for s in ordered])

        for step_def in ordered:
            job = await self._load_job(run_id, step_def.step_id)
            if not job:
                log_.warning("workflow.job_missing", step=step_def.step_id)
                continue

            job_status = JobStatus(job["status"])

            # Already terminal — reload output into context and move on
            if job_status in JOB_TERMINAL:
                if job["output"]:
                    ctx.merge(job["output"])
                log_.debug("workflow.step_skip_terminal", step=step_def.step_id, status=job_status)
                continue

            # Check for external pause / cancel signals
            await self._check_signals(run_id)

            # Check whether all dependencies completed
            deps_ready = await self._deps_satisfied(run_id, step_def)
            if not deps_ready:
                outcome = await self._handle_deps_failed(run_id, job, step_def)
                if outcome == "abort":
                    final = RunStatus.failed
                    await self._set_run_status(
                        run_id, final,
                        error=f"Step '{step_def.step_id}' blocked by failed dependency",
                        completed_at=_now(),
                    )
                    await self._audit.log(
                        run_id=run_id, event_type=EventType.run_failed,
                        data={"step": step_def.step_id, "reason": "dependency_failed"},
                    )
                    return final
                # skip/continue — context unchanged, proceed
                continue

            # Execute the step (with retry loop)
            try:
                output = await self._run_step(run_id, job, step_def, ctx, log_)
                ctx.merge(output)
                await self._persist_context(run_id, ctx)

            except WorkflowAbortError as exc:
                log_.error("workflow.abort", step=step_def.step_id, reason=exc.cause)
                await self._set_run_status(
                    run_id, RunStatus.failed,
                    error=str(exc), completed_at=_now(),
                )
                await self._audit.log(
                    run_id=run_id, event_type=EventType.run_failed,
                    data={"step": exc.step_id, "reason": exc.cause},
                )
                return RunStatus.failed

            except WorkflowPausedError:
                log_.info("workflow.paused", step=step_def.step_id)
                return RunStatus.paused

            except WorkflowCancelledError:
                log_.info("workflow.cancelled", step=step_def.step_id)
                await self._cancel_pending_jobs(run_id)
                return RunStatus.cancelled

        # All steps processed
        jobs = await self._load_all_jobs(run_id)
        any_failed = any(JobStatus(j["status"]) == JobStatus.failed for j in jobs)
        final = RunStatus.failed if any_failed else RunStatus.completed

        await self._set_run_status(
            run_id, final,
            completed_at=_now(),
            **({"error": "One or more non-blocking steps failed"} if any_failed else {}),
        )
        event = EventType.run_completed if final == RunStatus.completed else EventType.run_failed
        await self._audit.log(run_id=run_id, event_type=event,
                              data={"context_keys": list(ctx.snapshot().keys())})

        log_.info("workflow.done", status=final)
        return final

    # ── Step execution ────────────────────────────────────────────────────────

    async def _run_step(
        self,
        run_id:   str,
        job:      dict,
        step_def: StepDef,
        ctx:      WorkflowContext,
        log_:     Any,
    ) -> dict:
        """Execute one step with full retry loop. Returns the job's output dict."""
        job_id    = str(job["id"])
        attempt   = int(job["attempt"])
        max_atts  = step_def.max_retries + 1  # retries ON TOP of the first attempt

        while True:
            # Transition to scheduled
            await self._set_job_status(
                run_id, job_id, JobStatus.scheduled,
                attempt=attempt,
                scheduled_at=_now(),
            )
            await self._audit.log(
                run_id=run_id, job_id=job_id,
                event_type=EventType.job_scheduled,
                data={"step": step_def.step_id, "attempt": attempt},
            )

            try:
                job_instance = get_job(step_def.step_type)
                payload = job_instance.build_payload(ctx, step_def.config)
            except ContextKeyMissingError as exc:
                raise WorkflowAbortError(step_def.step_id, str(exc)) from exc

            # Transition to running
            started_at = _now()
            await self._set_job_status(
                run_id, job_id, JobStatus.running,
                started_at=started_at,
                celery_task_id=None,
            )
            await self._audit.log(
                run_id=run_id, job_id=job_id,
                event_type=EventType.job_started,
                data={"step": step_def.step_id, "attempt": attempt, "payload_keys": list(payload)},
            )
            log_.info("workflow.step_start", step=step_def.step_id, attempt=attempt)

            try:
                result = await self._dispatch(
                    job_id            = job_id,
                    task_name         = job_instance.celery_task_name,
                    queue             = job_instance.celery_queue,
                    payload           = payload,
                    timeout_seconds   = step_def.timeout_seconds,
                )
                output = job_instance.extract_output(result)

            except JobTimeoutError as exc:
                error_msg = str(exc)
            except Exception as exc:
                error_msg = str(exc)
            else:
                # ── Success path ──────────────────────────────────────────────
                duration_ms = int((time.monotonic() - _monotonic_start(started_at)) * 1000)
                await self._set_job_status(
                    run_id, job_id, JobStatus.completed,
                    output=output,
                    completed_at=_now(),
                    duration_ms=duration_ms,
                )
                await self._audit.log(
                    run_id=run_id, job_id=job_id,
                    event_type=EventType.job_completed,
                    data={"step": step_def.step_id, "attempt": attempt,
                          "output_keys": list(output), "duration_ms": duration_ms},
                )
                log_.info("workflow.step_done", step=step_def.step_id,
                          duration_ms=duration_ms, attempt=attempt)
                return output

            # ── Failure path ──────────────────────────────────────────────────
            log_.warning("workflow.step_error", step=step_def.step_id,
                         attempt=attempt, error=error_msg)
            await self._append_attempt_history(
                job_id, attempt=attempt, error=error_msg, started_at=started_at
            )

            if attempt < max_atts:
                delay = min(
                    step_def.retry_delay_seconds * (2 ** (attempt - 1)),
                    300.0,
                )
                attempt += 1
                await self._set_job_status(
                    run_id, job_id, JobStatus.retrying,
                    error=error_msg,
                    retry_after=_now_plus(delay),
                )
                await self._audit.log(
                    run_id=run_id, job_id=job_id,
                    event_type=EventType.job_retrying,
                    data={"step": step_def.step_id, "attempt": attempt,
                          "delay_seconds": delay, "error": error_msg},
                )
                log_.info("workflow.step_retry", step=step_def.step_id,
                          attempt=attempt, delay=delay)
                await asyncio.sleep(delay)
                continue  # loop back to dispatch
            else:
                # Retries exhausted
                await self._set_job_status(
                    run_id, job_id, JobStatus.failed,
                    error=error_msg, completed_at=_now(),
                )
                await self._audit.log(
                    run_id=run_id, job_id=job_id,
                    event_type=EventType.job_failed,
                    data={"step": step_def.step_id, "attempts": attempt, "error": error_msg},
                )

                if step_def.fail_policy == FailPolicy.fail_run:
                    raise WorkflowAbortError(step_def.step_id, error_msg)
                elif step_def.fail_policy == FailPolicy.skip:
                    await self._set_job_status(run_id, job_id, JobStatus.skipped)
                    await self._audit.log(
                        run_id=run_id, job_id=job_id,
                        event_type=EventType.job_skipped,
                        data={"reason": "fail_policy=skip after exhausted retries"},
                    )
                    return {}
                else:  # continue_
                    return {}

    # ── Dispatch ──────────────────────────────────────────────────────────────

    async def _dispatch(
        self,
        *,
        job_id:          str,
        task_name:       str,
        queue:           str,
        payload:         dict,
        timeout_seconds: float,
    ) -> dict:
        """Send a Celery task and await the result (non-blocking via executor)."""
        from worker.celery_app import app as celery_app

        async_result = celery_app.send_task(task_name, kwargs=payload, queue=queue)
        await self._set_celery_task_id(job_id, async_result.id)

        loop = asyncio.get_running_loop()
        try:
            result = await asyncio.wait_for(
                loop.run_in_executor(None, lambda: async_result.get(timeout=timeout_seconds)),
                timeout=timeout_seconds + 5,
            )
        except (asyncio.TimeoutError, Exception) as exc:
            if "timeout" in str(exc).lower() or isinstance(exc, asyncio.TimeoutError):
                raise JobTimeoutError(job_id, timeout_seconds) from exc
            raise

        return result or {}

    # ── Dependency resolution ─────────────────────────────────────────────────

    async def _deps_satisfied(self, run_id: str, step_def: StepDef) -> bool:
        if not step_def.depends_on:
            return True
        for dep_id in step_def.depends_on:
            dep_job = await self._load_job(run_id, dep_id)
            if dep_job is None:
                return False
            if JobStatus(dep_job["status"]) not in DEPS_OK_STATES:
                return False
        return True

    async def _handle_deps_failed(
        self, run_id: str, job: dict, step_def: StepDef
    ) -> str:
        """Handle step whose deps failed. Returns 'abort', 'skip', or 'continue'."""
        job_id = str(job["id"])
        reason = "upstream_dependency_failed"

        if step_def.fail_policy == FailPolicy.fail_run:
            await self._set_job_status(run_id, job_id, JobStatus.failed, error=reason)
            await self._audit.log(
                run_id=run_id, job_id=job_id, event_type=EventType.job_failed,
                data={"reason": reason, "depends_on": list(step_def.depends_on)},
            )
            return "abort"

        elif step_def.fail_policy == FailPolicy.skip:
            await self._set_job_status(run_id, job_id, JobStatus.skipped)
            await self._audit.log(
                run_id=run_id, job_id=job_id, event_type=EventType.job_skipped,
                data={"reason": reason},
            )
            return "skip"

        else:  # continue_
            await self._set_job_status(run_id, job_id, JobStatus.failed, error=reason)
            await self._audit.log(
                run_id=run_id, job_id=job_id, event_type=EventType.job_failed,
                data={"reason": reason},
            )
            return "continue"

    # ── Signal check (pause / cancel) ─────────────────────────────────────────

    async def _check_signals(self, run_id: str) -> None:
        """Check DB for pause / cancel signals between steps."""
        row = await self._db.execute(
            text("SELECT status FROM workflow_runs WHERE id=:id"),
            {"id": run_id},
        )
        status_val = row.scalar_one_or_none()
        if status_val is None:
            return
        status = RunStatus(status_val)
        if status == RunStatus.paused:
            raise WorkflowPausedError(f"Run {run_id} was paused")
        if status == RunStatus.cancelled:
            raise WorkflowCancelledError(f"Run {run_id} was cancelled")

    # ── DB helpers ────────────────────────────────────────────────────────────

    async def _load_run(self, run_id: str) -> dict | None:
        row = (await self._db.execute(
            text("""
                SELECT id, pipeline_name, pipeline_version, status,
                       context, channel_id, owner_id
                FROM workflow_runs
                WHERE id = :id
            """),
            {"id": run_id},
        )).mappings().one_or_none()
        return dict(row) if row else None

    async def _load_job(self, run_id: str, step_id: str) -> dict | None:
        row = (await self._db.execute(
            text("""
                SELECT id, step_id, step_type, status, attempt,
                       max_attempts, output, error, celery_task_id,
                       attempt_history
                FROM workflow_jobs
                WHERE run_id=:run_id AND step_id=:step_id
            """),
            {"run_id": run_id, "step_id": step_id},
        )).mappings().one_or_none()
        return dict(row) if row else None

    async def _load_all_jobs(self, run_id: str) -> list[dict]:
        rows = (await self._db.execute(
            text("SELECT id, step_id, status, output FROM workflow_jobs WHERE run_id=:id"),
            {"id": run_id},
        )).mappings().all()
        return [dict(r) for r in rows]

    async def _ensure_jobs_exist(self, run_id: str, pipeline: PipelineDef) -> None:
        """Create WorkflowJob rows for steps that don't have one yet."""
        existing = {r["step_id"] for r in await self._load_all_jobs(run_id)}
        for step in pipeline.steps:
            if step.step_id not in existing:
                await self._db.execute(
                    text("""
                        INSERT INTO workflow_jobs
                            (id, run_id, step_id, step_type, status, attempt,
                             max_attempts, attempt_history)
                        VALUES
                            (:id, :run_id, :step_id, :step_type, 'pending', 1,
                             :max_attempts, '[]'::jsonb)
                        ON CONFLICT (run_id, step_id) DO NOTHING
                    """),
                    {
                        "id":          str(uuid4()),
                        "run_id":      run_id,
                        "step_id":     step.step_id,
                        "step_type":   step.step_type,
                        "max_attempts": step.max_retries + 1,
                    },
                )
        await self._db.flush()

    async def _reset_orphaned_jobs(self, run_id: str) -> None:
        """Reset scheduled/running jobs left over from a crashed worker execution."""
        rows = (await self._db.execute(
            text("""
                SELECT id, step_id, status FROM workflow_jobs
                WHERE run_id=:run_id AND status IN ('scheduled', 'running')
            """),
            {"run_id": run_id},
        )).mappings().all()

        for row in rows:
            await self._db.execute(
                text("""
                    UPDATE workflow_jobs
                    SET status='pending', updated_at=NOW()
                    WHERE id=:id
                """),
                {"id": str(row["id"])},
            )
            await self._audit.log(
                run_id=run_id, job_id=str(row["id"]),
                event_type=EventType.engine_restart,
                data={"step": row["step_id"], "previous_status": row["status"]},
            )

        if rows:
            await self._db.flush()

    async def _set_run_status(
        self,
        run_id: str,
        status: RunStatus,
        *,
        error:        str | None       = None,
        started_at:   datetime | None  = None,
        completed_at: datetime | None  = None,
    ) -> None:
        parts = ["status=:status", "updated_at=NOW()"]
        params: dict = {"id": run_id, "status": status.value}

        if error is not None:
            parts.append("error=:error"); params["error"] = error
        if started_at is not None:
            parts.append("started_at=:started_at"); params["started_at"] = started_at
        if completed_at is not None:
            parts.append("completed_at=:completed_at"); params["completed_at"] = completed_at

        await self._db.execute(
            text(f"UPDATE workflow_runs SET {', '.join(parts)} WHERE id=:id"),
            params,
        )
        await self._db.flush()

    async def _set_job_status(
        self,
        run_id:         str,
        job_id:         str,
        status:         JobStatus,
        *,
        attempt:        int | None          = None,
        error:          str | None          = None,
        output:         dict | None         = None,
        celery_task_id: str | None          = None,
        scheduled_at:   datetime | None     = None,
        started_at:     datetime | None     = None,
        completed_at:   datetime | None     = None,
        retry_after:    datetime | None     = None,
        duration_ms:    int | None          = None,
    ) -> None:
        parts = ["status=:status", "updated_at=NOW()"]
        params: dict = {"id": job_id, "status": status.value}

        if attempt is not None:
            parts.append("attempt=:attempt"); params["attempt"] = attempt
        if error is not None:
            parts.append("error=:error"); params["error"] = error[:4000]
        if output is not None:
            parts.append("output=:output::jsonb"); params["output"] = json.dumps(output)
        if celery_task_id is not None:
            parts.append("celery_task_id=:ctid"); params["ctid"] = celery_task_id
        if scheduled_at is not None:
            parts.append("scheduled_at=:scheduled_at"); params["scheduled_at"] = scheduled_at
        if started_at is not None:
            parts.append("started_at=:started_at"); params["started_at"] = started_at
        if completed_at is not None:
            parts.append("completed_at=:completed_at"); params["completed_at"] = completed_at
        if retry_after is not None:
            parts.append("retry_after=:retry_after"); params["retry_after"] = retry_after
        if duration_ms is not None:
            parts.append("duration_ms=:duration_ms"); params["duration_ms"] = duration_ms

        await self._db.execute(
            text(f"UPDATE workflow_jobs SET {', '.join(parts)} WHERE id=:id"),
            params,
        )
        await self._db.flush()

    async def _set_celery_task_id(self, job_id: str, celery_task_id: str) -> None:
        await self._db.execute(
            text("UPDATE workflow_jobs SET celery_task_id=:ctid WHERE id=:id"),
            {"ctid": celery_task_id, "id": job_id},
        )
        await self._db.flush()

    async def _persist_context(self, run_id: str, ctx: WorkflowContext) -> None:
        await self._db.execute(
            text("UPDATE workflow_runs SET context=:ctx::jsonb WHERE id=:id"),
            {"ctx": json.dumps(ctx.snapshot()), "id": run_id},
        )
        await self._db.flush()

    async def _append_attempt_history(
        self,
        job_id:     str,
        *,
        attempt:    int,
        error:      str,
        started_at: datetime,
    ) -> None:
        entry = json.dumps({
            "attempt":    attempt,
            "error":      error[:500],
            "started_at": started_at.isoformat(),
            "failed_at":  _now().isoformat(),
        })
        await self._db.execute(
            text("""
                UPDATE workflow_jobs
                SET attempt_history = attempt_history || :entry::jsonb,
                    updated_at = NOW()
                WHERE id=:id
            """),
            {"entry": f"[{entry}]", "id": job_id},
        )
        await self._db.flush()

    async def _cancel_pending_jobs(self, run_id: str) -> None:
        await self._db.execute(
            text("""
                UPDATE workflow_jobs
                SET status='cancelled', updated_at=NOW()
                WHERE run_id=:run_id AND status IN ('pending', 'scheduled', 'retrying')
            """),
            {"run_id": run_id},
        )
        await self._db.flush()


# ── Time helpers ──────────────────────────────────────────────────────────────

def _now() -> datetime:
    return datetime.now(timezone.utc)


def _now_plus(seconds: float) -> datetime:
    from datetime import timedelta
    return datetime.now(timezone.utc) + timedelta(seconds=seconds)


_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


def _monotonic_start(dt: datetime) -> float:
    """Approximate monotonic start time from a wall-clock datetime."""
    return time.monotonic() - (datetime.now(timezone.utc) - dt).total_seconds()
