import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class PipelineStepSchema(BaseModel):
    id: str
    type: str
    name: str
    config: dict = Field(default_factory=dict)
    depends_on: list[str] = Field(default_factory=list)
    retry_limit: int = 3
    timeout_seconds: int = 300


class PipelineCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    channel_id: uuid.UUID | None = None
    steps: list[PipelineStepSchema] = Field(min_length=1)
    schedule_cron: str | None = None


class PipelineRead(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    channel_id: uuid.UUID | None
    steps: list[dict]
    is_active: bool
    schedule_cron: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class PipelineTriggerRequest(BaseModel):
    input: dict = Field(default_factory=dict)


class PipelineRunRead(BaseModel):
    id: uuid.UUID
    pipeline_id: uuid.UUID
    status: str
    triggered_by: str
    input: dict
    output: dict | None
    error: str | None
    step_results: list[dict]
    started_at: str | None
    completed_at: str | None
    created_at: datetime

    model_config = {"from_attributes": True}
