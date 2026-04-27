from __future__ import annotations

import json
import time
from collections.abc import Mapping, Sequence
from typing import Any, Literal, TypeVar

import structlog
from openai import APIConnectionError, APIStatusError, APITimeoutError, AsyncOpenAI
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from tenacity import (
    AsyncRetrying,
    RetryCallState,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from app.core.config import settings

logger = structlog.get_logger(__name__)

AgentRole = Literal["system", "user", "assistant", "tool"]
TModel = TypeVar("TModel", bound=BaseModel)

_RETRYABLE_STATUS_CODES = {408, 409, 425, 429, 500, 502, 503, 504}
_RETRYABLE_EXCEPTIONS = (APITimeoutError, APIConnectionError, ConnectionError, TimeoutError)


class AgentConfigurationError(RuntimeError):
    """Raised when an agent cannot be initialized because runtime configuration is invalid."""


class AgentExecutionError(RuntimeError):
    """Raised when an agent call fails after retries or returns an unusable response."""


class AgentJSONDecodeError(AgentExecutionError):
    """Raised when the LLM response cannot be parsed as valid JSON."""


class AgentMessage(BaseModel):
    model_config = ConfigDict(frozen=True)

    role: AgentRole
    content: str = Field(min_length=1)


class AgentUsage(BaseModel):
    model_config = ConfigDict(frozen=True)

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class AgentCallResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    content: str
    model: str
    usage: AgentUsage
    elapsed_ms: int


class BaseAgent:
    """
    Production-grade foundation for AI agents.

    Responsibilities:
    - OpenAI async client lifecycle
    - safe model invocation
    - retry/backoff for transient provider failures
    - structured logging
    - strict message normalization
    - JSON extraction and Pydantic validation
    - backward-compatible text call API for existing agents
    """

    def __init__(
        self,
        model: str | None = None,
        *,
        client: AsyncOpenAI | None = None,
        agent_name: str | None = None,
    ) -> None:
        self.model = model or settings.llm_default_model
        self.agent_name = agent_name or self.__class__.__name__
        self._owns_client = client is None

        if not self.model or not self.model.strip():
            raise AgentConfigurationError("LLM model name is empty.")

        if client is not None:
            self.client = client
            return

        if not settings.openai_api_key:
            raise AgentConfigurationError(
                "OPENAI_API_KEY is not configured. Set openai_api_key in environment settings."
            )

        self.client = AsyncOpenAI(
            api_key=settings.openai_api_key,
            timeout=60.0,
            max_retries=0,
        )

    async def __aenter__(self) -> BaseAgent:
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        await self.close()

    async def _call(
        self,
        system: str,
        messages: Sequence[Mapping[str, Any] | AgentMessage],
        *,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> str:
        result = await self._call_with_metadata(
            system=system,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
            json_mode=False,
        )
        return result.content

    async def _call_json(
        self,
        system: str,
        messages: Sequence[Mapping[str, Any] | AgentMessage],
        *,
        schema: type[TModel] | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> dict[str, Any] | TModel:
        result = await self._call_with_metadata(
            system=system,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
            json_mode=True,
        )

        payload = self._parse_json_payload(result.content)

        if schema is None:
            return payload

        try:
            return schema.model_validate(payload)
        except ValidationError as exc:
            logger.warning(
                "agent.json_schema_validation_failed",
                agent=self.agent_name,
                model=self.model,
                errors=exc.errors(include_url=False),
            )
            raise AgentJSONDecodeError(
                f"{self.agent_name} returned JSON that does not match schema {schema.__name__}."
            ) from exc

    async def _call_with_metadata(
        self,
        system: str,
        messages: Sequence[Mapping[str, Any] | AgentMessage],
        *,
        max_tokens: int | None,
        temperature: float | None,
        json_mode: bool,
    ) -> AgentCallResult:
        normalized_messages = self._build_messages(system=system, messages=messages)
        resolved_max_tokens = self._resolve_max_tokens(max_tokens)
        resolved_temperature = self._resolve_temperature(temperature)

        started = time.perf_counter()

        logger.info(
            "agent.call_started",
            agent=self.agent_name,
            model=self.model,
            message_count=len(normalized_messages),
            max_tokens=resolved_max_tokens,
            temperature=resolved_temperature,
            json_mode=json_mode,
        )

        try:
            async for attempt in AsyncRetrying(
                retry=retry_if_exception(self._is_retryable_exception),
                stop=stop_after_attempt(3),
                wait=wait_exponential(multiplier=1, min=2, max=10),
                reraise=True,
                before_sleep=self._log_retry,
            ):
                with attempt:
                    response = await self.client.chat.completions.create(
                        model=self.model,
                        max_tokens=resolved_max_tokens,
                        temperature=resolved_temperature,
                        messages=normalized_messages,
                        response_format={"type": "json_object"} if json_mode else None,
                    )
        except Exception as exc:
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            logger.error(
                "agent.call_failed",
                agent=self.agent_name,
                model=self.model,
                elapsed_ms=elapsed_ms,
                error_type=type(exc).__name__,
                error=self._safe_error_message(exc),
            )
            raise AgentExecutionError(
                f"{self.agent_name} failed to call LLM provider after retries."
            ) from exc

        elapsed_ms = int((time.perf_counter() - started) * 1000)

        if not response.choices:
            raise AgentExecutionError(f"{self.agent_name} received response without choices.")

        content = response.choices[0].message.content or ""
        content = content.strip()

        if not content:
            raise AgentExecutionError(f"{self.agent_name} received empty response content.")

        usage = AgentUsage(
            prompt_tokens=getattr(response.usage, "prompt_tokens", 0) if response.usage else 0,
            completion_tokens=getattr(response.usage, "completion_tokens", 0) if response.usage else 0,
            total_tokens=getattr(response.usage, "total_tokens", 0) if response.usage else 0,
        )

        logger.info(
            "agent.call_completed",
            agent=self.agent_name,
            model=self.model,
            elapsed_ms=elapsed_ms,
            prompt_tokens=usage.prompt_tokens,
            completion_tokens=usage.completion_tokens,
            total_tokens=usage.total_tokens,
        )

        return AgentCallResult(
            content=content,
            model=self.model,
            usage=usage,
            elapsed_ms=elapsed_ms,
        )

    async def close(self) -> None:
        if self._owns_client:
            await self.client.close()

    def _build_messages(
        self,
        *,
        system: str,
        messages: Sequence[Mapping[str, Any] | AgentMessage],
    ) -> list[dict[str, str]]:
        if not system or not system.strip():
            raise ValueError("System prompt cannot be empty.")

        normalized: list[dict[str, str]] = [
            {"role": "system", "content": system.strip()},
        ]

        for message in messages:
            agent_message = self._normalize_message(message)
            if agent_message.role == "system":
                raise ValueError("System messages must be passed through the system argument only.")

            normalized.append(
                {
                    "role": agent_message.role,
                    "content": agent_message.content,
                }
            )

        return normalized

    def _normalize_message(self, message: Mapping[str, Any] | AgentMessage) -> AgentMessage:
        if isinstance(message, AgentMessage):
            return message

        try:
            return AgentMessage.model_validate(message)
        except ValidationError as exc:
            raise ValueError(f"Invalid agent message: {exc.errors(include_url=False)}") from exc

    def _resolve_max_tokens(self, max_tokens: int | None) -> int:
        value = max_tokens if max_tokens is not None else settings.llm_max_tokens

        if value <= 0:
            raise ValueError("max_tokens must be greater than zero.")

        return value

    def _resolve_temperature(self, temperature: float | None) -> float:
        value = temperature if temperature is not None else settings.llm_temperature

        if value < 0 or value > 2:
            raise ValueError("temperature must be between 0 and 2.")

        return value

    def _parse_json_payload(self, content: str) -> dict[str, Any]:
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError:
            extracted = self._extract_json_object(content)
            if extracted is None:
                logger.warning(
                    "agent.json_decode_failed",
                    agent=self.agent_name,
                    model=self.model,
                    response_preview=content[:500],
                )
                raise AgentJSONDecodeError(f"{self.agent_name} returned invalid JSON.")

            try:
                parsed = json.loads(extracted)
            except json.JSONDecodeError as exc:
                logger.warning(
                    "agent.extracted_json_decode_failed",
                    agent=self.agent_name,
                    model=self.model,
                    response_preview=extracted[:500],
                )
                raise AgentJSONDecodeError(f"{self.agent_name} returned malformed JSON object.") from exc

        if not isinstance(parsed, dict):
            raise AgentJSONDecodeError(f"{self.agent_name} returned JSON, but root value is not an object.")

        return parsed

    def _extract_json_object(self, content: str) -> str | None:
        start = content.find("{")
        end = content.rfind("}")

        if start == -1 or end == -1 or end <= start:
            return None

        return content[start : end + 1]

    def _is_retryable_exception(self, exc: BaseException) -> bool:
        if isinstance(exc, _RETRYABLE_EXCEPTIONS):
            return True

        if isinstance(exc, APIStatusError):
            return exc.status_code in _RETRYABLE_STATUS_CODES

        return False

    def _log_retry(self, retry_state: RetryCallState) -> None:
        exc = retry_state.outcome.exception() if retry_state.outcome else None

        logger.warning(
            "agent.call_retrying",
            agent=self.agent_name,
            model=self.model,
            attempt=retry_state.attempt_number,
            error_type=type(exc).__name__ if exc else None,
            error=self._safe_error_message(exc) if exc else None,
        )

    def _safe_error_message(self, exc: BaseException | None) -> str | None:
        if exc is None:
            return None

        message = str(exc)
        message = message.replace(settings.openai_api_key, "[redacted]") if settings.openai_api_key else message

        if len(message) > 500:
            return f"{message[:500]}..."

        return message
