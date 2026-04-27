"""
Affiliate API — campaigns, links, video attachment, click tracking, revenue estimation.

Routes:
  # Campaigns
  GET    /channels/{id}/campaigns                    list campaigns
  POST   /channels/{id}/campaigns                    create campaign
  GET    /channels/{id}/campaigns/{cid}              get campaign
  PATCH  /channels/{id}/campaigns/{cid}              update campaign
  DELETE /channels/{id}/campaigns/{cid}              delete campaign
  GET    /channels/{id}/campaigns/{cid}/report       full campaign report

  # Links
  GET    /channels/{id}/affiliate-links              list links
  POST   /channels/{id}/affiliate-links              create link
  GET    /channels/{id}/affiliate-links/{lid}        get link
  PATCH  /channels/{id}/affiliate-links/{lid}        update link
  POST   /channels/{id}/affiliate-links/{lid}/mock-clicks  seed mock clicks
  GET    /channels/{id}/affiliate-links/{lid}/estimate     revenue projection
  GET    /channels/{id}/affiliate-links/{lid}/history      daily click history

  # Conversions (platform webhooks / manual)
  POST   /affiliate-links/{lid}/click               record click
  POST   /affiliate-links/{lid}/conversion          record conversion

  # Publication attachment
  GET    /publications/{id}/affiliate-links          list links on video
  POST   /publications/{id}/affiliate-links          attach link to video
  DELETE /publications/{id}/affiliate-links/{lid}    detach link from video
"""
import uuid
from datetime import datetime, timezone
import hashlib
import hmac

from fastapi import APIRouter, Header, HTTPException, Query, Request, status

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

router = APIRouter(tags=["affiliate"])


# ── helper ────────────────────────────────────────────────────────────────────

async def _owned_channel(channel_id: uuid.UUID, user_id: uuid.UUID, db) -> None:
    channel = await ChannelRepository(db).get_owned(channel_id, owner_id=user_id)
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")


def _client_ip(request: Request) -> str | None:
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    if request.client:
        return request.client.host
    return None


def _verify_tracking_signature(
    *,
    event_type: str,
    link_id: uuid.UUID,
    ts: int | None,
    nonce: str | None,
    signature: str | None,
) -> str | None:
    if not settings.affiliate_tracking_hmac_secret:
        return "hmac_secret_missing"
    if ts is None or not nonce or not signature:
        return "missing_signature_params"

    now = int(datetime.now(tz=timezone.utc).timestamp())
    if abs(now - ts) > settings.affiliate_tracking_max_skew_seconds:
        return "timestamp_out_of_window"

    payload = f"{event_type}:{link_id}:{ts}:{nonce}".encode("utf-8")
    expected = hmac.new(
        settings.affiliate_tracking_hmac_secret.encode("utf-8"),
        payload,
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(expected, signature):
        return "invalid_signature"
    return None


# ── Campaigns ─────────────────────────────────────────────────────────────────

@router.get(
    "/channels/{channel_id}/campaigns",
    response_model=list[CampaignRead],
    summary="List affiliate campaigns for a channel",
)
async def list_campaigns(
    channel_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
    status: CampaignStatusType | None = Query(default=None),
) -> list[CampaignRead]:
    await _owned_channel(channel_id, current_user.id, db)
    svc = AffiliateService(db)
    campaigns = await svc.list_campaigns(channel_id, status=status)
    return [CampaignRead.model_validate(c) for c in campaigns]


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
    svc = AffiliateService(db)
    campaign = await svc.create_campaign(
        channel_id=channel_id,
        data=payload.model_dump(exclude_none=True),
    )
    await db.commit()
    await db.refresh(campaign)
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
    svc = AffiliateService(db)
    campaign = await svc.get_campaign(campaign_id)
    if not campaign or campaign.channel_id != channel_id:
        raise HTTPException(status_code=404, detail="Campaign not found")
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
    svc = AffiliateService(db)
    campaign = await svc.update_campaign(
        campaign_id, payload.model_dump(exclude_none=True)
    )
    if not campaign or campaign.channel_id != channel_id:
        raise HTTPException(status_code=404, detail="Campaign not found")
    await db.commit()
    await db.refresh(campaign)
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
    svc = AffiliateService(db)
    campaign = await svc.get_campaign(campaign_id)
    if not campaign or campaign.channel_id != channel_id:
        raise HTTPException(status_code=404, detail="Campaign not found")
    await svc.delete_campaign(campaign_id)
    await db.commit()


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
    svc = AffiliateService(db)
    campaign = await svc.get_campaign(campaign_id)
    if not campaign or campaign.channel_id != channel_id:
        raise HTTPException(status_code=404, detail="Campaign not found")
    report = await svc.campaign_report(campaign_id)
    return CampaignReportRead.model_validate(report)


# ── Affiliate Links ───────────────────────────────────────────────────────────

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
    svc = AffiliateService(db)
    links = await svc.list_links(channel_id, campaign_id=campaign_id, active_only=active_only)
    return [AffiliateLinkRead.model_validate(l) for l in links]


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
    svc = AffiliateService(db)
    link = await svc.create_link(
        channel_id=channel_id,
        data=payload.model_dump(exclude_none=True),
    )
    await db.commit()
    await db.refresh(link)
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
    svc = AffiliateService(db)
    link = await svc.get_link(link_id)
    if not link or link.channel_id != channel_id:
        raise HTTPException(status_code=404, detail="Link not found")
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
    svc = AffiliateService(db)
    link = await svc.update_link(link_id, payload.model_dump(exclude_none=True))
    if not link or link.channel_id != channel_id:
        raise HTTPException(status_code=404, detail="Link not found")
    await db.commit()
    await db.refresh(link)
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
) -> dict:
    await _owned_channel(channel_id, current_user.id, db)
    svc = AffiliateService(db)
    link = await svc.get_link(link_id)
    if not link or link.channel_id != channel_id:
        raise HTTPException(status_code=404, detail="Link not found")
    count = await svc.generate_mock_clicks(
        link_id, count=payload.count, days_back=payload.days_back
    )
    await db.commit()
    return {"seeded": count}


