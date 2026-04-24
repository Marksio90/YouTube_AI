"""
ModelConfig and RetryPolicy — fully typed configuration for every LLM call.

Usage:
    config = ModelConfig.for_task("agent.scriptwriter")
    config = ModelConfig(temperature=0.9, max_tokens=16384)
    config = PRESETS["fast"].replace(temperature=0.3)
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field, replace as dc_replace
from typing import Any


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 3
    base_delay_seconds: float = 1.0
    max_delay_seconds: float = 30.0
    exponential_base: float = 2.0
    jitter: bool = True

    # Disabled retries sentinel
    @classmethod
    def no_retry(cls) -> "RetryPolicy":
        return cls(max_attempts=1)


@dataclass
class ModelConfig:
    # Provider routing
    provider: str = "openai"
    model: str = "gpt-4o-mini"

    # Sampling
    temperature: float = 0.7
    max_tokens: int = 4096
    top_p: float | None = None
    seed: int | None = None

    # Reliability
    timeout_seconds: float = 30.0
    retry: RetryPolicy = field(default_factory=RetryPolicy)

    # Defaults for prompt assembly
    system_prompt: str | None = None

    # Structured output hint (providers use this to set json_mode)
    json_mode: bool = False

    # Arbitrary provider-specific overrides (e.g. {"logprobs": True})
    extra: dict[str, Any] = field(default_factory=dict)

    # ── helpers ──────────────────────────────────────────────────────────────

    def replace(self, **changes: Any) -> "ModelConfig":
        """Return a shallow copy with fields overridden. frozen-safe."""
        obj = copy.copy(self)
        for k, v in changes.items():
            object.__setattr__(obj, k, v)
        return obj

    @classmethod
    def for_task(cls, task_name: str) -> "ModelConfig":
        """Return the pre-defined config for a task/agent name, falling back to 'default'."""
        return copy.deepcopy(PRESETS.get(task_name, PRESETS["default"]))

    def with_json_mode(self) -> "ModelConfig":
        return self.replace(json_mode=True)

    def with_no_retry(self) -> "ModelConfig":
        return self.replace(retry=RetryPolicy.no_retry())


# ── built-in presets ──────────────────────────────────────────────────────────
#
# Naming convention:
#   "default"       — baseline
#   "fast"          — low latency, short output
#   "precise"       — low temperature, deterministic
#   "creative"      — high temperature
#   "agent.<name>"  — per-agent defaults
#   "task.<name>"   — per-celery-task defaults

PRESETS: dict[str, ModelConfig] = {
    # ── general ───────────────────────────────────────────────────────────────
    "default": ModelConfig(),

    "fast": ModelConfig(
        model="gpt-4o-mini",
        temperature=0.5,
        max_tokens=1024,
        timeout_seconds=10.0,
        retry=RetryPolicy(max_attempts=2),
    ),

    "precise": ModelConfig(
        temperature=0.0,
        top_p=1.0,
        seed=42,
        retry=RetryPolicy(max_attempts=2),
    ),

    "creative": ModelConfig(
        temperature=0.95,
        max_tokens=8192,
        top_p=0.95,
    ),

    "long_form": ModelConfig(
        temperature=0.7,
        max_tokens=16384,
        timeout_seconds=120.0,
        retry=RetryPolicy(max_attempts=2, base_delay_seconds=5.0),
    ),

    # ── agent-specific ────────────────────────────────────────────────────────
    "agent.scout": ModelConfig(
        temperature=0.8,
        max_tokens=4096,
    ),

    "agent.opportunity_scorer": ModelConfig(
        temperature=0.2,
        max_tokens=2048,
        json_mode=True,
    ),

    "agent.research": ModelConfig(
        temperature=0.4,
        max_tokens=8192,
        timeout_seconds=60.0,
    ),

    "agent.scriptwriter": ModelConfig(
        temperature=0.75,
        max_tokens=16384,
        timeout_seconds=120.0,
        retry=RetryPolicy(max_attempts=2, base_delay_seconds=5.0),
    ),

    "agent.compliance": ModelConfig(
        temperature=0.05,
        max_tokens=2048,
        json_mode=True,
        retry=RetryPolicy(max_attempts=2),
    ),

    "agent.thumbnail": ModelConfig(
        temperature=0.8,
        max_tokens=3000,
    ),

    "agent.metadata": ModelConfig(
        temperature=0.3,
        max_tokens=2048,
        json_mode=True,
    ),

    "agent.optimization": ModelConfig(
        temperature=0.2,
        max_tokens=4096,
        json_mode=True,
    ),

    "agent.topic_researcher": ModelConfig(
        temperature=0.7,
        max_tokens=4096,
    ),

    "agent.recommender": ModelConfig(
        temperature=0.7,
        max_tokens=4096,
    ),

    # ── celery task-specific ──────────────────────────────────────────────────
    "task.generate_script": ModelConfig(
        temperature=0.75,
        max_tokens=16384,
        timeout_seconds=120.0,
    ),

    "task.generate_brief": ModelConfig(
        temperature=0.5,
        max_tokens=4096,
    ),

    "task.analyze_seo": ModelConfig(
        temperature=0.2,
        max_tokens=2048,
        json_mode=True,
    ),

    "task.check_compliance": ModelConfig(
        temperature=0.05,
        max_tokens=2048,
        json_mode=True,
    ),

    "task.discover_topics": ModelConfig(
        temperature=0.9,
        max_tokens=4096,
    ),

    "task.score_topic": ModelConfig(
        temperature=0.2,
        max_tokens=1024,
        json_mode=True,
    ),

    "task.generate_recommendations": ModelConfig(
        temperature=0.7,
        max_tokens=4096,
    ),
}
