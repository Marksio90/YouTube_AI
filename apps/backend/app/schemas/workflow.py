"""
Pydantic schemas for the workflow API.

Naming convention:
  *Create  — request body for creation
  *Read    — response body (always includes id + timestamps)
  *Update  — request body for partial updates (PATCH)
  *Action  — request body for action endpoints (pause, inject, etc.)
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.db.models.workflow import JobStatus, RunStatus


# ── WorkflowRun ───────────────────────────────────────────────────────────────

class WorkflowRunCreate(BaseModel):
    pipeline_name:  str = Field("youtube_content", description="Registered pipeline name")
    channel_id:     uuid.UUID | None = None
    triggered_by:   str = "manual"
    context:        dict[str, Any] = Field(default_factory=dict,
                                           description="Initial context / pipeline inputs")


class WorkflowJobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id:              uuid.UUID
    run_id:          uuid.UUID
    step_id:         str
    step_type:       str
    status:          JobStatus
    attempt:         int
    max_attempts:    int
    celery_task_id:  str | None
    output:          dict | None
    error:           str | None
    is_manual_result: bool
    manual_actor:    str | None
    attempt_history: list[dict]
    scheduled_at:   datetime | None
    started_at:     datetime | None
    completed_at:   datetime | None
    retry_after:    datetime | None
    duration_ms:    int | None
    created_at:     datetime
    updated_at:     datetime


class WorkflowRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id:               uuid.UUID
    channel_id:       uuid.UUID | None
    owner_id:         uuid.UUID
    pipeline_name:    str
    pipeline_version: str
    status:           RunStatus
    triggered_by:     str
    context:          dict[str, Any]
    error:            str | None
    started_at:       datetime | None
    completed_at:     datetime | None
    paused_at:        datetime | None
    parent_run_id:    uuid.UUID | None
    created_at:       datetime
    updated_at:       datetime
    jobs:             list[WorkflowJobRead] = Field(default_factory=list)


class WorkflowRunSummary(BaseModel):
    """Lightweight list-view — no jobs embedded."""
    model_config = ConfigDict(from_attributes=True)

    id:               uuid.UUID
    channel_id:       uuid.UUID | None
    pipeline_name:    str
    pipeline_version: str
    status:           RunStatus
    triggered_by:     str
    error:            str | None
    started_at:       datetime | None
    completed_at:     datetime | None
    paused_at:        datetime | None
    created_at:       datetime
    updated_at:       datetime


# ── Audit ─────────────────────────────────────────────────────────────────────

class WorkflowAuditEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id:          uuid.UUID
    run_id:      uuid.UUID
    job_id:      uuid.UUID | None
    event_type:  str
    actor:       str
    data:        dict[str, Any]
    occurred_at: datetime


# ── Action request bodies ─────────────────────────────────────────────────────

class TriggerRequest(BaseModel):
    """Body for POST /workflows — create and start a run."""
    pipeline_name: str = "youtube_content"
    channel_id:    uuid.UUID | None = None
    context:       dict[str, Any] = Field(default_factory=dict)


class RetryRequest(BaseModel):
    """Body for POST /workflows/{run_id}/retry."""
    reset_context: bool = Field(
        False,
        description="If true, reset context to the original run input before retrying",
    )


class InjectResultRequest(BaseModel):
    """Body for POST /workflows/{run_id}/jobs/{job_id}/inject."""
    output: dict[str, Any] = Field(..., description="Output dict to inject as job result")


class OverrideContextRequest(BaseModel):
    """Body for PATCH /workflows/{run_id}/context."""
    updates: dict[str, Any] = Field(..., description="Keys to merge into the run context")


# ── Responses ─────────────────────────────────────────────────────────────────

class WorkflowActionResponse(BaseModel):
    """Generic response for action endpoints."""
    status:  str
    run_id:  uuid.UUID
    message: str = ""
    task_id: str | None = None


class WorkflowListResponse(BaseModel):
    items:     list[WorkflowRunSummary]
    total:     int
    page:      int
    page_size: int
    has_next:  bool
    has_prev:  bool


class WorkflowAuditResponse(BaseModel):
    run_id: uuid.UUID
    events: list[WorkflowAuditEventRead]
    total:  int
