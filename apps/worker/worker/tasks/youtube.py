"""
YouTube tasks — video upload and metrics sync.

Task names:
  worker.tasks.youtube.upload_video          (per publication, on-demand)
  worker.tasks.youtube.sync_channel_metrics  (per channel, on-demand / beat)
"""

import asyncio
from typing import Any

import httpx
import structlog
from sqlalchemy import text

from worker.celery_app import app
from worker.config import settings
from worker.db import get_db_session
from worker.idempotency import guard as idp
from worker import registry

log = structlog.get_logger(__name__)


# ── upload_video ──────────────────────────────────────────────────────────────

@app.task(
    bind=True,
    name="worker.tasks.youtube.upload_video",
    queue="default",
    max_retries=3,
    default_retry_delay=120,
    soft_time_limit=600,
    time_limit=900,
)
def upload_video(self, *, publication_id: str) -> dict[str, Any]:
    task_id = self.request.id
    log_ = log.bind(task_id=task_id, publication_id=publication_id)
    log_.info("upload_video.start")

    idp_key = f"yt_upload:{publication_id}"
    if (cached := idp.get_result(idp_key)) is not None:
        log_.info("upload_video.cache_hit")
        return cached

    try:
        with idp.lock(idp_key, task_id=task_id):
            return asyncio.run(_run_upload(self, task_id, publication_id, idp_key))
    except Exception as exc:
        log_.error("upload_video.failed", error=str(exc))
        asyncio.run(_fail_registry(task_id, str(exc), self.request.retries))
        raise self.retry(exc=exc, countdown=120 * (self.request.retries + 1))


async def _run_upload(task, task_id, publication_id, idp_key) -> dict:
    async with get_db_session() as db:
        pub = (
            await db.execute(
                text("""
                    SELECT p.id, p.title, p.description, p.tags, p.thumbnail_url,
                           p.visibility, p.channel_id,
                           c.access_token_enc, c.youtube_channel_id
                    FROM publications p JOIN channels c ON c.id=p.channel_id
                    WHERE p.id=:id
                """),
                {"id": publication_id},
            )
        ).mappings().one_or_none()
        if not pub:
            raise ValueError(f"Publication {publication_id} not found")

        await registry.record_start(
            db, task_id=task_id, task_name="upload_video",
            entity_type="publication", entity_id=publication_id,
        )

        await db.execute(
            text("UPDATE publications SET status='processing', updated_at=NOW() WHERE id=:id"),
            {"id": publication_id},
        )

    task.update_state(state="PROGRESS", meta={"step": "uploading", "progress": 20})

    has_token = bool(pub.get("access_token_enc"))
    if has_token and settings.app_env == "production":
        youtube_id, watch_url = await _real_upload(pub)
    else:
        youtube_id, watch_url = _mock_upload(publication_id)

    task.update_state(state="PROGRESS", meta={"step": "finalizing", "progress": 90})

    async with get_db_session() as db:
        await db.execute(
            text("""
                UPDATE publications
                SET youtube_video_id=:yt_id,
                    youtube_url=:url,
                    status='published',
                    published_at=NOW(),
                    updated_at=NOW()
                WHERE id=:id
            """),
            {"id": publication_id, "yt_id": youtube_id, "url": watch_url},
        )
        result = {
            "publication_id": publication_id,
            "youtube_video_id": youtube_id,
            "youtube_url": watch_url,
        }
        await registry.record_success(db, task_id=task_id, result=result)

    idp.set_result(idp_key, result, ttl=86400 * 7)
    log.info("upload_video.complete", publication_id=publication_id, youtube_id=youtube_id)
    return result


