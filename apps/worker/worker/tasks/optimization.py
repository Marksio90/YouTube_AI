"""
Optimization tasks — content growth brain.

Task names:
  worker.tasks.optimization.optimize_channel        (per channel, on-demand)
  worker.tasks.optimization.optimize_all_channels   (beat: weekly)
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import date
from typing import Any

import structlog
from sqlalchemy import text

from worker.celery_app import app
from worker.config import settings
from worker.db import get_db_session
from worker.idempotency import guard as idp
from worker import registry

log = structlog.get_logger(__name__)


@app.task(
    bind=True,
    name="worker.tasks.optimization.optimize_channel",
    queue="ai",
    max_retries=2,
    default_retry_delay=60,
    soft_time_limit=480,
    time_limit=600,
)
def optimize_channel(
    self,
    *,
    channel_id: str,
    owner_id: str,
    period_days: int = 28,
    force: bool = False,
) -> dict[str, Any]:
    task_id = self.request.id
    log_ = log.bind(task_id=task_id, channel_id=channel_id, period_days=period_days)
    log_.info("optimize_channel.start")

    idp_key = f"optimization:{channel_id}:{period_days}:{date.today().isoformat()}"
    if not force and (cached := idp.get_result(idp_key)) is not None:
        log_.info("optimize_channel.cache_hit")
        return cached

    try:
        with idp.lock(idp_key, task_id=task_id):
            return asyncio.run(
                _run_optimize(self, task_id, channel_id, owner_id, period_days, idp_key)
            )
    except Exception as exc:
        log_.error("optimize_channel.failed", error=str(exc))
        asyncio.run(_fail_registry(task_id, str(exc), self.request.retries))
        raise self.retry(exc=exc, countdown=60 * (self.request.retries + 1))


async def _run_optimize(
    task, task_id: str, channel_id: str, owner_id: str, period_days: int, idp_key: str
) -> dict:
    from app.services.optimization import OptimizationService

    async with get_db_session() as db:
        await registry.record_start(
            db,
            task_id=task_id,
            task_name="optimize_channel",
            entity_type="channel",
            entity_id=channel_id,
            input_data={"period_days": period_days},
        )

    task.update_state(state="PROGRESS", meta={"step": "gathering_analytics", "progress": 15})

    async with get_db_session() as db:
        svc = OptimizationService(db)
        report = await svc.generate_report(
            uuid.UUID(channel_id),
            owner_id=uuid.UUID(owner_id),
            period_days=period_days,
            task_id=task_id,
        )
        await db.commit()

    task.update_state(state="PROGRESS", meta={"step": "complete", "progress": 100})

    result = {
        "channel_id": channel_id,
        "report_id": str(report.id),
        "growth_trajectory": report.growth_trajectory,
        "growth_score": report.growth_score,
        "period_days": period_days,
        "summary": report.summary,
        "content_recommendation_count": len(report.content_recommendations or []),
        "next_topic_count": len(report.next_topics or []),
    }

    async with get_db_session() as db:
        await registry.record_success(db, task_id=task_id, result=result)

    idp.set_result(idp_key, result, ttl=86400)
    log.info("optimize_channel.complete", channel_id=channel_id, growth_score=report.growth_score)
    return result


# ── beat: weekly optimization for all active channels ─────────────────────────

@app.task(
    name="worker.tasks.optimization.optimize_all_channels",
    queue="ai",
    max_retries=1,
    soft_time_limit=900,
    time_limit=1200,
)
def optimize_all_channels() -> dict[str, Any]:
    log.info("optimize_all_channels.start")
    return asyncio.run(_dispatch_all())


async def _dispatch_all() -> dict:
    async with get_db_session() as db:
        rows = (
            await db.execute(
                text("""
                    SELECT c.id, c.owner_id
                    FROM channels c
                    WHERE c.status='active'
                """)
            )
        ).mappings().all()

    dispatched = []
    for row in rows:
        task = optimize_channel.apply_async(
            kwargs={
                "channel_id": str(row["id"]),
                "owner_id": str(row["owner_id"]),
                "period_days": 28,
            },
            queue="ai",
        )
        dispatched.append(task.id)

    log.info("optimize_all_channels.dispatched", count=len(dispatched))
    return {"dispatched": len(dispatched), "task_ids": dispatched}


# ── helpers ───────────────────────────────────────────────────────────────────

async def _fail_registry(task_id: str, error: str, retry_count: int) -> None:
    try:
        async with get_db_session() as db:
            await registry.record_retry(db, task_id=task_id, retry_count=retry_count, error=error)
    except Exception:
        pass
