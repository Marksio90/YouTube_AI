from worker.agents.providers.base import LLMProvider, LLMResponse, Message
from worker.agents.providers.openai import OpenAIProvider
from worker.agents.providers.local import LocalLLMProvider

__all__ = ["LLMProvider", "LLMResponse", "Message", "OpenAIProvider", "LocalLLMProvider", "get_provider"]


def get_provider(name: str | None = None) -> LLMProvider:
    """Return the configured provider. Reads settings.llm_provider if name not given."""
    from worker.config import settings

    target = name or settings.llm_provider
    if target == "local":
        return LocalLLMProvider()
    return OpenAIProvider()
