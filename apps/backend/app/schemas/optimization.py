import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class ContentRecommendationRead(BaseModel):
    priority: Literal["critical", "high", "medium", "low"]
    rec_type: str
    title: str
    body: str
    metric_key: str | None = None
    metric_current: float | None = None
    metric_target: float | None = None
    impact_label: str | None = None
    evidence: str = ""


class NextTopicRead(BaseModel):
    title: str
    rationale: str
    urgency: Literal["high", "medium", "low"]
    estimated_ctr: float
    estimated_retention_pct: float
    estimated_views: int
    keyword_angle: str


class FormatSuggestionRead(BaseModel):
    format_label: str
    duration_range_seconds: list[int]
    opening_style: str
    structure: str
    rationale: str
    evidence: str
    expected_retention_lift_pct: float


class WatchTimeInsightRead(BaseModel):
    pattern: str
    impact: str
    action: str
    priority: Literal["critical", "high", "medium", "low"]


class CTRInsightRead(BaseModel):
    pattern: str
    evidence: str
    action: str
    expected_ctr_lift_pct: float


class OptimizationReportRead(BaseModel):
    id: uuid.UUID
    channel_id: uuid.UUID
    period_days: int
    status: str
    task_id: str | None

    # Metric snapshot
    channel_score: float
    ctr_period_pct: float
    ctr_trend_pct: float
    retention_period_pct: float
    retention_trend_pct: float
    watch_time_hours: float
    watch_time_trend_pct: float
    views_period: int
    views_trend_pct: float

    # AI synthesis
    growth_trajectory: Literal["accelerating", "stable", "declining", "new"]
    growth_score: float
    summary: str

    content_recommendations: list[ContentRecommendationRead] = Field(default_factory=list)
    next_topics: list[NextTopicRead] = Field(default_factory=list)
    format_suggestions: list[FormatSuggestionRead] = Field(default_factory=list)
    watch_time_insights: list[WatchTimeInsightRead] = Field(default_factory=list)
    ctr_insights: list[CTRInsightRead] = Field(default_factory=list)
    top_performer_patterns: list[str] = Field(default_factory=list)

    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_orm(cls, obj: Any) -> "OptimizationReportRead":
        def _parse_list(raw: Any, klass) -> list:
            if not raw:
                return []
            return [klass(**item) if isinstance(item, dict) else item for item in raw]

        return cls(
            id=obj.id,
            channel_id=obj.channel_id,
            period_days=obj.period_days,
            status=obj.status,
            task_id=obj.task_id,
            channel_score=obj.channel_score or 0.0,
            ctr_period_pct=round((obj.ctr_period or 0.0) * 100, 2),
            ctr_trend_pct=obj.ctr_trend_pct or 0.0,
            retention_period_pct=round((obj.retention_period or 0.0) * 100, 1),
            retention_trend_pct=obj.retention_trend_pct or 0.0,
            watch_time_hours=obj.watch_time_hours or 0.0,
            watch_time_trend_pct=obj.watch_time_trend_pct or 0.0,
            views_period=obj.views_period or 0,
            views_trend_pct=obj.views_trend_pct or 0.0,
            growth_trajectory=obj.growth_trajectory or "new",
            growth_score=obj.growth_score or 0.0,
            summary=obj.summary or "",
            content_recommendations=_parse_list(obj.content_recommendations, ContentRecommendationRead),
            next_topics=_parse_list(obj.next_topics, NextTopicRead),
            format_suggestions=_parse_list(obj.format_suggestions, FormatSuggestionRead),
            watch_time_insights=_parse_list(obj.watch_time_insights, WatchTimeInsightRead),
            ctr_insights=_parse_list(obj.ctr_insights, CTRInsightRead),
            top_performer_patterns=obj.top_performer_patterns or [],
            created_at=obj.created_at,
            updated_at=obj.updated_at,
        )

    model_config = {"from_attributes": True}


class OptimizationGenerateRequest(BaseModel):
    period_days: int = Field(default=28, ge=7, le=90)
    force: bool = False


class PublicationInsightsRead(BaseModel):
    publication_id: str
    title: str
    perf_score: float
    ctr_score: float
    retention_score: float
    raw_ctr_pct: float
    raw_retention_pct: float
    total_views: int
    rank_in_channel: int | None
    daily_trend: list[dict[str, Any]]
    quick_wins: list[dict[str, Any]]