@router.get(
    "/channels/{channel_id}/affiliate-links/{link_id}/estimate",
    response_model=RevenueEstimateRead,
    summary="Project 30-day revenue for an affiliate link",
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
    svc = AffiliateService(db)
    link = await svc.get_link(link_id)
    if not link or link.channel_id != channel_id:
        raise HTTPException(status_code=404, detail="Link not found")
    estimate = await svc.estimate_revenue(
        link_id, projected_clicks=projected_clicks, days=days
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
    svc = AffiliateService(db)
    link = await svc.get_link(link_id)
    if not link or link.channel_id != channel_id:
        raise HTTPException(status_code=404, detail="Link not found")
    rows = await svc.click_history(link_id, days=days, include_mock=include_mock)
    return [ClickHistoryRow.model_validate(r) for r in rows]


# ── Click / Conversion (public or webhook) ────────────────────────────────────

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
    ts: int | None = Query(default=None, description="unix timestamp for HMAC signature"),
    nonce: str | None = Query(default=None, max_length=128),
    signature: str | None = Query(default=None, max_length=128),
    x_fingerprint: str | None = Header(default=None, alias="X-Fingerprint"),
) -> ClickRead:
    svc = AffiliateService(db)
    ip_address = _client_ip(request)
    user_agent = request.headers.get("user-agent")
    signature_error = _verify_tracking_signature(
        event_type="click",
        link_id=link_id,
        ts=ts,
        nonce=nonce,
        signature=signature,
    )
    if signature_error:
        await svc.audit_security_event(
            event_type="click",
            decision="rejected",
            reason=signature_error,
            link_id=link_id,
            source=source,
            ip_address=ip_address,
            user_agent=user_agent,
            fingerprint=x_fingerprint,
        )
        await db.commit()
        raise HTTPException(status_code=401, detail="Invalid click signature")

    nonce_ok = await svc.register_tracking_nonce(link_id=link_id, event_type="click", nonce=nonce)
    if not nonce_ok:
        await svc.audit_security_event(
            event_type="click",
            decision="rejected",
            reason="replay_nonce",
            link_id=link_id,
            source=source,
            ip_address=ip_address,
            user_agent=user_agent,
            fingerprint=x_fingerprint,
        )
        await db.commit()
        raise HTTPException(status_code=409, detail="Replay detected")

    limited, limit_reason = await svc.click_rate_limit_exceeded(
        link_id=link_id,
        ip_address=ip_address,
        per_ip_limit=settings.affiliate_click_rate_limit_per_ip,
        per_link_limit=settings.affiliate_click_rate_limit_per_link,
        window_seconds=settings.affiliate_click_rate_limit_window_seconds,
    )
    if limited:
        await svc.audit_security_event(
            event_type="click",
            decision="rejected",
            reason=limit_reason,
            link_id=link_id,
            source=source,
            ip_address=ip_address,
            user_agent=user_agent,
            fingerprint=x_fingerprint,
        )
        await db.commit()
        raise HTTPException(status_code=429, detail="Rate limit exceeded")

    try:
        click = await svc.record_click(
            link_id,
            publication_id=publication_id,
            source=source,
            ip_address=ip_address,
            user_agent=user_agent,
            fingerprint=x_fingerprint,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    await svc.audit_security_event(
        event_type="click",
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
    return ClickRead.model_validate(click)


@router.post(
    "/affiliate-links/{link_id}/conversion",
    response_model=AffiliateLinkRead,
    summary="Record a conversion (webhook or manual entry)",
)
async def record_conversion(
    link_id: uuid.UUID,
    payload: ConversionRequest,
    db: DB,
    request: Request,
    source: str | None = Query(default=None, max_length=64),
    ts: int | None = Query(default=None, description="unix timestamp for HMAC signature"),
    nonce: str | None = Query(default=None, max_length=128),
    signature: str | None = Query(default=None, max_length=128),
    x_idempotency_key: str | None = Header(default=None, alias="X-Idempotency-Key"),
    x_fingerprint: str | None = Header(default=None, alias="X-Fingerprint"),
) -> AffiliateLinkRead:
    if not x_idempotency_key:
        raise HTTPException(status_code=400, detail="Missing X-Idempotency-Key")
    svc = AffiliateService(db)
    ip_address = _client_ip(request)
    user_agent = request.headers.get("user-agent")
    signature_error = _verify_tracking_signature(
        event_type="conversion",
        link_id=link_id,
        ts=ts,
        nonce=nonce,
        signature=signature,
    )
    if signature_error:
        await svc.audit_security_event(
            event_type="conversion",
            decision="rejected",
            reason=signature_error,
            link_id=link_id,
            source=source,
            ip_address=ip_address,
            user_agent=user_agent,
            fingerprint=x_fingerprint,
        )
        await db.commit()
        raise HTTPException(status_code=401, detail="Invalid conversion signature")

    nonce_ok = await svc.register_tracking_nonce(
        link_id=link_id,
        event_type="conversion",
        nonce=nonce,
    )
    if not nonce_ok:
        await svc.audit_security_event(
            event_type="conversion",
            decision="rejected",
            reason="replay_nonce",
            link_id=link_id,
            source=source,
            ip_address=ip_address,
            user_agent=user_agent,
            fingerprint=x_fingerprint,
        )
        await db.commit()
        raise HTTPException(status_code=409, detail="Replay detected")

    link = await svc.record_conversion(
        link_id,
        publication_id=payload.publication_id,
        revenue_usd=payload.revenue_usd,
        idempotency_key=x_idempotency_key,
        source=source,
        ip_address=ip_address,
        user_agent=user_agent,
        fingerprint=x_fingerprint,
    )
    if not link:
        raise HTTPException(status_code=404, detail="Link not found")
    await svc.audit_security_event(
        event_type="conversion",
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
    return AffiliateLinkRead.model_validate(link)


# ── Publication attachment ────────────────────────────────────────────────────

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
    svc = AffiliateService(db)
    rows = await svc.list_publication_links(publication_id)
    return [PublicationAffiliateLinkRead.model_validate(r) for r in rows]


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
    svc = AffiliateService(db)
    pal = await svc.attach_link_to_publication(
        publication_id=publication_id,
        link_id=payload.link_id,
        campaign_id=payload.campaign_id,
        position=payload.position,
        description_text=payload.description_text,
    )
    await db.commit()
    await db.refresh(pal)
    return PublicationAffiliateLinkRead.model_validate(pal)


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
    svc = AffiliateService(db)
    removed = await svc.detach_link_from_publication(
        publication_id=publication_id, link_id=link_id
    )
    if not removed:
        raise HTTPException(status_code=404, detail="Attachment not found")
    await db.commit()
