"""
Topic tasks — discovery and scoring.

Task names:
  worker.tasks.topics.discover_topics          (per channel, on-demand)
  worker.tasks.topics.score_topic              (per topic, on-demand)
  worker.tasks.topics.discover_topics_all_channels  (beat: weekly)
"""

import asyncio
import uuid
from datetime import date
from typing import Any

import structlog
from celery import Task
from sqlalchemy import text

from worker.celery_app import app
from worker.db import get_db_session
from worker.idempotency import guard as idp
from worker import registry
from worker.agents.topic_researcher import TopicResearcherAgent

log = structlog.get_logger(__name__)


class TopicTask(Task):
    abstract = True
    _researcher: TopicResearcherAgent | None = None

    @property
    def researcher(self) -> TopicResearcherAgent:
        if self._researcher is None:
            self._researcher = TopicResearcherAgent()
        return self._researcher


# ── discover_topics ───────────────────────────────────────────────────────────

@app.task(
    bind=True,
    base=TopicTask,
    name="worker.tasks.topics.discover_topics",
    queue="ai",
    max_retries=2,
    default_retry_delay=60,
    soft_time_limit=300,
    time_limit=400,
)
def discover_topics(
    self,
    *,
    channel_id: str,
    count: int = 10,
    force: bool = False,
) -> dict[str, Any]:
    task_id = self.request.id
    log_ = log.bind(task_id=task_id, channel_id=channel_id)
    log_.info("discover_topics.start")

    idp_key = f"discover:{channel_id}:{date.today().isoformat()}"
    if not force and (cached := idp.get_result(idp_key)) is not None:
        log_.info("discover_topics.cache_hit")
        return cached

    try:
        with idp.lock(idp_key, task_id=task_id):
            return asyncio.run(_run_discover(self, task_id, channel_id, count, idp_key))
    except Exception as exc:
        log_.error("discover_topics.failed", error=str(exc))
        asyncio.run(_fail_registry(task_id, str(exc), self.request.retries))
        raise self.retry(exc=exc, countdown=60)


async def _run_discover(task, task_id, channel_id, count, idp_key) -> dict:
    async with get_db_session() as db:
        channel = (
            await db.execute(
                text("SELECT name, niche FROM channels WHERE id=:id"),
                {"id": channel_id},
            )
        ).mappings().one_or_none()
        if not channel:
            raise ValueError(f"Channel {channel_id} not found")

        existing = (
            await db.execute(
                text("SELECT title FROM topics WHERE channel_id=:id ORDER BY created_at DESC LIMIT 50"),
                {"id": channel_id},
            )
        ).scalars().all()

        await registry.record_start(
            db, task_id=task_id, task_name="discover_topics",
            entity_type="channel", entity_id=channel_id,
        )

    task.update_state(state="PROGRESS", meta={"step": "ai_research", "progress": 20})
    topics = await task.researcher.discover(
        niche=channel["niche"],
        channel_name=channel["name"],
        existing_titles=list(existing),
        count=count,
    )

    task.update_state(state="PROGRESS", meta={"step": "persisting", "progress": 80})
    saved_ids = await _persist_topics(channel_id, topics)

    result = {"channel_id": channel_id, "discovered": len(saved_ids), "topic_ids": saved_ids}

    async with get_db_session() as db:
        await registry.record_success(db, task_id=task_id, result=result)

    idp.set_result(idp_key, result, ttl=43200)
    log.info("discover_topics.complete", channel_id=channel_id, count=len(saved_ids))
    return result


async def _persist_topics(channel_id: str, topics: list[dict]) -> list[str]:
    saved = []
    async with get_db_session() as db:
        for t in topics:
            topic_id = str(uuid.uuid4())
            await db.execute(
                text("""
                    INSERT INTO topics
                        (id, channel_id, title, description, keywords, source, status, trend_score)
                    VALUES
                        (:id, :channel_id, :title, :desc, :keywords, 'ai_suggested', 'new', :score)
                    ON CONFLICT DO NOTHING
                """),
                {
                    "id": topic_id,
                    "channel_id": channel_id,
                    "title": t.get("title", "")[:300],
                    "desc": t.get("description", "")[:2000],
                    "keywords": t.get("keywords", []),
                    "score": t.get("estimated_views_30d", 0) / 10_000,
                },
            )
            saved.append(topic_id)
    return saved


# ── score_topic ───────────────────────────────────────────────────────────────

@app.task(
    bind=True,
    base=TopicTask,
    name="worker.tasks.topics.score_topic",
    queue="ai",
    max_retries=2,
    default_retry_delay=30,
    soft_time_limit=120,
    time_limit=180,
)
def score_topic(self, *, topic_id: str, force: bool = False) -> dict[str, Any]:
    task_id = self.request.id
    log_ = log.bind(task_id=task_id, topic_id=topic_id)
    log_.info("score_topic.start")

    idp_key = f"score:{topic_id}"
    if not force and (cached := idp.get_result(idp_key)) is not None:
        return cached

    try:
        with idp.lock(idp_key, task_id=task_id):
            return asyncio.run(_run_score(self, task_id, topic_id, idp_key))
    except Exception as exc:
        log_.error("score_topic.failed", error=str(exc))
        raise self.retry(exc=exc)


async def _run_score(task, task_id, topic_id, idp_key) -> dict:
    async with get_db_session() as db:
        row = (
            await db.execute(
                text("""
                    SELECT t.title, t.description, t.keywords, c.niche
                    FROM topics t JOIN channels c ON c.id=t.channel_id
                    WHERE t.id=:id
                """),
                {"id": topic_id},
            )
        ).mappings().one_or_none()
        if not row:
            raise ValueError(f"Topic {topic_id} not found")

        await registry.record_start(db, task_id=task_id, task_name="score_topic",
                                    entity_type="topic", entity_id=topic_id)

    score_data = await task.researcher.score(
        title=row["title"],
        description=row.get("description") or "",
        keywords=list(row["keywords"] or []),
        niche=row["niche"],
    )

    overall = score_data.get("overall_score", 5.0)
    async with get_db_session() as db:
        await db.execute(
            text("UPDATE topics SET trend_score=:score, updated_at=NOW() WHERE id=:id"),
            {"id": topic_id, "score": overall},
        )
        await registry.record_success(db, task_id=task_id, result=score_data)

    idp.set_result(idp_key, score_data, ttl=43200)
    return score_data


# ── discover_topics_all_channels (beat) ───────────────────────────────────────

@app.task(
    name="worker.tasks.topics.discover_topics_all_channels",
    queue="ai",
    max_retries=1,
    soft_time_limit=1800,
    time_limit=2400,
)
def discover_topics_all_channels() -> dict[str, Any]:
    log.info("discover_topics_all_channels.start")
    return asyncio.run(_run_discover_all())


async def _run_discover_all() -> dict:
    async with get_db_session() as db:
        channel_ids = (
            await db.execute(
                text("SELECT id FROM channels WHERE status='active'")
            )
        ).scalars().all()

    results = []
    for cid in channel_ids:
        task = discover_topics.apply_async(
            kwargs={"channel_id": str(cid), "count": 10},
            queue="ai",
        )
        results.append(task.id)

    log.info("discover_topics_all_channels.dispatched", count=len(results))
    return {"dispatched": len(results), "task_ids": results}


async def _fail_registry(task_id: str, error: str, retry_count: int) -> None:
    try:
        async with get_db_session() as db:
            await registry.record_retry(db, task_id=task_id, retry_count=retry_count, error=error)
    except Exception:
        pass
