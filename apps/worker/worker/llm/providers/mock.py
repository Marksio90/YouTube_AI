"""
MockProvider — deterministic, zero-latency provider for testing and development.

Features:
  - No network calls — ever
  - Responses seeded from input hash → same prompt = same output every run
  - Auto-generates valid JSON matching any Pydantic schema
  - Pre-registered responses for specific patterns (override the auto-gen)
  - Configurable simulated latency and forced failure scenarios
  - Full token usage simulation

Usage:
    # Auto-generate based on schema shape
    provider = MockProvider()

    # Register specific responses
    provider.register("hello", "Hello! I'm the mock provider.")
    provider.register_json("score_topic", {"overall_score": 8.5, "recommendation": "pursue"})

    # Force a failure for error-path testing
    provider.register_failure("bad_input", RateLimitError("simulated rate limit"))
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import random
import time
from typing import Any, TypeVar, get_type_hints

import structlog

from worker.llm.config import ModelConfig
from worker.llm.errors import LLMError
from worker.llm.provider import BaseProvider
from worker.llm.response import LLMResponse
from worker.llm.types import FinishReason, Message, Usage, new_trace_id

try:
    from pydantic import BaseModel
    import pydantic.fields as _pf
    _HAS_PYDANTIC = True
except ImportError:
    _HAS_PYDANTIC = False

T = TypeVar("T")
log = structlog.get_logger(__name__)


class MockProvider(BaseProvider):
    """
    Deterministic mock provider. No network, no API keys, instant responses.
    Response content is seeded from the SHA-256 of the last user message so
    the same prompt always returns the same mock output (idempotent test runs).
    """

    name = "mock"

    def __init__(
        self,
        *,
        simulated_latency_ms: float = 0.0,
        token_simulation: bool = True,
    ) -> None:
        self._latency_ms = simulated_latency_ms
        self._token_simulation = token_simulation
        self._text_responses: dict[str, str] = {}
        self._json_responses: dict[str, dict] = {}
        self._failures: dict[str, LLMError] = {}

    # ── registration api ──────────────────────────────────────────────────────

    def register(self, key: str, response: str) -> None:
        """Register a text response for prompts containing `key`."""
        self._text_responses[key.lower()] = response

    def register_json(self, key: str, response: dict) -> None:
        """Register a JSON response for prompts containing `key`."""
        self._json_responses[key.lower()] = response

    def register_failure(self, key: str, error: LLMError) -> None:
        """Force a specific error when the prompt contains `key`."""
        self._failures[key.lower()] = error

    # ── impl ──────────────────────────────────────────────────────────────────

    async def _generate_text_impl(
        self,
        messages: list[Message],
        *,
        config: ModelConfig,
        trace_id: str,
    ) -> LLMResponse:
        await self._maybe_sleep()
        content_key = self._message_key(messages)
        self._check_failure(content_key, trace_id)

        # Prefer registered response
        for key, response in self._text_responses.items():
            if key in content_key:
                return self._build_response(response, config.model, trace_id, messages)

        # Auto-generate based on system prompt and user message
        if config.json_mode:
            generated = self._generate_mock_json_text(content_key)
        else:
            generated = self._generate_mock_text(content_key, messages)

        return self._build_response(generated, config.model, trace_id, messages)

    async def _generate_structured_impl(
        self,
        messages: list[Message],
        output_schema: type[T],
        *,
        config: ModelConfig,
        trace_id: str,
    ) -> tuple[T, LLMResponse]:
        await self._maybe_sleep()
        content_key = self._message_key(messages)
        self._check_failure(content_key, trace_id)

        # Prefer registered JSON response
        for key, response in self._json_responses.items():
            if key in content_key:
                raw = json.dumps(response)
                response_obj = self._build_response(raw, config.model, trace_id, messages)
                parsed = self._parse_and_validate(raw, output_schema, trace_id=trace_id, provider=self.name)
                return parsed, response_obj

        # Auto-generate from schema
        if _HAS_PYDANTIC and issubclass(output_schema, BaseModel):
            mock_data = _generate_from_pydantic(output_schema, seed=self._seed(content_key))
        else:
            mock_data = {}

        raw = json.dumps(mock_data)
        response_obj = self._build_response(raw, config.model, trace_id, messages)
        parsed = self._parse_and_validate(raw, output_schema, trace_id=trace_id, provider=self.name)
        return parsed, response_obj

    async def health_check(self) -> bool:
        return True

    async def close(self) -> None:
        pass

    # ── helpers ───────────────────────────────────────────────────────────────

    async def _maybe_sleep(self) -> None:
        if self._latency_ms > 0:
            await asyncio.sleep(self._latency_ms / 1000)

    def _check_failure(self, content_key: str, trace_id: str) -> None:
        for key, error in self._failures.items():
            if key in content_key:
                error.trace_id = trace_id
                raise error

    def _build_response(
        self, content: str, model: str, trace_id: str, messages: list[Message]
    ) -> LLMResponse:
        word_count = sum(len(m.content.split()) for m in messages)
        return LLMResponse(
            content=content,
            model=f"mock/{model}",
            provider=self.name,
            usage=Usage(
                input_tokens=word_count * 2 if self._token_simulation else 0,
                output_tokens=len(content.split()) * 2 if self._token_simulation else 0,
                total_tokens=word_count * 2 + len(content.split()) * 2 if self._token_simulation else 0,
            ),
            finish_reason=FinishReason.stop,
            latency_ms=self._latency_ms,
            trace_id=trace_id,
            mock=True,
        )

    @staticmethod
    def _message_key(messages: list[Message]) -> str:
        return " ".join(m.content.lower() for m in messages)

    @staticmethod
    def _seed(key: str) -> int:
        return int(hashlib.sha256(key.encode()).hexdigest()[:8], 16)

    @staticmethod
    def _generate_mock_text(key: str, messages: list[Message]) -> str:
        seed = int(hashlib.sha256(key.encode()).hexdigest()[:8], 16)
        rng = random.Random(seed)
        last_user = next((m.content[:80] for m in reversed(messages) if m.role.value == "user"), "this topic")
        templates = [
            f"Based on the analysis of '{last_user}', here is a comprehensive breakdown of the key considerations and recommended approach.",
            f"The topic of '{last_user}' presents several important factors worth examining. Here is a structured overview.",
            f"After careful evaluation of '{last_user}', the following framework provides actionable insights.",
        ]
        return rng.choice(templates)

    @staticmethod
    def _generate_mock_json_text(key: str) -> str:
        seed = int(hashlib.sha256(key.encode()).hexdigest()[:8], 16)
        rng = random.Random(seed)
        return json.dumps({
            "result": "mock_response",
            "score": round(rng.uniform(6.0, 9.5), 1),
            "status": "success",
            "summary": "Mock generated response for testing purposes.",
        })


# ── pydantic schema introspection for mock data generation ────────────────────

def _generate_from_pydantic(schema: type, *, seed: int) -> dict:
    """
    Recursively generate a valid mock dict from a Pydantic model's field definitions.
    Uses field types and names as hints for realistic mock values.
    """
    if not (_HAS_PYDANTIC and issubclass(schema, BaseModel)):
        return {}

    rng = random.Random(seed)
    result: dict[str, Any] = {}

    for field_name, field_info in schema.model_fields.items():
        annotation = field_info.annotation
        result[field_name] = _mock_value(field_name, annotation, rng, depth=0)

    return result


def _mock_value(name: str, annotation: Any, rng: random.Random, depth: int) -> Any:
    """Generate a realistic mock value based on field name and type annotation."""
    if depth > 3:
        return None

    import typing
    origin = getattr(annotation, "__origin__", None)
    args = getattr(annotation, "__args__", ())

    # Optional[X] → unwrap
    if origin is typing.Union:
        non_none = [a for a in args if a is not type(None)]
        if non_none:
            return _mock_value(name, non_none[0], rng, depth)
        return None

    # list[X]
    if origin is list:
        item_type = args[0] if args else str
        count = rng.randint(2, 4)
        return [_mock_value(f"{name}_{i}", item_type, rng, depth + 1) for i in range(count)]

    # dict[K, V]
    if origin is dict:
        return {f"key_{i}": _mock_value(name, args[1] if len(args) > 1 else str, rng, depth + 1)
                for i in range(2)}

    # Literal values
    if origin is typing.Literal:
        return rng.choice(args)

    # Nested Pydantic model
    if _HAS_PYDANTIC and isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return _generate_from_pydantic(annotation, seed=rng.randint(0, 2**32))

    # Primitive types
    if annotation is str or annotation == "str":
        return _mock_string(name, rng)
    if annotation is int or annotation == "int":
        return _mock_int(name, rng)
    if annotation is float or annotation == "float":
        return _mock_float(name, rng)
    if annotation is bool or annotation == "bool":
        return rng.choice([True, False])

    return None


def _mock_string(name: str, rng: random.Random) -> str:
    n = name.lower()
    if "title" in n:
        return rng.choice([
            "The Complete Guide to Maximizing Results",
            "7 Proven Strategies That Actually Work",
            "Why Most People Get This Completely Wrong",
        ])
    if "url" in n or "link" in n:
        return "https://example.com/mock-resource"
    if "email" in n:
        return "mock@example.com"
    if "score" in n or "rating" in n:
        return str(round(rng.uniform(6.0, 9.5), 1))
    if "description" in n or "summary" in n or "rationale" in n:
        return "Mock description generated for testing purposes. This represents realistic content."
    if "id" in n:
        return f"mock-{rng.randint(1000, 9999)}"
    if "color" in n or "hex" in n:
        return f"#{rng.randint(0, 0xFFFFFF):06X}"
    return f"mock_{name}_value"


def _mock_int(name: str, rng: random.Random) -> int:
    n = name.lower()
    if "view" in n or "impression" in n:
        return rng.randint(1000, 100000)
    if "token" in n:
        return rng.randint(100, 2000)
    if "second" in n or "duration" in n:
        return rng.randint(60, 600)
    if "count" in n:
        return rng.randint(1, 50)
    return rng.randint(1, 100)


def _mock_float(name: str, rng: random.Random) -> float:
    n = name.lower()
    if "score" in n or "rating" in n:
        return round(rng.uniform(5.0, 9.5), 1)
    if "confidence" in n or "probability" in n:
        return round(rng.uniform(0.7, 0.95), 2)
    if "ctr" in n:
        return round(rng.uniform(0.02, 0.08), 3)
    if "revenue" in n or "usd" in n:
        return round(rng.uniform(1.0, 500.0), 2)
    if "pct" in n or "percent" in n:
        return round(rng.uniform(5.0, 25.0), 1)
    return round(rng.uniform(0.0, 10.0), 2)
