import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query, Path

from app.api.v1.deps import CurrentUser, DB
from app.core.exceptions import NotFoundError
from app.schemas.analytics import (
    AnalyticsAggregate,
    AnalyticsSnapshotCreate,
    AnalyticsSnapshotRead,
    ChannelRankingResponse,
    PerformanceScoreRead,
    RecommendationActionRequest,
    RecommendationRead,
    TopicRankingResponse,
)
from app.schemas.common import TaskResponse
from app.services.analytics import AnalyticsService
from app.services.scoring import ScoringService

router = APIRouter(prefix="/analytics", tags=["analytics"])


# ── Snapshots ─────────────────────────────────────────────────────────────────

@router.get("/channels/{channel_id}", response_model=AnalyticsAggregate)
async def channel_analytics(
    channel_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
    days: int = Query(28, ge=1, le=365),
) -> AnalyticsAggregate:
    svc = AnalyticsService(db)
    return await svc.get_channel_aggregate(
        channel_id, owner_id=current_user.id, days=days
    )


@router.get("/publications/{publication_id}", response_model=list[AnalyticsSnapshotRead])
async def publication_analytics(
    publication_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
    date_from: date = Query(...),
    date_to: date = Query(...),
) -> list[AnalyticsSnapshotRead]:
    from app.repositories.publication import PublicationRepository
    pub = await PublicationRepository(db).get_for_user(publication_id, owner_id=current_user.id)
    if not pub:
        raise NotFoundError("Publication not found")
    svc = AnalyticsService(db)
    return await svc.get_publication_snapshots(
        publication_id, date_from=date_from, date_to=date_to
    )


@router.post("/snapshots", response_model=AnalyticsSnapshotRead)
async def upsert_snapshot(
    payload: AnalyticsSnapshotCreate,
    current_user: CurrentUser,
    db: DB,
) -> AnalyticsSnapshotRead:
    svc = AnalyticsService(db)
    return await svc.upsert_snapshot(payload, owner_id=current_user.id)


@router.post("/sync/channels/{channel_id}", response_model=TaskResponse)
async def sync_channel_analytics(
    channel_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
) -> TaskResponse:
    from app.repositories.channel import ChannelRepository
    import datetime as dt

    repo = ChannelRepository(db)
    channel = await repo.get_owned(channel_id, owner_id=current_user.id)
    if not channel:
        raise NotFoundError("Channel not found or access denied")

    from app.tasks.ai import enqueue_sync_channel
    task_id = enqueue_sync_channel(
        channel_id=str(channel_id),
        date=dt.date.today().isoformat(),
    )
    return TaskResponse(task_id=task_id, status="queued")


@router.post(
    "/sync/channels/{channel_id}/backfill",
    response_model=TaskResponse,
    status_code=202,
    summary="Backfill last N days of analytics for a channel and its videos",
)
async def backfill_channel_analytics(
    channel_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
    days: int = Query(28, ge=1, le=365),
    include_publications: bool = Query(True),
) -> TaskResponse:
    from app.repositories.channel import ChannelRepository
    repo = ChannelRepository(db)
    channel = await repo.get_owned(channel_id, owner_id=current_user.id)
    if not channel:
        raise NotFoundError("Channel not found or access denied")

    from app.tasks.ai import enqueue_backfill_channel
    task_id = enqueue_backfill_channel(
        channel_id=str(channel_id),
        days=days,
        include_publications=include_publications,
    )
    return TaskResponse(task_id=task_id, status="queued")


@router.post(
    "/sync/publications/{publication_id}",
    response_model=TaskResponse,
    status_code=202,
    summary="Trigger analytics sync for a single publication",
)
async def sync_publication_analytics(
    publication_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
    sync_date: date = Query(
        default=None,
        description="Date to sync (default: yesterday)",
    ),
) -> TaskResponse:
    from app.repositories.publication import PublicationRepository
    pub = await PublicationRepository(db).get_for_user(publication_id, owner_id=current_user.id)
    if not pub:
        raise NotFoundError("Publication not found")

    import datetime as dt
    d = sync_date.isoformat() if sync_date else (dt.date.today() - dt.timedelta(days=1)).isoformat()

    from app.tasks.ai import enqueue_sync_publication
    task_id = enqueue_sync_publication(
        publication_id=str(publication_id),
        date=d,
    )
    return TaskResponse(task_id=task_id, status="queued")


# ── Performance Scores ────────────────────────────────────────────────────────

@router.get(
    "/scores/channels/{channel_id}",
    response_model=PerformanceScoreRead,
    summary="Get or compute channel performance score",
)
async def channel_score(
    channel_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
    period: int = Query(28, ge=7, le=90),
) -> PerformanceScoreRead:
    svc = ScoringService(db)
    score = await svc.score_channel(
        channel_id, owner_id=current_user.id, period_days=period
    )
    return PerformanceScoreRead.from_orm_with_dims(score)


