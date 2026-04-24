import enum
import uuid
from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import Date, Enum, Float, ForeignKey, Integer, Numeric, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.db.models.channel import Channel
    from app.db.models.publication import Publication


class SnapshotType(str, enum.Enum):
    channel = "channel"
    publication = "publication"


class AnalyticsSnapshot(Base, UUIDMixin, TimestampMixin):
    """
    Point-in-time analytics record. One row per (channel, publication?, date).
    Channel-level snapshots have publication_id=NULL.
    """

    __tablename__ = "analytics_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "channel_id", "publication_id", "snapshot_date", "snapshot_type",
            name="uq_analytics_channel_pub_date_type",
        ),
    )

    channel_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("channels.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    publication_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("publications.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    snapshot_type: Mapped[SnapshotType] = mapped_column(
        Enum(SnapshotType, name="snapshot_type"),
        nullable=False,
        default=SnapshotType.channel,
    )

    # Reach
    impressions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    views: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    ctr: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    # Engagement
    watch_time_hours: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    avg_view_duration_seconds: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    like_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    comment_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Audience
    subscribers_gained: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    subscribers_lost: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Revenue
    revenue_usd: Mapped[float] = mapped_column(Numeric(12, 4), nullable=False, default=0.0)
    rpm: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    cpm: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    channel: Mapped["Channel"] = relationship("Channel", back_populates="analytics_snapshots")
    publication: Mapped["Publication | None"] = relationship(
        "Publication", back_populates="analytics"
    )

    def __repr__(self) -> str:
        return f"<AnalyticsSnapshot channel={self.channel_id} date={self.snapshot_date}>"
