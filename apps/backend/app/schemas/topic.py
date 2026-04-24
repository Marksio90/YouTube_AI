import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class TopicCreate(BaseModel):
    channel_id: uuid.UUID
    title: str = Field(min_length=3, max_length=300)
    description: str | None = Field(default=None, max_length=2000)
    keywords: list[str] = Field(default_factory=list, max_length=20)
    source: str = "manual"


class TopicUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=3, max_length=300)
    description: str | None = None
    keywords: list[str] | None = None
    status: str | None = None
    trend_score: float | None = Field(default=None, ge=0, le=10)
    research_notes: str | None = None


class TopicRead(BaseModel):
    id: uuid.UUID
    channel_id: uuid.UUID
    title: str
    description: str | None
    keywords: list[str]
    trend_score: float | None
    source: str
    status: str
    research_notes: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class TopicStatusCount(BaseModel):
    new: int = 0
    researching: int = 0
    briefed: int = 0
    rejected: int = 0
    archived: int = 0