@router.get(
    "/scores/publications/{publication_id}",
    response_model=PerformanceScoreRead,
    summary="Get or compute publication performance score",
)
async def publication_score(
    publication_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
    period: int = Query(28, ge=7, le=90),
) -> PerformanceScoreRead:
    from app.repositories.publication import PublicationRepository

    pub_repo = PublicationRepository(db)
    pub = await pub_repo.get_for_user(publication_id, owner_id=current_user.id)
    if not pub:
        raise NotFoundError("Publication not found")

    svc = ScoringService(db)
    score = await svc.score_publication(
        publication_id, channel_id=pub.channel_id, period_days=period
    )
    return PerformanceScoreRead.from_orm_with_dims(score)


@router.post(
    "/scores/channels/{channel_id}/compute",
    response_model=TaskResponse,
    summary="Enqueue score computation for a channel",
)
async def enqueue_channel_score(
    channel_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
    period: int = Query(28, ge=7, le=90),
) -> TaskResponse:
    from app.repositories.channel import ChannelRepository

    repo = ChannelRepository(db)
    channel = await repo.get_owned(channel_id, owner_id=current_user.id)
    if not channel:
        raise NotFoundError("Channel not found or access denied")

    from celery import current_app as celery_app
    task = celery_app.send_task(
        "worker.tasks.scoring.compute_channel_score",
        kwargs={
            "channel_id": str(channel_id),
            "owner_id": str(current_user.id),
            "period_days": period,
        },
        queue="analytics",
    )
    return TaskResponse(task_id=task.id, status="pending")


# ── Rankings ──────────────────────────────────────────────────────────────────

@router.get(
    "/rankings/topics",
    response_model=TopicRankingResponse,
    summary="Topic ranking by composite performance score",
)
async def topic_ranking(
    current_user: CurrentUser,
    db: DB,
    period: int = Query(28, ge=7, le=90),
) -> TopicRankingResponse:
    svc = ScoringService(db)
    return await svc.topic_ranking(current_user.id, period_days=period)


@router.get(
    "/rankings/channels",
    response_model=ChannelRankingResponse,
    summary="Channel ranking across all owner channels",
)
async def channel_ranking(
    current_user: CurrentUser,
    db: DB,
    period: int = Query(28, ge=7, le=90),
) -> ChannelRankingResponse:
    svc = ScoringService(db)
    return await svc.channel_ranking(current_user.id, period_days=period)


# ── Recommendations ───────────────────────────────────────────────────────────

@router.get(
    "/recommendations/{channel_id}",
    response_model=list[RecommendationRead],
    summary="List pending growth recommendations for a channel",
)
async def list_recommendations(
    channel_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
    status: str = Query("pending", pattern="^(pending|applied|dismissed|snoozed)$"),
    limit: int = Query(50, ge=1, le=100),
) -> list[RecommendationRead]:
    svc = ScoringService(db)
    recs = await svc.list_recommendations(channel_id, status=status, limit=limit)
    return [RecommendationRead.model_validate(r) for r in recs]


@router.post(
    "/recommendations/{channel_id}/generate",
    response_model=TaskResponse,
    summary="Trigger rule-based recommendation generation for a channel",
)
async def generate_recommendations(
    channel_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
) -> TaskResponse:
    from app.repositories.channel import ChannelRepository

    repo = ChannelRepository(db)
    channel = await repo.get_owned(channel_id, owner_id=current_user.id)
    if not channel:
        raise NotFoundError("Channel not found or access denied")

    from celery import current_app as celery_app
    task = celery_app.send_task(
        "worker.tasks.scoring.generate_recommendations",
        kwargs={"channel_id": str(channel_id), "force": True},
        queue="analytics",
    )
    return TaskResponse(task_id=task.id, status="pending")


@router.post(
    "/recommendations/{channel_id}/generate-sync",
    response_model=list[RecommendationRead],
    summary="Run rule-based recommendations synchronously (dev/small channels)",
)
async def generate_recommendations_sync(
    channel_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
    period: int = Query(28, ge=7, le=90),
) -> list[RecommendationRead]:
    from app.repositories.channel import ChannelRepository

    repo = ChannelRepository(db)
    channel = await repo.get_owned(channel_id, owner_id=current_user.id)
    if not channel:
        raise NotFoundError("Channel not found or access denied")

    svc = ScoringService(db)
    recs = await svc.generate_recommendations(
        channel_id, period_days=period, replace_existing=True
    )
    return [RecommendationRead.model_validate(r) for r in recs]


@router.post(
    "/recommendations/action/{rec_id}/apply",
    response_model=RecommendationRead,
)
async def apply_recommendation(
    rec_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
    payload: RecommendationActionRequest | None = None,
) -> RecommendationRead:
    svc = ScoringService(db)
    rec = await svc.action_recommendation(rec_id, action="apply")
    return RecommendationRead.model_validate(rec)


@router.post(
    "/recommendations/action/{rec_id}/dismiss",
    response_model=RecommendationRead,
)
async def dismiss_recommendation(
    rec_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
    payload: RecommendationActionRequest | None = None,
) -> RecommendationRead:
    svc = ScoringService(db)
    rec = await svc.action_recommendation(rec_id, action="dismiss")
    return RecommendationRead.model_validate(rec)


@router.post(
    "/recommendations/action/{rec_id}/snooze",
    response_model=RecommendationRead,
)
async def snooze_recommendation(
    rec_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
) -> RecommendationRead:
    svc = ScoringService(db)
    rec = await svc.action_recommendation(rec_id, action="snooze")
    return RecommendationRead.model_validate(rec)
