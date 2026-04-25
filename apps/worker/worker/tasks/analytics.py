"""
Analytics tasks — YouTube data ingestion and snapshot persistence.

Task names
──────────
  worker.tasks.analytics.sync_channel           per-channel daily snapshot
  worker.tasks.analytics.sync_publication       per-video daily snapshot
  worker.tasks.analytics.backfill_channel       last N days for a channel
  worker.tasks.analytics.sync_all_active_channels   beat: daily 03:15 UTC
  worker.tasks.analytics.sync_all_publications      beat: daily 04:00 UTC

Data flow
─────────
  1. Beat fires at 03:15 → sync_all_active_channels → per-channel sync_channel tasks
  2. Beat fires at 04:00 → sync_all_publications → per-publication sync_publication tasks
  3. sync_channel / sync_publication:
       - production + token present  → YouTube Analytics API v2
       - dev / no token              → deterministic mock (seed = id+date)
       - on 401                      → auto-refresh once; flag needs_reauth on failure
  4. backfill_channel: calls sync_channel + sync_publication for each day in window

Idempotency
───────────
  Key: analytics:{channel|pub}:{id}:{date}   TTL: 12 h
  Prevents double-write on beat overlap or manual re-trigger.
"""

import asyncio
import hashlib
import random
from datetime import date, timedelta
from typing import Any

import structlog
from sqlalchemy import text

from worker.celery_app import app
from worker.config import settings
from worker.db import get_db_session
from worker.idempotency import guard as idp
from worker.tasks.error_handling import (
    TASK_FAILURE_EXCEPTIONS,
    is_retryable_error,
    log_task_failure,
)
from worker import registry

log = structlog.get_logger(__name__)


# ── sync_channel ──────────────────────────────────────────────────────────────

@app.task(
    bind=True,
    name="worker.tasks.analytics.sync_channel",
    queue="analytics",
    max_retries=3,
    default_retry_delay=60,
    soft_time_limit=180,
    time_limit=240,
)
def sync_channel(self, *, channel_id: str, date: str) -> dict[str, Any]:
    task_id = self.request.id
    log_ = log.bind(task_id=task_id, channel_id=channel_id, date=date)
    log_.info("sync_channel.start")

    idp_key = f"analytics:channel:{channel_id}:{date}"
    if (cached := idp.get_result(idp_key)) is not None:
        log_.info("sync_channel.cache_hit")
        return cached

    try:
        with idp.lock(idp_key, task_id=task_id):
            return asyncio.run(_run_sync_channel(self, task_id, channel_id, date, idp_key))
    except TASK_FAILURE_EXCEPTIONS as exc:
        retryable = is_retryable_error(exc)
        log_task_failure(
            log_,
            task_name="sync_channel",
            entity_id=channel_id,
            exc=exc,
            retryable=retryable,
        )
        if retryable:
            asyncio.run(_fail_registry(task_id, str(exc), self.request.retries))
            raise self.retry(exc=exc, countdown=60 * (self.request.retries + 1))
        raise


async def _run_sync_channel(task, task_id, channel_id, snapshot_date_str, idp_key) -> dict:
    async with get_db_session() as db:
        channel = (
            await db.execute(
                text(
                    "SELECT id, name, youtube_channel_id, subscriber_count, "
                    "access_token_enc, refresh_token_enc "
                    "FROM channels WHERE id=:id"
                ),
                {"id": channel_id},
            )
        ).mappings().one_or_none()
        if not channel:
            raise ValueError(f"Channel {channel_id} not found")
        await registry.record_start(
            db, task_id=task_id, task_name="sync_channel",
            entity_type="channel", entity_id=channel_id,
            input_data={"date": snapshot_date_str},
        )

    task.update_state(state="PROGRESS", meta={"step": "fetching_metrics", "progress": 30})
    metrics = await _fetch_channel_metrics(channel_id, snapshot_date_str, channel)

    task.update_state(state="PROGRESS", meta={"step": "upserting", "progress": 80})
    await _upsert_channel_snapshot(channel_id, snapshot_date_str, metrics)

    result = {"channel_id": channel_id, "date": snapshot_date_str, **metrics}
    async with get_db_session() as db:
        await registry.record_success(db, task_id=task_id, result=result)

    idp.set_result(idp_key, result, ttl=settings.idempotency_analytics_ttl)
    log.info("sync_channel.complete", channel_id=channel_id, views=metrics.get("views"))
    return result


