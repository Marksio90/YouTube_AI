"""
Celery entry points for the workflow orchestration engine.

Tasks:
  run_workflow      — execute a new or resumed run
  resume_workflow   — resume a paused run (delegates to run_workflow)
  cancel_workflow   — cancel a running run externally

All of these are thin shells: they load the DB session and hand off to
WorkflowEngine so the execution logic stays testable without Celery.
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from typing import Any

import structlog
from celery.exceptions import SoftTimeLimitExceeded

from worker.celery_app import app
from worker.db import get_db_session

log = structlog.get_logger(__name__)


# ── run_workflow ──────────────────────────────────────────────────────────────

@app.task(
    bind=True,
    name="worker.tasks.workflow.run_workflow",
    queue="default",
    max_retries=0,
    soft_time_limit=14400,   # 4 hours — graceful shutdown signal
    time_limit=14700,        # 4h 5m — hard kill
    acks_late=True,
)
def run_workflow(self, *, run_id: str) -> dict[str, Any]:
    """
    Execute or resume a workflow run.

    Idempotent: safe to call multiple times for the same run_id.
    The engine skips already-completed steps automatically.
    """
    task_id = self.request.id
    log_ = log.bind(task_id=task_id, run_id=run_id)
    log_.info("run_workflow.start")

    try:
        return asyncio.run(_run_workflow_async(run_id, task_id, self))
    except SoftTimeLimitExceeded:
        log_.warning("run_workflow.soft_time_limit")
        asyncio.run(_mark_run_paused(run_id, reason="soft_time_limit"))
        return {"status": "paused", "run_id": run_id, "reason": "soft_time_limit"}
    except Exception as exc:
        log_.error("run_workflow.unhandled_error", error=str(exc))
        asyncio.run(_mark_run_failed(run_id, error=str(exc)))
        return {"status": "failed", "run_id": run_id, "error": str(exc)}


async def _run_workflow_async(
    run_id:  str,
    task_id: str,
    celery_task: Any,
) -> dict:
    from worker.workflow.engine import WorkflowEngine
    from worker.workflow.types import RunStatus

    async with get_db_session() as db:
        engine = WorkflowEngine(db)

        # Progress callback so the Celery task state stays fresh
        def _on_step(step_id: str, step_num: int, total: int) -> None:
            celery_task.update_state(
                state="PROGRESS",
                meta={"step": step_id, "step_num": step_num, "total": total},
            )

        final_status = await engine.execute(run_id)
        await db.commit()

    log.info("run_workflow.finished", run_id=run_id, status=final_status)
    return {
        "status":  final_status.value,
        "run_id":  run_id,
        "task_id": task_id,
    }


async def _mark_run_paused(run_id: str, reason: str) -> None:
    from sqlalchemy import text
    async with get_db_session() as db:
        await db.execute(
            text("""
                UPDATE workflow_runs
                SET status='paused', paused_at=NOW(), updated_at=NOW(),
                    error=:reason
                WHERE id=:id AND status='running'
            """),
            {"id": run_id, "reason": reason},
        )
        await db.commit()


async def _mark_run_failed(run_id: str, error: str) -> None:
    from sqlalchemy import text
    async with get_db_session() as db:
        await db.execute(
            text("""
                UPDATE workflow_runs
                SET status='failed', completed_at=NOW(), updated_at=NOW(),
                    error=:error
                WHERE id=:id AND status NOT IN ('completed', 'cancelled', 'failed')
            """),
            {"id": run_id, "error": error[:2000]},
        )
        await db.commit()


# ── resume_workflow ───────────────────────────────────────────────────────────

@app.task(
    bind=True,
    name="worker.tasks.workflow.resume_workflow",
    queue="default",
    max_retries=0,
    soft_time_limit=14400,
    time_limit=14700,
)
def resume_workflow(self, *, run_id: str) -> dict[str, Any]:
    """Resume a paused workflow. Sets status → running, then delegates to engine."""
    log_ = log.bind(task_id=self.request.id, run_id=run_id)
    log_.info("resume_workflow.start")

    async def _resume() -> dict:
        from sqlalchemy import text
        from worker.workflow.types import EventType
        from worker.workflow.audit import AuditLogger

        async with get_db_session() as db:
            await db.execute(
                text("""
                    UPDATE workflow_runs
                    SET status='running', paused_at=NULL, error=NULL,
                        updated_at=NOW()
                    WHERE id=:id AND status='paused'
                """),
                {"id": run_id},
            )
            audit = AuditLogger(db)
            await audit.log(
                run_id=run_id, event_type=EventType.run_resumed,
                actor="system", data={"triggered_by": "resume_workflow_task"},
            )
            await db.commit()

        return asyncio.run(_run_workflow_async(run_id, self.request.id, self))

    try:
        return asyncio.run(_resume())
    except Exception as exc:
        log_.error("resume_workflow.error", error=str(exc))
        return {"status": "error", "run_id": run_id, "error": str(exc)}


# ── cancel_workflow ───────────────────────────────────────────────────────────

@app.task(
    bind=True,
    name="worker.tasks.workflow.cancel_workflow",
    queue="high",
    max_retries=0,
)
def cancel_workflow(self, *, run_id: str, actor: str = "system") -> dict[str, Any]:
    """
    Signal a running workflow to stop cleanly.

    Sets run.status = cancelled; the engine polls this between steps
    and raises WorkflowCancelledError, which stops execution gracefully.
    """
    log_ = log.bind(run_id=run_id, actor=actor)
    log_.info("cancel_workflow.start")

    async def _cancel() -> dict:
        from sqlalchemy import text
        from worker.workflow.audit import AuditLogger
        from worker.workflow.types import EventType

        async with get_db_session() as db:
            result = await db.execute(
                text("""
                    UPDATE workflow_runs
                    SET status='cancelled', completed_at=NOW(), updated_at=NOW()
                    WHERE id=:id AND status NOT IN ('completed', 'cancelled', 'failed')
                    RETURNING id
                """),
                {"id": run_id},
            )
            cancelled = result.fetchone() is not None
            if cancelled:
                await db.execute(
                    text("""
                        UPDATE workflow_jobs
                        SET status='cancelled', updated_at=NOW()
                        WHERE run_id=:id AND status IN ('pending', 'scheduled', 'retrying')
                    """),
                    {"id": run_id},
                )
                audit = AuditLogger(db)
                await audit.log(
                    run_id=run_id, event_type=EventType.run_cancelled,
                    actor=actor, data={"manual": True},
                )
            await db.commit()

        return {"status": "cancelled" if cancelled else "noop", "run_id": run_id}

    try:
        return asyncio.run(_cancel())
    except Exception as exc:
        log_.error("cancel_workflow.error", error=str(exc))
        return {"status": "error", "run_id": run_id, "error": str(exc)}
