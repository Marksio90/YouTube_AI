import enum
import uuid
from typing import Any

from sqlalchemy import Enum, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDMixin


class VideoRenderStatus(str, enum.Enum):
    queued = "queued"
    planning = "planning"
    rendering = "rendering"
    completed = "completed"
    failed = "failed"


class VideoRenderJob(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "video_render_jobs"

    video_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("videos.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
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
        index=True,
    )
    task_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    status: Mapped[VideoRenderStatus] = mapped_column(
        Enum(VideoRenderStatus, name="video_render_status"),
        nullable=False,
        default=VideoRenderStatus.queued,
        index=True,
    )
    engine: Mapped[str] = mapped_column(String(64), nullable=False, default="mock-compositor-v1")
    input_audio_url: Mapped[str] = mapped_column(Text, nullable=False)
    scene_plan: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    assets: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    timeline: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB, nullable=True)
    output_video_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

