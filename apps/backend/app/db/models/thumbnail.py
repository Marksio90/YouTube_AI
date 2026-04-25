import enum
import uuid

from sqlalchemy import BigInteger, Boolean, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from typing import TYPE_CHECKING

from app.db.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.db.models.channel import Channel
    from app.db.models.publication import Publication


class ThumbnailStatus(str, enum.Enum):
    queued = "queued"
    generating = "generating"
    ready = "ready"
    failed = "failed"
    archived = "archived"


class ImageProvider(str, enum.Enum):
    dalle3 = "dalle3"
    placeholder = "placeholder"
    mock = "mock"


class Thumbnail(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "thumbnails"

    publication_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("publications.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    channel_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("channels.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Groups all variants generated together for A/B testing
    ab_group_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
    )
    variant_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    status: Mapped[ThumbnailStatus] = mapped_column(
        String(20),
        nullable=False,
        default=ThumbnailStatus.queued,
        index=True,
    )
    image_provider: Mapped[ImageProvider] = mapped_column(
        String(20),
        nullable=False,
        default=ImageProvider.mock,
    )
    image_url: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Concept data from ThumbnailAgent
    concept_id: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    headline_text: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    sub_text: Mapped[str | None] = mapped_column(String(100), nullable=True)
    layout: Mapped[str] = mapped_column(String(50), nullable=False, default="bold_text")
    color_scheme: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    composition: Mapped[str | None] = mapped_column(Text, nullable=True)
    visual_elements: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    ai_image_prompt: Mapped[str] = mapped_column(Text, nullable=False, default="")
    predicted_ctr_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    channel_style: Mapped[str] = mapped_column(String(50), nullable=False, default="clean_modern")

    # A/B scoring — updated via impression/click events
    impressions: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    clicks: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    is_winner: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Job tracking
    task_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    publication: Mapped["Publication"] = relationship("Publication")
    channel: Mapped["Channel"] = relationship("Channel")

    @property
    def actual_ctr(self) -> float | None:
        if self.impressions == 0:
            return None
        return round(self.clicks / self.impressions, 4)

    def __repr__(self) -> str:
        return f"<Thumbnail {self.headline_text[:40]} variant={self.variant_index} [{self.status}]>"
