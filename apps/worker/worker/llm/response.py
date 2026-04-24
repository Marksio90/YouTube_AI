"""
LLMResponse — the normalised output from any provider.
Every generate_text / generate_structured_output call returns this.
"""
from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel

from worker.llm.types import FinishReason, Usage


class LLMResponse(BaseModel):
    content: str
    model: str
    provider: str
    usage: Usage
    finish_reason: FinishReason = FinishReason.stop
    latency_ms: float = 0.0
    trace_id: str = ""
    mock: bool = False
    timestamp: datetime = None  # type: ignore[assignment]

    def model_post_init(self, __context: object) -> None:
        if self.timestamp is None:
            self.timestamp = datetime.now(timezone.utc)

    @property
    def input_tokens(self) -> int:
        return self.usage.input_tokens

    @property
    def output_tokens(self) -> int:
        return self.usage.output_tokens

    @property
    def total_tokens(self) -> int:
        return self.usage.total_tokens

    @property
    def cost_usd_estimate(self) -> float:
        """Rough cost estimate based on gpt-4o-mini pricing ($0.15/$0.60 per 1M tokens)."""
        input_cost = self.usage.input_tokens * 0.00000015
        output_cost = self.usage.output_tokens * 0.00000060
        return round(input_cost + output_cost, 8)
