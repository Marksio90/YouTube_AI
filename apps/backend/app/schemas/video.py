import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class VideoCreate(BaseModel):
    channel_id: uuid.UUID
    title: str = Field(min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=5000)
    visibility: str = "private"
    scheduled_at: datetime | None = None


class VideoUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=5000)
    visibility: str | None = None
    scheduled_at: datetime | None = None
    status: str | None = None


class VideoRead(BaseModel):
    id: uuid.UUID
    channel_id: uuid.UUID
    youtube_video_id: str | None
    title: str
    description: str | None
    status: str
    visibility: str
    thumbnail_url: str | None
    duration_seconds: int | None
    scheduled_at: datetime | None
    published_at: datetime | None
    script_id: uuid.UUID | None
    view_count: int
    like_count: int
    comment_count: int
    revenue_usd: float
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
