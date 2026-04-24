import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field


# ── AnalyticsSnapshot ─────────────────────────────────────────────────────────

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


# ── PerformanceScore ──────────────────────────────────────────────────────────

class DimensionalScores(BaseModel):
    view_score:      float = Field(ge=0, le=100)
    ctr_score:       float = Field(ge=0, le=100)
    retention_score: float = Field(ge=0, le=100)
    revenue_score:   float = Field(ge=0, le=100)
    growth_score:    float = Field(ge=0, le=100)


class PerformanceScoreRead(BaseModel):
    id: uuid.UUID
    channel_id: uuid.UUID
    publication_id: uuid.UUID | None

    period_days: int
    score: float                    # 0–100 composite
    dimensions: DimensionalScores
    raw_views: int
    raw_ctr: float
    raw_retention: float
    raw_rpm: float
    raw_revenue: float
    raw_subs_net: int

    rank_in_channel: int | None
    rank_overall:    int | None
    computed_at: datetime

    model_config = {"from_attributes": True}

    @classmethod
    def from_orm_with_dims(cls, obj) -> "PerformanceScoreRead":
        return cls(
            id=obj.id,
            channel_id=obj.channel_id,
            publication_id=obj.publication_id,
            period_days=obj.period_days,
            score=obj.score,
            dimensions=DimensionalScores(
                view_score=obj.view_score,
                ctr_score=obj.ctr_score,
                retention_score=obj.retention_score,
                revenue_score=obj.revenue_score,
                growth_score=obj.growth_score,
            ),
            raw_views=obj.raw_views,
            raw_ctr=obj.raw_ctr,
            raw_retention=obj.raw_retention,
            raw_rpm=obj.raw_rpm,
            raw_revenue=float(obj.raw_revenue),
            raw_subs_net=obj.raw_subs_net,
            rank_in_channel=obj.rank_in_channel,
            rank_overall=obj.rank_overall,
            computed_at=obj.computed_at,
        )


# ── Rankings ──────────────────────────────────────────────────────────────────

class TopicRankEntry(BaseModel):
    topic_id: uuid.UUID
    title: str
    score: float                    # composite rank score
    trend_score: float | None
    publication_count: int
    avg_views: float
    avg_perf_score: float
    total_revenue: float
    recommendation: Literal["pursue", "consider", "monitor", "kill"]


class ChannelRankEntry(BaseModel):
    channel_id: uuid.UUID
    name: str
    niche: str
    score: float
    rank: int
    total_views: int
    total_revenue: float
    avg_ctr: float
    net_subscribers: int


class TopicRankingResponse(BaseModel):
    period_days: int
    entries: list[TopicRankEntry]


class ChannelRankingResponse(BaseModel):
    period_days: int
    entries: list[ChannelRankEntry]


# ── Recommendations ───────────────────────────────────────────────────────────

RecommendationType = Literal[
    "improve_thumbnail",
    "improve_hook",
    "repeat_format",
    "kill_topic",
    "scale_topic",
    "localize",
]

RecommendationPriority = Literal["critical", "high", "medium", "low"]
RecommendationStatus   = Literal["pending", "applied", "dismissed", "snoozed"]


class RecommendationRead(BaseModel):
    id: uuid.UUID
    channel_id: uuid.UUID
    publication_id: uuid.UUID | None
    topic_id: uuid.UUID | None

    rec_type:  RecommendationType
    priority:  RecommendationPriority
    status:    RecommendationStatus
    source:    Literal["rule", "ai"]

    title:     str
    body:      str
    rationale: str

    metric_key:     str | None
    metric_current: float | None
    metric_target:  float | None
    impact_label:   str | None

    expires_at:  datetime | None
    actioned_at: datetime | None
    created_at:  datetime

    model_config = {"from_attributes": True}


class RecommendationActionRequest(BaseModel):
    note: str | None = None
