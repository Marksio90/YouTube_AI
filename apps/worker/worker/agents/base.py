import json
import re
from typing import Any

import structlog
from anthropic import AsyncAnthropic, APIStatusError, APITimeoutError
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from worker.config import settings

log = structlog.get_logger(__name__)

_RETRYABLE = (APIStatusError, APITimeoutError, ConnectionError, TimeoutError)


class BaseAgent:
    """
    Foundation for all AI agents.
    - Single AsyncAnthropic client per instance (reused across calls).
    - Prompt caching via ephemeral cache_control on the system message.
    - Automatic retry with exponential backoff on transient failures.
    - _call_json() helper for tasks that always need structured output.
    """

    def __init__(self, model: str | None = None) -> None:
        self.model = model or settings.llm_default_model
        self._client = AsyncAnthropic(api_key=settings.anthropic_api_key)

    @retry(
        retry=retry_if_exception_type(_RETRYABLE),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        reraise=True,
    )
    async def _call(
        self,
        system: str,
        messages: list[dict[str, Any]],
        *,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> str:
        response = await self._client.messages.create(
            model=self.model,
            max_tokens=max_tokens or settings.llm_max_tokens,
            temperature=temperature if temperature is not None else settings.llm_temperature,
            system=[
                {
                    "type": "text",
                    "text": system,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=messages,
        )
        return response.content[0].text

    async def _call_json(
        self,
        system: str,
        user_message: str,
        *,
        temperature: float = 0.3,
    ) -> dict:
        raw = await self._call(
            system,
            [{"role": "user", "content": user_message}],
            temperature=temperature,
        )
        return self._parse_json(raw)

    @staticmethod
    def _parse_json(raw: str) -> dict:
        raw = raw.strip()
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            # Strip markdown code fences if present
            match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
            if match:
                return json.loads(match.group(1))
            # Last resort: find outermost {...}
            match = re.search(r"\{.*\}", raw, re.DOTALL)
            if match:
                return json.loads(match.group())
            raise ValueError(f"No valid JSON found in agent response: {raw[:300]}")

    async def close(self) -> None:
        await self._client.close()
