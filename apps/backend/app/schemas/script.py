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


class ScriptAudioGenerateRequest(BaseModel):
    voice_id: str = Field(default="alloy", min_length=2, max_length=100)
    provider: str = Field(default="openai", pattern="^(openai|elevenlabs)$")
    tempo: float = Field(default=1.0, ge=0.5, le=2.0)
    tone: float = Field(default=0.0, ge=-12.0, le=12.0)


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
    audio_url: str | None
    audio_duration_seconds: float | None
    audio_provider: str | None
    audio_voice_id: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
