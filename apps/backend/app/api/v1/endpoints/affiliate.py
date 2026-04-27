"""
Affiliate API — campaigns, links, video attachment, click tracking, revenue estimation.

Routes are mounted under /api/v1/affiliate through the v1 router.

Campaigns:
  GET    /affiliate/channels/{channel_id}/campaigns
  POST   /affiliate/channels/{channel_id}/campaigns
  GET    /affiliate/channels/{channel_id}/campaigns/{campaign_id}
  PATCH  /affiliate/channels/{channel_id}/campaigns/{campaign_id}
  DELETE /affiliate/channels/{channel_id}/campaigns/{campaign_id}
  GET    /affiliate/channels/{channel_id}/campaigns/{campaign_id}/report

Links:
  GET    /affiliate/channels/{channel_id}/affiliate-links
  POST   /affiliate/channels/{channel_id}/affiliate-links
  GET    /affiliate/channels/{channel_id}/affiliate-links/{link_id}
  PATCH  /affiliate/channels/{channel_id}/affiliate-links/{link_id}
  POST   /affiliate/channels/{channel_id}/affiliate-links/{link_id}/mock-clicks
  GET    /affiliate/channels/{channel_id}/affiliate-links/{link_id}/estimate
  GET    /affiliate/channels/{channel_id}/affiliate-links/{link_id}/history

Tracking:
  POST   /affiliate/affiliate-links/{link_id}/click
  POST   /affiliate/affiliate-links/{link_id}/conversion

Publication attachment:
  GET    /affiliate/publications/{publication_id}/affiliate-links
  POST   /affiliate/publications/{publication_id}/affiliate-links
  DELETE /affiliate/publications/{publication_id}/affiliate-links/{link_id}
"""

from __future__ import annotations

import hashlib
import hmac
import uuid
from datetime import datetime, timezone
from typing import Any

import structlog
from fastapi import APIRouter, Header, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import CurrentUser, DB
from app.core.config import settings
from app.repositories.channel import ChannelRepository
from app.schemas.affiliate import (
    AffiliateLinkCreate,
    AffiliateLinkRead,
    AffiliateLinkUpdate,
    AttachLinkRequest,
    CampaignCreate,
    CampaignRead,
    CampaignReportRead,
    CampaignStatusType,
    CampaignUpdate,
    ClickHistoryRow,
    ClickRead,
    ConversionRequest,
    MockClicksRequest,
    PublicationAffiliateLinkRead,
    RevenueEstimateRead,
)
from app.services.affiliate import AffiliateService
from app.services.publication import PublicationService

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/affiliate", tags=["affiliate"])

TRACKING_EVENT_CLICK = "click"
TRACKING_EVENT_CONVERSION = "conversion"

TRACKING_REJECTION_INVALID_SIGNATURE = "invalid_signature"
TRACKING_REJECTION_REPLAY_NONCE = "replay_nonce"
TRACKING_REJECTION_RATE_LIMIT = "rate_limit_exceeded"


async def _owned_channel(channel_id: uuid.UUID, user_id: uuid.UUID, db: AsyncSession) -> None:
    channel = await ChannelRepository(db).get_owned(channel_id, owner_id=user_id)
    if not channel:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Channel not found")


async def _owned_publication(publication_id: uuid.UUID, user_id: uuid.UUID, db: AsyncSession) -> None:
    svc = PublicationService(db)
    await svc.get_for_user(publication_id, owner_id=user_id)


async def _owned_link(
    *,
    service: AffiliateService,
    channel_id: uuid.UUID,
    link_id: uuid.UUID,
) -> Any:
    link = await service.get_link(link_id)
    if not link or link.channel_id != channel_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Link not found")
    return link


async def _owned_campaign(
    *,
    service: AffiliateService,
    channel_id: uuid.UUID,
    campaign_id: uuid.UUID,
) -> Any:
    campaign = await service.get_campaign(campaign_id)
    if not campaign or campaign.channel_id != channel_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")
    return campaign


