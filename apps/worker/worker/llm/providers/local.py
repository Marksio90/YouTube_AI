"""
LocalLLMProvider — Ollama / LM Studio / any OpenAI-compatible local server.

No extra dependencies: uses the openai SDK pointed at a local endpoint.
Model name mapping: if the config requests an OpenAI model name (e.g. gpt-4o-mini),
the local model name from settings is used instead.

Startup:
    ollama serve
    ollama pull llama3.2

Config (via env):
    LLM_LOCAL_BASE_URL=http://localhost:11434/v1
    LLM_LOCAL_MODEL=llama3.2
"""
from __future__ import annotations

import time
from typing import TypeVar

from openai import AsyncOpenAI, APIConnectionError

from worker.llm.config import ModelConfig
from worker.llm.errors import ProviderUnavailableError
from worker.llm.provider import BaseProvider
from worker.llm.response import LLMResponse
from worker.llm.types import FinishReason, Message, Usage
from worker.config import settings

T = TypeVar("T")

# OpenAI model names that should be redirected to the local model
_OPENAI_MODEL_PREFIXES = ("gpt-", "o1-", "o3-", "chatgpt-")


class LocalLLMProvider(BaseProvider):
    name = "local"

    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
    ) -> None:
        self._base_url = base_url or settings.llm_local_base_url
        self._local_model = model or settings.llm_local_model
        # Ollama doesn't require a real API key
        self._client = AsyncOpenAI(api_key="local-no-auth", base_url=self._base_url)

    # ── impl ──────────────────────────────────────────────────────────────────

    async def _generate_text_impl(
        self,
        messages: list[Message],
        *,
        config: ModelConfig,
        trace_id: str,
    ) -> LLMResponse:
        t0 = time.monotonic()
        effective_model = self._resolve_model(config.model)
        kwargs = self._build_kwargs(config)

        try:
            resp = await self._client.chat.completions.create(
                model=effective_model,
                messages=[m.to_dict() for m in messages],  # type: ignore[arg-type]
                **kwargs,
            )
        except APIConnectionError as exc:
            raise ProviderUnavailableError(
                f"Local LLM server unreachable at {self._base_url} — is Ollama running?",
                provider=self.name,
                model=effective_model,
                trace_id=trace_id,
            ) from exc

        content = resp.choices[0].message.content or ""

        return LLMResponse(
            content=content,
            model=effective_model,
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
        # Try with json_mode first; some local models don't support it
        try:
            response = await self._generate_text_impl(messages, config=config, trace_id=trace_id)
        except Exception:
            # Retry without json_mode if unsupported
            fallback_config = config.replace(json_mode=False)
            response = await self._generate_text_impl(messages, config=fallback_config, trace_id=trace_id)

        parsed = self._parse_and_validate(
            response.content, output_schema, trace_id=trace_id, provider=self.name
        )
        return parsed, response

    async def health_check(self) -> bool:
        try:
            models = await self._client.models.list()
            return len(list(models)) > 0
        except Exception:
            return False

    async def close(self) -> None:
        await self._client.close()

    # ── helpers ───────────────────────────────────────────────────────────────

    def _resolve_model(self, requested: str) -> str:
        if any(requested.startswith(p) for p in _OPENAI_MODEL_PREFIXES):
            return self._local_model
        return requested

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
        kwargs.update(config.extra)
        return kwargs
