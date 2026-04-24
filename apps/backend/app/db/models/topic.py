import enum
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Enum, ForeignKey, Numeric, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.db.models.brief import Brief
    from app.db.models.channel import Channel


class TopicStatus(str, enum.Enum):
    new = "new"
    researching = "researching"
    briefed = "briefed"
    rejected = "rejected"
    archived = "archived"


class TopicSource(str, enum.Enum):
    manual = "manual"
    trending = "trending"
    competitor = "competitor"
    ai_suggested = "ai_suggested"


class Topic(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "topics"

    channel_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("channels.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    keywords: Mapped[list[str]] = mapped_column(
        ARRAY(String(100)), nullable=False, default=list
    )
    trend_score: Mapped[float | None] = mapped_column(Numeric(4, 2), nullable=True)
    source: Mapped[TopicSource] = mapped_column(
        Enum(TopicSource, name="topic_source"),
        nullable=False,
        default=TopicSource.manual,
    )
    status: Mapped[TopicStatus] = mapped_column(
        Enum(TopicStatus, name="topic_status"),
        nullable=False,
        default=TopicStatus.new,
        index=True,
    )
    research_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    channel: Mapped["Channel"] = relationship("Channel", back_populates="topics")
    briefs: Mapped[list["Brief"]] = relationship(
        "Brief", back_populates="topic", lazy="select"
    )

    def __repr__(self) -> str:
        return f"<Topic {self.title[:60]}>"
