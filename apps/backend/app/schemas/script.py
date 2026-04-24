import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class ScriptCreate(BaseModel):
    channel_id: uuid.UUID
    title: str = Field(min_length=1, max_length=200)
    hook: str = ""
    body: str = ""
    cta: str = ""
    keywords: list[str] = Field(default_factory=list, max_length=20)
    target_duration_seconds: int = Field(default=600, ge=60, le=3600)
    tone: str = "educational"


class ScriptGenerateRequest(BaseModel):
    channel_id: uuid.UUID
    topic: str = Field(min_length=3, max_length=500)
    tone: str = "educational"
    target_duration_seconds: int = Field(default=600, ge=60, le=3600)
    keywords: list[str] = Field(default_factory=list, max_length=10)
    additional_context: str | None = Field(default=None, max_length=2000)


class ScriptUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    hook: str | None = None
    body: str | None = None
    cta: str | None = None
    keywords: list[str] | None = None
    status: str | None = None


class ScriptRead(BaseModel):
    id: uuid.UUID
    channel_id: uuid.UUID
    title: str
    hook: str
    body: str
    cta: str
    keywords: list[str]
    target_duration_seconds: int
    tone: str
    status: str
    seo_score: float | None
    compliance_score: float | None
    version: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
