"""
LLMError hierarchy — every failure is explicit and structured.
All errors carry provider name, model, trace_id, and the original cause.
"""
from __future__ import annotations


class LLMError(Exception):
    """Root of all LLM errors."""

    def __init__(self, message: str, *, provider: str = "", model: str = "", trace_id: str = "") -> None:
        super().__init__(message)
        self.message = message
        self.provider = provider
        self.model = model
        self.trace_id = trace_id


class ProviderError(LLMError):
    """Non-retryable provider error — bad request, auth failure, invalid model."""

    def __init__(self, message: str, *, status_code: int | None = None, **kw) -> None:
        super().__init__(message, **kw)
        self.status_code = status_code


class RateLimitError(LLMError):
    """Provider rate limit hit — retryable with backoff."""

    def __init__(self, message: str, *, retry_after_seconds: float | None = None, **kw) -> None:
        super().__init__(message, **kw)
        self.retry_after_seconds = retry_after_seconds


class TimeoutError(LLMError):
    """Request exceeded the configured timeout — retryable."""

    def __init__(self, message: str, *, timeout_seconds: float, **kw) -> None:
        super().__init__(message, **kw)
        self.timeout_seconds = timeout_seconds


class OutputValidationError(LLMError):
    """Model output couldn't be parsed or validated against the schema."""

    def __init__(self, message: str, *, raw: str = "", schema: str = "", **kw) -> None:
        super().__init__(message, **kw)
        self.raw = raw[:500]
        self.schema = schema


class ProviderUnavailableError(LLMError):
    """Provider is unreachable — network error or local server down."""
    pass


class MaxRetriesExceededError(LLMError):
    """All retry attempts exhausted."""

    def __init__(self, message: str, *, attempts: int, last_error: Exception, **kw) -> None:
        super().__init__(message, **kw)
        self.attempts = attempts
        self.last_error = last_error


# Errors that are safe to retry automatically
RETRYABLE_ERRORS = (RateLimitError, TimeoutError, ProviderUnavailableError, ConnectionError, OSError)
