"""Supported provider/model matrix and validation helpers.

Single source of truth for:
- startup config validation (fail-fast)
- provider registry error messages
- deploy documentation
"""
from __future__ import annotations

from collections.abc import Mapping

SUPPORTED_PROVIDERS: tuple[str, ...] = ("openai", "local", "mock")
OPENAI_MODEL_PREFIXES: tuple[str, ...] = ("gpt-", "o1-", "o3-", "chatgpt-")

SUPPORTED_PROVIDER_MODEL_MATRIX: Mapping[str, str] = {
    "openai": "gpt-* | o1-* | o3-* | chatgpt-*",
    "local": "LLM_LOCAL_MODEL or openai-style aliases (gpt-*, o1-*, o3-*, chatgpt-*)",
    "mock": "any non-empty model name",
}


def normalize_provider_name(name: str) -> str:
    return name.strip().lower()


def is_provider_supported(name: str) -> bool:
    return normalize_provider_name(name) in SUPPORTED_PROVIDERS


def is_model_supported(provider: str, model: str) -> bool:
    provider_name = normalize_provider_name(provider)
    model_name = model.strip()
    if not model_name:
        return False

    if provider_name == "openai":
        return any(model_name.startswith(prefix) for prefix in OPENAI_MODEL_PREFIXES)
    if provider_name in {"local", "mock"}:
        return True
    return False


def matrix_as_text() -> str:
    return "; ".join(
        f"{provider}: {rule}"
        for provider, rule in SUPPORTED_PROVIDER_MODEL_MATRIX.items()
    )
