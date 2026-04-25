"""
Media tasks — audio, video render foundation, and thumbnail generation.

Task names:
  worker.tasks.media.generate_audio      (per script)
  worker.tasks.media.render_video        (per video)
  worker.tasks.media.generate_thumbnail  (per publication)
"""

import asyncio
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
def generate_audio(
    self,
    *,
    script_id: str,
    provider: str = "openai",
    voice_id: str = "alloy",
    tempo: float = 1.0,
    tone: float = 0.0,
) -> dict[str, Any]:
    task_id = self.request.id
    provider = provider or settings.tts_provider_default
    log_ = log.bind(task_id=task_id, script_id=script_id, provider=provider, voice_id=voice_id)
    log_.info("generate_audio.start")

    idp_key = f"audio:{script_id}:{provider}:{voice_id}:{tempo}:{tone}"
    if (cached := idp.get_result(idp_key)) is not None:
        log_.info("generate_audio.cache_hit")
        return cached

    try:
        if provider not in {"openai", "elevenlabs"}:
            raise ValueError(f"Unsupported TTS provider: {provider}")
        if not 0.5 <= tempo <= 2.0:
            raise ValueError("tempo must be between 0.5 and 2.0")
        if not -12.0 <= tone <= 12.0:
            raise ValueError("tone must be between -12.0 and 12.0")
        with idp.lock(idp_key, task_id=task_id):
            return asyncio.run(
                _run_generate_audio(
                    self,
                    task_id=task_id,
                    script_id=script_id,
                    provider=provider,
                    voice_id=voice_id,
                    tempo=tempo,
                    tone=tone,
                    idp_key=idp_key,
                )
            )
    except ValueError:
        raise
    except Exception as exc:
        log_.error("generate_audio.failed", error=str(exc))
        asyncio.run(_fail_registry(task_id, str(exc), self.request.retries))
        asyncio.run(_mark_audio_job_failure(task_id=task_id, error=str(exc), attempts=self.request.retries + 1))
        raise self.retry(exc=exc, countdown=30 * (self.request.retries + 1))


async def _run_generate_audio(
    task,
    *,
    task_id: str,
    script_id: str,
    provider: str,
    voice_id: str,
    tempo: float,
    tone: float,
    idp_key: str,
) -> dict:
    async with get_db_session() as db:
        script = (
            await db.execute(
                text("SELECT id, channel_id, body FROM scripts WHERE id=:id"),
                {"id": script_id},
            )
        ).mappings().one_or_none()
        if not script:
            raise ValueError(f"Script {script_id} not found")
        if not script.get("body"):
            raise ValueError(f"Script {script_id} has empty body")

        await registry.record_start(
            db, task_id=task_id, task_name="generate_audio",
            entity_type="script", entity_id=script_id,
            input_data={"voice_id": voice_id, "provider": provider, "tempo": tempo, "tone": tone},
        )
        await _upsert_audio_job(
            db=db,
            task_id=task_id,
            script_id=script_id,
            channel_id=str(script["channel_id"]),
            provider=provider,
            voice_id=voice_id,
            tempo=tempo,
            tone=tone,
            status="processing",
            attempts=task.request.retries + 1,
            max_attempts=task.max_retries + 1,
        )

    task.update_state(state="PROGRESS", meta={"step": "synthesizing", "progress": 30})

    if settings.app_env == "production":
        audio_bytes = await _real_tts(
            body=script["body"],
            provider=provider,
            voice_id=voice_id,
            tempo=tempo,
            tone=tone,
        )
        audio_url = _upload_audio_to_storage(audio_bytes, script_id)
    else:
        audio_url = _mock_audio(script_id)

    words = len(str(script["body"]).split()) if script.get("body") else 0
    duration_seconds = _estimate_duration_seconds(words, tempo=tempo)

    task.update_state(state="PROGRESS", meta={"step": "persisting", "progress": 80})

    async with get_db_session() as db:
        await db.execute(
            text("""
                UPDATE scripts
                SET audio_url=:url,
                    audio_duration_seconds=:dur,
                    audio_provider=:provider,
                    audio_voice_id=:voice_id,
                    updated_at=NOW()
                WHERE id=:id
            """),
            {
                "id": script_id,
                "url": audio_url,
                "dur": duration_seconds,
                "provider": provider,
                "voice_id": voice_id,
            },
        )
        await _upsert_audio_job(
            db=db,
            task_id=task_id,
            script_id=script_id,
            channel_id=str(script["channel_id"]),
            provider=provider,
            voice_id=voice_id,
            tempo=tempo,
            tone=tone,
            status="completed",
            attempts=task.request.retries + 1,
            max_attempts=task.max_retries + 1,
            audio_url=audio_url,
            duration_seconds=duration_seconds,
            error_message=None,
        )
        result = {
            "script_id": script_id,
            "audio_url": audio_url,
            "duration_seconds": duration_seconds,
            "provider": provider,
            "voice_id": voice_id,
            "tempo": tempo,
            "tone": tone,
        }
        await registry.record_success(db, task_id=task_id, result=result)

    idp.set_result(idp_key, result, ttl=86400)
    log.info("generate_audio.complete", script_id=script_id, duration_seconds=duration_seconds)
    return result


