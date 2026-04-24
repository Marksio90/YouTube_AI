"""
LLMProvider — the interface every provider must implement.
BaseProvider — abstract base that adds retry, timeout, and logging on top.

Provider implementors inherit BaseProvider and override _generate_text_impl
and _generate_structured_impl only — retry/timeout/logging are free.

    class MyProvider(BaseProvider):
        name = "my_provider"

        async def _generate_text_impl(self, messages, *, config) -> LLMResponse:
            ...  # pure API call, no retry/timeout here

        async def _generate_structured_impl(self, messages, schema, *, config) -> tuple[T, LLMResponse]:
            ...
"""
from __future__ import annotations

import asyncio
import json
import random
import time
from abc import ABC, abstractmethod
from typing import Any, Generic, TypeVar

import structlog

from worker.llm.config import ModelConfig, RetryPolicy
from worker.llm.errors import (
    LLMError,
    MaxRetriesExceededError,
    OutputValidationError,
    RETRYABLE_ERRORS,
    TimeoutError as LLMTimeoutError,
)
from worker.llm.response import LLMResponse
from worker.llm.types import Message, new_trace_id

try:
    from pydantic import BaseModel, ValidationError
    _HAS_PYDANTIC = True
except ImportError:
    _HAS_PYDANTIC = False

T = TypeVar("T")

log = structlog.get_logger(__name__)


# ── abstract interface ────────────────────────────────────────────────────────

class LLMProvider(ABC):
    """
    The provider interface. Implement this to add any backend.
    Callers use generate_text() and generate_structured_output() — never the _impl variants.
    """

    name: str

    @abstractmethod
    async def generate_text(
        self,
        messages: list[Message],
        *,
        config: ModelConfig,
    ) -> LLMResponse:
        """Generate a plain text response."""
        ...

    @abstractmethod
    async def generate_structured_output(
        self,
        messages: list[Message],
        output_schema: type[T],
        *,
        config: ModelConfig,
    ) -> tuple[T, LLMResponse]:
        """
        Generate a response and validate it against output_schema (a Pydantic model).
        Returns (parsed_instance, raw_response).
        """
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        """Return True if the provider is reachable and accepting requests."""
        ...

    @abstractmethod
    async def close(self) -> None:
        """Release all provider resources (HTTP clients, connections, etc.)."""
        ...


# ── concrete base with cross-cutting concerns ─────────────────────────────────