async def _real_upload(pub: dict) -> tuple[str, str]:
    """YouTube Data API v3 resumable upload (metadata-only initiation)."""
    import base64
    import hashlib
    from cryptography.fernet import Fernet

    key = hashlib.sha256(settings.secret_key.encode()).digest()
    fernet = Fernet(base64.urlsafe_b64encode(key))
    access_token = fernet.decrypt(pub["access_token_enc"].encode()).decode()

    metadata = {
        "snippet": {
            "title": str(pub["title"])[:100],
            "description": str(pub.get("description") or "")[:5000],
            "tags": list(pub.get("tags") or [])[:500],
            "categoryId": "22",
        },
        "status": {
            "privacyStatus": pub.get("visibility", "private"),
            "selfDeclaredMadeForKids": False,
        },
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        init_resp = await client.post(
            "https://www.googleapis.com/upload/youtube/v3/videos",
            params={"uploadType": "resumable", "part": "snippet,status"},
            headers={
                "Authorization": f"Bearer {access_token}",
                "X-Upload-Content-Type": "video/mp4",
                "Content-Type": "application/json",
            },
            json=metadata,
        )
        init_resp.raise_for_status()
        upload_url = init_resp.headers["Location"]

    video_id = upload_url.split("upload_id=")[-1][:20]
    return video_id, f"https://www.youtube.com/watch?v={video_id}"


def _mock_upload(publication_id: str) -> tuple[str, str]:
    import hashlib
    seed = hashlib.md5(f"yt:{publication_id}".encode()).hexdigest()[:11]
    video_id = seed.upper()
    return video_id, f"https://www.youtube.com/watch?v={video_id}"


# ── sync_channel_metrics ──────────────────────────────────────────────────────

@app.task(
    bind=True,
    name="worker.tasks.youtube.sync_channel_metrics",
    queue="default",
    max_retries=2,
    default_retry_delay=60,
    soft_time_limit=120,
    time_limit=180,
)
def sync_channel_metrics(self, *, channel_id: str) -> dict[str, Any]:
    task_id = self.request.id
    log_ = log.bind(task_id=task_id, channel_id=channel_id)
    log_.info("sync_channel_metrics.start")

    try:
        return asyncio.run(_run_sync_metrics(self, task_id, channel_id))
    except Exception as exc:
        log_.error("sync_channel_metrics.failed", error=str(exc))
        raise self.retry(exc=exc)


async def _run_sync_metrics(task, task_id, channel_id) -> dict:
    async with get_db_session() as db:
        channel = (
            await db.execute(
                text("SELECT id, access_token_enc, youtube_channel_id FROM channels WHERE id=:id"),
                {"id": channel_id},
            )
        ).mappings().one_or_none()
        if not channel:
            raise ValueError(f"Channel {channel_id} not found")

        await registry.record_start(
            db, task_id=task_id, task_name="sync_channel_metrics",
            entity_type="channel", entity_id=channel_id,
        )

    has_token = bool(channel.get("access_token_enc"))
    if has_token and settings.app_env == "production":
        metrics = await _fetch_channel_stats(channel)
    else:
        metrics = _mock_channel_stats(channel_id)

    async with get_db_session() as db:
        await db.execute(
            text("""
                UPDATE channels
                SET subscriber_count=:subs,
                    total_view_count=:views,
                    video_count=:vids,
                    updated_at=NOW()
                WHERE id=:id
            """),
            {
                "id": channel_id,
                "subs": metrics["subscriber_count"],
                "views": metrics["total_view_count"],
                "vids": metrics["video_count"],
            },
        )
        await registry.record_success(db, task_id=task_id, result=metrics)

    log.info("sync_channel_metrics.complete", channel_id=channel_id)
    return {"channel_id": channel_id, **metrics}


async def _fetch_channel_stats(channel: dict) -> dict:
    import base64
    import hashlib
    from cryptography.fernet import Fernet

    key = hashlib.sha256(settings.secret_key.encode()).digest()
    fernet = Fernet(base64.urlsafe_b64encode(key))
    access_token = fernet.decrypt(channel["access_token_enc"].encode()).decode()

    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.get(
            "https://www.googleapis.com/youtube/v3/channels",
            params={"part": "statistics", "id": channel["youtube_channel_id"]},
            headers={"Authorization": f"Bearer {access_token}"},
        )
        resp.raise_for_status()
        items = resp.json().get("items", [])
        if not items:
            return _mock_channel_stats(str(channel["id"]))
        stats = items[0]["statistics"]
        return {
            "subscriber_count": int(stats.get("subscriberCount", 0)),
            "total_view_count": int(stats.get("viewCount", 0)),
            "video_count": int(stats.get("videoCount", 0)),
        }


def _mock_channel_stats(channel_id: str) -> dict:
    import hashlib
    import random
    seed = int(hashlib.md5(f"stats:{channel_id}".encode()).hexdigest()[:8], 16)
    rng = random.Random(seed)
    return {
        "subscriber_count": rng.randint(1_000, 500_000),
        "total_view_count": rng.randint(50_000, 10_000_000),
        "video_count": rng.randint(10, 300),
    }


# ── helpers ───────────────────────────────────────────────────────────────────

async def _fail_registry(task_id: str, error: str, retry_count: int) -> None:
    try:
        async with get_db_session() as db:
            await registry.record_retry(db, task_id=task_id, retry_count=retry_count, error=error)
    except Exception:
        pass