async def _real_tts(
    *,
    body: str,
    provider: str,
    voice_id: str,
    tempo: float,
    tone: float,
) -> bytes:
    """Production TTS synthesis for OpenAI/ElevenLabs providers."""
    import httpx

    if provider == "openai":
        if not settings.openai_api_key:
            raise RuntimeError("Missing OPENAI_API_KEY for OpenAI TTS")
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                "https://api.openai.com/v1/audio/speech",
                headers={"Authorization": f"Bearer {settings.openai_api_key}"},
                json={
                    "model": "gpt-4o-mini-tts",
                    "input": body[:8000],
                    "voice": voice_id,
                    "response_format": "mp3",
                    "speed": tempo,
                },
            )
            resp.raise_for_status()
            return resp.content

    if provider == "elevenlabs":
        if not settings.elevenlabs_api_key:
            raise RuntimeError("Missing ELEVENLABS_API_KEY for ElevenLabs TTS")
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
                headers={
                    "xi-api-key": settings.elevenlabs_api_key,
                    "Accept": "audio/mpeg",
                    "Content-Type": "application/json",
                },
                json={
                    "text": body[:8000],
                    "model_id": "eleven_multilingual_v2",
                    "voice_settings": {
                        "stability": max(0.0, min(1.0, 0.65 - tone / 24)),
                        "similarity_boost": max(0.0, min(1.0, 0.8 + tone / 24)),
                        "style": 0.2,
                        "use_speaker_boost": True,
                    },
                },
            )
            resp.raise_for_status()
            return resp.content

    raise ValueError(f"Unsupported TTS provider: {provider}")


def _mock_audio(script_id: str) -> str:
    return f"{settings.mock_media_base_url}/audio/{script_id}/voice_en.mp3"


def _estimate_duration_seconds(word_count: int, *, tempo: float) -> float:
    safe_word_count = max(word_count, 1)
    safe_tempo = max(0.5, min(2.0, tempo))
    return round((safe_word_count / (150 * safe_tempo)) * 60, 1)


def _upload_audio_to_storage(audio_bytes: bytes, script_id: str) -> str:
    import boto3

    key = f"audio/{script_id}/{uuid.uuid4()}.mp3"
    s3 = boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url or None,
        aws_access_key_id=settings.s3_access_key_id,
        aws_secret_access_key=settings.s3_secret_access_key,
        region_name=settings.s3_region,
    )
    s3.put_object(Bucket=settings.s3_bucket_media, Key=key, Body=audio_bytes, ContentType="audio/mpeg")
    return f"https://{settings.s3_bucket_media}.s3.{settings.s3_region}.amazonaws.com/{key}"


# ── render_video ───────────────────────────────────────────────────────────────

@app.task(
    bind=True,
    name="worker.tasks.media.render_video",
    queue="media",
    max_retries=3,
    default_retry_delay=45,
    soft_time_limit=900,
    time_limit=1200,
)
def render_video(
    self,
    *,
    video_id: str,
    audio_url: str,
    scene_plan: list[dict],
    assets: list[dict],
    engine: str = "mock-compositor-v1",
) -> dict[str, Any]:
    import hashlib

    task_id = self.request.id
    log_ = log.bind(task_id=task_id, video_id=video_id, engine=engine)
    log_.info("render_video.start")

    payload_fingerprint = hashlib.sha256(
        f"{video_id}|{audio_url}|{scene_plan}|{assets}|{engine}".encode("utf-8")
    ).hexdigest()
    idp_key = f"render_video:{payload_fingerprint}"
    if (cached := idp.get_result(idp_key)) is not None:
        log_.info("render_video.cache_hit")
        return cached

    try:
        with idp.lock(idp_key, task_id=task_id):
            return asyncio.run(
                _run_render_video(
                    task=self,
                    task_id=task_id,
                    video_id=video_id,
                    audio_url=audio_url,
                    scene_plan=scene_plan,
                    assets=assets,
                    engine=engine,
                    idp_key=idp_key,
                )
            )
    except Exception as exc:
        log_.error("render_video.failed", error=str(exc))
        asyncio.run(_fail_registry(task_id, str(exc), self.request.retries))
        asyncio.run(_mark_render_job_failure(task_id=task_id, error=str(exc), attempts=self.request.retries + 1))
        raise self.retry(exc=exc, countdown=45 * (self.request.retries + 1))


