"""
Media tasks — audio, video render foundation, and thumbnail generation.

Task names:
  worker.tasks.media.generate_audio      (per script)
  worker.tasks.media.render_video        (per video)
  worker.tasks.media.generate_thumbnail  (per publication)
"""

import asyncio
import json
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


# ── generate_thumbnail ────────────────────────────────────────────────────────

@app.task(
    bind=True,
    name="worker.tasks.media.generate_thumbnail",
    queue="media",
    max_retries=2,
    default_retry_delay=30,
    soft_time_limit=300,
    time_limit=400,
)
def generate_thumbnail(
    self,
    *,
    publication_id: str,
    channel_style: str = "clean_modern",
    count: int = 3,
) -> dict[str, Any]:
    task_id = self.request.id
    log_ = log.bind(task_id=task_id, publication_id=publication_id, count=count)
    log_.info("generate_thumbnail.start")

    idp_key = f"thumbnail:{publication_id}:{channel_style}:{count}"
    if (cached := idp.get_result(idp_key)) is not None:
        log_.info("generate_thumbnail.cache_hit")
        return cached

    try:
        with idp.lock(idp_key, task_id=task_id):
            return asyncio.run(
                _run_generate_thumbnail(self, task_id, publication_id, channel_style, count, idp_key)
            )
    except Exception as exc:
        log_.error("generate_thumbnail.failed", error=str(exc))
        asyncio.run(_fail_registry(task_id, str(exc), self.request.retries))
        raise self.retry(exc=exc, countdown=30 * (self.request.retries + 1))


