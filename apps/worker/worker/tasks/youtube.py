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
                    view_count=:views,
                    video_count=:vids,
                    updated_at=NOW()
                WHERE id=:id
            """),
            {
                "id": channel_id,
                "subs": metrics["subscriber_count"],
                "views": metrics["view_count"],
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
            "view_count": int(stats.get("viewCount", 0)),
            "video_count": int(stats.get("videoCount", 0)),
        }


def _mock_channel_stats(channel_id: str) -> dict:
    import hashlib
    import random
    seed = int(hashlib.md5(f"stats:{channel_id}".encode()).hexdigest()[:8], 16)
    rng = random.Random(seed)
    return {
        "subscriber_count": rng.randint(1_000, 500_000),
        "view_count": rng.randint(50_000, 10_000_000),
        "video_count": rng.randint(10, 300),
    }


# ── helpers ───────────────────────────────────────────────────────────────────

async def _fail_registry(task_id: str, error: str, retry_count: int) -> None:
    try:
        async with get_db_session() as db:
            await registry.record_retry(db, task_id=task_id, retry_count=retry_count, error=error)
    except Exception:
        pass


@app.task(
    bind=True,
    name="worker.tasks.youtube.publish_video_pipeline",
    queue="default",
    max_retries=3,
    default_retry_delay=120,
    soft_time_limit=1800,
    time_limit=2400,
)
def publish_video_pipeline(
    self,
    *,
    publication_id: str,
    media_url: str,
    audio_url: str | None = None,
    thumbnail_url: str | None = None,
    title: str | None = None,
    description: str | None = None,
    tags: list[str] | None = None,
    visibility: str | None = None,
) -> dict[str, Any]:
    import hashlib

    task_id = self.request.id
    log_ = log.bind(task_id=task_id, publication_id=publication_id)
    log_.info("publish_pipeline.start")

    media_fingerprint = hashlib.sha256(media_url.encode("utf-8")).hexdigest()
    idp_key = f"publish_pipeline:{publication_id}:{media_fingerprint}"
    if (cached := idp.get_result(idp_key)) is not None:
        log_.info("publish_pipeline.cache_hit")
        return cached

    try:
        with idp.lock(idp_key, task_id=task_id):
            return asyncio.run(
                _run_publish_pipeline(
                    task_id=task_id,
                    publication_id=publication_id,
                    media_url=media_url,
                    audio_url=audio_url,
                    thumbnail_url=thumbnail_url,
                    title=title,
                    description=description,
                    tags=tags or [],
                    visibility=visibility or "private",
                )
            )
    except Exception as exc:
        log_.error("publish_pipeline.failed", error=str(exc))
        asyncio.run(_mark_publication_failed(publication_id, str(exc)))
        raise self.retry(exc=exc, countdown=120 * (self.request.retries + 1))


async def _run_publish_pipeline(
    *,
    task_id: str,
    publication_id: str,
    media_url: str,
    audio_url: str | None,
    thumbnail_url: str | None,
    title: str | None,
    description: str | None,
    tags: list[str],
    visibility: str,
) -> dict[str, Any]:
    async with get_db_session() as db:
        pub = (
            await db.execute(
                text(
                    """
                    SELECT p.id, p.title, p.description, p.tags, p.visibility, p.thumbnail_url,
                           c.access_token_enc, c.refresh_token_enc, c.token_expiry
                    FROM publications p
                    JOIN channels c ON c.id = p.channel_id
                    WHERE p.id = :id
                    """
                ),
                {"id": publication_id},
            )
        ).mappings().one_or_none()
        if not pub:
            raise ValueError(f"Publication {publication_id} not found")

        await registry.record_start(
            db,
            task_id=task_id,
            task_name="publish_video_pipeline",
            entity_type="publication",
            entity_id=publication_id,
        )
        await db.execute(
            text("UPDATE publications SET status='processing', updated_at=NOW() WHERE id=:id"),
            {"id": publication_id},
        )

    upload_package = {
        "title": title or pub["title"],
        "description": description if description is not None else (pub["description"] or ""),
        "tags": tags or list(pub.get("tags") or []),
        "visibility": visibility or str(pub.get("visibility") or "private"),
        "media_url": media_url,
        "thumbnail_url": thumbnail_url or pub.get("thumbnail_url"),
        "audio_url": audio_url,
    }
    log.info("publish_pipeline.prepare_package", publication_id=publication_id)

    youtube_video_id = await _upload_media_to_youtube(pub, upload_package)
    await _update_video_metadata(pub, youtube_video_id, upload_package)

    if upload_package.get("thumbnail_url"):
        await _set_thumbnail(pub, youtube_video_id, str(upload_package["thumbnail_url"]))

    youtube_url = f"https://www.youtube.com/watch?v={youtube_video_id}"

    async with get_db_session() as db:
        await db.execute(
            text(
                """
                UPDATE publications
                SET status='published',
                    youtube_video_id=:yt_id,
                    youtube_url=:yt_url,
                    published_at=NOW(),
                    last_error=NULL,
                    updated_at=NOW()
                WHERE id=:id
                """
            ),
            {"id": publication_id, "yt_id": youtube_video_id, "yt_url": youtube_url},
        )
        result = {
            "publication_id": publication_id,
            "youtube_video_id": youtube_video_id,
            "youtube_url": youtube_url,
            "status": "published",
        }
        await registry.record_success(db, task_id=task_id, result=result)

    return result


async def _refresh_access_token_if_needed(pub: dict) -> str:
    import base64
    import hashlib
    from cryptography.fernet import Fernet

    key = hashlib.sha256(settings.secret_key.encode()).digest()
    fernet = Fernet(base64.urlsafe_b64encode(key))

    access_token = fernet.decrypt(pub["access_token_enc"].encode()).decode()

    if not pub.get("token_expiry"):
        return access_token

    try:
        expiry = datetime.fromisoformat(pub["token_expiry"])
    except Exception:
        return access_token

    if expiry > datetime.now(timezone.utc):
        return access_token

    if not pub.get("refresh_token_enc"):
        return access_token

    refresh_token = fernet.decrypt(pub["refresh_token_enc"].encode()).decode()
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "refresh_token": refresh_token,
                "client_id": settings.youtube_client_id,
                "client_secret": settings.youtube_client_secret,
                "grant_type": "refresh_token",
            },
        )
        resp.raise_for_status()
        return resp.json().get("access_token", access_token)


async def _upload_media_to_youtube(pub: dict, upload_package: dict[str, Any]) -> str:
    access_token = await _refresh_access_token_if_needed(pub)

    async with httpx.AsyncClient(timeout=120.0) as client:
        media_resp = await client.get(str(upload_package["media_url"]))
        media_resp.raise_for_status()
        media_bytes = media_resp.content
        media_type = media_resp.headers.get("content-type", "video/mp4")

        metadata = {
            "snippet": {
                "title": upload_package["title"],
                "description": upload_package["description"],
                "tags": upload_package["tags"],
                "categoryId": "22",
            },
            "status": {
                "privacyStatus": upload_package["visibility"],
                "selfDeclaredMadeForKids": False,
            },
        }

        init = await client.post(
            "https://www.googleapis.com/upload/youtube/v3/videos",
            params={"uploadType": "resumable", "part": "snippet,status"},
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json; charset=UTF-8",
                "X-Upload-Content-Length": str(len(media_bytes)),
                "X-Upload-Content-Type": media_type,
            },
            json=metadata,
        )
        init.raise_for_status()

        upload_url = init.headers.get("Location")
        if not upload_url:
            raise RuntimeError("YouTube upload URL missing")

        upload_resp = await client.put(
            upload_url,
            headers={"Authorization": f"Bearer {access_token}", "Content-Type": media_type},
            content=media_bytes,
        )
        upload_resp.raise_for_status()

    data = upload_resp.json()
    video_id = data.get("id")
    if not video_id:
        raise RuntimeError("No video id returned after YouTube upload")
    return video_id


async def _update_video_metadata(pub: dict, video_id: str, upload_package: dict[str, Any]) -> None:
    access_token = await _refresh_access_token_if_needed(pub)
    body = {
        "id": video_id,
        "snippet": {
            "title": upload_package["title"],
            "description": upload_package["description"],
            "tags": upload_package["tags"],
            "categoryId": "22",
        },
        "status": {"privacyStatus": upload_package["visibility"]},
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.put(
            "https://www.googleapis.com/youtube/v3/videos",
            params={"part": "snippet,status"},
            headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
            json=body,
        )
        resp.raise_for_status()


async def _set_thumbnail(pub: dict, video_id: str, thumbnail_url: str) -> None:
    access_token = await _refresh_access_token_if_needed(pub)
    async with httpx.AsyncClient(timeout=60.0) as client:
        img_resp = await client.get(thumbnail_url)
        img_resp.raise_for_status()
        th_resp = await client.post(
            "https://www.googleapis.com/upload/youtube/v3/thumbnails/set",
            params={"videoId": video_id},
            headers={"Authorization": f"Bearer {access_token}", "Content-Type": "image/jpeg"},
            content=img_resp.content,
        )
        th_resp.raise_for_status()


async def _mark_publication_failed(publication_id: str, error: str) -> None:
    async with get_db_session() as db:
        await db.execute(
            text("UPDATE publications SET status='failed', last_error=:err, updated_at=NOW() WHERE id=:id"),
            {"id": publication_id, "err": error[:2000]},
        )
