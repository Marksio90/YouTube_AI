"""
Shared schemas for every agent: input base, output base, execution trace.
All agent-specific schemas extend AgentInput / AgentOutput.
"""
from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class ExecutionStatus(str, Enum):
    pending = "pending"
    running = "running"
    success = "success"
    failed = "failed"


class AgentTrace(BaseModel):
    """Full execution record attached to every agent output."""

    trace_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    agent_name: str
    model: str
    provider: str
    status: ExecutionStatus = ExecutionStatus.pending
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: datetime | None = None
    duration_ms: float | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    input_hash: str = ""
    error: str | None = None
    mock: bool = False
    retries: int = 0
    extra: dict[str, Any] = Field(default_factory=dict)

    def mark_success(
        self,
        *,
        input_tokens: int = 0,
        output_tokens: int = 0,
        mock: bool = False,
        extra: dict[str, Any] | None = None,
    ) -> None:
        self.completed_at = datetime.now(timezone.utc)
        self.duration_ms = (self.completed_at - self.started_at).total_seconds() * 1000
        self.status = ExecutionStatus.success
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.total_tokens = input_tokens + output_tokens
        self.mock = mock
        if extra:
            self.extra.update(extra)

    def mark_failure(self, error: str) -> None:
        self.completed_at = datetime.now(timezone.utc)
        self.duration_ms = (self.completed_at - self.started_at).total_seconds() * 1000
        self.status = ExecutionStatus.failed
        self.error = error[:2000]


class AgentInput(BaseModel):
    """Base class for all agent inputs. Adds input fingerprinting."""

    def input_hash(self) -> str:
        return hashlib.sha256(self.model_dump_json().encode()).hexdigest()[:16]


class AgentOutput(BaseModel):
    """Base class for all agent outputs. Carries execution trace."""

    trace: AgentTrace | None = None
