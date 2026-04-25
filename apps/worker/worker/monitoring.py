from __future__ import annotations

import threading
from typing import Any

from celery import signals
from celery.app.base import Celery
from prometheus_client import Counter, Gauge, start_http_server
from redis import Redis

from worker.config import settings

WORKER_JOB_TOTAL = Counter(
    "worker_jobs_total",
    "Total number of executed worker jobs",
    ["task_name", "status"],
)

WORKER_UP = Gauge(
    "worker_up",
    "Worker process status (1=up)",
)

QUEUE_SIZE = Gauge(
    "celery_queue_size",
    "Number of pending messages in a Celery queue",
    ["queue"],
)

CELERY_WORKERS_ONLINE = Gauge(
    "celery_workers_online",
    "Number of online Celery workers visible from inspect.ping()",
)

_MONITOR_THREAD_STARTED = False
_CELERY_APP: Celery | None = None


def _redis_client() -> Redis:
    return Redis.from_url(settings.redis_url, decode_responses=True)


def _collect_queue_metrics() -> None:
    client = _redis_client()
    queue_names = ["high", "ai", "media", "analytics", "default"]
    for name in queue_names:
        try:
            size = client.llen(name)
            QUEUE_SIZE.labels(queue=name).set(size)
        except Exception:
            QUEUE_SIZE.labels(queue=name).set(0)


def _collect_worker_online_metric() -> None:
    if _CELERY_APP is None:
        CELERY_WORKERS_ONLINE.set(0)
        return

    try:
        inspector = _CELERY_APP.control.inspect(timeout=1.0)
        ping = inspector.ping() or {}
        CELERY_WORKERS_ONLINE.set(float(len(ping)))
    except Exception:
        CELERY_WORKERS_ONLINE.set(0)


def _metrics_loop() -> None:
    while True:
        _collect_queue_metrics()
        _collect_worker_online_metric()
        threading.Event().wait(15)


def start_metrics_server(celery_app: Celery) -> None:
    global _MONITOR_THREAD_STARTED
    global _CELERY_APP

    _CELERY_APP = celery_app

    if _MONITOR_THREAD_STARTED:
        return

    start_http_server(9108)
    monitor_thread = threading.Thread(target=_metrics_loop, name="worker-metrics", daemon=True)
    monitor_thread.start()
    WORKER_UP.set(1)
    _MONITOR_THREAD_STARTED = True


@signals.worker_ready.connect
def _on_worker_ready(**_kwargs: Any) -> None:
    WORKER_UP.set(1)


@signals.task_prerun.connect
def _on_task_prerun(task: Any = None, **_kwargs: Any) -> None:
    if task is None:
        return
    WORKER_JOB_TOTAL.labels(task_name=task.name, status="started").inc()


@signals.task_success.connect
def _on_task_success(sender: Any = None, **_kwargs: Any) -> None:
    if sender is None:
        return
    WORKER_JOB_TOTAL.labels(task_name=sender.name, status="success").inc()


@signals.task_failure.connect
def _on_task_failure(sender: Any = None, **_kwargs: Any) -> None:
    if sender is None:
        return
    WORKER_JOB_TOTAL.labels(task_name=sender.name, status="failure").inc()