def _client_ip(request: Request) -> str | None:
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        first_ip = forwarded_for.split(",", maxsplit=1)[0].strip()
        return first_ip or None

    real_ip = request.headers.get("x-real-ip")
    if real_ip:
        return real_ip.strip() or None

    if request.client:
        return request.client.host

    return None


def _tracking_signature_error(
    *,
    event_type: str,
    link_id: uuid.UUID,
    ts: int | None,
    nonce: str | None,
    signature: str | None,
) -> str | None:
    secret = settings.affiliate_tracking_hmac_secret

    if not secret:
        return "hmac_secret_missing"

    if ts is None or not nonce or not signature:
        return "missing_signature_params"

    now = int(datetime.now(tz=timezone.utc).timestamp())
    max_skew = settings.affiliate_tracking_max_skew_seconds

    if max_skew <= 0:
        return "invalid_max_skew_config"

    if abs(now - ts) > max_skew:
        return "timestamp_out_of_window"

    payload = f"{event_type}:{link_id}:{ts}:{nonce}".encode("utf-8")
    expected = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()

    if not hmac.compare_digest(expected, signature):
        return "invalid_signature"

    return None


async def _audit_tracking_event(
    *,
    service: AffiliateService,
    event_type: str,
    decision: str,
    reason: str | None,
    link_id: uuid.UUID | None,
    source: str | None,
    ip_address: str | None,
    user_agent: str | None,
    fingerprint: str | None,
) -> None:
    await service.audit_security_event(
        event_type=event_type,
        decision=decision,
        reason=reason,
        link_id=link_id,
        source=source,
        ip_address=ip_address,
        user_agent=user_agent,
        fingerprint=fingerprint,
    )


async def _reject_tracking_event(
    *,
    db: AsyncSession,
    service: AffiliateService,
    event_type: str,
    reason: str,
    link_id: uuid.UUID,
    source: str | None,
    ip_address: str | None,
    user_agent: str | None,
    fingerprint: str | None,
    status_code: int,
    detail: str,
) -> None:
    await _audit_tracking_event(
        service=service,
        event_type=event_type,
        decision="rejected",
        reason=reason,
        link_id=link_id,
        source=source,
        ip_address=ip_address,
        user_agent=user_agent,
        fingerprint=fingerprint,
    )
    await db.commit()
    raise HTTPException(status_code=status_code, detail=detail)


def _ensure_development_mock_allowed() -> None:
    environment = getattr(settings, "environment", None) or getattr(settings, "app_env", None) or "development"
    normalized = str(environment).lower()

    if normalized in {"prod", "production"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Mock click seeding is disabled in production",
        )


@router.get(
    "/channels/{channel_id}/campaigns",
    response_model=list[CampaignRead],
    summary="List affiliate campaigns for a channel",
)
async def list_campaigns(
    channel_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
    status_filter: CampaignStatusType | None = Query(default=None, alias="status"),
) -> list[CampaignRead]:
    await _owned_channel(channel_id, current_user.id, db)

    service = AffiliateService(db)
    campaigns = await service.list_campaigns(channel_id, status=status_filter)

    return [CampaignRead.model_validate(campaign) for campaign in campaigns]


@router.post(
    "/channels/{channel_id}/campaigns",
    response_model=CampaignRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create an affiliate campaign",
)
async def create_campaign(
    channel_id: uuid.UUID,
    payload: CampaignCreate,
    current_user: CurrentUser,
    db: DB,
) -> CampaignRead:
    await _owned_channel(channel_id, current_user.id, db)

    service = AffiliateService(db)

    try:
        campaign = await service.create_campaign(
            channel_id=channel_id,
            data=payload.model_dump(exclude_none=True),
        )
        await db.commit()
        await db.refresh(campaign)
    except Exception:
        await db.rollback()
        logger.exception(
            "affiliate.campaign_create_failed",
            channel_id=str(channel_id),
            user_id=str(current_user.id),
        )
        raise

    return CampaignRead.model_validate(campaign)


