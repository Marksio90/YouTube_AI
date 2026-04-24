"""
PerformanceScore  — computed composite score per publication or channel.
Recommendation    — typed, actionable growth recommendation.

Both are write-once-per-period / upserted by the scoring worker.
"""
from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.db.models.channel import Channel
    from app.db.models.publication import Publication
    from app.db.models.topic import Topic


# ── PerformanceScore ──────────────────────────────────────────────────────────

class PerformanceScore(Base, UUIDMixin, TimestampMixin):
    """
    Point-in-time composite score.  One row per (channel, publication?, period_days).
    Channel-level scores have publication_id=NULL.

    Score dimensions (0–100 each):
      view_score      — views vs. channel median
      ctr_score       — CTR vs. 4% benchmark
      retention_score — avg_view_duration vs. target duration
      revenue_score   — RPM vs. $2.50 benchmark
      growth_score    — net subscriber rate vs. views

    composite = weighted average (see WEIGHTS in scoring service)
    """

    __tablename__ = "performance_scores"
    __table_args__ = (
        UniqueConstraint(
            "channel_id", "publication_id", "period_days",
            name="uq_perf_channel_pub_period",
        ),
        Index("ix_perf_channel_period", "channel_id", "period_days"),
        Index("ix_perf_pub_period", "publication_id", "period_days"),
    )

    channel_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("channels.id", ondelete="CASCADE"),
        nullable=False,
    )
    publication_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("publications.id", ondelete="CASCADE"),
        nullable=True,
    )
    period_days: Mapped[int] = mapped_column(Integer, nullable=False)

    # Composite (0–100)
    score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    # Dimensional (0–100 each)
    view_score:      Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    ctr_score:       Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    retention_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    revenue_score:   Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    growth_score:    Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    # Raw values used in computation (for transparency)
    raw_views:      Mapped[int]   = mapped_column(Integer, nullable=False, default=0)
    raw_ctr:        Mapped[float] = mapped_column(Float,   nullable=False, default=0.0)
    raw_retention:  Mapped[float] = mapped_column(Float,   nullable=False, default=0.0)
    raw_rpm:        Mapped[float] = mapped_column(Float,   nullable=False, default=0.0)
    raw_revenue:    Mapped[float] = mapped_column(Numeric(12, 4), nullable=False, default=0.0)
    raw_subs_net:   Mapped[int]   = mapped_column(Integer, nullable=False, default=0)

    # Rankings (NULL = not yet ranked)
    rank_in_channel: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rank_overall:    Mapped[int | None] = mapped_column(Integer, nullable=True)

    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    channel:     Mapped["Channel"]            = relationship("Channel")
    publication: Mapped["Publication | None"] = relationship("Publication")

    def __repr__(self) -> str:
        target = f"pub={self.publication_id}" if self.publication_id else "channel"
        return f"<PerformanceScore {target} period={self.period_days}d score={self.score:.1f}>"


# ── Recommendation ────────────────────────────────────────────────────────────

class RecommendationType(str, enum.Enum):
    improve_thumbnail = "improve_thumbnail"
    improve_hook      = "improve_hook"
    repeat_format     = "repeat_format"
    kill_topic        = "kill_topic"
    scale_topic       = "scale_topic"
    localize          = "localize"


class RecommendationPriority(str, enum.Enum):
    critical = "critical"
    high     = "high"
    medium   = "medium"
    low      = "low"


class RecommendationStatus(str, enum.Enum):
    pending   = "pending"
    applied   = "applied"
    dismissed = "dismissed"
    snoozed   = "snoozed"


class RecommendationSource(str, enum.Enum):
    rule = "rule"
    ai   = "ai"


class Recommendation(Base, UUIDMixin, TimestampMixin):
    """
    Typed, actionable growth recommendation.

    Each recommendation targets a specific channel (required), and optionally
    a publication or topic.  `rec_type` drives the UI card template.

    Status lifecycle:  pending → applied | dismissed | snoozed
    """

    __tablename__ = "recommendations"
    __table_args__ = (
        Index("ix_rec_channel_status", "channel_id", "status"),
        Index("ix_rec_channel_type",   "channel_id", "rec_type"),
    )

    channel_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("channels.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    publication_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("publications.id", ondelete="SET NULL"),
        nullable=True,
    )
    topic_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("topics.id", ondelete="SET NULL"),
        nullable=True,
    )

    rec_type: Mapped[RecommendationType] = mapped_column(
        Enum(RecommendationType, name="recommendation_type"),
        nullable=False,
        index=True,
    )
    priority: Mapped[RecommendationPriority] = mapped_column(
        Enum(RecommendationPriority, name="recommendation_priority"),
        nullable=False,
        default=RecommendationPriority.medium,
    )
    status: Mapped[RecommendationStatus] = mapped_column(
        Enum(RecommendationStatus, name="recommendation_status"),
        nullable=False,
        default=RecommendationStatus.pending,
        index=True,
    )
    source: Mapped[RecommendationSource] = mapped_column(
        Enum(RecommendationSource, name="recommendation_source"),
        nullable=False,
        default=RecommendationSource.rule,
    )

    title:     Mapped[str]          = mapped_column(String(200), nullable=False)
    body:      Mapped[str]          = mapped_column(Text, nullable=False)
    rationale: Mapped[str]          = mapped_column(Text, nullable=False)

    # Evidence
    metric_key:     Mapped[str | None] = mapped_column(String(50), nullable=True)
    metric_current: Mapped[float | None] = mapped_column(Float, nullable=True)
    metric_target:  Mapped[float | None] = mapped_column(Float, nullable=True)
    impact_label:   Mapped[str | None]   = mapped_column(String(100), nullable=True)

    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    actioned_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    channel:     Mapped["Channel"]            = relationship("Channel")
    publication: Mapped["Publication | None"] = relationship("Publication")
    topic:       Mapped["Topic | None"]       = relationship("Topic")

    def __repr__(self) -> str:
        return f"<Recommendation {self.rec_type.value} ch={self.channel_id} status={self.status.value}>"
