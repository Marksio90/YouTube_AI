from __future__ import annotations

import uuid
from datetime import date, timedelta

import structlog
from fastapi import APIRouter, HTTPException, Query, status

from app.api.v1.deps import CurrentUser, DB
from app.core.exceptions import NotFoundError
from app.db.models.monetization import RevenueSource
from app.repositories.channel import ChannelRepository
from app.schemas.monetization import (
    AffiliateLinkCreate,
    AffiliateLinkRead,
    AffiliateLinkUpdate,
    ChannelRevenueOverview,
    PublicationRevenueOverview,
    ROISummary,
    RevenueStreamCreate,
    RevenueStreamRead,
)
from app.services.monetization import MonetizationService
from app.services.publication import PublicationService

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/monetization", tags=["monetization"])

DEFAULT_DAYS = 30
MIN_DAYS = 7
MAX_DAYS = 365
DEFAULT_LIMIT = 100
MAX_LIMIT = 500


def _default_window(days: int) -> tuple[date, date]:
    period_end = date.today()
    period_start = period_end - timedelta(days=days - 1)
    return period_start, period_end


async def _verify_channel_access(
    db: DB,
    channel_id: uuid.UUID,
    *,
    owner_id: uuid.UUID,
    organization_id: uuid.UUID | None,
) -> None:
    channel = await ChannelRepository(db).get_owned(
        channel_id,
        owner_id=owner_id,
        organization_id=organization_id,
    )
    if not channel:
        raise NotFoundError("Channel not found")


async def _verify_publication_access(
    db: DB,
    publication_id: uuid.UUID,
    *,
    owner_id: uuid.UUID,
):
    return await PublicationService(db).get_for_user(publication_id, owner_id=owner_id)


def _validate_stream_period(payload: RevenueStreamCreate) -> None:
    if payload.period_start > payload.period_end:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="period_start cannot be later than period_end",
        )


@router.get(
    "/channels/{channel_id}/overview",
    response_model=ChannelRevenueOverview,
    summary="Revenue overview for a channel",
)
async def channel_revenue_overview(
    channel_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
    days: int = Query(DEFAULT_DAYS, ge=MIN_DAYS, le=MAX_DAYS),
) -> ChannelRevenueOverview:
    await _verify_channel_access(
        db,
        channel_id,
        owner_id=current_user.id,
        organization_id=current_user.organization_id,
    )

    period_start, period_end = _default_window(days)
    service = MonetizationService(db)

    return await service.channel_overview(
        channel_id,
        period_start=period_start,
        period_end=period_end,
    )


@router.get(
    "/channels/{channel_id}/roi",
    response_model=ROISummary,
    summary="ROI summary including per-video breakdown",
)
async def channel_roi(
    channel_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
    days: int = Query(DEFAULT_DAYS, ge=MIN_DAYS, le=MAX_DAYS),
) -> ROISummary:
    await _verify_channel_access(
        db,
        channel_id,
        owner_id=current_user.id,
        organization_id=current_user.organization_id,
    )

    period_start, period_end = _default_window(days)
    service = MonetizationService(db)

    return await service.roi_summary(
        channel_id,
        period_start=period_start,
        period_end=period_end,
    )


@router.get(
    "/channels/{channel_id}/streams",
    response_model=list[RevenueStreamRead],
    summary="List revenue streams for a channel",
)
async def list_channel_streams(
    channel_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
    days: int = Query(DEFAULT_DAYS, ge=MIN_DAYS, le=MAX_DAYS),
    source: RevenueSource | None = Query(default=None),
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
) -> list[RevenueStreamRead]:
    await _verify_channel_access(
        db,
        channel_id,
        owner_id=current_user.id,
        organization_id=current_user.organization_id,
    )

    period_start, period_end = _default_window(days)
    service = MonetizationService(db)

    streams = await service.list_streams(
        channel_id,
        source=source,
        period_start=period_start,
        period_end=period_end,
        limit=limit,
    )

    return [RevenueStreamRead.model_validate(stream) for stream in streams]


@router.post(
    "/channels/{channel_id}/streams",
    response_model=RevenueStreamRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create or update a revenue stream",
)
async def upsert_stream(
    channel_id: uuid.UUID,
    payload: RevenueStreamCreate,
    current_user: CurrentUser,
    db: DB,
) -> RevenueStreamRead:
    await _verify_channel_access(
        db,
        channel_id,
        owner_id=current_user.id,
        organization_id=current_user.organization_id,
    )

    if payload.channel_id != channel_id:
        payload = payload.model_copy(update={"channel_id": channel_id})

    _validate_stream_period(payload)

    if payload.publication_id is not None:
        publication = await _verify_publication_access(
            db,
            payload.publication_id,
            owner_id=current_user.id,
        )
        if publication.channel_id != channel_id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="publication_id does not belong to this channel",
            )

    service = MonetizationService(db)

    try:
        stream = await service.upsert_stream(payload)
        await db.commit()
        await db.refresh(stream)
    except Exception:
        await db.rollback()
        logger.exception(
            "monetization.stream_upsert_failed",
            channel_id=str(channel_id),
            owner_id=str(current_user.id),
            source=payload.source,
            publication_id=str(payload.publication_id) if payload.publication_id else None,
        )
        raise

    return RevenueStreamRead.model_validate(stream)


