"""
Local LLM provider — Ollama / LM Studio via OpenAI-compatible API.

Usage:
    provider = LocalLLMProvider(base_url="http://localhost:11434/v1", model="llama3.2")
    agent = ScoutAgent(provider=provider)

No extra dependencies — uses the same openai SDK pointed at a local endpoint.
json_mode is best-effort: if the local model doesn't support it, we strip fences client-side.
"""
from __future__ import annotations

import re

from openai import AsyncOpenAI

from worker.agents.providers.base import LLMProvider, LLMResponse
from worker.config import settings


class LocalLLMProvider(LLMProvider):
    name = "local"

    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
    ) -> None:
        self._base_url = base_url or settings.llm_local_base_url
        self._model = model or settings.llm_local_model
        # Ollama doesn't require a real API key
        self._client = AsyncOpenAI(api_key="local", base_url=self._base_url)

    async def complete(
        self,
        messages: list[dict],
        *,
        model: str,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        json_mode: bool = False,
    ) -> LLMResponse:
        # Local models use their own name regardless of requested OpenAI model
        effective_model = self._model

        kwargs: dict = {}
        # Only send json format hint if Ollama supports it (>=0.1.34)
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        try:
            resp = await self._client.chat.completions.create(
                model=effective_model,
                messages=messages,  # type: ignore[arg-type]
                temperature=temperature,
                max_tokens=max_tokens,
                **kwargs,
            )
            content = resp.choices[0].message.content or ""
            input_tokens = resp.usage.prompt_tokens if resp.usage else 0
            output_tokens = resp.usage.completion_tokens if resp.usage else 0
        except Exception:
            # Retry without json_mode if model doesn't support it
            resp = await self._client.chat.completions.create(
                model=effective_model,
                messages=messages,  # type: ignore[arg-type]
                temperature=temperature,
                max_tokens=max_tokens,
            )
            content = resp.choices[0].message.content or ""
            input_tokens = resp.usage.prompt_tokens if resp.usage else 0
            output_tokens = resp.usage.completion_tokens if resp.usage else 0

        # Strip markdown fences if local model wrapped JSON in them
        if json_mode and content.startswith("```"):
            match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", content, re.DOTALL)
            if match:
                content = match.group(1)

        return LLMResponse(
            content=content,
            model=effective_model,
            provider=self.name,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            finish_reason=resp.choices[0].finish_reason or "stop",
        )

    async def close(self) -> None:
        await self._client.close()
