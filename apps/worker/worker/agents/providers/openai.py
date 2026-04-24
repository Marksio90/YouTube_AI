"""
OpenAI provider — gpt-4o-mini default, supports json_mode for structured output.
"""
from __future__ import annotations

from openai import AsyncOpenAI

from worker.agents.providers.base import LLMProvider, LLMResponse
from worker.config import settings


class OpenAIProvider(LLMProvider):
    name = "openai"

    def __init__(self, api_key: str | None = None, base_url: str | None = None) -> None:
        self._client = AsyncOpenAI(
            api_key=api_key or settings.openai_api_key,
            base_url=base_url,
        )

    async def complete(
        self,
        messages: list[dict],
        *,
        model: str,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        json_mode: bool = False,
    ) -> LLMResponse:
        kwargs: dict = {}
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        resp = await self._client.chat.completions.create(
            model=model,
            messages=messages,  # type: ignore[arg-type]
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs,
        )

        return LLMResponse(
            content=resp.choices[0].message.content or "",
            model=resp.model,
            provider=self.name,
            input_tokens=resp.usage.prompt_tokens if resp.usage else 0,
            output_tokens=resp.usage.completion_tokens if resp.usage else 0,
            finish_reason=resp.choices[0].finish_reason or "stop",
        )

    async def close(self) -> None:
        await self._client.close()