async def _run_generate_thumbnail(
    task, task_id: str, publication_id: str, channel_style: str, count: int, idp_key: str
) -> dict:
    from worker.agents.thumbnail import ThumbnailAgent, ThumbnailInput

    async with get_db_session() as db:
        pub = (
            await db.execute(
                text("""
                    SELECT p.id, p.title, p.description, c.id as channel_id,
                           c.name as channel_name, c.niche
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
            input_data={"channel_style": channel_style, "count": count},
        )

    task.update_state(state="PROGRESS", meta={"step": "designing_concepts", "progress": 20})

    # Generate concepts via ThumbnailAgent
    agent = ThumbnailAgent(settings=settings)
    inp = ThumbnailInput(
        title=pub["title"] or "",
        topic=pub["description"] or pub["title"] or "",
        niche=pub["niche"] or "general",
        channel_style=channel_style,
        count=min(max(count, 1), 5),
    )
    if settings.app_env == "production":
        agent_output = await agent.execute(inp)
    else:
        agent_output = await agent.mock_execute(inp)

    ab_group_id = str(uuid.uuid4())
    channel_id = str(pub["channel_id"])

    task.update_state(state="PROGRESS", meta={"step": "generating_images", "progress": 40})

    thumbnail_ids: list[str] = []
    top_pick_url: str | None = None

    for idx, concept in enumerate(agent_output.concepts):
        thumb_id = str(uuid.uuid4())

        # Insert record as generating
        async with get_db_session() as db:
            await _upsert_thumbnail(
                db,
                thumb_id=thumb_id,
                publication_id=publication_id,
                channel_id=channel_id,
                ab_group_id=ab_group_id,
                variant_index=idx,
                status="generating",
                image_provider="dalle3" if settings.app_env == "production" else "placeholder",
                concept=concept,
                channel_style=channel_style,
                task_id=task_id,
            )

        progress = 40 + int(50 * (idx + 1) / len(agent_output.concepts))
        task.update_state(state="PROGRESS", meta={"step": f"variant_{idx}", "progress": progress})

        try:
            if settings.app_env == "production":
                image_bytes = await _dalle_image(concept.ai_image_prompt)
            else:
                image_bytes = _placeholder_image(concept.color_scheme.model_dump())

            final_bytes = _apply_text_overlay(
                image_bytes,
                concept.headline_text,
                concept.sub_text,
                concept.color_scheme.model_dump(),
                concept.layout,
            )
            image_url = _upload_thumbnail(final_bytes, publication_id, thumb_id)
            is_top = concept.concept_id == agent_output.top_pick_id

            async with get_db_session() as db:
                await _upsert_thumbnail(
                    db,
                    thumb_id=thumb_id,
                    publication_id=publication_id,
                    channel_id=channel_id,
                    ab_group_id=ab_group_id,
                    variant_index=idx,
                    status="ready",
                    image_provider="dalle3" if settings.app_env == "production" else "placeholder",
                    concept=concept,
                    channel_style=channel_style,
                    task_id=task_id,
                    image_url=image_url,
                    is_active=is_top,
                )

            if is_top:
                top_pick_url = image_url

        except Exception as exc:
            log.warning("generate_thumbnail.variant_failed", thumb_id=thumb_id, error=str(exc))
            async with get_db_session() as db:
                await db.execute(
                    text(
                        "UPDATE thumbnails SET status='failed', error_message=:err, updated_at=NOW() "
                        "WHERE id=:id"
                    ),
                    {"id": thumb_id, "err": str(exc)[:2000]},
                )

        thumbnail_ids.append(thumb_id)

    # Set publications.thumbnail_url to the top pick
    if top_pick_url:
        async with get_db_session() as db:
            await db.execute(
                text("UPDATE publications SET thumbnail_url=:url, updated_at=NOW() WHERE id=:id"),
                {"id": publication_id, "url": top_pick_url},
            )

    task.update_state(state="PROGRESS", meta={"step": "persisting", "progress": 95})

    result = {
        "publication_id": publication_id,
        "ab_group_id": ab_group_id,
        "thumbnail_ids": thumbnail_ids,
        "top_pick_id": agent_output.top_pick_id,
        "thumbnail_url": top_pick_url,
        "split_test_recommendation": agent_output.split_test_recommendation,
        "design_rationale": agent_output.design_rationale,
        "variant_count": len(thumbnail_ids),
    }

    async with get_db_session() as db:
        await registry.record_success(db, task_id=task_id, result=result)

    idp.set_result(idp_key, result, ttl=86400)
    log.info("generate_thumbnail.complete", publication_id=publication_id, variants=len(thumbnail_ids))
    return result


async def _dalle_image(prompt: str) -> bytes:
    """DALL-E 3 image generation — production path."""
    import httpx

    if not settings.openai_api_key:
        raise RuntimeError("Missing OPENAI_API_KEY for DALL-E")

    async with httpx.AsyncClient(timeout=90.0) as client:
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

        img_resp = await client.get(image_url, timeout=60.0)
        img_resp.raise_for_status()
        return img_resp.content


def _placeholder_image(color_scheme: dict) -> bytes:
    from worker.image_utils import create_placeholder_image
    return create_placeholder_image(color_scheme)


def _apply_text_overlay(
    image_bytes: bytes,
    headline: str,
    sub_text: str | None,
    color_scheme: dict,
    layout: str,
) -> bytes:
    from worker.image_utils import overlay_text
    return overlay_text(image_bytes, headline, sub_text, color_scheme, layout)


def _upload_thumbnail(image_bytes: bytes, publication_id: str, thumb_id: str) -> str:
    import boto3

    key = f"thumbnails/{publication_id}/{thumb_id}.png"
    s3 = boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url or None,
        aws_access_key_id=settings.s3_access_key_id,
        aws_secret_access_key=settings.s3_secret_access_key,
        region_name=settings.s3_region,
    )
    s3.put_object(Bucket=settings.s3_bucket_media, Key=key, Body=image_bytes, ContentType="image/png")
    return f"https://{settings.s3_bucket_media}.s3.{settings.s3_region}.amazonaws.com/{key}"


async def _upsert_thumbnail(
    db,
    *,
    thumb_id: str,
    publication_id: str,
    channel_id: str,
    ab_group_id: str,
    variant_index: int,
    status: str,
    image_provider: str,
    concept,
    channel_style: str,
    task_id: str,
    image_url: str | None = None,
    is_active: bool = False,
) -> None:
    await db.execute(
        text("""
            INSERT INTO thumbnails (
                id, publication_id, channel_id, ab_group_id, variant_index,
                status, image_provider, image_url,
                concept_id, headline_text, sub_text, layout,
                color_scheme, composition, visual_elements, ai_image_prompt,
                predicted_ctr_score, channel_style,
                is_active, task_id, attempts,
                created_at, updated_at
            ) VALUES (
                :id, :publication_id, :channel_id, :ab_group_id, :variant_index,
                :status, :image_provider, :image_url,
                :concept_id, :headline_text, :sub_text, :layout,
                :color_scheme::jsonb, :composition, :visual_elements::jsonb, :ai_image_prompt,
                :predicted_ctr_score, :channel_style,
                :is_active, :task_id, 1,
                NOW(), NOW()
            )
            ON CONFLICT (id) DO UPDATE SET
                status=:status,
                image_url=:image_url,
                is_active=:is_active,
                updated_at=NOW()
        """),
        {
            "id": thumb_id,
            "publication_id": publication_id,
            "channel_id": channel_id,
            "ab_group_id": ab_group_id,
            "variant_index": variant_index,
            "status": status,
            "image_provider": image_provider,
            "image_url": image_url,
            "concept_id": concept.concept_id,
            "headline_text": concept.headline_text,
            "sub_text": concept.sub_text,
            "layout": concept.layout,
            "color_scheme": json.dumps(concept.color_scheme.model_dump()),
            "composition": concept.composition,
            "visual_elements": json.dumps(concept.visual_elements),
            "ai_image_prompt": concept.ai_image_prompt,
            "predicted_ctr_score": concept.predicted_ctr_score,
            "channel_style": channel_style,
            "is_active": is_active,
            "task_id": task_id,
        },
    )


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

async def _fail_registry(task_id: str, error: str, retry_count: int) -> None:
    try:
        async with get_db_session() as db:
            await registry.record_retry(db, task_id=task_id, retry_count=retry_count, error=error)
    except Exception:
        pass
