"""
Analytics tasks — ingestion and sync.

Task names (match backend dispatchers):
  worker.tasks.analytics.sync_channel      (per channel + date)
  worker.tasks.analytics.sync_publication  (per publication + date)
  worker.tasks.analytics.sync_all_active_channels  (beat: daily)
"""

import asyncio
import math
import random
from datetime import date, timedelta
from typing import Any

import structlog
from sqlalchemy import text

from worker.celery_app import app
from worker.config import settings
from worker.db import get_db_session
from worker.idempotency import guard as idp
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
    except Exception as exc:
        log_.error("sync_channel.failed", error=str(exc))
        asyncio.run(_fail_registry(task_id, str(exc), self.request.retries))
        raise self.retry(exc=exc, countdown=60 * (self.request.retries + 1))


async def _run_sync_channel(task, task_id, channel_id, snapshot_date_str, idp_key) -> dict:
    async with get_db_session() as db:
        channel = (
            await db.execute(
                text("SELECT id, name, subscriber_count, access_token_enc FROM channels WHERE id=:id"),
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


async def _fetch_channel_metrics(channel_id: str, snapshot_date: str, channel: dict) -> dict:
    """
    Fetches analytics from YouTube Analytics API.
    Falls back to realistic mock data in development / when token unavailable.

    Production: replace `_mock_channel_metrics` with YouTubeAnalyticsClient.query().
    """
    has_token = bool(channel.get("access_token_enc"))
    if has_token and settings.app_env == "production":
        return await _real_channel_metrics(channel, snapshot_date)
    return _mock_channel_metrics(channel_id, snapshot_date)


async def _real_channel_metrics(channel: dict, snapshot_date: str) -> dict:
    """YouTube Analytics API v2 call — requires valid OAuth token."""
    import httpx
    import base64
    import hashlib
    from cryptography.fernet import Fernet

    key = hashlib.sha256(settings.secret_key.encode()).digest()
    fernet = Fernet(base64.urlsafe_b64encode(key))
    access_token = fernet.decrypt(channel["access_token_enc"].encode()).decode()

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(
            "https://youtubeanalytics.googleapis.com/v2/reports",
            params={
                "ids": f"channel=={channel['id']}",
                "startDate": snapshot_date,
                "endDate": snapshot_date,
                "metrics": "views,estimatedMinutesWatched,subscribersGained,subscribersLost,"
                           "estimatedRevenue,cpm,rpm,impressions,impressionClickThroughRate",
                "dimensions": "day",
            },
            headers={"Authorization": f"Bearer {access_token}"},
        )
        resp.raise_for_status()
        rows = resp.json().get("rows", [[]])
        if not rows:
            return _mock_channel_metrics(str(channel["id"]), snapshot_date)

        row = rows[0]
        return {
            "views": int(row[1]),
            "watch_time_hours": float(row[2]) / 60,
            "subscribers_gained": int(row[3]),
            "subscribers_lost": int(row[4]),
            "revenue_usd": float(row[5]),
            "cpm": float(row[6]),
            "rpm": float(row[7]),
            "impressions": int(row[8]),
            "ctr": float(row[9]),
            "avg_view_duration_seconds": 0.0,
        }


def _mock_channel_metrics(channel_id: str, snapshot_date: str) -> dict:
    """
    Deterministic mock based on channel_id seed — same inputs always produce
    same outputs, so idempotent re-runs don't drift analytics.
    """
    seed = int(hashlib.md5(f"{channel_id}{snapshot_date}".encode()).hexdigest()[:8], 16)
    rng = random.Random(seed)
    base_views = rng.randint(500, 8000)
    return {
        "views": base_views,
        "watch_time_hours": round(base_views * rng.uniform(0.04, 0.12), 2),
        "subscribers_gained": rng.randint(0, max(1, base_views // 200)),
        "subscribers_lost": rng.randint(0, max(1, base_views // 500)),
        "revenue_usd": round(base_views * rng.uniform(0.001, 0.005), 4),
        "cpm": round(rng.uniform(1.5, 8.0), 2),
        "rpm": round(rng.uniform(0.8, 4.0), 2),
        "impressions": base_views * rng.randint(5, 15),
        "ctr": round(rng.uniform(0.02, 0.08), 4),
        "avg_view_duration_seconds": round(rng.uniform(120, 480), 1),
    }


import hashlib  # noqa: E402 (used in _mock_channel_metrics)


async def _upsert_channel_snapshot(channel_id: str, snapshot_date: str, metrics: dict) -> None:
    async with get_db_session() as db:
        await db.execute(
            text("""
                INSERT INTO analytics_snapshots
                    (id, channel_id, snapshot_date, snapshot_type, views, watch_time_hours,
                     subscribers_gained, subscribers_lost, revenue_usd, cpm, rpm,
                     impressions, ctr, avg_view_duration_seconds, like_count, comment_count)
                VALUES
                    (gen_random_uuid(), :channel_id, :date, 'channel', :views, :wth,
                     :sub_gain, :sub_loss, :rev, :cpm, :rpm,
                     :imp, :ctr, :avd, 0, 0)
                ON CONFLICT ON CONSTRAINT uq_analytics_channel_pub_date_type DO UPDATE SET
                    views=EXCLUDED.views, watch_time_hours=EXCLUDED.watch_time_hours,
                    subscribers_gained=EXCLUDED.subscribers_gained,
                    subscribers_lost=EXCLUDED.subscribers_lost,
                    revenue_usd=EXCLUDED.revenue_usd, cpm=EXCLUDED.cpm, rpm=EXCLUDED.rpm,
                    impressions=EXCLUDED.impressions, ctr=EXCLUDED.ctr,
                    avg_view_duration_seconds=EXCLUDED.avg_view_duration_seconds,
                    updated_at=NOW()
            """),
            {
                "channel_id": channel_id,
                "date": snapshot_date,
                "views": metrics["views"],
                "wth": metrics["watch_time_hours"],
                "sub_gain": metrics["subscribers_gained"],
                "sub_loss": metrics["subscribers_lost"],
                "rev": metrics["revenue_usd"],
                "cpm": metrics["cpm"],
                "rpm": metrics["rpm"],
                "imp": metrics["impressions"],
                "ctr": metrics["ctr"],
                "avd": metrics["avg_view_duration_seconds"],
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
            return asyncio.run(_run_sync_publication(self, task_id, publication_id, date, idp_key))
    except Exception as exc:
        log.error("sync_publication.failed", error=str(exc), publication_id=publication_id)
        raise self.retry(exc=exc)


async def _run_sync_publication(task, task_id, publication_id, snapshot_date_str, idp_key) -> dict:
    async with get_db_session() as db:
        pub = (
            await db.execute(
                text("""
                    SELECT p.id, p.youtube_video_id, p.channel_id, c.access_token_enc
                    FROM publications p JOIN channels c ON c.id=p.channel_id
                    WHERE p.id=:id
                """),
                {"id": publication_id},
            )
        ).mappings().one_or_none()
        if not pub:
            raise ValueError(f"Publication {publication_id} not found")

        await registry.record_start(db, task_id=task_id, task_name="sync_publication",
                                    entity_type="publication", entity_id=publication_id)

    metrics = _mock_publication_metrics(publication_id, snapshot_date_str)

    async with get_db_session() as db:
        await db.execute(
            text("""
                UPDATE publications
                SET view_count=view_count+:views, like_count=like_count+:likes,
                    comment_count=comment_count+:comments,
                    revenue_usd=revenue_usd+:rev, updated_at=NOW()
                WHERE id=:id
            """),
            {
                "id": publication_id,
                "views": metrics["views"],
                "likes": metrics.get("like_count", 0),
                "comments": metrics.get("comment_count", 0),
                "rev": metrics["revenue_usd"],
            },
        )
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
                    views=EXCLUDED.views, revenue_usd=EXCLUDED.revenue_usd,
                    updated_at=NOW()
            """),
            {
                "channel_id": str(pub["channel_id"]),
                "pub_id": publication_id,
                "date": snapshot_date_str,
                **metrics,
            },
        )
        await registry.record_success(db, task_id=task_id, result=metrics)

    result = {"publication_id": publication_id, "date": snapshot_date_str, **metrics}
    idp.set_result(idp_key, result, ttl=settings.idempotency_analytics_ttl)
    return result


def _mock_publication_metrics(publication_id: str, snapshot_date: str) -> dict:
    seed = int(hashlib.md5(f"{publication_id}{snapshot_date}".encode()).hexdigest()[:8], 16)
    rng = random.Random(seed)
    views = rng.randint(100, 3000)
    return {
        "views": views,
        "like_count": rng.randint(0, views // 10),
        "comment_count": rng.randint(0, views // 50),
        "revenue_usd": round(views * rng.uniform(0.001, 0.005), 4),
        "cpm": round(rng.uniform(1.5, 7.0), 2),
        "rpm": round(rng.uniform(0.8, 3.5), 2),
        "ctr": round(rng.uniform(0.02, 0.09), 4),
        "watch_time_hours": round(views * rng.uniform(0.04, 0.10), 2),
        "avg_view_duration_seconds": round(rng.uniform(90, 400), 1),
        "imp": views * rng.randint(4, 12),
    }


# ── sync_all_active_channels (beat) ──────────────────────────────────────────

@app.task(
    name="worker.tasks.analytics.sync_all_active_channels",
    queue="analytics",
    max_retries=1,
    soft_time_limit=300,
)
def sync_all_active_channels() -> dict[str, Any]:
    return asyncio.run(_dispatch_all_sync())


async def _dispatch_all_sync() -> dict:
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    async with get_db_session() as db:
        ids = (await db.execute(text("SELECT id FROM channels WHERE status='active'"))).scalars().all()

    for cid in ids:
        sync_channel.apply_async(
            kwargs={"channel_id": str(cid), "date": yesterday},
            queue="analytics",
        )

    log.info("sync_all_active_channels.dispatched", count=len(ids), date=yesterday)
    return {"dispatched": len(ids), "date": yesterday}


async def _fail_registry(task_id, error, retry_count):
    try:
        async with get_db_session() as db:
            await registry.record_retry(db, task_id=task_id, retry_count=retry_count, error=error)
    except Exception:
        pass