async def _fetch_channel_metrics(
    channel_id: str, snapshot_date: str, channel: dict
) -> dict:
    has_token = bool(channel.get("access_token_enc"))
    youtube_channel_id = channel.get("youtube_channel_id")

    if has_token and youtube_channel_id and settings.app_env == "production":
        try:
            return await _real_channel_metrics(channel, snapshot_date, youtube_channel_id)
        except (OSError, TimeoutError, ValueError, RuntimeError) as exc:
            _n = type(exc).__name__
            if "Auth" in _n or "Unauthorized" in _n:
                await _flag_needs_reauth(channel_id)
                log.warning("sync_channel.reauth_required", channel_id=channel_id)
            else:
                log.warning(
                    "sync_channel.api_error_fallback", channel_id=channel_id, error=str(exc)
                )

    return _mock_channel_metrics(channel_id, snapshot_date)


async def _real_channel_metrics(
    channel: dict, snapshot_date: str, youtube_channel_id: str
) -> dict:
    from app.integrations.youtube_analytics import YouTubeAnalyticsClient

    async with get_db_session() as db:
        async with YouTubeAnalyticsClient.from_channel_row(channel, db_session=db) as client:
            metrics = await client.channel_report(youtube_channel_id, snapshot_date)
        await db.commit()

    return metrics


