from __future__ import annotations

import uuid
from datetime import date, timedelta

import structlog
from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import CurrentUser, DB
from app.core.celery import send_task
from app.core.exceptions import NotFoundError
from app.repositories.channel import ChannelRepository
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
from app.services.publication import PublicationService
from app.services.scoring import ScoringService
from app.tasks.ai import (
    enqueue_backfill_channel,
    enqueue_sync_channel,
    enqueue_sync_publication,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/analytics", tags=["analytics"])

DEFAULT_ANALYTICS_DAYS = 28
MAX_ANALYTICS_DAYS = 365
DEFAULT_SCORE_PERIOD = 28
MIN_SCORE_PERIOD = 7
MAX_SCORE_PERIOD = 90
DEFAULT_RECOMMENDATION_LIMIT = 50
MAX_RECOMMENDATION_LIMIT = 100


async def _ensure_owned_channel(
    *,
    db: AsyncSession,
    channel_id: uuid.UUID,
    owner_id: uuid.UUID,
) -> None:
    channel = await ChannelRepository(db).get_owned(channel_id, owner_id=owner_id)
    if not channel:
        raise NotFoundError("Channel not found or access denied")


async def _ensure_owned_publication(
    *,
    db: AsyncSession,
    publication_id: uuid.UUID,
    owner_id: uuid.UUID,
):
    return await PublicationService(db).get_for_user(publication_id, owner_id=owner_id)


def _resolve_date_range(
    *,
    days: int | None,
    date_from: date | None,
    date_to: date | None,
) -> tuple[date, date]:
    if days is not None:
        resolved_to = date.today()
        resolved_from = resolved_to - timedelta(days=days - 1)
        return resolved_from, resolved_to

    if date_from is None or date_to is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Provide either `days` or both `date_from` and `date_to`",
        )

    if date_from > date_to:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="`date_from` cannot be later than `date_to`",
        )

    if (date_to - date_from).days + 1 > MAX_ANALYTICS_DAYS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Date range cannot exceed {MAX_ANALYTICS_DAYS} days",
        )

    return date_from, date_to


def _enqueue_analytics_task(
    *,
    task_name: str,
    kwargs: dict,
) -> TaskResponse:
    task = send_task(task_name=task_name, kwargs=kwargs, queue="analytics")
    return TaskResponse(task_id=task.id, status="pending")


@router.get(
    "/channels/{channel_id}",
    response_model=AnalyticsAggregate,
    summary="Get aggregate analytics for a channel",
)
async def channel_analytics(
    channel_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
    days: int = Query(DEFAULT_ANALYTICS_DAYS, ge=1, le=MAX_ANALYTICS_DAYS),
) -> AnalyticsAggregate:
    service = AnalyticsService(db)
    return await service.get_channel_aggregate(
        channel_id,
        owner_id=current_user.id,
        days=days,
    )


@router.get(
    "/publications/{publication_id}",
    response_model=list[AnalyticsSnapshotRead],
    summary="Get analytics snapshots for a publication",
)
async def publication_analytics(
    publication_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
    days: int | None = Query(default=None, ge=1, le=MAX_ANALYTICS_DAYS),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
) -> list[AnalyticsSnapshotRead]:
    await _ensure_owned_publication(
        db=db,
        publication_id=publication_id,
        owner_id=current_user.id,
    )

    resolved_from, resolved_to = _resolve_date_range(
        days=days,
        date_from=date_from,
        date_to=date_to,
    )

    service = AnalyticsService(db)
    return await service.get_publication_snapshots(
        publication_id,
        date_from=resolved_from,
        date_to=resolved_to,
    )


@router.get(
    "/overview",
    response_model=list[AnalyticsAggregate],
    summary="Get analytics overview for all owned channels",
)
async def overview_analytics(
    current_user: CurrentUser,
    db: DB,
    days: int = Query(DEFAULT_ANALYTICS_DAYS, ge=1, le=MAX_ANALYTICS_DAYS),
) -> list[AnalyticsAggregate]:
    service = AnalyticsService(db)
    return await service.get_overview_aggregates(owner_id=current_user.id, days=days)


@router.post(
    "/snapshots",
    response_model=AnalyticsSnapshotRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create or update an analytics snapshot",
)
async def upsert_snapshot(
    payload: AnalyticsSnapshotCreate,
    current_user: CurrentUser,
    db: DB,
) -> AnalyticsSnapshotRead:
    service = AnalyticsService(db)

    try:
        snapshot = await service.upsert_snapshot(payload, owner_id=current_user.id)
        await db.commit()
    except Exception:
        await db.rollback()
        logger.exception(
            "analytics.snapshot_upsert_failed",
            channel_id=str(payload.channel_id),
            publication_id=str(payload.publication_id) if payload.publication_id else None,
            owner_id=str(current_user.id),
        )
        raise

    return snapshot