@router.get(
    "/channels/{channel_id}/campaigns/{campaign_id}",
    response_model=CampaignRead,
    summary="Get a campaign",
)
async def get_campaign(
    channel_id: uuid.UUID,
    campaign_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
) -> CampaignRead:
    await _owned_channel(channel_id, current_user.id, db)

    service = AffiliateService(db)
    campaign = await _owned_campaign(
        service=service,
        channel_id=channel_id,
        campaign_id=campaign_id,
    )

    return CampaignRead.model_validate(campaign)


@router.patch(
    "/channels/{channel_id}/campaigns/{campaign_id}",
    response_model=CampaignRead,
    summary="Update a campaign",
)
async def update_campaign(
    channel_id: uuid.UUID,
    campaign_id: uuid.UUID,
    payload: CampaignUpdate,
    current_user: CurrentUser,
    db: DB,
) -> CampaignRead:
    await _owned_channel(channel_id, current_user.id, db)

    service = AffiliateService(db)
    await _owned_campaign(service=service, channel_id=channel_id, campaign_id=campaign_id)

    try:
        campaign = await service.update_campaign(
            campaign_id,
            payload.model_dump(exclude_none=True),
        )
        if not campaign or campaign.channel_id != channel_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")

        await db.commit()
        await db.refresh(campaign)
    except HTTPException:
        await db.rollback()
        raise
    except Exception:
        await db.rollback()
        logger.exception(
            "affiliate.campaign_update_failed",
            channel_id=str(channel_id),
            campaign_id=str(campaign_id),
            user_id=str(current_user.id),
        )
        raise

    return CampaignRead.model_validate(campaign)


@router.delete(
    "/channels/{channel_id}/campaigns/{campaign_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a campaign",
)
async def delete_campaign(
    channel_id: uuid.UUID,
    campaign_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
) -> None:
    await _owned_channel(channel_id, current_user.id, db)

    service = AffiliateService(db)
    await _owned_campaign(service=service, channel_id=channel_id, campaign_id=campaign_id)

    try:
        deleted = await service.delete_campaign(campaign_id)
        if not deleted:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")
        await db.commit()
    except HTTPException:
        await db.rollback()
        raise
    except Exception:
        await db.rollback()
        logger.exception(
            "affiliate.campaign_delete_failed",
            channel_id=str(channel_id),
            campaign_id=str(campaign_id),
            user_id=str(current_user.id),
        )
        raise


@router.get(
    "/channels/{channel_id}/campaigns/{campaign_id}/report",
    response_model=CampaignReportRead,
    summary="Full campaign report with per-link breakdown",
)
async def campaign_report(
    channel_id: uuid.UUID,
    campaign_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
) -> CampaignReportRead:
    await _owned_channel(channel_id, current_user.id, db)

    service = AffiliateService(db)
    await _owned_campaign(service=service, channel_id=channel_id, campaign_id=campaign_id)

    report = await service.campaign_report(campaign_id)

    return CampaignReportRead.model_validate(report)


@router.get(
    "/channels/{channel_id}/affiliate-links",
    response_model=list[AffiliateLinkRead],
    summary="List affiliate links for a channel",
)
async def list_links(
    channel_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
    campaign_id: uuid.UUID | None = Query(default=None),
    active_only: bool = Query(default=True),
) -> list[AffiliateLinkRead]:
    await _owned_channel(channel_id, current_user.id, db)

    service = AffiliateService(db)

    if campaign_id is not None:
        await _owned_campaign(service=service, channel_id=channel_id, campaign_id=campaign_id)

    links = await service.list_links(
        channel_id,
        campaign_id=campaign_id,
        active_only=active_only,
    )

    return [AffiliateLinkRead.model_validate(link) for link in links]


