"""
Core types shared across the entire LLM abstraction layer.
Import these in providers, templates, configs — never import from specific providers here.
"""
from __future__ import annotations

import uuid
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class Role(str, Enum):
    system = "system"
    user = "user"
    assistant = "assistant"


class Message(BaseModel):
    role: Role
    content: str

    # ── convenience constructors ───────────────────────────────────────────────

    @classmethod
    def system(cls, content: str) -> "Message":
        return cls(role=Role.system, content=content)

    @classmethod
    def user(cls, content: str) -> "Message":
        return cls(role=Role.user, content=content)

    @classmethod
    def assistant(cls, content: str) -> "Message":
        return cls(role=Role.assistant, content=content)

    def to_dict(self) -> dict:
        return {"role": self.role.value, "content": self.content}


class Usage(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0

    @classmethod
    def from_openai(cls, usage: object | None) -> "Usage":
        if usage is None:
            return cls()
        return cls(
            input_tokens=getattr(usage, "prompt_tokens", 0),
            output_tokens=getattr(usage, "completion_tokens", 0),
            total_tokens=getattr(usage, "total_tokens", 0),
        )


class FinishReason(str, Enum):
    stop = "stop"
    length = "length"
    content_filter = "content_filter"
    tool_calls = "tool_calls"
    unknown = "unknown"

    @classmethod
    def from_str(cls, value: str | None) -> "FinishReason":
        try:
            return cls(value or "unknown")
        except ValueError:
            return cls.unknown


def new_trace_id() -> str:
    return str(uuid.uuid4())
