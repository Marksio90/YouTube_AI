import enum
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, DateTime, Enum, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.db.models.channel import Channel
    from app.db.models.script import Script


class VideoStatus(str, enum.Enum):
    draft = "draft"
    scripting = "scripting"
    producing = "producing"
    rendering = "rendering"
    review = "review"
    scheduled = "scheduled"
    published = "published"
    failed = "failed"


class VideoVisibility(str, enum.Enum):
    public = "public"
    unlisted = "unlisted"
    private = "private"


class Video(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "videos"

    channel_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("channels.id", ondelete="CASCADE"), nullable=False, index=True
    )
    script_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("scripts.id", ondelete="SET NULL"), nullable=True
    )
    pipeline_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    youtube_video_id: Mapped[str | None] = mapped_column(
        String(20), unique=True, nullable=True, index=True
    )
    title: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[VideoStatus] = mapped_column(
        Enum(VideoStatus, name="video_status"),
        nullable=False,
        default=VideoStatus.draft,
        index=True,
    )
    visibility: Mapped[VideoVisibility] = mapped_column(
        Enum(VideoVisibility, name="video_visibility"),
        nullable=False,
        default=VideoVisibility.private,
    )
    thumbnail_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    scheduled_at: Mapped[str | None] = mapped_column(DateTime(timezone=True), nullable=True)
    published_at: Mapped[str | None] = mapped_column(DateTime(timezone=True), nullable=True)

    view_count: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    like_count: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    comment_count: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    revenue_usd: Mapped[float] = mapped_column(Numeric(12, 4), nullable=False, default=0.0)

    channel: Mapped["Channel"] = relationship("Channel", back_populates="videos")
    script: Mapped["Script | None"] = relationship("Script", back_populates="videos")

    def __repr__(self) -> str:
        return f"<Video {self.title[:40]}>"
