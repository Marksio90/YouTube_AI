import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field


class AnalyticsSnapshotCreate(BaseModel):
    channel_id: uuid.UUID
    publication_id: uuid.UUID | None = None
    snapshot_date: date
    snapshot_type: str = "channel"
    impressions: int = 0
    views: int = 0
    ctr: float = 0.0
    watch_time_hours: float = 0.0
    avg_view_duration_seconds: float = 0.0
    like_count: int = 0
    comment_count: int = 0
    subscribers_gained: int = 0
    subscribers_lost: int = 0
    revenue_usd: float = 0.0
    rpm: float = 0.0
    cpm: float = 0.0


class AnalyticsSnapshotRead(BaseModel):
    id: uuid.UUID
    channel_id: uuid.UUID
    publication_id: uuid.UUID | None
    snapshot_date: date
    snapshot_type: str
    impressions: int
    views: int
    ctr: float
    watch_time_hours: float
    avg_view_duration_seconds: float
    like_count: int
    comment_count: int
    subscribers_gained: int
    subscribers_lost: int
    revenue_usd: float
    rpm: float
    cpm: float
    created_at: datetime

    model_config = {"from_attributes": True}


class AnalyticsPeriodQuery(BaseModel):
    channel_id: uuid.UUID
    date_from: date
    date_to: date
    publication_id: uuid.UUID | None = None


class AnalyticsAggregate(BaseModel):
    channel_id: uuid.UUID
    date_from: date
    date_to: date
    total_views: int
    total_watch_time_hours: float
    total_revenue_usd: float
    subscribers_gained: int
    subscribers_lost: int
    net_subscribers: int
    avg_rpm: float
    avg_ctr: float
    daily_snapshots: list[AnalyticsSnapshotRead] = Field(default_factory=list)
