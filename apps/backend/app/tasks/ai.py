"""
Backend-side task dispatchers. These functions enqueue work to the worker
via Celery's broker — they do NOT contain task implementations.
"""

from app.core.celery import send_task


def enqueue_generate_script(
    *,
    channel_id: str,
    topic: str,
    tone: str = "educational",
    target_duration_seconds: int = 600,
    keywords: list[str] | None = None,
    additional_context: str | None = None,
) -> str:
    result = send_task(task_name="worker.tasks.ai.generate_script",
        kwargs={
            "channel_id": channel_id,
            "topic": topic,
            "tone": tone,
            "target_duration_seconds": target_duration_seconds,
            "keywords": keywords or [],
            "additional_context": additional_context,
        },
        queue="ai",
    )
    return result.id


def enqueue_generate_brief(*, channel_id: str, topic_id: str) -> str:
    result = send_task(task_name="worker.tasks.ai.generate_brief",
        kwargs={"channel_id": channel_id, "topic_id": topic_id},
        queue="ai",
    )
    return result.id


def enqueue_seo_analysis(*, script_id: str) -> str:
    result = send_task(task_name="worker.tasks.ai.analyze_seo",
        kwargs={"script_id": script_id},
        queue="ai",
    )
    return result.id


def enqueue_compliance_check(*, script_id: str) -> str:
    result = send_task(task_name="worker.tasks.ai.check_compliance",
        kwargs={"script_id": script_id},
        queue="ai",
    )
    return result.id


def enqueue_discover_topics(
    *,
    channel_id: str,
    count: int = 10,
    force: bool = False,
) -> str:
    result = send_task(task_name="worker.tasks.topics.discover_topics",
        kwargs={"channel_id": channel_id, "count": count, "force": force},
        queue="ai",
    )
    return result.id


def enqueue_score_topic(*, topic_id: str, force: bool = False) -> str:
    result = send_task(task_name="worker.tasks.topics.score_topic",
        kwargs={"topic_id": topic_id, "force": force},
        queue="ai",
    )
    return result.id


def enqueue_generate_recommendations(*, channel_id: str, force: bool = False) -> str:
    result = send_task(task_name="worker.tasks.recommendations.generate_recommendations",
        kwargs={"channel_id": channel_id, "force": force},
        queue="ai",
    )
    return result.id


def enqueue_generate_audio(
    *,
    script_id: str,
    provider: str = "openai",
    voice_id: str = "alloy",
    tempo: float = 1.0,
    tone: float = 0.0,
) -> str:
    result = send_task(task_name="worker.tasks.media.generate_audio",
        kwargs={
            "script_id": script_id,
            "provider": provider,
            "voice_id": voice_id,
            "tempo": tempo,
            "tone": tone,
        },
        queue="media",
    )
    return result.id


def enqueue_optimize_channel(
    *,
    channel_id: str,
    owner_id: str,
    period_days: int = 28,
    force: bool = False,
) -> str:
    result = send_task(
        task_name="worker.tasks.optimization.optimize_channel",
        kwargs={
            "channel_id": channel_id,
            "owner_id": owner_id,
            "period_days": period_days,
            "force": force,
        },
        queue="ai",
    )
    return result.id


def enqueue_generate_thumbnails(
    *,
    publication_id: str,
    channel_style: str = "clean_modern",
    count: int = 3,
) -> str:
    result = send_task(
        task_name="worker.tasks.media.generate_thumbnail",
        kwargs={
            "publication_id": publication_id,
            "channel_style": channel_style,
            "count": count,
        },
        queue="media",
    )
    return result.id
