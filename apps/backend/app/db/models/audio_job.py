import enum
import uuid

from sqlalchemy import Enum, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDMixin


class AudioProvider(str, enum.Enum):
    openai = "openai"
    elevenlabs = "elevenlabs"


class AudioJobStatus(str, enum.Enum):
    queued = "queued"
    processing = "processing"
    completed = "completed"
    failed = "failed"


class AudioJob(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "audio_jobs"

    script_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("scripts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    channel_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("channels.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    task_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    provider: Mapped[AudioProvider] = mapped_column(
        Enum(AudioProvider, name="audio_provider"),
        nullable=False,
        default=AudioProvider.openai,
    )
    voice_id: Mapped[str] = mapped_column(String(100), nullable=False, default="alloy")
    tempo: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    tone: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    status: Mapped[AudioJobStatus] = mapped_column(
        Enum(AudioJobStatus, name="audio_job_status"),
        nullable=False,
        default=AudioJobStatus.queued,
        index=True,
    )
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    audio_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