class BaseProvider(LLMProvider, ABC):
    """
    Adds retry, timeout, and structured logging on top of the raw provider.
    Subclasses implement _generate_text_impl and _generate_structured_impl only.
    """

    @abstractmethod
    async def _generate_text_impl(
        self,
        messages: list[Message],
        *,
        config: ModelConfig,
        trace_id: str,
    ) -> LLMResponse:
        ...

    @abstractmethod
    async def _generate_structured_impl(
        self,
        messages: list[Message],
        output_schema: type[T],
        *,
        config: ModelConfig,
        trace_id: str,
    ) -> tuple[T, LLMResponse]:
        ...

    # ── public api (handles retry + timeout + logging) ────────────────────────

    async def generate_text(
        self,
        messages: list[Message],
        *,
        config: ModelConfig,
    ) -> LLMResponse:
        trace_id = new_trace_id()
        return await self._with_retry_and_timeout(
            lambda: self._generate_text_impl(messages, config=config, trace_id=trace_id),
            config=config,
            trace_id=trace_id,
            operation="generate_text",
        )

    async def generate_structured_output(
        self,
        messages: list[Message],
        output_schema: type[T],
        *,
        config: ModelConfig,
    ) -> tuple[T, LLMResponse]:
        trace_id = new_trace_id()
        structured_config = config.with_json_mode() if not config.json_mode else config
        return await self._with_retry_and_timeout(
            lambda: self._generate_structured_impl(
                messages, output_schema, config=structured_config, trace_id=trace_id
            ),
            config=structured_config,
            trace_id=trace_id,
            operation="generate_structured_output",
        )

    # ── retry + timeout engine ────────────────────────────────────────────────

    async def _with_retry_and_timeout(
        self,
        fn: Any,
        *,
        config: ModelConfig,
        trace_id: str,
        operation: str,
    ) -> Any:
        policy = config.retry
        last_exc: Exception = RuntimeError("unreachable")

        for attempt in range(policy.max_attempts):
            log_ = log.bind(
                provider=self.name,
                model=config.model,
                trace_id=trace_id,
                attempt=attempt + 1,
                max_attempts=policy.max_attempts,
                operation=operation,
            )

            t0 = time.monotonic()
            try:
                log_.debug("llm.request.start")
                result = await asyncio.wait_for(fn(), timeout=config.timeout_seconds)
                elapsed_ms = (time.monotonic() - t0) * 1000

                log_.info(
                    "llm.request.complete",
                    latency_ms=round(elapsed_ms, 1),
                    tokens=getattr(getattr(result, "usage", None), "total_tokens", 0)
                    if not isinstance(result, tuple)
                    else getattr(getattr(result[1], "usage", None), "total_tokens", 0),
                )
                return result

            except asyncio.TimeoutError as exc:
                elapsed_ms = (time.monotonic() - t0) * 1000
                last_exc = LLMTimeoutError(
                    f"Request timed out after {config.timeout_seconds}s",
                    timeout_seconds=config.timeout_seconds,
                    provider=self.name,
                    model=config.model,
                    trace_id=trace_id,
                )
                log_.warning(
                    "llm.request.timeout",
                    latency_ms=round(elapsed_ms, 1),
                    timeout_seconds=config.timeout_seconds,
                )

            except RETRYABLE_ERRORS as exc:
                elapsed_ms = (time.monotonic() - t0) * 1000
                last_exc = exc
                log_.warning(
                    "llm.request.retryable_error",
                    error=str(exc),
                    error_type=type(exc).__name__,
                    latency_ms=round(elapsed_ms, 1),
                )

            except LLMError:
                raise  # non-retryable LLM errors propagate immediately

            except Exception as exc:
                elapsed_ms = (time.monotonic() - t0) * 1000
                last_exc = exc
                log_.warning(
                    "llm.request.error",
                    error=str(exc),
                    error_type=type(exc).__name__,
                    latency_ms=round(elapsed_ms, 1),
                )

            # Back off before next attempt
            if attempt < policy.max_attempts - 1:
                delay = _compute_backoff(attempt, policy)
                log_.debug("llm.retry.backoff", delay_seconds=round(delay, 2))
                await asyncio.sleep(delay)

        log.error(
            "llm.request.exhausted",
            provider=self.name,
            model=config.model,
            trace_id=trace_id,
            attempts=policy.max_attempts,
        )
        raise MaxRetriesExceededError(
            f"All {policy.max_attempts} attempts failed for {self.name}/{config.model}",
            attempts=policy.max_attempts,
            last_error=last_exc,
            provider=self.name,
            model=config.model,
            trace_id=trace_id,
        )

    # ── json parsing helper shared by all providers ───────────────────────────

    @staticmethod
    def _parse_and_validate(raw: str, output_schema: type[T], *, trace_id: str, provider: str) -> T:
        """Parse JSON string and validate against a Pydantic model."""
        import re

        text = raw.strip()
        # Strip markdown code fences if present
        if text.startswith("```"):
            match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
            if match:
                text = match.group(1)

        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            # Last resort: find outermost {}
            match = re.search(r"\{.*\}", text, re.DOTALL)
            if match:
                try:
                    data = json.loads(match.group())
                except json.JSONDecodeError:
                    raise OutputValidationError(
                        "Response is not valid JSON",
                        raw=raw,
                        schema=output_schema.__name__,
                        provider=provider,
                        trace_id=trace_id,
                    ) from exc
            else:
                raise OutputValidationError(
                    "Response is not valid JSON",
                    raw=raw,
                    schema=output_schema.__name__,
                    provider=provider,
                    trace_id=trace_id,
                ) from exc

        try:
            if _HAS_PYDANTIC and issubclass(output_schema, BaseModel):
                return output_schema.model_validate(data)
            return output_schema(**data)  # type: ignore[call-arg]
        except Exception as exc:
            raise OutputValidationError(
                f"Response failed {output_schema.__name__} validation: {exc}",
                raw=raw,
                schema=output_schema.__name__,
                provider=provider,
                trace_id=trace_id,
            ) from exc


# ── backoff helper ────────────────────────────────────────────────────────────

def _compute_backoff(attempt: int, policy: RetryPolicy) -> float:
    delay = min(
        policy.base_delay_seconds * (policy.exponential_base ** attempt),
        policy.max_delay_seconds,
    )
    if policy.jitter:
        delay *= random.uniform(0.5, 1.5)
    return delay
