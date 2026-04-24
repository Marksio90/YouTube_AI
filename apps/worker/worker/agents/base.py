import structlog
from anthropic import AsyncAnthropic
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from worker.config import settings

logger = structlog.get_logger(__name__)


class BaseAgent:
    def __init__(self, model: str | None = None) -> None:
        self.model = model or settings.llm_default_model
        self.client = AsyncAnthropic(api_key=settings.anthropic_api_key)

    @retry(
        retry=retry_if_exception_type(Exception),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
    )
    async def _call(self, system: str, messages: list[dict], *, max_tokens: int | None = None, temperature: float | None = None) -> str:
        response = await self.client.messages.create(
            model=self.model,
            max_tokens=max_tokens or settings.llm_max_tokens,
            temperature=temperature or settings.llm_temperature,
            system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            messages=messages,
        )
        return response.content[0].text