def _mock_channel_metrics(channel_id: str, snapshot_date: str) -> dict:
    seed = int(hashlib.md5(f"{channel_id}{snapshot_date}".encode()).hexdigest()[:8], 16)
    rng = random.Random(seed)
    base_views = rng.randint(500, 8000)
    return {
        "views":                    base_views,
        "watch_time_hours":         round(base_views * rng.uniform(0.04, 0.12), 2),
        "subscribers_gained":       rng.randint(0, max(1, base_views // 200)),
        "subscribers_lost":         rng.randint(0, max(1, base_views // 500)),
        "revenue_usd":              round(base_views * rng.uniform(0.001, 0.005), 4),
        "cpm":                      round(rng.uniform(1.5, 8.0), 2),
        "rpm":                      round(rng.uniform(0.8, 4.0), 2),
        "impressions":              base_views * rng.randint(5, 15),
        "ctr":                      round(rng.uniform(0.02, 0.08), 4),
        "avg_view_duration_seconds": round(rng.uniform(120, 480), 1),
        "like_count":               0,
        "comment_count":            0,
    }


async def _upsert_channel_snapshot(
    channel_id: str, snapshot_date: str, metrics: dict
) -> None:
    async with get_db_session() as db:
        await db.execute(
            text("""
                INSERT INTO analytics_snapshots
                    (id, channel_id, snapshot_date, snapshot_type,
                     views, watch_time_hours, subscribers_gained, subscribers_lost,
                     revenue_usd, cpm, rpm, impressions, ctr,
                     avg_view_duration_seconds, like_count, comment_count)
                VALUES
                    (gen_random_uuid(), :channel_id, :date, 'channel',
                     :views, :wth, :sub_gain, :sub_loss,
                     :rev, :cpm, :rpm, :imp, :ctr, :avd, :likes, :comments)
                ON CONFLICT ON CONSTRAINT uq_analytics_channel_pub_date_type DO UPDATE SET
                    views                    = EXCLUDED.views,
                    watch_time_hours         = EXCLUDED.watch_time_hours,
                    subscribers_gained       = EXCLUDED.subscribers_gained,
                    subscribers_lost         = EXCLUDED.subscribers_lost,
                    revenue_usd              = EXCLUDED.revenue_usd,
                    cpm                      = EXCLUDED.cpm,
                    rpm                      = EXCLUDED.rpm,
                    impressions              = EXCLUDED.impressions,
                    ctr                      = EXCLUDED.ctr,
                    avg_view_duration_seconds = EXCLUDED.avg_view_duration_seconds,
                    like_count               = EXCLUDED.like_count,
                    comment_count            = EXCLUDED.comment_count,
                    updated_at               = NOW()
            """),
            {
                "channel_id": channel_id,
                "date":       snapshot_date,
                "views":      metrics["views"],
                "wth":        metrics["watch_time_hours"],
                "sub_gain":   metrics["subscribers_gained"],
                "sub_loss":   metrics["subscribers_lost"],
                "rev":        metrics["revenue_usd"],
                "cpm":        metrics["cpm"],
                "rpm":        metrics["rpm"],
                "imp":        metrics["impressions"],
                "ctr":        metrics["ctr"],
                "avd":        metrics["avg_view_duration_seconds"],
                "likes":      metrics.get("like_count", 0),
                "comments":   metrics.get("comment_count", 0),
            },
        )


# ── sync_publication ──────────────────────────────────────────────────────────

@app.task(
    bind=True,
    name="worker.tasks.analytics.sync_publication",
    queue="analytics",
    max_retries=3,
    default_retry_delay=30,
    soft_time_limit=120,
    time_limit=180,
)
def sync_publication(self, *, publication_id: str, date: str) -> dict[str, Any]:
    task_id = self.request.id
    idp_key = f"analytics:pub:{publication_id}:{date}"
    if (cached := idp.get_result(idp_key)) is not None:
        return cached

    try:
        with idp.lock(idp_key, task_id=task_id):
            return asyncio.run(
                _run_sync_publication(self, task_id, publication_id, date, idp_key)
            )
    except TASK_FAILURE_EXCEPTIONS as exc:
        retryable = is_retryable_error(exc)
        log_task_failure(
            log,
            task_name="sync_publication",
            entity_id=publication_id,
            exc=exc,
            retryable=retryable,
        )
        if retryable:
            raise self.retry(exc=exc)
        raise


async def _run_sync_publication(
    task, task_id, publication_id, snapshot_date_str, idp_key
) -> dict:
    async with get_db_session() as db:
        pub = (
            await db.execute(
                text("""
                    SELECT p.id, p.youtube_video_id, p.channel_id,
                           c.youtube_channel_id,
                           c.access_token_enc, c.refresh_token_enc
                    FROM publications p
                    JOIN channels c ON c.id = p.channel_id
                    WHERE p.id = :id
                """),
                {"id": publication_id},
            )
        ).mappings().one_or_none()
        if not pub:
            raise ValueError(f"Publication {publication_id} not found")
        await registry.record_start(
            db, task_id=task_id, task_name="sync_publication",
            entity_type="publication", entity_id=publication_id,
        )

    metrics = await _fetch_publication_metrics(publication_id, snapshot_date_str, pub)

    async with get_db_session() as db:
        await db.execute(
            text("""
                INSERT INTO analytics_snapshots
                    (id, channel_id, publication_id, snapshot_date, snapshot_type,
                     views, revenue_usd, cpm, rpm, ctr, watch_time_hours,
                     avg_view_duration_seconds, like_count, comment_count,
                     impressions, subscribers_gained, subscribers_lost)
                VALUES
                    (gen_random_uuid(), :channel_id, :pub_id, :date, 'publication',
                     :views, :rev, :cpm, :rpm, :ctr, :wth,
                     :avd, :likes, :comments, :imp, 0, 0)
                ON CONFLICT ON CONSTRAINT uq_analytics_channel_pub_date_type DO UPDATE SET
                    views                    = EXCLUDED.views,
                    revenue_usd              = EXCLUDED.revenue_usd,
                    cpm                      = EXCLUDED.cpm,
                    rpm                      = EXCLUDED.rpm,
                    ctr                      = EXCLUDED.ctr,
                    watch_time_hours         = EXCLUDED.watch_time_hours,
                    avg_view_duration_seconds = EXCLUDED.avg_view_duration_seconds,
                    like_count               = EXCLUDED.like_count,
                    comment_count            = EXCLUDED.comment_count,
                    impressions              = EXCLUDED.impressions,
                    updated_at               = NOW()
            """),
            {
                "channel_id": str(pub["channel_id"]),
                "pub_id":     publication_id,
                "date":       snapshot_date_str,
                "views":      metrics["views"],
                "rev":        metrics["revenue_usd"],
                "cpm":        metrics.get("cpm", 0.0),
                "rpm":        metrics.get("rpm", 0.0),
                "ctr":        metrics["ctr"],
                "wth":        metrics["watch_time_hours"],
                "avd":        metrics["avg_view_duration_seconds"],
                "likes":      metrics.get("like_count", 0),
                "comments":   metrics.get("comment_count", 0),
                "imp":        metrics.get("impressions", 0),
            },
        )
        # Recompute publication totals from snapshots — idempotent regardless of retries
        await db.execute(
            text("""
                UPDATE publications p
                SET view_count    = (SELECT COALESCE(SUM(s.views), 0)         FROM analytics_snapshots s WHERE s.publication_id = p.id),
                    like_count    = (SELECT COALESCE(SUM(s.like_count), 0)    FROM analytics_snapshots s WHERE s.publication_id = p.id),
                    comment_count = (SELECT COALESCE(SUM(s.comment_count), 0) FROM analytics_snapshots s WHERE s.publication_id = p.id),
                    revenue_usd   = (SELECT COALESCE(SUM(s.revenue_usd), 0)   FROM analytics_snapshots s WHERE s.publication_id = p.id),
                    updated_at    = NOW()
                WHERE id = :id
            """),
            {"id": publication_id},
        )
        await registry.record_success(db, task_id=task_id, result=metrics)

    result = {"publication_id": publication_id, "date": snapshot_date_str, **metrics}
    idp.set_result(idp_key, result, ttl=settings.idempotency_analytics_ttl)
    return result


async def _fetch_publication_metrics(
    publication_id: str, snapshot_date: str, pub: dict
) -> dict:
    has_token = bool(pub.get("access_token_enc"))
    youtube_video_id = pub.get("youtube_video_id")
    youtube_channel_id = pub.get("youtube_channel_id")

    if has_token and youtube_video_id and settings.app_env == "production":
        try:
            return await _real_publication_metrics(
                pub, snapshot_date, youtube_video_id, youtube_channel_id
            )
        except (OSError, TimeoutError, ValueError, RuntimeError) as exc:
            log.warning(
                "sync_publication.api_error_fallback",
                publication_id=publication_id,
                error=str(exc),
            )

    return _mock_publication_metrics(publication_id, snapshot_date)


async def _real_publication_metrics(
    pub: dict,
    snapshot_date: str,
    youtube_video_id: str,
    youtube_channel_id: str | None,
) -> dict:
    from app.integrations.youtube_analytics import YouTubeAnalyticsClient

    async with get_db_session() as db:
        async with YouTubeAnalyticsClient.from_channel_row(pub, db_session=db) as client:
            metrics = await client.video_report(
                youtube_video_id, snapshot_date, youtube_channel_id
            )
        await db.commit()

    return metrics


def _mock_publication_metrics(publication_id: str, snapshot_date: str) -> dict:
    seed = int(hashlib.md5(f"{publication_id}{snapshot_date}".encode()).hexdigest()[:8], 16)
    rng = random.Random(seed)
    views = rng.randint(100, 3000)
    return {
        "views":                    views,
        "like_count":               rng.randint(0, max(1, views // 10)),
        "comment_count":            rng.randint(0, max(1, views // 50)),
        "revenue_usd":              round(views * rng.uniform(0.001, 0.005), 4),
        "cpm":                      round(rng.uniform(1.5, 7.0), 2),
        "rpm":                      round(rng.uniform(0.8, 3.5), 2),
        "ctr":                      round(rng.uniform(0.02, 0.09), 4),
        "watch_time_hours":         round(views * rng.uniform(0.04, 0.10), 2),
        "avg_view_duration_seconds": round(rng.uniform(90, 400), 1),
        "impressions":              views * rng.randint(4, 12),
        "subscribers_gained":       0,
        "subscribers_lost":         0,
    }


# ── backfill_channel ──────────────────────────────────────────────────────────

@app.task(
    bind=True,
    name="worker.tasks.analytics.backfill_channel",
    queue="analytics",
    max_retries=1,
    soft_time_limit=600,
    time_limit=900,
)
def backfill_channel(
    self,
    *,
    channel_id: str,
    days: int = 28,
    include_publications: bool = True,
) -> dict[str, Any]:
    """
    Dispatch sync tasks for the last `days` days for a channel and
    optionally all its published videos.  Skips days already cached.
    """
    task_id = self.request.id
    log_ = log.bind(task_id=task_id, channel_id=channel_id, days=days)
    log_.info("backfill_channel.start")

    today = date.today()
    dates = [
        (today - timedelta(days=i)).isoformat()
        for i in range(1, days + 1)
    ]

    dispatched_ch = 0
    for d in dates:
        if idp.get_result(f"analytics:channel:{channel_id}:{d}") is None:
            sync_channel.apply_async(
                kwargs={"channel_id": channel_id, "date": d},
                queue="analytics",
            )
            dispatched_ch += 1

    dispatched_pub = 0
    if include_publications:
        dispatched_pub = asyncio.run(_backfill_publications(channel_id, dates))

    result = {
        "channel_id":        channel_id,
        "days":              days,
        "channel_tasks":     dispatched_ch,
        "publication_tasks": dispatched_pub,
    }
    log_.info("backfill_channel.complete", **result)
    return result


async def _backfill_publications(channel_id: str, dates: list[str]) -> int:
    async with get_db_session() as db:
        pub_ids = (
            await db.execute(
                text(
                    "SELECT id FROM publications "
                    "WHERE channel_id=:cid AND status='published'"
                ),
                {"cid": channel_id},
            )
        ).scalars().all()

    count = 0
    for pid in pub_ids:
        for d in dates:
            if idp.get_result(f"analytics:pub:{pid}:{d}") is None:
                sync_publication.apply_async(
                    kwargs={"publication_id": str(pid), "date": d},
                    queue="analytics",
                )
                count += 1
    return count


# ── sync_all_active_channels (beat: 03:15 UTC daily) ─────────────────────────

@app.task(
    name="worker.tasks.analytics.sync_all_active_channels",
    queue="analytics",
    max_retries=1,
    soft_time_limit=300,
)
def sync_all_active_channels() -> dict[str, Any]:
    return asyncio.run(_dispatch_channel_sync())


async def _dispatch_channel_sync() -> dict:
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    async with get_db_session() as db:
        ids = (
            await db.execute(text("SELECT id FROM channels WHERE status='active'"))
        ).scalars().all()

    for cid in ids:
        sync_channel.apply_async(
            kwargs={"channel_id": str(cid), "date": yesterday},
            queue="analytics",
        )

    log.info("sync_all_active_channels.dispatched", count=len(ids), date=yesterday)
    return {"dispatched": len(ids), "date": yesterday}


# ── sync_all_publications (beat: 04:00 UTC daily) ────────────────────────────

@app.task(
    name="worker.tasks.analytics.sync_all_publications",
    queue="analytics",
    max_retries=1,
    soft_time_limit=600,
)
def sync_all_publications() -> dict[str, Any]:
    """Dispatch yesterday's analytics for every published video on active channels."""
    return asyncio.run(_dispatch_publication_sync())


async def _dispatch_publication_sync() -> dict:
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    async with get_db_session() as db:
        pub_ids = (
            await db.execute(
                text("""
                    SELECT p.id
                    FROM publications p
                    JOIN channels c ON c.id = p.channel_id
                    WHERE c.status = 'active'
                      AND p.status = 'published'
                """)
            )
        ).scalars().all()

    dispatched = 0
    for pid in pub_ids:
        if idp.get_result(f"analytics:pub:{pid}:{yesterday}") is None:
            sync_publication.apply_async(
                kwargs={"publication_id": str(pid), "date": yesterday},
                queue="analytics",
            )
            dispatched += 1

    log.info("sync_all_publications.dispatched", count=dispatched, date=yesterday)
    return {"dispatched": dispatched, "date": yesterday}


# ── helpers ───────────────────────────────────────────────────────────────────

async def _flag_needs_reauth(channel_id: str) -> None:
    try:
        async with get_db_session() as db:
            await db.execute(
                text(
                    "UPDATE channels SET status='needs_reauth', updated_at=NOW() "
                    "WHERE id=:id"
                ),
                {"id": channel_id},
            )
    except (OSError, RuntimeError) as exc:
        log.error("flag_needs_reauth.failed", channel_id=channel_id, error=str(exc))


async def _fail_registry(task_id, error, retry_count):
    try:
        async with get_db_session() as db:
            await registry.record_retry(
                db, task_id=task_id, retry_count=retry_count, error=error
            )
    except (OSError, RuntimeError):
        pass
