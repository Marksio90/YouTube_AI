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


class ScenePlanItem(BaseModel):
    scene_id: str = Field(min_length=1, max_length=80)
    start_seconds: float = Field(ge=0)
    duration_seconds: float = Field(gt=0)
    narration: str | None = Field(default=None, max_length=2000)
    asset_query: str | None = Field(default=None, max_length=500)
    transition: str | None = Field(default="cut", max_length=40)


class RenderAssetItem(BaseModel):
    asset_id: str = Field(min_length=1, max_length=80)
    type: str = Field(pattern="^(image|video|overlay|subtitle)$")
    url: str = Field(min_length=5, max_length=5000)
    scene_id: str | None = Field(default=None, max_length=80)
    start_seconds: float | None = Field(default=None, ge=0)
    duration_seconds: float | None = Field(default=None, gt=0)


class VideoRenderRequest(BaseModel):
    audio_url: str = Field(min_length=5, max_length=5000)
    scene_plan: list[ScenePlanItem] = Field(default_factory=list, min_length=1, max_length=300)
    assets: list[RenderAssetItem] = Field(default_factory=list, max_length=2000)
    engine: str = Field(default="mock-compositor-v1", max_length=64)


class VideoRead(BaseModel):
    id: uuid.UUID
    channel_id: uuid.UUID
    youtube_video_id: str | None
    title: str
    description: str | None
    status: str
    visibility: str
    thumbnail_url: str | None
    render_url: str | None
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
