"""
worker.llm — LLM abstraction layer.

Quick-start:
    from worker.llm import get_provider, templates, ModelConfig

    provider = get_provider()                     # from settings
    config   = ModelConfig.for_task("agent.scout")

    messages = templates.get_chat("agent.scout").render(
        niche="finance", channel_name="WealthPro",
        days_back=7, competitors="none", count=10,
        filters="", schema="{...}",
    )
    response = await provider.generate_text(messages, config=config)
    print(response.content)
"""
from worker.llm.types import (
    FinishReason,
    Message,
    Role,
    Usage,
    new_trace_id,
)
from worker.llm.errors import (
    LLMError,
    MaxRetriesExceededError,
    OutputValidationError,
    ProviderError,
    ProviderUnavailableError,
    RateLimitError,
    TimeoutError as LLMTimeoutError,
    RETRYABLE_ERRORS,
)
from worker.llm.response import LLMResponse
from worker.llm.config import ModelConfig, RetryPolicy, PRESETS
from worker.llm.provider import LLMProvider, BaseProvider
from worker.llm.providers.openai import OpenAIProvider
from worker.llm.providers.local import LocalLLMProvider
from worker.llm.providers.mock import MockProvider
from worker.llm.registry import ProviderRegistry, registry, get_provider
from worker.llm.templates import (
    ChatTemplate,
    PromptTemplate,
    TemplateRenderError,
    TemplateRegistry,
    templates,
)

__all__ = [
    # types
    "Role",
    "Message",
    "Usage",
    "FinishReason",
    "new_trace_id",
    # errors
    "LLMError",
    "ProviderError",
    "RateLimitError",
    "LLMTimeoutError",
    "OutputValidationError",
    "ProviderUnavailableError",
    "MaxRetriesExceededError",
    "RETRYABLE_ERRORS",
    # response
    "LLMResponse",
    # config
    "ModelConfig",
    "RetryPolicy",
    "PRESETS",
    # providers
    "LLMProvider",
    "BaseProvider",
    "OpenAIProvider",
    "LocalLLMProvider",
    "MockProvider",
    # registry
    "ProviderRegistry",
    "registry",
    "get_provider",
    # templates
    "PromptTemplate",
    "ChatTemplate",
    "TemplateRenderError",
    "TemplateRegistry",
    "templates",
]
