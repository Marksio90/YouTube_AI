import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field


# ── Enums ─────────────────────────────────────────────────────────────────────

RevenueSourceType = Literal["ads", "affiliate", "products", "sponsorship"]
AffiliatePlatformType = Literal["amazon", "impact", "shareasale", "cj", "custom"]
CommissionType = Literal["percentage", "fixed"]


# ── RevenueStream ─────────────────────────────────────────────────────────────

class RevenueStreamRead(BaseModel):
    id: uuid.UUID
    channel_id: uuid.UUID
    publication_id: uuid.UUID | None
    source: RevenueSourceType
    period_start: date
    period_end: date
    revenue_usd: float
    impressions: int
    clicks: int
    conversions: int
    rpm: float
    cpm: float
    commission_rate: float | None
    cost_usd: float
    roi_pct: float | None
    is_estimated: bool
    notes: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class RevenueStreamCreate(BaseModel):
    channel_id: uuid.UUID
    publication_id: uuid.UUID | None = None
    source: RevenueSourceType
    period_start: date
    period_end: date
    revenue_usd: float = Field(ge=0)
    impressions: int = Field(ge=0, default=0)
    clicks: int = Field(ge=0, default=0)
    conversions: int = Field(ge=0, default=0)
    rpm: float = Field(ge=0, default=0.0)
    cpm: float = Field(ge=0, default=0.0)
    commission_rate: float | None = None
    cost_usd: float = Field(ge=0, default=0.0)
    is_estimated: bool = True
    notes: str | None = None


# ── AffiliateLink ─────────────────────────────────────────────────────────────

class AffiliateLinkRead(BaseModel):
    id: uuid.UUID
    channel_id: uuid.UUID
    publication_id: uuid.UUID | None
    platform: AffiliatePlatformType
    name: str
    destination_url: str
    slug: str | None
    tracking_id: str | None
    commission_type: CommissionType
    commission_value: float
    total_clicks: int
    total_conversions: int
    total_revenue_usd: float
    is_active: bool
    expires_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class AffiliateLinkCreate(BaseModel):
    channel_id: uuid.UUID
    publication_id: uuid.UUID | None = None
    platform: AffiliatePlatformType = "custom"
    name: str = Field(min_length=1, max_length=200)
    destination_url: str = Field(min_length=1)
    slug: str | None = Field(None, max_length=100)
    tracking_id: str | None = None
    commission_type: CommissionType = "percentage"
    commission_value: float = Field(ge=0, default=0.0)
    expires_at: datetime | None = None


class AffiliateLinkUpdate(BaseModel):
    name: str | None = None
    destination_url: str | None = None
    tracking_id: str | None = None
    commission_type: CommissionType | None = None
    commission_value: float | None = None
    is_active: bool | None = None
    expires_at: datetime | None = None


# ── Aggregated views ──────────────────────────────────────────────────────────

class RevenueBySource(BaseModel):
    source: RevenueSourceType
    revenue_usd: float
    share_pct: float          # 0–100, fraction of total revenue
    roi_pct: float | None


class ChannelRevenueOverview(BaseModel):
    channel_id: uuid.UUID
    period_start: date
    period_end: date
    total_revenue_usd: float
    total_cost_usd: float
    overall_roi_pct: float | None
    by_source: list[RevenueBySource]
    top_streams: list[RevenueStreamRead]


class PublicationRevenueOverview(BaseModel):
    publication_id: uuid.UUID
    channel_id: uuid.UUID
    total_revenue_usd: float
    total_cost_usd: float
    roi_pct: float | None
    by_source: list[RevenueBySource]
    streams: list[RevenueStreamRead]


class ROISummary(BaseModel):
    channel_id: uuid.UUID
    period_start: date
    period_end: date
    total_revenue_usd: float
    total_cost_usd: float
    roi_pct: float | None
    revenue_per_video: float          # total_revenue / num videos in period
    cost_per_video: float
    best_publication_id: uuid.UUID | None
    best_publication_roi: float | None
    worst_publication_id: uuid.UUID | None
    worst_publication_roi: float | None
