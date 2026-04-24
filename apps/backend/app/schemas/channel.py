import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class ChannelCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    niche: str = Field(min_length=1, max_length=100)
    handle: str | None = None


class ChannelUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    niche: str | None = Field(default=None, min_length=1, max_length=100)
    handle: str | None = None


class ChannelRead(BaseModel):
    id: uuid.UUID
    youtube_channel_id: str | None
    name: str
    handle: str | None
    thumbnail_url: str | None
    niche: str
    status: str
    subscriber_count: int
    view_count: int
    video_count: int
    monetization_enabled: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