@router.post(
    "/channels/{channel_id}/affiliate-links",
    response_model=AffiliateLinkRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create an affiliate link",
)
async def create_link(
    channel_id: uuid.UUID,
    payload: AffiliateLinkCreate,
    current_user: CurrentUser,
    db: DB,
) -> AffiliateLinkRead:
    await _owned_channel(channel_id, current_user.id, db)

    service = AffiliateService(db)
    data = payload.model_dump(exclude_none=True)

    campaign_id = data.get("campaign_id")
    if campaign_id is not None:
        await _owned_campaign(service=service, channel_id=channel_id, campaign_id=campaign_id)

    publication_id = data.get("publication_id")
    if publication_id is not None:
        await _owned_publication(publication_id, current_user.id, db)

    try:
        link = await service.create_link(channel_id=channel_id, data=data)
        await db.commit()
        await db.refresh(link)
    except Exception:
        await db.rollback()
        logger.exception(
            "affiliate.link_create_failed",
            channel_id=str(channel_id),
            user_id=str(current_user.id),
        )
        raise

    return AffiliateLinkRead.model_validate(link)


@router.get(
    "/channels/{channel_id}/affiliate-links/{link_id}",
    response_model=AffiliateLinkRead,
    summary="Get an affiliate link",
)
async def get_link(
    channel_id: uuid.UUID,
    link_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
) -> AffiliateLinkRead:
    await _owned_channel(channel_id, current_user.id, db)

    service = AffiliateService(db)
    link = await _owned_link(service=service, channel_id=channel_id, link_id=link_id)

    return AffiliateLinkRead.model_validate(link)


@router.patch(
    "/channels/{channel_id}/affiliate-links/{link_id}",
    response_model=AffiliateLinkRead,
    summary="Update an affiliate link",
)
async def update_link(
    channel_id: uuid.UUID,
    link_id: uuid.UUID,
    payload: AffiliateLinkUpdate,
    current_user: CurrentUser,
    db: DB,
) -> AffiliateLinkRead:
    await _owned_channel(channel_id, current_user.id, db)

    service = AffiliateService(db)
    await _owned_link(service=service, channel_id=channel_id, link_id=link_id)

    data = payload.model_dump(exclude_none=True)

    campaign_id = data.get("campaign_id")
    if campaign_id is not None:
        await _owned_campaign(service=service, channel_id=channel_id, campaign_id=campaign_id)

    publication_id = data.get("publication_id")
    if publication_id is not None:
        await _owned_publication(publication_id, current_user.id, db)

    try:
        link = await service.update_link(link_id, data)
        if not link or link.channel_id != channel_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Link not found")

        await db.commit()
        await db.refresh(link)
    except HTTPException:
        await db.rollback()
        raise
    except Exception:
        await db.rollback()
        logger.exception(
            "affiliate.link_update_failed",
            channel_id=str(channel_id),
            link_id=str(link_id),
            user_id=str(current_user.id),
        )
        raise

    return AffiliateLinkRead.model_validate(link)


@router.post(
    "/channels/{channel_id}/affiliate-links/{link_id}/mock-clicks",
    summary="Seed mock click events for development",
)
async def seed_mock_clicks(
    channel_id: uuid.UUID,
    link_id: uuid.UUID,
    payload: MockClicksRequest,
    current_user: CurrentUser,
    db: DB,
) -> dict[str, int]:
    _ensure_development_mock_allowed()

    await _owned_channel(channel_id, current_user.id, db)

    service = AffiliateService(db)
    await _owned_link(service=service, channel_id=channel_id, link_id=link_id)

    try:
        count = await service.generate_mock_clicks(
            link_id,
            count=payload.count,
            days_back=payload.days_back,
        )
        await db.commit()
    except ValueError as exc:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except Exception:
        await db.rollback()
        logger.exception(
            "affiliate.mock_click_seed_failed",
            channel_id=str(channel_id),
            link_id=str(link_id),
            user_id=str(current_user.id),
        )
        raise

    return {"seeded": count}