async def _run_render_video(
    *,
    task,
    task_id: str,
    video_id: str,
    audio_url: str,
    scene_plan: list[dict],
    assets: list[dict],
    engine: str,
    idp_key: str,
) -> dict[str, Any]:
    from worker.video.renderer import get_renderer
    from worker.video.timeline import build_timeline

    async with get_db_session() as db:
        video = (
            await db.execute(
                text("SELECT id, channel_id, script_id FROM videos WHERE id=:id"),
                {"id": video_id},
            )
        ).mappings().one_or_none()
        if not video:
            raise ValueError(f"Video {video_id} not found")

        await registry.record_start(
            db,
            task_id=task_id,
            task_name="render_video",
            entity_type="video",
            entity_id=video_id,
            input_data={"audio_url": audio_url, "engine": engine},
        )
        await db.execute(
            text("UPDATE videos SET status='rendering', updated_at=NOW() WHERE id=:id"),
            {"id": video_id},
        )
        await _upsert_video_render_job(
            db=db,
            task_id=task_id,
            video_id=video_id,
            channel_id=str(video["channel_id"]),
            script_id=str(video["script_id"]) if video.get("script_id") else None,
            status="planning",
            engine=engine,
            audio_url=audio_url,
            scene_plan=scene_plan,
            assets=assets,
            timeline=None,
            attempts=task.request.retries + 1,
            max_attempts=task.max_retries + 1,
        )

    task.update_state(state="PROGRESS", meta={"step": "timeline_builder", "progress": 20})
    timeline = build_timeline(audio_url=audio_url, scene_plan=scene_plan, assets=assets)

    async with get_db_session() as db:
        await _upsert_video_render_job(
            db=db,
            task_id=task_id,
            video_id=video_id,
            channel_id=str(video["channel_id"]),
            script_id=str(video["script_id"]) if video.get("script_id") else None,
            status="rendering",
            engine=engine,
            audio_url=audio_url,
            scene_plan=scene_plan,
            assets=assets,
            timeline=timeline,
            attempts=task.request.retries + 1,
            max_attempts=task.max_retries + 1,
        )

    task.update_state(state="PROGRESS", meta={"step": "rendering", "progress": 70})
    renderer = get_renderer(engine)
    video_url, duration_seconds = renderer.render(video_id=video_id, audio_url=audio_url, timeline=timeline)

    task.update_state(state="PROGRESS", meta={"step": "persisting", "progress": 90})
    async with get_db_session() as db:
        await db.execute(
            text(
                """
                UPDATE videos
                SET render_url=:render_url,
                    duration_seconds=:duration_seconds,
                    status='review',
                    updated_at=NOW()
                WHERE id=:id
                """
            ),
            {"id": video_id, "render_url": video_url, "duration_seconds": int(round(duration_seconds))},
        )
        await _upsert_video_render_job(
            db=db,
            task_id=task_id,
            video_id=video_id,
            channel_id=str(video["channel_id"]),
            script_id=str(video["script_id"]) if video.get("script_id") else None,
            status="completed",
            engine=engine,
            audio_url=audio_url,
            scene_plan=scene_plan,
            assets=assets,
            timeline=timeline,
            output_video_url=video_url,
            duration_seconds=duration_seconds,
            attempts=task.request.retries + 1,
            max_attempts=task.max_retries + 1,
        )
        result = {
            "video_id": video_id,
            "video_url": video_url,
            "media_url": video_url,
            "duration_seconds": duration_seconds,
            "timeline": timeline,
            "engine": renderer.engine_name,
        }
        await registry.record_success(db, task_id=task_id, result=result)

    idp.set_result(idp_key, result, ttl=86400)
    log.info("render_video.complete", video_id=video_id, video_url=video_url)
    return result


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

