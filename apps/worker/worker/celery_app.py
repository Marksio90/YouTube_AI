from celery import Celery
from celery.signals import setup_logging

from worker.config import settings

app = Celery("ai_media_os")

app.conf.update(
    broker_url=settings.celery_broker_url,
    result_backend=settings.celery_result_backend,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_routes={
        "worker.tasks.ai.*": {"queue": "ai"},
        "worker.tasks.pipeline.*": {"queue": "pipeline"},
        "worker.tasks.youtube.*": {"queue": "default"},
    },
    beat_scheduler="redbeat.RedBeatScheduler",
    redbeat_redis_url=settings.redis_url,
    task_soft_time_limit=600,
    task_time_limit=900,
)

app.autodiscover_tasks(["worker.tasks"])


@setup_logging.connect
def configure_logging(**kwargs):
    import logging
    import structlog

    structlog.configure(
        processors=[
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        logger_factory=structlog.stdlib.LoggerFactory(),
    )
