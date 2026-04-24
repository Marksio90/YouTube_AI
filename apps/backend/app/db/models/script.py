import enum
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Enum, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.db.models.video import Video


class ScriptTone(str, enum.Enum):
    educational = "educational"
    entertaining = "entertaining"
    inspirational = "inspirational"
    controversial = "controversial"
    news = "news"


class ScriptStatus(str, enum.Enum):
    draft = "draft"
    review = "review"
    approved = "approved"
    rejected = "rejected"
    archived = "archived"


class Script(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "scripts"

    channel_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("channels.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    hook: Mapped[str] = mapped_column(Text, nullable=False, default="")
    body: Mapped[str] = mapped_column(Text, nullable=False, default="")
    cta: Mapped[str] = mapped_column(Text, nullable=False, default="")
    keywords: Mapped[list[str]] = mapped_column(ARRAY(String(100)), nullable=False, default=list)
    target_duration_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=600)
    tone: Mapped[ScriptTone] = mapped_column(
        Enum(ScriptTone, name="script_tone"),
        nullable=False,
        default=ScriptTone.educational,
    )
    status: Mapped[ScriptStatus] = mapped_column(
        Enum(ScriptStatus, name="script_status"),
        nullable=False,
        default=ScriptStatus.draft,
        index=True,
    )
    seo_score: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    compliance_score: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    videos: Mapped[list["Video"]] = relationship("Video", back_populates="script")

    def __repr__(self) -> str:
        return f"<Script {self.title[:40]} v{self.version}>"
