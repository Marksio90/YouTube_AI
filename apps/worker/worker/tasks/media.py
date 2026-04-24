"""
Media tasks — audio and thumbnail generation (mock implementations).

Task names:
  worker.tasks.media.generate_audio      (per script)
  worker.tasks.media.generate_thumbnail  (per publication)
"""

import asyncio
import hashlib
import uuid
from typing import Any

import structlog
from sqlalchemy import text

from worker.celery_app import app
from worker.config import settings
from worker.db import get_db_session
from worker.idempotency import guard as idp
from worker import registry

log = structlog.get_logger(__name__)


# ── generate_audio ────────────────────────────────────────────────────────────

@app.task(
    bind=True,
    name="worker.tasks.media.generate_audio",
    queue="media",
    max_retries=2,
    default_retry_delay=30,
    soft_time_limit=300,
    time_limit=400,
)
def generate_audio(self, *, script_id: str, voice_id: str = "alloy") -> dict[str, Any]:
    task_id = self.request.id
    log_ = log.bind(task_id=task_id, script_id=script_id, voice_id=voice_id)
    log_.info("generate_audio.start")

    idp_key = f"audio:{script_id}:{voice_id}"
    if (cached := idp.get_result(idp_key)) is not None:
        log_.info("generate_audio.cache_hit")
        return cached

    try:
        with idp.lock(idp_key, task_id=task_id):
            return asyncio.run(_run_generate_audio(self, task_id, script_id, voice_id, idp_key))
    except Exception as exc:
        log_.error("generate_audio.failed", error=str(exc))
        asyncio.run(_fail_registry(task_id, str(exc), self.request.retries))
        raise self.retry(exc=exc, countdown=30 * (self.request.retries + 1))


async def _run_generate_audio(task, task_id, script_id, voice_id, idp_key) -> dict:
    async with get_db_session() as db:
        script = (
            await db.execute(
                text("SELECT id, body, word_count FROM scripts WHERE id=:id"),
                {"id": script_id},
            )
        ).mappings().one_or_none()
        if not script:
            raise ValueError(f"Script {script_id} not found")

        await registry.record_start(
            db, task_id=task_id, task_name="generate_audio",
            entity_type="script", entity_id=script_id,
            input_data={"voice_id": voice_id},
        )

    task.update_state(state="PROGRESS", meta={"step": "synthesizing", "progress": 30})

    if settings.app_env == "production":
        audio_url, duration_seconds = await _real_tts(script["body"], voice_id, script_id)
    else:
        audio_url, duration_seconds = _mock_audio(script_id, script.get("word_count") or 500)

    task.update_state(state="PROGRESS", meta={"step": "persisting", "progress": 80})

    async with get_db_session() as db:
        await db.execute(
            text("""
                UPDATE scripts
                SET audio_url=:url, audio_duration_seconds=:dur, updated_at=NOW()
                WHERE id=:id
            """),
            {"id": script_id, "url": audio_url, "dur": duration_seconds},
        )
        result = {"script_id": script_id, "audio_url": audio_url, "duration_seconds": duration_seconds}
        await registry.record_success(db, task_id=task_id, result=result)

    idp.set_result(idp_key, result, ttl=86400)
    log.info("generate_audio.complete", script_id=script_id, duration_seconds=duration_seconds)
    return result


async def _real_tts(body: str, voice_id: str, script_id: str) -> tuple[str, float]:
    """OpenAI TTS API call — production path."""
    import httpx
    import boto3

    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(
            "https://api.openai.com/v1/audio/speech",
            headers={"Authorization": f"Bearer {settings.openai_api_key}"},
            json={
                "model": "tts-1-hd",
                "input": body[:4096],
                "voice": voice_id,
                "response_format": "mp3",
            },
        )
        resp.raise_for_status()
        audio_bytes = resp.content

    key = f"audio/{script_id}/{uuid.uuid4()}.mp3"
    s3 = boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url or None,
        aws_access_key_id=settings.s3_access_key_id,
        aws_secret_access_key=settings.s3_secret_access_key,
        region_name=settings.s3_region,
    )
    s3.put_object(Bucket=settings.s3_bucket_media, Key=key, Body=audio_bytes, ContentType="audio/mpeg")
    url = f"https://{settings.s3_bucket_media}.s3.{settings.s3_region}.amazonaws.com/{key}"

    words = len(body.split())
    duration = (words / 150) * 60
    return url, round(duration, 1)


def _mock_audio(script_id: str, word_count: int) -> tuple[str, float]:
    """Returns a deterministic mock audio URL and realistic duration."""
    seed_hex = hashlib.md5(f"audio:{script_id}".encode()).hexdigest()[:8]
    duration = round((word_count / 150) * 60 * (1 + int(seed_hex, 16) % 20 / 100), 1)
    url = f"{settings.mock_media_base_url}/audio/{script_id}/voice_en.mp3"
    return url, duration


