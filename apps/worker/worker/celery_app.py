from celery import Celery
from celery.schedules import crontab
from celery.signals import setup_logging, worker_ready

from worker.config import settings

app = Celery("ai_media_os")

# ── Core config ───────────────────────────────────────────────────────────────
app.conf.update(
    broker_url=settings.celery_broker_url,
    result_backend=settings.celery_result_backend,

    # Serialization
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],

    # Reliability
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    task_track_started=True,
    result_expires=86_400 * 7,  # 7 days

    # Timezone
    timezone="UTC",
    enable_utc=True,

    # Timeouts (overridden per task where needed)
    task_soft_time_limit=600,
    task_time_limit=900,

    # Beat scheduler (RedBeat keeps schedule in Redis — survives restarts)
    beat_scheduler="redbeat.RedBeatScheduler",
    redbeat_redis_url=settings.redis_url,
)

# ── Queue definitions ─────────────────────────────────────────────────────────
# high     — compliance, publishing decisions (latency-sensitive)
# ai       — LLM-heavy: script gen, brief gen, SEO, recommendations, topic scoring
# media    — I/O-heavy: audio gen, thumbnail gen (long-running, isolated workers)
# analytics— data ingestion, metrics sync (bursty, can lag)
# default  — YouTube ops, pipeline orchestration, misc
app.conf.task_queues = {
    "high":      {"exchange": "high",      "routing_key": "high"},
    "ai":        {"exchange": "ai",        "routing_key": "ai"},
    "media":     {"exchange": "media",     "routing_key": "media"},
    "analytics": {"exchange": "analytics", "routing_key": "analytics"},
    "default":   {"exchange": "default",   "routing_key": "default"},
}

app.conf.task_default_queue = "default"
app.conf.task_default_exchange = "default"
app.conf.task_default_routing_key = "default"

# ── Task routing ──────────────────────────────────────────────────────────────
app.conf.task_routes = {
    # Compliance is high-priority (blocks publication)
    "worker.tasks.ai.check_compliance": {"queue": "high"},

    # AI / LLM heavy
    "worker.tasks.ai.*":               {"queue": "ai"},
    "worker.tasks.topics.*":           {"queue": "ai"},
    "worker.tasks.recommendations.*":  {"queue": "ai"},

    # Media generation
    "worker.tasks.media.*":            {"queue": "media"},

    # Analytics ingestion
    "worker.tasks.analytics.*":        {"queue": "analytics"},

    # YouTube + pipeline orchestration
    "worker.tasks.youtube.*":          {"queue": "default"},
    "worker.tasks.pipeline.*":         {"queue": "default"},
}

# ── Beat schedule (periodic tasks) ───────────────────────────────────────────
app.conf.beat_schedule = {
    # Sync YouTube analytics for all active channels at 03:15 UTC daily
    "daily-analytics-sync": {
        "task": "worker.tasks.analytics.sync_all_active_channels",
        "schedule": crontab(hour=3, minute=15),
        "options": {"queue": "analytics"},
    },
    # Discover trending topics weekly (Monday 05:00 UTC)
    "weekly-topic-discovery": {
        "task": "worker.tasks.topics.discover_topics_all_channels",
        "schedule": crontab(hour=5, minute=0, day_of_week=1),
        "options": {"queue": "ai"},
    },
    # Generate content recommendations weekly (Tuesday 06:00 UTC)
    "weekly-recommendations": {
        "task": "worker.tasks.recommendations.generate_all_channels",
        "schedule": crontab(hour=6, minute=0, day_of_week=2),
        "options": {"queue": "ai"},
    },
}


# ── Signals ───────────────────────────────────────────────────────────────────
@setup_logging.connect
def on_setup_logging(**_kwargs) -> None:
    from worker.logging import configure_logging
    configure_logging()


@worker_ready.connect
def on_worker_ready(**_kwargs) -> None:
    """Ensure worker-owned DB tables exist on first start."""
    import asyncio
    from worker.db import get_db_session
    from worker import registry

    async def _init():
        async with get_db_session() as db:
            await registry.ensure_table(db)

    asyncio.run(_init())


# ── Task registration (explicit — no autodiscover magic) ──────────────────────
import worker.tasks.ai             # noqa: E402, F401
import worker.tasks.analytics      # noqa: E402, F401
import worker.tasks.media          # noqa: E402, F401
import worker.tasks.pipeline       # noqa: E402, F401
import worker.tasks.recommendations  # noqa: E402, F401
import worker.tasks.topics         # noqa: E402, F401
import worker.tasks.youtube        # noqa: E402, F401
