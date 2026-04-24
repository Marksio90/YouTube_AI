"""
Backend-side task dispatchers. These functions enqueue work to the worker
via Celery's broker — they do NOT contain task implementations.
"""

from app.core.celery import celery_client


def enqueue_generate_script(
    *,
    channel_id: str,
    topic: str,
    tone: str = "educational",
    target_duration_seconds: int = 600,
    keywords: list[str] | None = None,
    additional_context: str | None = None,
) -> str:
    result = celery_client.send_task(
        "worker.tasks.ai.generate_script",
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
    result = celery_client.send_task(
        "worker.tasks.ai.generate_brief",
        kwargs={"channel_id": channel_id, "topic_id": topic_id},
        queue="ai",
    )
    return result.id


def enqueue_seo_analysis(*, script_id: str) -> str:
    result = celery_client.send_task(
        "worker.tasks.ai.analyze_seo",
        kwargs={"script_id": script_id},
        queue="ai",
    )
    return result.id


def enqueue_compliance_check(*, script_id: str) -> str:
    result = celery_client.send_task(
        "worker.tasks.ai.check_compliance",
        kwargs={"script_id": script_id},
        queue="ai",
    )
    return result.id