# ── generate_thumbnail ────────────────────────────────────────────────────────

@app.task(
    bind=True,
    name="worker.tasks.media.generate_thumbnail",
    queue="media",
    max_retries=2,
    default_retry_delay=30,
    soft_time_limit=180,
    time_limit=240,
)
def generate_thumbnail(
    self,
    *,
    publication_id: str,
    style: str = "bold_text",
) -> dict[str, Any]:
    task_id = self.request.id
    log_ = log.bind(task_id=task_id, publication_id=publication_id, style=style)
    log_.info("generate_thumbnail.start")

    idp_key = f"thumbnail:{publication_id}:{style}"
    if (cached := idp.get_result(idp_key)) is not None:
        log_.info("generate_thumbnail.cache_hit")
        return cached

    try:
        with idp.lock(idp_key, task_id=task_id):
            return asyncio.run(_run_generate_thumbnail(self, task_id, publication_id, style, idp_key))
    except Exception as exc:
        log_.error("generate_thumbnail.failed", error=str(exc))
        asyncio.run(_fail_registry(task_id, str(exc), self.request.retries))
        raise self.retry(exc=exc, countdown=30 * (self.request.retries + 1))


async def _run_generate_thumbnail(task, task_id, publication_id, style, idp_key) -> dict:
    async with get_db_session() as db:
        pub = (
            await db.execute(
                text("""
                    SELECT p.id, p.title, p.description, c.name as channel_name, c.niche
                    FROM publications p JOIN channels c ON c.id=p.channel_id
                    WHERE p.id=:id
                """),
                {"id": publication_id},
            )
        ).mappings().one_or_none()
        if not pub:
            raise ValueError(f"Publication {publication_id} not found")

        await registry.record_start(
            db, task_id=task_id, task_name="generate_thumbnail",
            entity_type="publication", entity_id=publication_id,
            input_data={"style": style},
        )

    task.update_state(state="PROGRESS", meta={"step": "generating", "progress": 40})

    if settings.app_env == "production":
        thumbnail_url = await _real_thumbnail(pub, style, publication_id)
    else:
        thumbnail_url = _mock_thumbnail(publication_id)

    task.update_state(state="PROGRESS", meta={"step": "persisting", "progress": 85})

    async with get_db_session() as db:
        await db.execute(
            text("UPDATE publications SET thumbnail_url=:url, updated_at=NOW() WHERE id=:id"),
            {"id": publication_id, "url": thumbnail_url},
        )
        result = {"publication_id": publication_id, "thumbnail_url": thumbnail_url}
        await registry.record_success(db, task_id=task_id, result=result)

    idp.set_result(idp_key, result, ttl=86400)
    log.info("generate_thumbnail.complete", publication_id=publication_id)
    return result


async def _real_thumbnail(pub: dict, style: str, publication_id: str) -> str:
    """DALL-E 3 image generation — production path."""
    import httpx
    import boto3

    prompt = (
        f"YouTube thumbnail for a video titled '{pub['title']}'. "
        f"Channel niche: {pub['niche']}. Style: {style}. "
        "Bold text overlay, high contrast, eye-catching, professional, 16:9 aspect ratio. "
        "No faces, no people."
    )

    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            "https://api.openai.com/v1/images/generations",
            headers={"Authorization": f"Bearer {settings.openai_api_key}"},
            json={
                "model": "dall-e-3",
                "prompt": prompt[:1000],
                "n": 1,
                "size": "1792x1024",
                "quality": "standard",
            },
        )
        resp.raise_for_status()
        image_url = resp.json()["data"][0]["url"]

        img_resp = await client.get(image_url)
        img_resp.raise_for_status()
        image_bytes = img_resp.content

    key = f"thumbnails/{publication_id}/{uuid.uuid4()}.png"
    s3 = boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url or None,
        aws_access_key_id=settings.s3_access_key_id,
        aws_secret_access_key=settings.s3_secret_access_key,
        region_name=settings.s3_region,
    )
    s3.put_object(Bucket=settings.s3_bucket_media, Key=key, Body=image_bytes, ContentType="image/png")
    return f"https://{settings.s3_bucket_media}.s3.{settings.s3_region}.amazonaws.com/{key}"


def _mock_thumbnail(publication_id: str) -> str:
    """Returns a deterministic mock thumbnail URL."""
    return f"{settings.mock_media_base_url}/thumbnails/{publication_id}/thumb.jpg"


# ── helpers ───────────────────────────────────────────────────────────────────

async def _fail_registry(task_id: str, error: str, retry_count: int) -> None:
    try:
        async with get_db_session() as db:
            await registry.record_retry(db, task_id=task_id, retry_count=retry_count, error=error)
    except Exception:
        pass
