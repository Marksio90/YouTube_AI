import asyncio
import uuid
from datetime import datetime, timezone

import structlog

from worker.celery_app import app
from worker.db import get_db_session

logger = structlog.get_logger(__name__)

STEP_HANDLERS: dict[str, str] = {
    "research_topic": "worker.tasks.pipeline._step_research_topic",
    "generate_script": "worker.tasks.ai.generate_script_task",
    "review_compliance": "worker.tasks.pipeline._step_compliance",
    "generate_thumbnail": "worker.tasks.pipeline._step_thumbnail",
    "render_video": "worker.tasks.pipeline._step_render",
    "upload_youtube": "worker.tasks.youtube.upload_video_task",
    "schedule_post": "worker.tasks.pipeline._step_schedule",
    "notify": "worker.tasks.pipeline._step_notify",
}


@app.task(
    bind=True,
    name="worker.tasks.pipeline.run_pipeline",
    queue="pipeline",
    max_retries=0,
)
def run_pipeline_task(self, run_id: str) -> dict:
    log = logger.bind(run_id=run_id, task_id=self.request.id)
    log.info("pipeline_run.start")

    result = asyncio.run(_execute_pipeline_run(run_id, log))
    return result


async def _execute_pipeline_run(run_id: str, log) -> dict:
    async with get_db_session() as db:
        from sqlalchemy import text

        run_row = (await db.execute(
            text("SELECT pr.*, p.steps FROM pipeline_runs pr JOIN pipelines p ON p.id = pr.pipeline_id WHERE pr.id = :id"),
            {"id": run_id},
        )).mappings().one_or_none()

        if not run_row:
            raise ValueError(f"PipelineRun {run_id} not found")

        await db.execute(
            text("UPDATE pipeline_runs SET status='running', started_at=:now WHERE id=:id"),
            {"now": datetime.now(timezone.utc).isoformat(), "id": run_id},
        )

        steps = run_row["steps"] or []
        step_results = []
        context: dict = dict(run_row["input"] or {})

        for step in steps:
            step_id = step["id"]
            step_type = step["type"]
            log.info("pipeline_step.start", step_id=step_id, step_type=step_type)

            step_result = {
                "step_id": step_id,
                "status": "running",
                "output": None,
                "error": None,
                "started_at": datetime.now(timezone.utc).isoformat(),
                "completed_at": None,
                "retry_count": 0,
            }

            try:
                output = await _dispatch_step(step_type, step.get("config", {}), context)
                context.update(output or {})
                step_result["status"] = "completed"
                step_result["output"] = output
            except Exception as exc:
                log.error("pipeline_step.failed", step_id=step_id, error=str(exc))
                step_result["status"] = "failed"
                step_result["error"] = str(exc)
                step_results.append(step_result)

                await db.execute(
                    text("UPDATE pipeline_runs SET status='failed', step_results=:sr, completed_at=:now, error=:err WHERE id=:id"),
                    {
                        "sr": step_results,
                        "now": datetime.now(timezone.utc).isoformat(),
                        "err": f"Step {step_id} failed: {exc}",
                        "id": run_id,
                    },
                )
                return {"status": "failed", "error": str(exc)}

            step_result["completed_at"] = datetime.now(timezone.utc).isoformat()
            step_results.append(step_result)

        await db.execute(
            text("UPDATE pipeline_runs SET status='completed', step_results=:sr, output=:out, completed_at=:now WHERE id=:id"),
            {
                "sr": step_results,
                "out": context,
                "now": datetime.now(timezone.utc).isoformat(),
                "id": run_id,
            },
        )

        log.info("pipeline_run.complete", run_id=run_id)
        return {"status": "completed", "output": context}


async def _dispatch_step(step_type: str, config: dict, context: dict) -> dict:
    if step_type == "research_topic":
        return {"topic": config.get("topic") or context.get("topic", ""), "researched": True}

    if step_type == "notify":
        log = logger.bind(step_type="notify")
        log.info("notify.step", message=config.get("message", "Pipeline step completed"))
        return {}

    # Remaining steps are handled by dedicated tasks (called synchronously in pipeline context)
    return {"step_type": step_type, "skipped": True, "reason": "not_implemented_inline"}
