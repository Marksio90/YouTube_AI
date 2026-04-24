import enum
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Enum, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.db.models.channel import Channel
    from app.db.models.script import Script
    from app.db.models.topic import Topic


class BriefStatus(str, enum.Enum):
    draft = "draft"
    approved = "approved"
    rejected = "rejected"
    archived = "archived"


class Brief(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "briefs"

    channel_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("channels.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    topic_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("topics.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    target_audience: Mapped[str] = mapped_column(Text, nullable=False, default="")
    key_points: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    seo_keywords: Mapped[list[str]] = mapped_column(
        ARRAY(String(100)), nullable=False, default=list
    )
    competitor_urls: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    estimated_duration_seconds: Mapped[int] = mapped_column(
        Integer, nullable=False, default=600
    )
    tone: Mapped[str] = mapped_column(String(50), nullable=False, default="educational")
    status: Mapped[BriefStatus] = mapped_column(
        Enum(BriefStatus, name="brief_status"),
        nullable=False,
        default=BriefStatus.draft,
        index=True,
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    channel: Mapped["Channel"] = relationship("Channel", back_populates="briefs")
    topic: Mapped["Topic | None"] = relationship("Topic", back_populates="briefs")
    scripts: Mapped[list["Script"]] = relationship(
        "Script", back_populates="brief", lazy="select"
    )

    def __repr__(self) -> str:
        return f"<Brief {self.title[:60]}>"
