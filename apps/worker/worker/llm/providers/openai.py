"""
OpenAIProvider — production LLM provider backed by the OpenAI Chat Completions API.

Supports:
  - generate_text         plain chat completion
  - generate_structured_output  json_mode + Pydantic validation
  - health_check          lightweight models.list call
  - Automatic token usage extraction
"""
from __future__ import annotations

import time
from typing import TypeVar

from openai import AsyncOpenAI, APIStatusError, APIConnectionError, RateLimitError as OAIRateLimitError

from worker.llm.config import ModelConfig
from worker.llm.errors import ProviderError, RateLimitError
from worker.llm.provider import BaseProvider
from worker.llm.response import LLMResponse
from worker.llm_support import OPENAI_MODEL_PREFIXES
from worker.llm.types import FinishReason, Message, Usage
from worker.config import settings

T = TypeVar("T")


class OpenAIProvider(BaseProvider):
    name = "openai"
    supported_model_prefixes = OPENAI_MODEL_PREFIXES

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        organization: str | None = None,
    ) -> None:
        self._client = AsyncOpenAI(
            api_key=api_key or settings.openai_api_key,
            base_url=base_url,
            organization=organization,
        )

    # ── impl ──────────────────────────────────────────────────────────────────

    async def _generate_text_impl(
        self,
        messages: list[Message],
        *,
        config: ModelConfig,
        trace_id: str,
    ) -> LLMResponse:
        t0 = time.monotonic()
        kwargs = self._build_kwargs(config)

        try:
            resp = await self._client.chat.completions.create(
                model=config.model,
                messages=[m.to_dict() for m in messages],  # type: ignore[arg-type]
                **kwargs,
            )
        except OAIRateLimitError as exc:
            raise RateLimitError(
                str(exc), provider=self.name, model=config.model, trace_id=trace_id
            ) from exc
        except APIStatusError as exc:
            raise ProviderError(
                str(exc), status_code=exc.status_code,
                provider=self.name, model=config.model, trace_id=trace_id,
            ) from exc
        except APIConnectionError as exc:
            from worker.llm.errors import ProviderUnavailableError
            raise ProviderUnavailableError(
                str(exc), provider=self.name, model=config.model, trace_id=trace_id
            ) from exc

        return LLMResponse(
            content=resp.choices[0].message.content or "",
            model=resp.model,
            provider=self.name,
            usage=Usage.from_openai(resp.usage),
            finish_reason=FinishReason.from_str(resp.choices[0].finish_reason),
            latency_ms=(time.monotonic() - t0) * 1000,
            trace_id=trace_id,
        )

    async def _generate_structured_impl(
        self,
        messages: list[Message],
        output_schema: type[T],
        *,
        config: ModelConfig,
        trace_id: str,
    ) -> tuple[T, LLMResponse]:
        response = await self._generate_text_impl(messages, config=config, trace_id=trace_id)
        parsed = self._parse_and_validate(
            response.content, output_schema, trace_id=trace_id, provider=self.name
        )
        return parsed, response

    # ── health + lifecycle ────────────────────────────────────────────────────

    async def health_check(self) -> bool:
        try:
            await self._client.models.list()
            return True
        except Exception:
            return False

    async def close(self) -> None:
        await self._client.close()

    # ── helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _build_kwargs(config: ModelConfig) -> dict:
        kwargs: dict = {
            "temperature": config.temperature,
            "max_tokens": config.max_tokens,
        }
        if config.json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        if config.top_p is not None:
            kwargs["top_p"] = config.top_p
        if config.seed is not None:
            kwargs["seed"] = config.seed
        kwargs.update(config.extra)
        return kwargs
