"""
ProviderRegistry — global provider catalog.

Providers register once at startup. Callers ask for a provider by name or use
the default. Swap all agents to a different provider by changing one env var.

    # Change to local LLM for all agents
    LLM_PROVIDER=local

    # Use mock for all tests
    registry.set_default("mock")

    # Per-agent override
    agent = ScoutAgent(provider=registry.get("local"))
"""
from __future__ import annotations

import structlog

from worker.llm.provider import LLMProvider
from worker.llm_support import SUPPORTED_PROVIDERS, is_provider_supported

log = structlog.get_logger(__name__)


class ProviderRegistry:
    def __init__(self) -> None:
        self._providers: dict[str, LLMProvider] = {}
        self._default: str = "openai"

    def register(self, name: str, provider: LLMProvider) -> None:
        self._providers[name] = provider
        log.debug("llm.registry.registered", provider=name)

    def get(self, name: str | None = None) -> LLMProvider:
        target = name or self._default
        if target not in self._providers:
            # Lazy-init built-in providers on first use
            self._providers[target] = _build_builtin(target)
        return self._providers[target]

    def set_default(self, name: str) -> None:
        self._default = name
        log.info("llm.registry.default_changed", provider=name)

    def list_providers(self) -> list[str]:
        return list(self._providers.keys())

    @property
    def default_name(self) -> str:
        return self._default


def _build_builtin(name: str) -> LLMProvider:
    from worker.llm.providers.openai import OpenAIProvider
    from worker.llm.providers.local import LocalLLMProvider
    from worker.llm.providers.mock import MockProvider

    if name == "openai":
        return OpenAIProvider()
    if name == "local":
        return LocalLLMProvider()
    if name == "mock":
        return MockProvider()
    raise KeyError(
        f"Unknown provider '{name}'. Register it with registry.register('{name}', provider) "
        f"or use a built-in: {' | '.join(SUPPORTED_PROVIDERS)}"
    )


# ── global singleton ──────────────────────────────────────────────────────────

registry = ProviderRegistry()


def get_provider(name: str | None = None) -> LLMProvider:
    """
    Module-level shortcut. Reads LLM_PROVIDER from settings if name is None.

        provider = get_provider()          # uses settings.llm_provider
        provider = get_provider("mock")    # always mock
        provider = get_provider("local")   # always local
    """
    from worker.config import settings
    target = name or settings.llm_provider
    if not is_provider_supported(target):
        raise KeyError(
            f"Unsupported provider '{target}'. Supported providers: {', '.join(SUPPORTED_PROVIDERS)}"
        )
    return registry.get(target)
