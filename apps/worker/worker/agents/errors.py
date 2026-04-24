"""Agent error hierarchy — every failure type is explicit and carries context."""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from worker.agents.schemas import AgentTrace


class AgentError(Exception):
    """Root of all agent exceptions."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class AgentExecutionError(AgentError):
    """Raised when agent.execute() fails at runtime."""

    def __init__(self, agent: str, message: str, trace: "AgentTrace | None" = None) -> None:
        super().__init__(f"[{agent}] {message}")
        self.agent = agent
        self.trace = trace


class AgentValidationError(AgentError):
    """Raised when the LLM returns output that doesn't parse / validate."""

    def __init__(self, agent: str, raw: str, reason: str) -> None:
        super().__init__(f"[{agent}] output validation failed: {reason}")
        self.agent = agent
        self.raw = raw[:500]
        self.reason = reason


class AgentTimeoutError(AgentError):
    """Raised when the LLM call exceeds the timeout budget."""

    def __init__(self, agent: str, timeout_seconds: float) -> None:
        super().__init__(f"[{agent}] timed out after {timeout_seconds}s")
        self.agent = agent
        self.timeout_seconds = timeout_seconds


class ProviderError(AgentError):
    """Raised when the LLM provider returns an unrecoverable error."""

    def __init__(self, provider: str, status_code: int | None, message: str) -> None:
        super().__init__(f"[{provider}] HTTP {status_code}: {message}")
        self.provider = provider
        self.status_code = status_code
