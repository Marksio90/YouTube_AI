import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

CampaignStatusType = Literal["draft", "active", "paused", "completed", "archived"]
AffiliatePlatformType = Literal["amazon", "impact", "shareasale", "cj", "custom"]
CommissionType = Literal["percentage", "fixed"]


# ── Campaign ──────────────────────────────────────────────────────────────────

class CampaignRead(BaseModel):
    id: uuid.UUID
    channel_id: uuid.UUID
    name: str
    description: str | None
    status: CampaignStatusType
    niche_tags: list[str]
    topic_ids: list[str]
    starts_at: datetime | None
    ends_at: datetime | None
    target_clicks: int | None
    target_conversions: int | None
    target_revenue_usd: float | None
    budget_usd: float | None
    total_clicks: int
    total_conversions: int
    total_revenue_usd: float
    clicks_pct: float | None
    revenue_pct: float | None
    notes: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class CampaignCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    status: CampaignStatusType = "draft"
    niche_tags: list[str] = Field(default_factory=list)
    topic_ids: list[str] = Field(default_factory=list)
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    target_clicks: int | None = Field(default=None, ge=0)
    target_conversions: int | None = Field(default=None, ge=0)
    target_revenue_usd: float | None = Field(default=None, ge=0)
    budget_usd: float | None = Field(default=None, ge=0)
    notes: str | None = None


class CampaignUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    status: CampaignStatusType | None = None
    niche_tags: list[str] | None = None
    topic_ids: list[str] | None = None
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    target_clicks: int | None = None
    target_conversions: int | None = None
    target_revenue_usd: float | None = None
    budget_usd: float | None = None
    notes: str | None = None


# ── AffiliateLink ─────────────────────────────────────────────────────────────

class AffiliateLinkRead(BaseModel):
    id: uuid.UUID
    channel_id: uuid.UUID
    publication_id: uuid.UUID | None
    campaign_id: uuid.UUID | None
    platform: AffiliatePlatformType
    name: str
    destination_url: str
    slug: str | None
    tracking_id: str | None
    niche_tags: list[str]
    commission_type: CommissionType
    commission_value: float
    avg_order_value_usd: float
    total_clicks: int
    total_conversions: int
    total_revenue_usd: float
    commission_per_conversion_usd: float
    effective_cvr: float
    is_active: bool
    expires_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class AffiliateLinkCreate(BaseModel):
    platform: AffiliatePlatformType = "custom"
    name: str = Field(min_length=1, max_length=200)
    destination_url: str
    slug: str | None = Field(default=None, max_length=100)
    tracking_id: str | None = None
    niche_tags: list[str] = Field(default_factory=list)
    commission_type: CommissionType = "percentage"
    commission_value: float = Field(ge=0, default=0.0)
    avg_order_value_usd: float = Field(ge=0, default=50.0)
    campaign_id: uuid.UUID | None = None
    publication_id: uuid.UUID | None = None
    is_active: bool = True
    expires_at: datetime | None = None


class AffiliateLinkUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    destination_url: str | None = None
    slug: str | None = None
    tracking_id: str | None = None
    niche_tags: list[str] | None = None
    commission_type: CommissionType | None = None
    commission_value: float | None = Field(default=None, ge=0)
    avg_order_value_usd: float | None = Field(default=None, ge=0)
    campaign_id: uuid.UUID | None = None
    is_active: bool | None = None
    expires_at: datetime | None = None


# ── PublicationAffiliateLink ──────────────────────────────────────────────────

class PublicationAffiliateLinkRead(BaseModel):
    publication_id: uuid.UUID
    link_id: uuid.UUID
    campaign_id: uuid.UUID | None
    position: int
    description_text: str | None
    clicks: int
    conversions: int
    revenue_usd: float
    created_at: datetime

    model_config = {"from_attributes": True}


class AttachLinkRequest(BaseModel):
    link_id: uuid.UUID
    campaign_id: uuid.UUID | None = None
    position: int = Field(default=0, ge=0)
    description_text: str | None = Field(default=None, max_length=500)


# ── Click / Conversion ────────────────────────────────────────────────────────

class ClickRead(BaseModel):
    id: uuid.UUID
    link_id: uuid.UUID
    publication_id: uuid.UUID | None
    campaign_id: uuid.UUID | None
    clicked_at: datetime
    is_mock: bool
    estimated_revenue_usd: float

    model_config = {"from_attributes": True}


class ConversionRequest(BaseModel):
    publication_id: uuid.UUID | None = None
    revenue_usd: float | None = Field(default=None, ge=0)


class MockClicksRequest(BaseModel):
    count: int = Field(default=30, ge=1, le=500)
    days_back: int = Field(default=30, ge=1, le=365)


# ── Revenue estimation ────────────────────────────────────────────────────────

class RevenueEstimateRead(BaseModel):
    link_id: str
    link_name: str
    platform: str
    days: int
    clicks_per_day: float
    projected_clicks: int
    effective_cvr: float
    projected_conversions: int
    commission_per_conversion_usd: float
    projected_revenue_usd: float
    confidence: Literal["actual", "estimated"]


# ── Campaign report ───────────────────────────────────────────────────────────

class CampaignLinkRow(BaseModel):
    link_id: str
    name: str
    platform: str
    total_clicks: int
    total_conversions: int
    total_revenue_usd: float
    effective_cvr_pct: float
    commission_per_conversion_usd: float
    is_active: bool


class CampaignReportRead(BaseModel):
    campaign_id: str
    name: str
    status: str
    total_clicks: int
    total_conversions: int
    total_revenue_usd: float
    clicks_pct: float | None
    revenue_pct: float | None
    clicks_last_7d: int
    target_clicks: int | None
    target_conversions: int | None
    target_revenue_usd: float | None
    budget_usd: float | None
    links: list[CampaignLinkRow]
    link_count: int


# ── Click history ─────────────────────────────────────────────────────────────

class ClickHistoryRow(BaseModel):
    date: str
    clicks: int
