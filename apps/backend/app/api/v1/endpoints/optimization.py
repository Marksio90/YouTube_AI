"""
Optimization API — content growth brain.

Routes:
  POST /channels/{channel_id}/optimization/generate
  POST /channels/{channel_id}/optimization/generate-sync
  GET  /channels/{channel_id}/optimization
  GET  /channels/{channel_id}/optimization/next-topics
  GET  /channels/{channel_id}/optimization/format-insights
  GET  /publications/{publication_id}/optimization
"""

from __future__ import annotations

import uuid
from typing import Any

import structlog
from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import CurrentUser, DB
from app.core.exceptions import NotFoundError
from app.repositories.channel import ChannelRepository
from app.schemas.common import TaskResponse
from app.schemas.optimization import (
    OptimizationGenerateRequest,
    OptimizationReportRead,
    PublicationInsightsRead,
)
from app.services.optimization import OptimizationService
from app.tasks.ai import enqueue_optimize_channel

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["optimization"])

DEFAULT_NEXT_TOPICS_LIMIT = 10
MAX_NEXT_TOPICS_LIMIT = 20


async def _ensure_owned_channel(
    *,
    db: AsyncSession,
    channel_id: uuid.UUID,
    current_user: CurrentUser,
) -> None:
    channel = await ChannelRepository(db).get_owned(
        channel_id,
        owner_id=current_user.id,
        organization_id=current_user.organization_id,
    )
    if not channel:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Channel not found",
        )


async def _latest_ready_report_row(
    *,
    db: AsyncSession,
    channel_id: uuid.UUID,
    columns: str,
) -> dict[str, Any]:
    row = (
        await db.execute(
            text(
                f"""
                SELECT {columns}
                FROM optimization_reports
                WHERE channel_id = :channel_id
                  AND status = 'ready'
                ORDER BY updated_at DESC
                LIMIT 1
                """
            ),
            {"channel_id": str(channel_id)},
        )
    ).mappings().one_or_none()

    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No optimization report yet. POST /generate to create one.",
        )

    return dict(row)


@router.post(
    "/channels/{channel_id}/optimization/generate",
    response_model=TaskResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Enqueue content optimization report for a channel",
)
async def generate_optimization_report(
    channel_id: uuid.UUID,
    payload: OptimizationGenerateRequest,
    current_user: CurrentUser,
    db: DB,
) -> TaskResponse:
    await _ensure_owned_channel(db=db, channel_id=channel_id, current_user=current_user)

    task_id = enqueue_optimize_channel(
        channel_id=str(channel_id),
        owner_id=str(current_user.id),
        period_days=payload.period_days,
        force=payload.force,
    )

    logger.info(
        "optimization.report_queued",
        channel_id=str(channel_id),
        owner_id=str(current_user.id),
        organization_id=str(current_user.organization_id),
        period_days=payload.period_days,
        force=payload.force,
        task_id=task_id,
    )

    return TaskResponse(task_id=task_id, status="queued")


@router.get(
    "/channels/{channel_id}/optimization",
    response_model=OptimizationReportRead,
    summary="Get latest optimization report for a channel",
)
async def get_optimization_report(
    channel_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
) -> OptimizationReportRead:
    await _ensure_owned_channel(db=db, channel_id=channel_id, current_user=current_user)

    service = OptimizationService(db)
    report = await service.get_latest_report(channel_id)

    if not report:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No optimization report yet. POST /generate to create one.",
        )

    return OptimizationReportRead.model_validate(report)


@router.get(
    "/channels/{channel_id}/optimization/next-topics",
    response_model=list[dict[str, Any]],
    summary="AI-suggested next topics from the latest optimization report",
)
async def get_next_topics(
    channel_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
    limit: int = Query(DEFAULT_NEXT_TOPICS_LIMIT, ge=1, le=MAX_NEXT_TOPICS_LIMIT),
) -> list[dict[str, Any]]:
    await _ensure_owned_channel(db=db, channel_id=channel_id, current_user=current_user)

    row = await _latest_ready_report_row(
        db=db,
        channel_id=channel_id,
        columns="next_topics",
    )

    next_topics = row.get("next_topics") or []
    if not isinstance(next_topics, list):
        logger.warning(
            "optimization.next_topics_invalid_shape",
            channel_id=str(channel_id),
            value_type=type(next_topics).__name__,
        )
        return []

    return next_topics[:limit]


@router.get(
    "/channels/{channel_id}/optimization/format-insights",
    response_model=dict[str, Any],
    summary="Format suggestions and watch-time insights from the latest report",
)
async def get_format_insights(
    channel_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
) -> dict[str, Any]:
    await _ensure_owned_channel(db=db, channel_id=channel_id, current_user=current_user)

    row = await _latest_ready_report_row(
        db=db,
        channel_id=channel_id,
        columns="""
            format_suggestions,
            watch_time_insights,
            ctr_insights,
            growth_trajectory,
            growth_score,
            summary
        """,
    )

    return {
        "growth_trajectory": row.get("growth_trajectory"),
        "growth_score": row.get("growth_score"),
        "summary": row.get("summary"),
        "format_suggestions": row.get("format_suggestions") or [],
        "watch_time_insights": row.get("watch_time_insights") or [],
        "ctr_insights": row.get("ctr_insights") or [],
    }


@router.get(
    "/publications/{publication_id}/optimization",
    response_model=PublicationInsightsRead,
    summary="Deep-dive performance insights for a single publication",
)
async def get_publication_optimization(
    publication_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
) -> PublicationInsightsRead:
    service = OptimizationService(db)

    try:
        data = await service.get_publication_insights(
            publication_id,
            owner_id=current_user.id,
        )
    except NotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Publication not found",
        ) from exc

    return PublicationInsightsRead.model_validate(data)


@router.post(
    "/channels/{channel_id}/optimization/generate-sync",
    response_model=OptimizationReportRead,
    summary="Generate optimization report synchronously for dev or small channels",
)
async def generate_optimization_sync(
    channel_id: uuid.UUID,
    payload: OptimizationGenerateRequest,
    current_user: CurrentUser,
    db: DB,
) -> OptimizationReportRead:
    await _ensure_owned_channel(db=db, channel_id=channel_id, current_user=current_user)

    service = OptimizationService(db)

    try:
        report = await service.generate_report(
            channel_id,
            owner_id=current_user.id,
            period_days=payload.period_days,
        )
        await db.commit()
        await db.refresh(report)
    except Exception:
        await db.rollback()
        logger.exception(
            "optimization.generate_sync_failed",
            channel_id=str(channel_id),
            owner_id=str(current_user.id),
            organization_id=str(current_user.organization_id),
            period_days=payload.period_days,
            force=payload.force,
        )
        raise

    logger.info(
        "optimization.generate_sync_completed",
        channel_id=str(channel_id),
        owner_id=str(current_user.id),
        report_id=str(report.id),
        period_days=payload.period_days,
    )

    return OptimizationReportRead.model_validate(report)
