"""
Optimization API — content growth brain.

Routes:
  POST /channels/{id}/optimization/generate          enqueue optimization report
  GET  /channels/{id}/optimization                   latest report
  GET  /channels/{id}/optimization/next-topics       AI-suggested next topics
  GET  /channels/{id}/optimization/format-insights   format suggestions + watch-time insights
  GET  /publications/{id}/optimization               publication deep-dive
"""
import uuid

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import text

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

router = APIRouter(tags=["optimization"])


# ── generate ──────────────────────────────────────────────────────────────────

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
    channel = await ChannelRepository(db).get_owned(channel_id, owner_id=current_user.id)
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")

    from app.tasks.ai import enqueue_optimize_channel
    task_id = enqueue_optimize_channel(
        channel_id=str(channel_id),
        owner_id=str(current_user.id),
        period_days=payload.period_days,
        force=payload.force,
    )
    return TaskResponse(task_id=task_id, status="queued")


# ── latest report ─────────────────────────────────────────────────────────────

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
    channel = await ChannelRepository(db).get_owned(channel_id, owner_id=current_user.id)
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")

    svc = OptimizationService(db)
    report = await svc.get_latest_report(channel_id)
    if not report:
        raise HTTPException(
            status_code=404,
            detail="No optimization report yet. POST /generate to create one.",
        )
    return OptimizationReportRead.from_orm(report)


# ── next topics view ──────────────────────────────────────────────────────────

@router.get(
    "/channels/{channel_id}/optimization/next-topics",
    response_model=list[dict],
    summary="AI-suggested next topics from the latest optimization report",
)
async def get_next_topics(
    channel_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
    limit: int = Query(10, ge=1, le=20),
) -> list[dict]:
    channel = await ChannelRepository(db).get_owned(channel_id, owner_id=current_user.id)
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")

    row = (
        await db.execute(
            text("""
                SELECT next_topics FROM optimization_reports
                WHERE channel_id=:cid AND status='ready'
                ORDER BY updated_at DESC LIMIT 1
            """),
            {"cid": str(channel_id)},
        )
    ).mappings().one_or_none()

    if not row:
        raise HTTPException(
            status_code=404,
            detail="No optimization report yet. POST /generate to create one.",
        )
    return (row["next_topics"] or [])[:limit]


# ── format insights view ──────────────────────────────────────────────────────

@router.get(
    "/channels/{channel_id}/optimization/format-insights",
    response_model=dict,
    summary="Format suggestions and watch-time insights from the latest report",
)
async def get_format_insights(
    channel_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
) -> dict:
    channel = await ChannelRepository(db).get_owned(channel_id, owner_id=current_user.id)
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")

    row = (
        await db.execute(
            text("""
                SELECT format_suggestions, watch_time_insights, ctr_insights,
                       growth_trajectory, growth_score, summary
                FROM optimization_reports
                WHERE channel_id=:cid AND status='ready'
                ORDER BY updated_at DESC LIMIT 1
            """),
            {"cid": str(channel_id)},
        )
    ).mappings().one_or_none()

    if not row:
        raise HTTPException(
            status_code=404,
            detail="No optimization report yet. POST /generate to create one.",
        )

    return {
        "growth_trajectory": row["growth_trajectory"],
        "growth_score": row["growth_score"],
        "summary": row["summary"],
        "format_suggestions": row["format_suggestions"] or [],
        "watch_time_insights": row["watch_time_insights"] or [],
        "ctr_insights": row["ctr_insights"] or [],
    }


# ── publication deep-dive ─────────────────────────────────────────────────────

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
    svc = OptimizationService(db)
    try:
        data = await svc.get_publication_insights(
            publication_id, owner_id=current_user.id
        )
    except NotFoundError:
        raise HTTPException(status_code=404, detail="Publication not found")
    return PublicationInsightsRead(**data)


# ── sync generate (small channels / dev) ──────────────────────────────────────

@router.post(
    "/channels/{channel_id}/optimization/generate-sync",
    response_model=OptimizationReportRead,
    summary="Generate optimization report synchronously (dev/small channels)",
)
async def generate_optimization_sync(
    channel_id: uuid.UUID,
    payload: OptimizationGenerateRequest,
    current_user: CurrentUser,
    db: DB,
) -> OptimizationReportRead:
    channel = await ChannelRepository(db).get_owned(channel_id, owner_id=current_user.id)
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")

    svc = OptimizationService(db)
    report = await svc.generate_report(
        channel_id,
        owner_id=current_user.id,
        period_days=payload.period_days,
    )
    await db.commit()
    return OptimizationReportRead.from_orm(report)
