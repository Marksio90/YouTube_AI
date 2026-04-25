from __future__ import annotations

from typing import Any

from celery import Celery
from celery.result import AsyncResult

from app.core.config import settings
from app.core.request_context import get_correlation_id

# Lightweight Celery client used by the backend to enqueue tasks.
# Task execution happens in apps/worker. No task implementations here.
celery_client = Celery("ai_media_os_backend")
celery_client.conf.update(
    broker_url=settings.celery_broker_url,
    result_backend=settings.celery_result_backend,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
)


def send_task(*, task_name: str, kwargs: dict[str, Any], queue: str) -> AsyncResult:
    correlation_id = get_correlation_id()
    headers = {"correlation_id": correlation_id} if correlation_id else None
    return celery_client.send_task(task_name, kwargs=kwargs, queue=queue, headers=headers)
