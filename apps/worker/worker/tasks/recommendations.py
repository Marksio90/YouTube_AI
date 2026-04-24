"""
Recommendation tasks — AI-powered content strategy generation.

Task names:
  worker.tasks.recommendations.generate_recommendations  (per channel, on-demand)
  worker.tasks.recommendations.generate_all_channels     (beat: weekly)
"""

import asyncio
from datetime import date, timedelta
from typing import Any

import structlog
from celery import Task
from sqlalchemy import text

from worker.celery_app import app
from worker.db import get_db_session
from worker.idempotency import guard as idp
from worker import registry
from worker.agents.recommender import RecommenderAgent

log = structlog.get_logger(__name__)


class RecommendationTask(Task):
    abstract = True
    _recommender: RecommenderAgent | None = None

    @property
    def recommender(self) -> RecommenderAgent:
        if self._recommender is None:
            self._recommender = RecommenderAgent()
        return self._recommender


# ── generate_recommendations ──────────────────────────────────────────────────

@app.task(
    bind=True,
    base=RecommendationTask,
    name="worker.tasks.recommendations.generate_recommendations",
    queue="ai",
    max_retries=2,
    default_retry_delay=60,
    soft_time_limit=300,
    time_limit=400,
)
def generate_recommendations(
    self,
    *,
    channel_id: str,
    force: bool = False,
) -> dict[str, Any]:
    task_id = self.request.id
    log_ = log.bind(task_id=task_id, channel_id=channel_id)
    log_.info("generate_recommendations.start")

    idp_key = f"recommendations:{channel_id}:{date.today().isoformat()}"
    if not force and (cached := idp.get_result(idp_key)) is not None:
        log_.info("generate_recommendations.cache_hit")
        return cached

    try:
        with idp.lock(idp_key, task_id=task_id):
            return asyncio.run(_run_recommendations(self, task_id, channel_id, idp_key))
    except Exception as exc:
        log_.error("generate_recommendations.failed", error=str(exc))
        asyncio.run(_fail_registry(task_id, str(exc), self.request.retries))
        raise self.retry(exc=exc, countdown=60 * (self.request.retries + 1))


async def _run_recommendations(task, task_id, channel_id, idp_key) -> dict:
    async with get_db_session() as db:
        channel = (
            await db.execute(
                text("SELECT id, name, niche FROM channels WHERE id=:id"),
                {"id": channel_id},
            )
        ).mappings().one_or_none()
        if not channel:
            raise ValueError(f"Channel {channel_id} not found")

        cutoff_90d = (date.today() - timedelta(days=90)).isoformat()
        top_videos = (
            await db.execute(
                text("""
                    SELECT title, view_count, revenue_usd
                    FROM publications
                    WHERE channel_id=:cid AND status='published'
                      AND published_at >= :cutoff
                    ORDER BY view_count DESC
                    LIMIT 10
                """),
                {"cid": channel_id, "cutoff": cutoff_90d},
            )
        ).mappings().all()

        cutoff_28d = (date.today() - timedelta(days=28)).isoformat()
        analytics_agg = (
            await db.execute(
                text("""
                    SELECT
                        COALESCE(SUM(views), 0)              AS total_views,
                        COALESCE(SUM(revenue_usd), 0)        AS total_revenue_usd,
                        COALESCE(AVG(rpm), 0)                AS avg_rpm,
                        COALESCE(SUM(subscribers_gained), 0) AS subscribers_gained
                    FROM analytics_snapshots
                    WHERE channel_id=:cid
                      AND snapshot_type='channel'
                      AND snapshot_date >= :cutoff
                """),
                {"cid": channel_id, "cutoff": cutoff_28d},
            )
        ).mappings().one()

        existing_topics = (
            await db.execute(
                text("""
                    SELECT title FROM topics
                    WHERE channel_id=:cid AND status NOT IN ('rejected', 'archived')
                    ORDER BY created_at DESC
                    LIMIT 20
                """),
                {"cid": channel_id},
            )
        ).scalars().all()

        await registry.record_start(
            db, task_id=task_id, task_name="generate_recommendations",
            entity_type="channel", entity_id=channel_id,
        )

    task.update_state(state="PROGRESS", meta={"step": "ai_analysis", "progress": 30})

    recommendations = await task.recommender.generate(
        channel_name=channel["name"],
        niche=channel["niche"],
        top_videos=[dict(v) for v in top_videos],
        analytics_summary=dict(analytics_agg),
        existing_topics=list(existing_topics),
    )

    task.update_state(state="PROGRESS", meta={"step": "persisting", "progress": 80})
    await _persist_recommendations(channel_id, recommendations)

    result = {"channel_id": channel_id, "date": date.today().isoformat(), **recommendations}

    async with get_db_session() as db:
        await registry.record_success(db, task_id=task_id, result=result)

    idp.set_result(idp_key, result, ttl=86400)
    log.info(
        "generate_recommendations.complete",
        channel_id=channel_id,
        priority_topics=len(recommendations.get("priority_topics", [])),
    )
    return result


async def _persist_recommendations(channel_id: str, recommendations: dict) -> None:
    priority_topics = recommendations.get("priority_topics", [])
    if not priority_topics:
        return

    async with get_db_session() as db:
        for topic in priority_topics:
            await db.execute(
                text("""
                    INSERT INTO topics
                        (id, channel_id, title, description, keywords, source, status, trend_score)
                    VALUES
                        (gen_random_uuid(), :cid, :title, :desc, '{}', 'ai_suggested', 'new', :score)
                    ON CONFLICT DO NOTHING
                """),
                {
                    "cid": channel_id,
                    "title": str(topic.get("title", ""))[:300],
                    "desc": str(topic.get("rationale", ""))[:2000],
                    "score": min(10.0, topic.get("estimated_views", 0) / 10_000),
                },
            )


# ── generate_all_channels (beat) ─────────────────────────────────────────────

@app.task(
    name="worker.tasks.recommendations.generate_all_channels",
    queue="ai",
    max_retries=1,
    soft_time_limit=600,
    time_limit=800,
)
def generate_all_channels() -> dict[str, Any]:
    log.info("generate_all_channels.start")
    return asyncio.run(_dispatch_all())


async def _dispatch_all() -> dict:
    async with get_db_session() as db:
        ids = (
            await db.execute(text("SELECT id FROM channels WHERE status='active'"))
        ).scalars().all()

    dispatched = []
    for cid in ids:
        task = generate_recommendations.apply_async(
            kwargs={"channel_id": str(cid)},
            queue="ai",
        )
        dispatched.append(task.id)

    log.info("generate_all_channels.dispatched", count=len(dispatched))
    return {"dispatched": len(dispatched), "task_ids": dispatched}


# ── helpers ───────────────────────────────────────────────────────────────────

async def _fail_registry(task_id: str, error: str, retry_count: int) -> None:
    try:
        async with get_db_session() as db:
            await registry.record_retry(db, task_id=task_id, retry_count=retry_count, error=error)
    except Exception:
        pass
