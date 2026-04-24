import enum
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, DateTime, Enum, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.db.models.analytics import AnalyticsSnapshot
    from app.db.models.brief import Brief
    from app.db.models.channel import Channel
    from app.db.models.script import Script


class PublicationStatus(str, enum.Enum):
    draft = "draft"
    rendering = "rendering"
    review = "review"
    scheduled = "scheduled"
    published = "published"
    failed = "failed"


class PublicationVisibility(str, enum.Enum):
    public = "public"
    unlisted = "unlisted"
    private = "private"


class Publication(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "publications"

    channel_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("channels.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    script_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("scripts.id", ondelete="SET NULL"),
        nullable=True,
    )
    brief_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("briefs.id", ondelete="SET NULL"),
        nullable=True,
    )
    youtube_video_id: Mapped[str | None] = mapped_column(
        String(20), unique=True, nullable=True, index=True
    )
    title: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    tags: Mapped[list[str]] = mapped_column(ARRAY(String(100)), nullable=False, default=list)
    status: Mapped[PublicationStatus] = mapped_column(
        Enum(PublicationStatus, name="publication_status"),
        nullable=False,
        default=PublicationStatus.draft,
        index=True,
    )
    visibility: Mapped[PublicationVisibility] = mapped_column(
        Enum(PublicationVisibility, name="publication_visibility"),
        nullable=False,
        default=PublicationVisibility.private,
    )
    thumbnail_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    scheduled_at: Mapped[str | None] = mapped_column(DateTime(timezone=True), nullable=True)
    published_at: Mapped[str | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # YouTube metrics (periodically synced)
    view_count: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    like_count: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    comment_count: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    revenue_usd: Mapped[float] = mapped_column(Numeric(12, 4), nullable=False, default=0.0)

    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    channel: Mapped["Channel"] = relationship("Channel", back_populates="publications")
    script: Mapped["Script | None"] = relationship("Script", back_populates="publications")
    brief: Mapped["Brief | None"] = relationship("Brief")
    analytics: Mapped[list["AnalyticsSnapshot"]] = relationship(
        "AnalyticsSnapshot",
        back_populates="publication",
        lazy="select",
    )

    def __repr__(self) -> str:
        return f"<Publication {self.title[:60]} [{self.status}]>"
