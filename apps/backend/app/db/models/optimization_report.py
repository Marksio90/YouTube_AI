"""
OptimizationReport — persisted growth brain snapshot.

One row per (channel, period_days) — upserted each time the optimizer runs.
Stores all AI-generated growth intelligence as JSONB for flexible querying.
"""
from __future__ import annotations

import uuid

from sqlalchemy import Float, ForeignKey, Integer, String, Text, UniqueConstraint, Index
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from typing import TYPE_CHECKING

from app.db.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.db.models.channel import Channel


class OptimizationReport(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "optimization_reports"
    __table_args__ = (
        UniqueConstraint("channel_id", "period_days", name="uq_opt_report_channel_period"),
        Index("ix_opt_report_channel_id", "channel_id"),
        Index("ix_opt_report_status", "status"),
    )

    channel_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("channels.id", ondelete="CASCADE"),
        nullable=False,
    )
    period_days: Mapped[int] = mapped_column(Integer, nullable=False, default=28)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    task_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Computed metric inputs (for display + debugging)
    channel_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    ctr_period: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    ctr_trend_pct: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    retention_period: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    retention_trend_pct: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    watch_time_hours: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    watch_time_trend_pct: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    views_period: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    views_trend_pct: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    # AI outputs
    growth_trajectory: Mapped[str] = mapped_column(String(20), nullable=False, default="new")
    growth_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")

    content_recommendations: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    next_topics: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    format_suggestions: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    watch_time_insights: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    ctr_insights: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    top_performer_patterns: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)

    channel: Mapped["Channel"] = relationship("Channel")

    def __repr__(self) -> str:
        return (
            f"<OptimizationReport ch={self.channel_id} "
            f"period={self.period_days}d trajectory={self.growth_trajectory} "
            f"score={self.growth_score:.1f}>"
        )
