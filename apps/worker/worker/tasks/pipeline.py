"""
Pipeline orchestration task — drives multi-step content production workflows.

Task names:
  worker.tasks.pipeline.run_pipeline  (per pipeline_run, on-demand)

A pipeline run dispatches downstream tasks (ai, media, youtube) and tracks
overall status. Steps are executed sequentially; failure marks run as failed.
"""

import asyncio
from datetime import datetime, timezone
from typing import Any

import structlog
from sqlalchemy import text

from worker.celery_app import app
from worker.db import get_db_session
from worker.idempotency import guard as idp
from worker import registry

log = structlog.get_logger(__name__)

_STEP_TO_TASK = {
    "generate_brief":     ("worker.tasks.ai.generate_brief",     "ai"),
    "generate_script":    ("worker.tasks.ai.generate_script",    "ai"),
    "analyze_seo":        ("worker.tasks.ai.analyze_seo",        "ai"),
    "check_compliance":   ("worker.tasks.ai.check_compliance",   "high"),
    "discover_topics":    ("worker.tasks.topics.discover_topics", "ai"),
    "generate_audio":     ("worker.tasks.media.generate_audio",  "media"),
    "render_video":       ("worker.tasks.media.render_video",    "media"),
    "generate_thumbnail": ("worker.tasks.media.generate_thumbnail", "media"),
    "upload_video":       ("worker.tasks.youtube.publish_video_pipeline",  "default"),
}


@app.task(
    bind=True,
    name="worker.tasks.pipeline.run_pipeline",
    queue="default",
    max_retries=0,
    soft_time_limit=1800,
    time_limit=2400,
)
def run_pipeline(self, *, run_id: str) -> dict[str, Any]:
    task_id = self.request.id
    log_ = log.bind(task_id=task_id, run_id=run_id)
    log_.info("run_pipeline.start")

    idp_key = f"pipeline:{run_id}"
    if (cached := idp.get_result(idp_key)) is not None:
        log_.info("run_pipeline.cache_hit")
        return cached

    try:
        with idp.lock(idp_key, task_id=task_id):
            return asyncio.run(_run_pipeline(self, task_id, run_id, idp_key))
    except Exception as exc:
        log_.error("run_pipeline.failed", error=str(exc))
        return {"status": "failed", "error": str(exc)}