@router.post(
    "/sync/channels/{channel_id}",
    response_model=TaskResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Trigger analytics sync for a channel",
)
async def sync_channel_analytics(
    channel_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
    sync_date: date | None = Query(default=None, description="Date to sync, default: today"),
) -> TaskResponse:
    await _ensure_owned_channel(db=db, channel_id=channel_id, owner_id=current_user.id)

    resolved_date = sync_date or date.today()
    task_id = enqueue_sync_channel(
        channel_id=str(channel_id),
        date=resolved_date.isoformat(),
    )

    return TaskResponse(task_id=task_id, status="queued")


@router.post(
    "/sync/channels/{channel_id}/backfill",
    response_model=TaskResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Backfill analytics for a channel and optionally its publications",
)
async def backfill_channel_analytics(
    channel_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
    days: int = Query(DEFAULT_ANALYTICS_DAYS, ge=1, le=MAX_ANALYTICS_DAYS),
    include_publications: bool = Query(default=True),
) -> TaskResponse:
    await _ensure_owned_channel(db=db, channel_id=channel_id, owner_id=current_user.id)

    task_id = enqueue_backfill_channel(
        channel_id=str(channel_id),
        days=days,
        include_publications=include_publications,
    )

    return TaskResponse(task_id=task_id, status="queued")


@router.post(
    "/sync/publications/{publication_id}",
    response_model=TaskResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Trigger analytics sync for a single publication",
)
async def sync_publication_analytics(
    publication_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
    sync_date: date | None = Query(default=None, description="Date to sync, default: yesterday"),
) -> TaskResponse:
    await _ensure_owned_publication(
        db=db,
        publication_id=publication_id,
        owner_id=current_user.id,
    )

    resolved_date = sync_date or (date.today() - timedelta(days=1))
    task_id = enqueue_sync_publication(
        publication_id=str(publication_id),
        date=resolved_date.isoformat(),
    )

    return TaskResponse(task_id=task_id, status="queued")


@router.get(
    "/scores/channels/{channel_id}",
    response_model=PerformanceScoreRead,
    summary="Get or compute channel performance score",
)
async def channel_score(
    channel_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
    period: int = Query(DEFAULT_SCORE_PERIOD, ge=MIN_SCORE_PERIOD, le=MAX_SCORE_PERIOD),
) -> PerformanceScoreRead:
    await _ensure_owned_channel(db=db, channel_id=channel_id, owner_id=current_user.id)

    service = ScoringService(db)
    score = await service.score_channel(
        channel_id,
        owner_id=current_user.id,
        period_days=period,
    )

    await db.commit()
    await db.refresh(score)

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
    period: int = Query(DEFAULT_SCORE_PERIOD, ge=MIN_SCORE_PERIOD, le=MAX_SCORE_PERIOD),
) -> PerformanceScoreRead:
    publication = await _ensure_owned_publication(
        db=db,
        publication_id=publication_id,
        owner_id=current_user.id,
    )

    service = ScoringService(db)
    score = await service.score_publication(
        publication_id,
        channel_id=publication.channel_id,
        period_days=period,
    )

    await db.commit()
    await db.refresh(score)

    return PerformanceScoreRead.from_orm_with_dims(score)


@router.post(
    "/scores/channels/{channel_id}/compute",
    response_model=TaskResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Enqueue score computation for a channel",
)
async def enqueue_channel_score(
    channel_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
    period: int = Query(DEFAULT_SCORE_PERIOD, ge=MIN_SCORE_PERIOD, le=MAX_SCORE_PERIOD),
) -> TaskResponse:
    await _ensure_owned_channel(db=db, channel_id=channel_id, owner_id=current_user.id)

    return _enqueue_analytics_task(
        task_name="worker.tasks.scoring.compute_channel_score",
        kwargs={
            "channel_id": str(channel_id),
            "owner_id": str(current_user.id),
            "period_days": period,
        },
    )


@router.get(
    "/rankings/topics",
    response_model=TopicRankingResponse,
    summary="Topic ranking by composite performance score",
)
async def topic_ranking(
    current_user: CurrentUser,
    db: DB,
    period: int = Query(DEFAULT_SCORE_PERIOD, ge=MIN_SCORE_PERIOD, le=MAX_SCORE_PERIOD),
) -> TopicRankingResponse:
    service = ScoringService(db)
    return await service.topic_ranking(current_user.id, period_days=period)


@router.get(
    "/rankings/channels",
    response_model=ChannelRankingResponse,
    summary="Channel ranking across all owner channels",
)
async def channel_ranking(
    current_user: CurrentUser,
    db: DB,
    period: int = Query(DEFAULT_SCORE_PERIOD, ge=MIN_SCORE_PERIOD, le=MAX_SCORE_PERIOD),
) -> ChannelRankingResponse:
    service = ScoringService(db)
    return await service.channel_ranking(current_user.id, period_days=period)


