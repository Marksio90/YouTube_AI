import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class BriefCreate(BaseModel):
    channel_id: uuid.UUID
    topic_id: uuid.UUID | None = None
    title: str = Field(min_length=3, max_length=300)
    target_audience: str = Field(default="", max_length=500)
    key_points: list[str] = Field(default_factory=list, max_length=20)
    seo_keywords: list[str] = Field(default_factory=list, max_length=20)
    competitor_urls: list[str] = Field(default_factory=list, max_length=10)
    estimated_duration_seconds: int = Field(default=600, ge=60, le=3600)
    tone: str = "educational"
    notes: str | None = Field(default=None, max_length=2000)


class BriefGenerateRequest(BaseModel):
    channel_id: uuid.UUID
    topic_id: uuid.UUID
    additional_instructions: str | None = Field(default=None, max_length=1000)


class BriefUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=3, max_length=300)
    target_audience: str | None = None
    key_points: list[str] | None = None
    seo_keywords: list[str] | None = None
    competitor_urls: list[str] | None = None
    estimated_duration_seconds: int | None = Field(default=None, ge=60, le=3600)
    tone: str | None = None
    status: str | None = None
    notes: str | None = None


class BriefRead(BaseModel):
    id: uuid.UUID
    channel_id: uuid.UUID
    topic_id: uuid.UUID | None
    title: str
    target_audience: str
    key_points: list[str]
    seo_keywords: list[str]
    competitor_urls: list[str]
    estimated_duration_seconds: int
    tone: str
    status: str
    notes: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