async def _run_pipeline(task, task_id, run_id, idp_key) -> dict:
    async with get_db_session() as db:
        run = (
            await db.execute(
                text("""
                    SELECT pr.id, pr.pipeline_id, pr.input, pr.channel_id,
                           p.steps
                    FROM pipeline_runs pr
                    JOIN pipelines p ON p.id=pr.pipeline_id
                    WHERE pr.id=:id
                """),
                {"id": run_id},
            )
        ).mappings().one_or_none()
        if not run:
            raise ValueError(f"PipelineRun {run_id} not found")

        await registry.record_start(
            db, task_id=task_id, task_name="run_pipeline",
            entity_type="pipeline_run", entity_id=run_id,
        )

        await db.execute(
            text("UPDATE pipeline_runs SET status='running', started_at=:now WHERE id=:id"),
            {"now": _now_iso(), "id": run_id},
        )

    steps: list[dict] = run["steps"] or []
    context: dict = dict(run["input"] or {})
    step_results: list[dict] = []

    for step in steps:
        step_id = str(step.get("id", ""))
        step_type = str(step.get("type", ""))
        step_config = dict(step.get("config", {}))

        log.info("pipeline_step.start", run_id=run_id, step_id=step_id, step_type=step_type)
        task.update_state(
            state="PROGRESS",
            meta={"step": step_type, "step_id": step_id, "total_steps": len(steps)},
        )

        step_result: dict = {
            "step_id": step_id,
            "step_type": step_type,
            "status": "running",
            "output": None,
            "error": None,
            "started_at": _now_iso(),
            "completed_at": None,
        }

        try:
            output = await _execute_step(step_type, step_config, context, run_id)
            context.update(output or {})
            step_result["status"] = "completed"
            step_result["output"] = output
        except Exception as exc:
            log.error("pipeline_step.failed", run_id=run_id, step_id=step_id, error=str(exc))
            step_result["status"] = "failed"
            step_result["error"] = str(exc)
            step_results.append(step_result)

            async with get_db_session() as db:
                await db.execute(
                    text("""
                        UPDATE pipeline_runs
                        SET status='failed', step_results=:sr,
                            completed_at=:now, error=:err
                        WHERE id=:id
                    """),
                    {
                        "sr": step_results,
                        "now": _now_iso(),
                        "err": f"Step '{step_type}' ({step_id}) failed: {exc}",
                        "id": run_id,
                    },
                )
                await registry.record_failure(db, task_id=task_id, error=str(exc))

            return {"status": "failed", "run_id": run_id, "failed_step": step_type}

        step_result["completed_at"] = _now_iso()
        step_results.append(step_result)

    async with get_db_session() as db:
        await db.execute(
            text("""
                UPDATE pipeline_runs
                SET status='completed', step_results=:sr, output=:out, completed_at=:now
                WHERE id=:id
            """),
            {"sr": step_results, "out": context, "now": _now_iso(), "id": run_id},
        )
        await registry.record_success(db, task_id=task_id, result={"context": context})

    result = {"status": "completed", "run_id": run_id, "steps_completed": len(steps)}
    idp.set_result(idp_key, result, ttl=86400)
    log.info("run_pipeline.complete", run_id=run_id, steps=len(steps))
    return result


async def _execute_step(step_type: str, config: dict, context: dict, run_id: str) -> dict:
    """Dispatch a step to the appropriate Celery task and wait for the result."""
    if step_type not in _STEP_TO_TASK:
        log.warning("pipeline_step.unknown", step_type=step_type)
        return {"step_type": step_type, "skipped": True}

    task_name, queue = _STEP_TO_TASK[step_type]
    kwargs = _build_kwargs(step_type, config, context)

    from worker.celery_app import app as celery_app
    async_result = celery_app.send_task(task_name, kwargs=kwargs, queue=queue)

    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, lambda: async_result.get(timeout=600))
    return result or {}


def _build_kwargs(step_type: str, config: dict, context: dict) -> dict:
    """Merge step config with pipeline context to build task kwargs."""
    merged = {**context, **config}
    lookup = {
        "generate_brief":     lambda m: {"topic_id": m["topic_id"]},
        "generate_script":    lambda m: {"brief_id": m.get("brief_id"), "topic_id": m.get("topic_id")},
        "analyze_seo":        lambda m: {"script_id": m["script_id"]},
        "check_compliance":   lambda m: {"script_id": m["script_id"]},
        "discover_topics":    lambda m: {"channel_id": m["channel_id"], "count": m.get("count", 10)},
        "generate_audio":     lambda m: {"script_id": m["script_id"], "voice_id": m.get("voice_id", "alloy")},
        "render_video":       lambda m: {
            "video_id": m["video_id"],
            "audio_url": m["audio_url"],
            "scene_plan": m["scene_plan"],
            "assets": m.get("assets", []),
            "engine": m.get("engine", "mock-compositor-v1"),
        },
        "generate_thumbnail": lambda m: {"publication_id": m["publication_id"]},
        "upload_video":       lambda m: {
            "publication_id": m["publication_id"],
            "media_url": m.get("media_url") or m["audio_url"],
            "audio_url": m.get("audio_url"),
            "thumbnail_url": m.get("thumbnail_url"),
            "title": m.get("title") or m.get("optimized_title"),
            "description": m.get("description") or m.get("optimized_description"),
            "tags": m.get("tags", []),
            "visibility": m.get("visibility", "private"),
        },
    }
    builder = lookup.get(step_type)
    return builder(merged) if builder else merged


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