@router.get(
    "/publications/{publication_id}/overview",
    response_model=PublicationRevenueOverview,
    summary="Revenue breakdown for a single publication",
)
async def publication_revenue_overview(
    publication_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
) -> PublicationRevenueOverview:
    service = MonetizationService(db)

    overview = await service.publication_overview(
        publication_id,
        owner_id=current_user.id,
        organization_id=current_user.organization_id,
    )
    if not overview:
        raise NotFoundError("Publication not found")

    return overview


@router.get(
    "/channels/{channel_id}/affiliate-links",
    response_model=list[AffiliateLinkRead],
    summary="List affiliate links for a channel",
)
async def list_affiliate_links(
    channel_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
    active_only: bool = Query(default=True),
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
) -> list[AffiliateLinkRead]:
    await _verify_channel_access(
        db,
        channel_id,
        owner_id=current_user.id,
        organization_id=current_user.organization_id,
    )

    service = MonetizationService(db)
    links = await service.list_affiliate_links(
        channel_id,
        active_only=active_only,
        limit=limit,
    )

    return [AffiliateLinkRead.model_validate(link) for link in links]


@router.post(
    "/channels/{channel_id}/affiliate-links",
    response_model=AffiliateLinkRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new affiliate link",
)
async def create_affiliate_link(
    channel_id: uuid.UUID,
    payload: AffiliateLinkCreate,
    current_user: CurrentUser,
    db: DB,
) -> AffiliateLinkRead:
    await _verify_channel_access(
        db,
        channel_id,
        owner_id=current_user.id,
        organization_id=current_user.organization_id,
    )

    if payload.channel_id != channel_id:
        payload = payload.model_copy(update={"channel_id": channel_id})

    if payload.publication_id is not None:
        publication = await _verify_publication_access(
            db,
            payload.publication_id,
            owner_id=current_user.id,
        )
        if publication.channel_id != channel_id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="publication_id does not belong to this channel",
            )

    service = MonetizationService(db)

    try:
        link = await service.create_affiliate_link(payload)
        await db.commit()
        await db.refresh(link)
    except Exception:
        await db.rollback()
        logger.exception(
            "monetization.affiliate_link_create_failed",
            channel_id=str(channel_id),
            owner_id=str(current_user.id),
            publication_id=str(payload.publication_id) if payload.publication_id else None,
        )
        raise

    return AffiliateLinkRead.model_validate(link)


@router.patch(
    "/affiliate-links/{link_id}",
    response_model=AffiliateLinkRead,
    summary="Update an affiliate link",
)
async def update_affiliate_link(
    link_id: uuid.UUID,
    payload: AffiliateLinkUpdate,
    current_user: CurrentUser,
    db: DB,
) -> AffiliateLinkRead:
    service = MonetizationService(db)

    try:
        link = await service.update_affiliate_link(
            link_id,
            payload,
            owner_id=current_user.id,
            organization_id=current_user.organization_id,
        )
        if not link:
            raise NotFoundError("Affiliate link not found")

        await db.commit()
        await db.refresh(link)
    except NotFoundError:
        await db.rollback()
        raise
    except Exception:
        await db.rollback()
        logger.exception(
            "monetization.affiliate_link_update_failed",
            link_id=str(link_id),
            owner_id=str(current_user.id),
        )
        raise

    return AffiliateLinkRead.model_validate(link)


@router.post(
    "/affiliate-links/{link_id}/click",
    response_model=AffiliateLinkRead,
    summary="Record an authenticated click on an affiliate link",
)
async def record_click(
    link_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
) -> AffiliateLinkRead:
    service = MonetizationService(db)

    try:
        link = await service.record_click(
            link_id,
            owner_id=current_user.id,
            organization_id=current_user.organization_id,
        )
        if not link:
            raise NotFoundError("Affiliate link not found")

        await db.commit()
        await db.refresh(link)
    except NotFoundError:
        await db.rollback()
        raise
    except Exception:
        await db.rollback()
        logger.exception(
            "monetization.affiliate_click_record_failed",
            link_id=str(link_id),
            owner_id=str(current_user.id),
        )
        raise

    return AffiliateLinkRead.model_validate(link)


@router.post(
    "/affiliate-links/{link_id}/conversion",
    response_model=AffiliateLinkRead,
    summary="Record an authenticated conversion on an affiliate link",
)
async def record_conversion(
    link_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
    revenue_usd: float = Query(..., ge=0, description="Commission earned from this conversion"),
) -> AffiliateLinkRead:
    service = MonetizationService(db)

    try:
        link = await service.record_conversion(
            link_id,
            revenue_usd,
            owner_id=current_user.id,
            organization_id=current_user.organization_id,
        )
        if not link:
            raise NotFoundError("Affiliate link not found")

        await db.commit()
        await db.refresh(link)
    except NotFoundError:
        await db.rollback()
        raise
    except Exception:
        await db.rollback()
        logger.exception(
            "monetization.affiliate_conversion_record_failed",
            link_id=str(link_id),
            owner_id=str(current_user.id),
            revenue_usd=revenue_usd,
        )
        raise

    return AffiliateLinkRead.model_validate(link)