@router.get(
    "/channels/{channel_id}/affiliate-links/{link_id}/estimate",
    response_model=RevenueEstimateRead,
    summary="Project revenue for an affiliate link",
)
async def revenue_estimate(
    channel_id: uuid.UUID,
    link_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
    days: int = Query(default=30, ge=7, le=365),
    projected_clicks: int | None = Query(default=None, ge=0),
) -> RevenueEstimateRead:
    await _owned_channel(channel_id, current_user.id, db)

    service = AffiliateService(db)
    await _owned_link(service=service, channel_id=channel_id, link_id=link_id)

    estimate = await service.estimate_revenue(
        link_id,
        projected_clicks=projected_clicks,
        days=days,
    )

    return RevenueEstimateRead.model_validate(estimate)


@router.get(
    "/channels/{channel_id}/affiliate-links/{link_id}/history",
    response_model=list[ClickHistoryRow],
    summary="Daily click history for chart rendering",
)
async def click_history(
    channel_id: uuid.UUID,
    link_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
    days: int = Query(default=30, ge=7, le=365),
    include_mock: bool = Query(default=True),
) -> list[ClickHistoryRow]:
    await _owned_channel(channel_id, current_user.id, db)

    service = AffiliateService(db)
    await _owned_link(service=service, channel_id=channel_id, link_id=link_id)

    rows = await service.click_history(link_id, days=days, include_mock=include_mock)

    return [ClickHistoryRow.model_validate(row) for row in rows]


@router.post(
    "/affiliate-links/{link_id}/click",
    response_model=ClickRead,
    status_code=status.HTTP_201_CREATED,
    summary="Record a click event",
)
async def record_click(
    link_id: uuid.UUID,
    db: DB,
    request: Request,
    publication_id: uuid.UUID | None = Query(default=None),
    source: str | None = Query(default=None, max_length=64),
    ts: int | None = Query(default=None, description="Unix timestamp for HMAC signature"),
    nonce: str | None = Query(default=None, min_length=8, max_length=128),
    signature: str | None = Query(default=None, min_length=32, max_length=128),
    x_fingerprint: str | None = Header(default=None, alias="X-Fingerprint", max_length=256),
) -> ClickRead:
    service = AffiliateService(db)
    ip_address = _client_ip(request)
    user_agent = request.headers.get("user-agent")

    signature_error = _tracking_signature_error(
        event_type=TRACKING_EVENT_CLICK,
        link_id=link_id,
        ts=ts,
        nonce=nonce,
        signature=signature,
    )
    if signature_error:
        await _reject_tracking_event(
            db=db,
            service=service,
            event_type=TRACKING_EVENT_CLICK,
            reason=signature_error,
            link_id=link_id,
            source=source,
            ip_address=ip_address,
            user_agent=user_agent,
            fingerprint=x_fingerprint,
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid click signature",
        )

    if nonce is None:
        await _reject_tracking_event(
            db=db,
            service=service,
            event_type=TRACKING_EVENT_CLICK,
            reason="missing_nonce_after_signature_validation",
            link_id=link_id,
            source=source,
            ip_address=ip_address,
            user_agent=user_agent,
            fingerprint=x_fingerprint,
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid click signature",
        )

    nonce_ok = await service.register_tracking_nonce(
        link_id=link_id,
        event_type=TRACKING_EVENT_CLICK,
        nonce=nonce,
    )
    if not nonce_ok:
        await _reject_tracking_event(
            db=db,
            service=service,
            event_type=TRACKING_EVENT_CLICK,
            reason=TRACKING_REJECTION_REPLAY_NONCE,
            link_id=link_id,
            source=source,
            ip_address=ip_address,
            user_agent=user_agent,
            fingerprint=x_fingerprint,
            status_code=status.HTTP_409_CONFLICT,
            detail="Replay detected",
        )

    limited, limit_reason = await service.click_rate_limit_exceeded(
        link_id=link_id,
        ip_address=ip_address,
        per_ip_limit=settings.affiliate_click_rate_limit_per_ip,
        per_link_limit=settings.affiliate_click_rate_limit_per_link,
        window_seconds=settings.affiliate_click_rate_limit_window_seconds,
    )
    if limited:
        await _reject_tracking_event(
            db=db,
            service=service,
            event_type=TRACKING_EVENT_CLICK,
            reason=limit_reason or TRACKING_REJECTION_RATE_LIMIT,
            link_id=link_id,
            source=source,
            ip_address=ip_address,
            user_agent=user_agent,
            fingerprint=x_fingerprint,
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded",
        )

    try:
        click = await service.record_click(
            link_id,
            publication_id=publication_id,
            source=source,
            ip_address=ip_address,
            user_agent=user_agent,
            fingerprint=x_fingerprint,
        )
        await _audit_tracking_event(
            service=service,
            event_type=TRACKING_EVENT_CLICK,
            decision="accepted",
            reason=None,
            link_id=link_id,
            source=source,
            ip_address=ip_address,
            user_agent=user_agent,
            fingerprint=x_fingerprint,
        )
        await db.commit()
        await db.refresh(click)
    except ValueError as exc:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except Exception:
        await db.rollback()
        logger.exception(
            "affiliate.click_record_failed",
            link_id=str(link_id),
            publication_id=str(publication_id) if publication_id else None,
            source=source,
        )
        raise

    return ClickRead.model_validate(click)