async def _upsert_audio_job(
    *,
    db,
    task_id: str,
    script_id: str,
    channel_id: str,
    provider: str,
    voice_id: str,
    tempo: float,
    tone: float,
    status: str,
    attempts: int,
    max_attempts: int,
    audio_url: str | None = None,
    duration_seconds: float | None = None,
    error_message: str | None = None,
) -> None:
    await db.execute(
        text(
            """
            INSERT INTO audio_jobs (
                id, script_id, channel_id, task_id, provider, voice_id, tempo, tone, status,
                attempts, max_attempts, audio_url, duration_seconds, error_message,
                created_at, updated_at
            )
            VALUES (
                :id, :script_id, :channel_id, :task_id, :provider, :voice_id, :tempo, :tone, :status,
                :attempts, :max_attempts, :audio_url, :duration_seconds, :error_message,
                NOW(), NOW()
            )
            ON CONFLICT (task_id) DO UPDATE
            SET status=:status,
                attempts=:attempts,
                max_attempts=:max_attempts,
                audio_url=:audio_url,
                duration_seconds=:duration_seconds,
                error_message=:error_message,
                updated_at=NOW()
            """
        ),
        {
            "id": str(uuid.uuid4()),
            "script_id": script_id,
            "channel_id": channel_id,
            "task_id": task_id,
            "provider": provider,
            "voice_id": voice_id,
            "tempo": tempo,
            "tone": tone,
            "status": status,
            "attempts": attempts,
            "max_attempts": max_attempts,
            "audio_url": audio_url,
            "duration_seconds": duration_seconds,
            "error_message": error_message,
        },
    )


async def _mark_audio_job_failure(*, task_id: str, error: str, attempts: int) -> None:
    try:
        async with get_db_session() as db:
            await db.execute(
                text(
                    """
                    UPDATE audio_jobs
                    SET status='failed',
                        attempts=:attempts,
                        error_message=:error,
                        updated_at=NOW()
                    WHERE task_id=:task_id
                    """
                ),
                {"task_id": task_id, "error": error[:2000], "attempts": attempts},
            )
    except Exception:
        pass


async def _upsert_video_render_job(
    *,
    db,
    task_id: str,
    video_id: str,
    channel_id: str,
    script_id: str | None,
    status: str,
    engine: str,
    audio_url: str,
    scene_plan: list[dict],
    assets: list[dict],
    timeline: list[dict] | None,
    attempts: int,
    max_attempts: int,
    output_video_url: str | None = None,
    duration_seconds: float | None = None,
    error_message: str | None = None,
) -> None:
    await db.execute(
        text(
            """
            INSERT INTO video_render_jobs (
                id, video_id, channel_id, script_id, task_id, status, engine,
                input_audio_url, scene_plan, assets, timeline, output_video_url,
                attempts, max_attempts, duration_seconds, error_message,
                created_at, updated_at
            )
            VALUES (
                :id, :video_id, :channel_id, :script_id, :task_id, :status, :engine,
                :input_audio_url, :scene_plan, :assets, :timeline, :output_video_url,
                :attempts, :max_attempts, :duration_seconds, :error_message,
                NOW(), NOW()
            )
            ON CONFLICT (task_id) DO UPDATE
            SET status=:status,
                timeline=:timeline,
                output_video_url=:output_video_url,
                attempts=:attempts,
                max_attempts=:max_attempts,
                duration_seconds=:duration_seconds,
                error_message=:error_message,
                updated_at=NOW()
            """
        ),
        {
            "id": str(uuid.uuid4()),
            "video_id": video_id,
            "channel_id": channel_id,
            "script_id": script_id,
            "task_id": task_id,
            "status": status,
            "engine": engine,
            "input_audio_url": audio_url,
            "scene_plan": scene_plan,
            "assets": assets,
            "timeline": timeline,
            "output_video_url": output_video_url,
            "attempts": attempts,
            "max_attempts": max_attempts,
            "duration_seconds": duration_seconds,
            "error_message": error_message,
        },
    )


async def _mark_render_job_failure(*, task_id: str, error: str, attempts: int) -> None:
    try:
        async with get_db_session() as db:
            await db.execute(
                text(
                    """
                    UPDATE video_render_jobs
                    SET status='failed',
                        attempts=:attempts,
                        error_message=:error,
                        updated_at=NOW()
                    WHERE task_id=:task_id
                    """
                ),
                {"task_id": task_id, "error": error[:2000], "attempts": attempts},
            )
    except Exception:
        pass

async def _fail_registry(task_id: str, error: str, retry_count: int) -> None:
    try:
        async with get_db_session() as db:
            await registry.record_retry(db, task_id=task_id, retry_count=retry_count, error=error)
    except Exception:
        pass
