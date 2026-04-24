from celery import Celery

from app.core.config import settings

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