@router.post(
    "/affiliate-links/{link_id}/conversion",
    response_model=AffiliateLinkRead,
    summary="Record a conversion",
)
async def record_conversion(
    link_id: uuid.UUID,
    payload: ConversionRequest,
    db: DB,
    request: Request,
    source: str | None = Query(default=None, max_length=64),
    ts: int | None = Query(default=None, description="Unix timestamp for HMAC signature"),
    nonce: str | None = Query(default=None, min_length=8, max_length=128),
    signature: str | None = Query(default=None, min_length=32, max_length=128),
    x_idempotency_key: str | None = Header(default=None, alias="X-Idempotency-Key", max_length=128),
    x_fingerprint: str | None = Header(default=None, alias="X-Fingerprint", max_length=256),
) -> AffiliateLinkRead:
    if not x_idempotency_key or not x_idempotency_key.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing X-Idempotency-Key",
        )

    service = AffiliateService(db)
    ip_address = _client_ip(request)
    user_agent = request.headers.get("user-agent")

    signature_error = _tracking_signature_error(
        event_type=TRACKING_EVENT_CONVERSION,
        link_id=link_id,
        ts=ts,
        nonce=nonce,
        signature=signature,
    )
    if signature_error:
        await _reject_tracking_event(
            db=db,
            service=service,
            event_type=TRACKING_EVENT_CONVERSION,
            reason=signature_error,
            link_id=link_id,
            source=source,
            ip_address=ip_address,
            user_agent=user_agent,
            fingerprint=x_fingerprint,
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid conversion signature",
        )

    if nonce is None:
        await _reject_tracking_event(
            db=db,
            service=service,
            event_type=TRACKING_EVENT_CONVERSION,
            reason="missing_nonce_after_signature_validation",
            link_id=link_id,
            source=source,
            ip_address=ip_address,
            user_agent=user_agent,
            fingerprint=x_fingerprint,
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid conversion signature",
        )

    nonce_ok = await service.register_tracking_nonce(
        link_id=link_id,
        event_type=TRACKING_EVENT_CONVERSION,
        nonce=nonce,
    )
    if not nonce_ok:
        await _reject_tracking_event(
            db=db,
            service=service,
            event_type=TRACKING_EVENT_CONVERSION,
            reason=TRACKING_REJECTION_REPLAY_NONCE,
            link_id=link_id,
            source=source,
            ip_address=ip_address,
            user_agent=user_agent,
            fingerprint=x_fingerprint,
            status_code=status.HTTP_409_CONFLICT,
            detail="Replay detected",
        )

    try:
        link = await service.record_conversion(
            link_id,
            publication_id=payload.publication_id,
            revenue_usd=payload.revenue_usd,
            idempotency_key=x_idempotency_key.strip(),
            source=source,
            ip_address=ip_address,
            user_agent=user_agent,
            fingerprint=x_fingerprint,
        )
        if not link:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Link not found")

        await _audit_tracking_event(
            service=service,
            event_type=TRACKING_EVENT_CONVERSION,
            decision="accepted",
            reason=None,
            link_id=link_id,
            source=source,
            ip_address=ip_address,
            user_agent=user_agent,
            fingerprint=x_fingerprint,
        )
        await db.commit()
        await db.refresh(link)
    except HTTPException:
        await db.rollback()
        raise
    except Exception:
        await db.rollback()
        logger.exception(
            "affiliate.conversion_record_failed",
            link_id=str(link_id),
            publication_id=str(payload.publication_id) if payload.publication_id else None,
            source=source,
        )
        raise

    return AffiliateLinkRead.model_validate(link)


