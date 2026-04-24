"""
LLM provider abstraction — all agents talk to this interface, never to SDKs directly.
Swap providers by passing a different implementation to any BaseAgent constructor.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Literal

from pydantic import BaseModel


class Message(dict):
    """TypedDict-style helper. Keys: role (system|user|assistant), content (str)."""


class LLMResponse(BaseModel):
    content: str
    model: str
    provider: str
    input_tokens: int = 0
    output_tokens: int = 0
    finish_reason: str = "stop"


class LLMProvider(ABC):
    """
    Abstract LLM provider. Implementors: OpenAIProvider, LocalLLMProvider.
    All agents call complete() — never a specific SDK directly.
    """

    name: str

    @abstractmethod
    async def complete(
        self,
        messages: list[dict],
        *,
        model: str,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        json_mode: bool = False,
    ) -> LLMResponse: ...

    @abstractmethod
    async def close(self) -> None: ...
