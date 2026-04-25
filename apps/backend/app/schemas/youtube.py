import uuid
from datetime import datetime

from pydantic import BaseModel, Field, HttpUrl


class YouTubeConnectResponse(BaseModel):
    auth_url: HttpUrl
    state: str


class YouTubeCallbackResponse(BaseModel):
    channel_id: uuid.UUID
    youtube_channel_id: str
    connected: bool = True


class YouTubeUploadRequest(BaseModel):
    channel_id: uuid.UUID
    title: str = Field(min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=5000)
    tags: list[str] = Field(default_factory=list, max_length=50)
    visibility: str = Field(default="private", pattern="^(private|public|unlisted)$")
    media_url: HttpUrl


class YouTubeUploadResponse(BaseModel):
    youtube_video_id: str
    youtube_url: HttpUrl


class YouTubeMetadataUpdateRequest(BaseModel):
    channel_id: uuid.UUID
    title: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=5000)
    tags: list[str] | None = Field(default=None, max_length=50)
    visibility: str | None = Field(default=None, pattern="^(private|public|unlisted)$")


class YouTubeVideoStatsResponse(BaseModel):
    youtube_video_id: str
    view_count: int
    like_count: int
    comment_count: int
    favorite_count: int
    fetched_at: datetime