@router.get(
    "/publications/{publication_id}/affiliate-links",
    response_model=list[PublicationAffiliateLinkRead],
    summary="List affiliate links attached to a publication",
)
async def list_publication_links(
    publication_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
) -> list[PublicationAffiliateLinkRead]:
    await _owned_publication(publication_id, current_user.id, db)

    service = AffiliateService(db)
    rows = await service.list_publication_links(publication_id)

    return [PublicationAffiliateLinkRead.model_validate(row) for row in rows]


@router.post(
    "/publications/{publication_id}/affiliate-links",
    response_model=PublicationAffiliateLinkRead,
    status_code=status.HTTP_201_CREATED,
    summary="Attach an affiliate link to a publication",
)
async def attach_link(
    publication_id: uuid.UUID,
    payload: AttachLinkRequest,
    current_user: CurrentUser,
    db: DB,
) -> PublicationAffiliateLinkRead:
    await _owned_publication(publication_id, current_user.id, db)

    service = AffiliateService(db)

    link = await service.get_link(payload.link_id)
    if not link:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Link not found")

    await _owned_channel(link.channel_id, current_user.id, db)

    if payload.campaign_id is not None:
        await _owned_campaign(
            service=service,
            channel_id=link.channel_id,
            campaign_id=payload.campaign_id,
        )

    try:
        publication_link = await service.attach_link_to_publication(
            publication_id=publication_id,
            link_id=payload.link_id,
            campaign_id=payload.campaign_id,
            position=payload.position,
            description_text=payload.description_text,
        )
        await db.commit()
        await db.refresh(publication_link)
    except Exception:
        await db.rollback()
        logger.exception(
            "affiliate.publication_attach_failed",
            publication_id=str(publication_id),
            link_id=str(payload.link_id),
            user_id=str(current_user.id),
        )
        raise

    return PublicationAffiliateLinkRead.model_validate(publication_link)


@router.delete(
    "/publications/{publication_id}/affiliate-links/{link_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Detach an affiliate link from a publication",
)
async def detach_link(
    publication_id: uuid.UUID,
    link_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
) -> None:
    await _owned_publication(publication_id, current_user.id, db)

    service = AffiliateService(db)
    link = await service.get_link(link_id)
    if not link:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Link not found")

    await _owned_channel(link.channel_id, current_user.id, db)

    try:
        removed = await service.detach_link_from_publication(
            publication_id=publication_id,
            link_id=link_id,
        )
        if not removed:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Attachment not found",
            )
        await db.commit()
    except HTTPException:
        await db.rollback()
        raise
    except Exception:
        await db.rollback()
        logger.exception(
            "affiliate.publication_detach_failed",
            publication_id=str(publication_id),
            link_id=str(link_id),
            user_id=str(current_user.id),
        )
        raise
