import enum
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Boolean, Enum, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.db.models.user import User
    from app.db.models.video import Video


class ChannelStatus(str, enum.Enum):
    active = "active"
    inactive = "inactive"
    suspended = "suspended"
    pending_auth = "pending_auth"


class Channel(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "channels"

    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    youtube_channel_id: Mapped[str | None] = mapped_column(
        String(64), unique=True, nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    handle: Mapped[str | None] = mapped_column(String(100), nullable=True)
    thumbnail_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    niche: Mapped[str] = mapped_column(String(100), nullable=False, default="general")
    status: Mapped[ChannelStatus] = mapped_column(
        Enum(ChannelStatus, name="channel_status"),
        nullable=False,
        default=ChannelStatus.pending_auth,
    )
    subscriber_count: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    view_count: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    video_count: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    monetization_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # OAuth tokens (encrypted at rest in production)
    access_token_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    refresh_token_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    token_expiry: Mapped[str | None] = mapped_column(String(64), nullable=True)

    owner: Mapped["User"] = relationship("User", back_populates="channels")
    videos: Mapped[list["Video"]] = relationship(
        "Video", back_populates="channel", lazy="select"
    )

    def __repr__(self) -> str:
        return f"<Channel {self.name}>"
