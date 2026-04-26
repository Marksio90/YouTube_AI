import uuid
from datetime import date, timedelta
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.v1.deps import CurrentUser, DB
from app.core.exceptions import NotFoundError
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

router = APIRouter(prefix="/monetization", tags=["monetization"])

_DEFAULT_DAYS = 30


def _default_window(days: int) -> tuple[date, date]:
    end   = date.today()
    start = end - timedelta(days=days)
    return start, end


# ── Channel revenue ───────────────────────────────────────────────────────────

@router.get(
    "/channels/{channel_id}/overview",
    response_model=ChannelRevenueOverview,
    summary="Revenue overview for a channel (all sources combined)",
)
async def channel_revenue_overview(
    channel_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
    days: int = Query(_DEFAULT_DAYS, ge=7, le=365),
) -> ChannelRevenueOverview:
    await _verify_channel_access(
        db,
        channel_id,
        owner_id=current_user.id,
        organization_id=current_user.organization_id,
    )
    period_start, period_end = _default_window(days)
    svc = MonetizationService(db)
    return await svc.channel_overview(
        channel_id, period_start=period_start, period_end=period_end
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
    days: int = Query(_DEFAULT_DAYS, ge=7, le=365),
) -> ROISummary:
    await _verify_channel_access(
        db,
        channel_id,
        owner_id=current_user.id,
        organization_id=current_user.organization_id,
    )
    period_start, period_end = _default_window(days)
    svc = MonetizationService(db)
    return await svc.roi_summary(
        channel_id, period_start=period_start, period_end=period_end
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
    days: int = Query(_DEFAULT_DAYS, ge=7, le=365),
    source: str | None = Query(None, pattern="^(ads|affiliate|products|sponsorship)$"),
    limit: int = Query(100, ge=1, le=500),
) -> list[RevenueStreamRead]:
    await _verify_channel_access(
        db,
        channel_id,
        owner_id=current_user.id,
        organization_id=current_user.organization_id,
    )
    period_start, period_end = _default_window(days)
    svc = MonetizationService(db)
    from app.db.models.monetization import RevenueSource
    return await svc.list_streams(
        channel_id,
        source=RevenueSource(source) if source else None,
        period_start=period_start,
        period_end=period_end,
        limit=limit,
    )


@router.post(
    "/channels/{channel_id}/streams",
    response_model=RevenueStreamRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create or update a revenue stream (idempotent on channel+source+period)",
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
    svc = MonetizationService(db)
    stream = await svc.upsert_stream(payload)
    await db.commit()
    return RevenueStreamRead.model_validate(stream)


# ── Publication revenue ───────────────────────────────────────────────────────

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
    svc = MonetizationService(db)
    overview = await svc.publication_overview(
        publication_id,
        owner_id=current_user.id,
        organization_id=current_user.organization_id,
    )
    if not overview:
        raise NotFoundError("Publication not found")
    return overview


# ── Affiliate links ───────────────────────────────────────────────────────────

@router.get(
    "/channels/{channel_id}/affiliate-links",
    response_model=list[AffiliateLinkRead],
    summary="List affiliate links for a channel",
)
async def list_affiliate_links(
    channel_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
    active_only: bool = Query(True),
    limit: int = Query(100, ge=1, le=500),
) -> list[AffiliateLinkRead]:
    await _verify_channel_access(
        db,
        channel_id,
        owner_id=current_user.id,
        organization_id=current_user.organization_id,
    )
    svc = MonetizationService(db)
    links = await svc.list_affiliate_links(
        channel_id, active_only=active_only, limit=limit
    )
    return [AffiliateLinkRead.model_validate(l) for l in links]


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
    svc = MonetizationService(db)
    link = await svc.create_affiliate_link(payload)
    await db.commit()
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
    svc = MonetizationService(db)
    link = await svc.update_affiliate_link(
        link_id,
        payload,
        owner_id=current_user.id,
        organization_id=current_user.organization_id,
    )
    if not link:
        raise NotFoundError("Affiliate link not found")
    await db.commit()
    return AffiliateLinkRead.model_validate(link)


@router.post(
    "/affiliate-links/{link_id}/click",
    response_model=AffiliateLinkRead,
    summary="Record a click on an affiliate link",
)
async def record_click(
    link_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
) -> AffiliateLinkRead:
    svc = MonetizationService(db)
    link = await svc.record_click(
        link_id,
        owner_id=current_user.id,
        organization_id=current_user.organization_id,
    )
    if not link:
        raise NotFoundError("Affiliate link not found")
    await db.commit()
    return AffiliateLinkRead.model_validate(link)


@router.post(
    "/affiliate-links/{link_id}/conversion",
    response_model=AffiliateLinkRead,
    summary="Record a conversion on an affiliate link",
)
async def record_conversion(
    link_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
    revenue_usd: float = Query(..., ge=0, description="Commission earned from this conversion"),
) -> AffiliateLinkRead:
    svc = MonetizationService(db)
    link = await svc.record_conversion(
        link_id,
        revenue_usd,
        owner_id=current_user.id,
        organization_id=current_user.organization_id,
    )
    if not link:
        raise NotFoundError("Affiliate link not found")
    await db.commit()
    return AffiliateLinkRead.model_validate(link)


# ── Private ───────────────────────────────────────────────────────────────────

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