@router.get(
    "/recommendations/{channel_id}",
    response_model=list[RecommendationRead],
    summary="List growth recommendations for a channel",
)
async def list_recommendations(
    channel_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
    recommendation_status: str = Query(
        default="pending",
        alias="status",
        pattern="^(pending|applied|dismissed|snoozed)$",
    ),
    limit: int = Query(DEFAULT_RECOMMENDATION_LIMIT, ge=1, le=MAX_RECOMMENDATION_LIMIT),
) -> list[RecommendationRead]:
    await _ensure_owned_channel(db=db, channel_id=channel_id, owner_id=current_user.id)

    service = ScoringService(db)
    recommendations = await service.list_recommendations(
        channel_id,
        status=recommendation_status,
        limit=limit,
    )

    return [RecommendationRead.model_validate(recommendation) for recommendation in recommendations]


@router.post(
    "/recommendations/{channel_id}/generate",
    response_model=TaskResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Trigger rule-based recommendation generation for a channel",
)
async def generate_recommendations(
    channel_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
) -> TaskResponse:
    await _ensure_owned_channel(db=db, channel_id=channel_id, owner_id=current_user.id)

    return _enqueue_analytics_task(
        task_name="worker.tasks.scoring.generate_recommendations",
        kwargs={
            "channel_id": str(channel_id),
            "force": True,
        },
    )


@router.post(
    "/recommendations/{channel_id}/generate-sync",
    response_model=list[RecommendationRead],
    summary="Run rule-based recommendations synchronously for dev or small channels",
)
async def generate_recommendations_sync(
    channel_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
    period: int = Query(DEFAULT_SCORE_PERIOD, ge=MIN_SCORE_PERIOD, le=MAX_SCORE_PERIOD),
) -> list[RecommendationRead]:
    await _ensure_owned_channel(db=db, channel_id=channel_id, owner_id=current_user.id)

    service = ScoringService(db)

    try:
        recommendations = await service.generate_recommendations(
            channel_id,
            period_days=period,
            replace_existing=True,
        )
        await db.commit()
    except Exception:
        await db.rollback()
        logger.exception(
            "analytics.recommendations_generate_sync_failed",
            channel_id=str(channel_id),
            owner_id=str(current_user.id),
            period_days=period,
        )
        raise

    return [RecommendationRead.model_validate(recommendation) for recommendation in recommendations]


@router.post(
    "/recommendations/action/{rec_id}/apply",
    response_model=RecommendationRead,
    summary="Mark a recommendation as applied",
)
async def apply_recommendation(
    rec_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
    payload: RecommendationActionRequest | None = None,
) -> RecommendationRead:
    return await _action_recommendation(
        rec_id=rec_id,
        current_user=current_user,
        db=db,
        action="apply",
        payload=payload,
    )


@router.post(
    "/recommendations/action/{rec_id}/dismiss",
    response_model=RecommendationRead,
    summary="Dismiss a recommendation",
)
async def dismiss_recommendation(
    rec_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
    payload: RecommendationActionRequest | None = None,
) -> RecommendationRead:
    return await _action_recommendation(
        rec_id=rec_id,
        current_user=current_user,
        db=db,
        action="dismiss",
        payload=payload,
    )


@router.post(
    "/recommendations/action/{rec_id}/snooze",
    response_model=RecommendationRead,
    summary="Snooze a recommendation",
)
async def snooze_recommendation(
    rec_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
    payload: RecommendationActionRequest | None = None,
) -> RecommendationRead:
    return await _action_recommendation(
        rec_id=rec_id,
        current_user=current_user,
        db=db,
        action="snooze",
        payload=payload,
    )


async def _action_recommendation(
    *,
    rec_id: uuid.UUID,
    current_user: CurrentUser,
    db: AsyncSession,
    action: str,
    payload: RecommendationActionRequest | None,
) -> RecommendationRead:
    service = ScoringService(db)

    recommendation = await service.action_recommendation(rec_id, action=action)
    if not recommendation:
        raise NotFoundError("Recommendation not found")

    await _ensure_owned_channel(
        db=db,
        channel_id=recommendation.channel_id,
        owner_id=current_user.id,
    )

    if payload and payload.note:
        logger.info(
            "analytics.recommendation_action_note_received",
            recommendation_id=str(rec_id),
            action=action,
            note_length=len(payload.note),
            owner_id=str(current_user.id),
        )

    try:
        await db.commit()
        await db.refresh(recommendation)
    except Exception:
        await db.rollback()
        logger.exception(
            "analytics.recommendation_action_failed",
            recommendation_id=str(rec_id),
            action=action,
            owner_id=str(current_user.id),
        )
        raise

    return RecommendationRead.model_validate(recommendation)
