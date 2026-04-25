import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class PublicationCreate(BaseModel):
    channel_id: uuid.UUID
    title: str = Field(min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=5000)
    script_id: uuid.UUID | None = None
    brief_id: uuid.UUID | None = None
    tags: list[str] = Field(default_factory=list, max_length=30)
    visibility: str = "private"
    scheduled_at: datetime | None = None


class PublicationUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=5000)
    tags: list[str] | None = None
    visibility: str | None = None
    scheduled_at: datetime | None = None
    status: str | None = None
    thumbnail_url: str | None = None


class PublicationRead(BaseModel):
    id: uuid.UUID
    channel_id: uuid.UUID
    script_id: uuid.UUID | None
    brief_id: uuid.UUID | None
    youtube_video_id: str | None
    title: str
    description: str | None
    tags: list[str]
    status: str
    visibility: str
    thumbnail_url: str | None
    duration_seconds: int | None
    scheduled_at: datetime | None
    published_at: datetime | None
    view_count: int
    like_count: int
    comment_count: int
    revenue_usd: float
    last_error: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class PublicationMetrics(BaseModel):
    publication_id: uuid.UUID
    view_count: int
    like_count: int
    comment_count: int
    revenue_usd: float
    watch_time_hours: float = 0.0
    avg_view_duration_seconds: float = 0.0
    ctr: float = 0.0


class PublishPipelineRequest(BaseModel):
    media_url: str
    audio_url: str | None = None
    thumbnail_url: str | None = None
    title: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=5000)
    tags: list[str] | None = None
    visibility: str | None = None
