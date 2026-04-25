"""
Scoring tasks — compute performance scores and generate recommendations.

Task names:
  worker.tasks.scoring.compute_channel_score    (per channel, on-demand)
  worker.tasks.scoring.compute_all_scores       (beat: daily after analytics sync)
  worker.tasks.scoring.generate_recommendations (per channel, on-demand)
  worker.tasks.scoring.generate_all_recommendations (beat: daily)
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import date, timedelta
from typing import Any

import structlog
from sqlalchemy import text

from worker.celery_app import app
from worker.db import get_db_session
from worker.idempotency import guard as idp
from worker.tasks.error_handling import TASK_FAILURE_EXCEPTIONS, is_retryable_error, log_task_failure

log = structlog.get_logger(__name__)

_DEFAULT_PERIODS = [7, 28, 90]


# ── compute_channel_score ─────────────────────────────────────────────────────

@app.task(
    bind=True,
    name="worker.tasks.scoring.compute_channel_score",
    queue="analytics",
    max_retries=3,
    default_retry_delay=30,
    soft_time_limit=120,
    time_limit=180,
)
def compute_channel_score(
    self,
    *,
    channel_id: str,
    owner_id: str,
    period_days: int = 28,
) -> dict[str, Any]:
    task_id = self.request.id
    log_ = log.bind(task_id=task_id, channel_id=channel_id, period=period_days)
    log_.info("compute_channel_score.start")

    idp_key = f"score:channel:{channel_id}:{period_days}:{date.today()}"
    if (cached := idp.get_result(idp_key)) is not None:
        return cached

    try:
        with idp.lock(idp_key, task_id=task_id):
            result = asyncio.run(
                _run_channel_score(channel_id, owner_id, period_days)
            )
        idp.set_result(idp_key, result, ttl=3600 * 6)
        log_.info("compute_channel_score.done", score=result.get("score"))
        return result
    except TASK_FAILURE_EXCEPTIONS as exc:
        retryable = is_retryable_error(exc)
        log_task_failure(
            log_,
            task_name="compute_channel_score",
            entity_id=channel_id,
            exc=exc,
            retryable=retryable,
        )
        if retryable:
            raise self.retry(exc=exc, countdown=30 * (self.request.retries + 1))
        raise


async def _run_channel_score(channel_id: str, owner_id: str, period_days: int) -> dict:
    from app.services.scoring import ScoringService

    async with get_db_session() as db:
        svc = ScoringService(db)
        score = await svc.score_channel(
            uuid.UUID(channel_id),
            owner_id=uuid.UUID(owner_id),
            period_days=period_days,
        )
        await db.commit()
        return {
            "channel_id": channel_id,
            "period_days": period_days,
            "score": round(score.score, 1),
            "rank_overall": score.rank_overall,
        }


# ── generate_recommendations ──────────────────────────────────────────────────

@app.task(
    bind=True,
    name="worker.tasks.scoring.generate_recommendations",
    queue="analytics",
    max_retries=2,
    default_retry_delay=60,
    soft_time_limit=180,
    time_limit=240,
)
def generate_recommendations(
    self,
    *,
    channel_id: str,
    period_days: int = 28,
    force: bool = False,
) -> dict[str, Any]:
    task_id = self.request.id
    log_ = log.bind(task_id=task_id, channel_id=channel_id)
    log_.info("generate_recommendations.start")

    idp_key = f"recs:channel:{channel_id}:{period_days}:{date.today()}"
    if not force and (cached := idp.get_result(idp_key)) is not None:
        return cached

    try:
        with idp.lock(idp_key, task_id=task_id):
            result = asyncio.run(_run_recommendations(channel_id, period_days))
        idp.set_result(idp_key, result, ttl=3600 * 12)
        log_.info("generate_recommendations.done", count=result.get("count"))
        return result
    except TASK_FAILURE_EXCEPTIONS as exc:
        retryable = is_retryable_error(exc)
        log_task_failure(
            log_,
            task_name="generate_recommendations",
            entity_id=channel_id,
            exc=exc,
            retryable=retryable,
        )
        if retryable:
            raise self.retry(exc=exc, countdown=60 * (self.request.retries + 1))
        raise


async def _run_recommendations(channel_id: str, period_days: int) -> dict:
    from app.services.scoring import ScoringService

    async with get_db_session() as db:
        svc = ScoringService(db)
        recs = await svc.generate_recommendations(
            uuid.UUID(channel_id), period_days=period_days, replace_existing=True
        )
        await db.commit()
        return {
            "channel_id": channel_id,
            "period_days": period_days,
            "count": len(recs),
            "types": [r.rec_type.value for r in recs],
        }


# ── compute_all_scores (beat) ─────────────────────────────────────────────────

@app.task(
    name="worker.tasks.scoring.compute_all_scores",
    queue="analytics",
    max_retries=1,
    soft_time_limit=600,
    time_limit=700,
)
def compute_all_scores() -> dict[str, Any]:
    log.info("compute_all_scores.start")
    return asyncio.run(_dispatch_all_scores())


async def _dispatch_all_scores() -> dict:
    async with get_db_session() as db:
        rows = (
            await db.execute(
                text("SELECT id, owner_id FROM channels WHERE status='active'")
            )
        ).mappings().all()

    dispatched = 0
    for row in rows:
        for period in _DEFAULT_PERIODS:
            compute_channel_score.apply_async(
                kwargs={
                    "channel_id": str(row["id"]),
                    "owner_id":   str(row["owner_id"]),
                    "period_days": period,
                },
                queue="analytics",
            )
            dispatched += 1

    log.info("compute_all_scores.dispatched", count=dispatched)
    return {"dispatched": dispatched, "date": date.today().isoformat()}


# ── generate_all_recommendations (beat) ──────────────────────────────────────

@app.task(
    name="worker.tasks.scoring.generate_all_recommendations",
    queue="analytics",
    max_retries=1,
    soft_time_limit=600,
    time_limit=700,
)
def generate_all_recommendations() -> dict[str, Any]:
    log.info("generate_all_recommendations.start")
    return asyncio.run(_dispatch_all_recs())


async def _dispatch_all_recs() -> dict:
    async with get_db_session() as db:
        ids = (
            await db.execute(text("SELECT id FROM channels WHERE status='active'"))
        ).scalars().all()

    dispatched = 0
    for cid in ids:
        generate_recommendations.apply_async(
            kwargs={"channel_id": str(cid), "period_days": 28},
            queue="analytics",
        )
        dispatched += 1

    log.info("generate_all_recommendations.dispatched", count=dispatched)
    return {"dispatched": dispatched}
