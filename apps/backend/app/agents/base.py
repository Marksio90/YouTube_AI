import structlog
from openai import AsyncOpenAI, APIStatusError, APITimeoutError, APIConnectionError
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.core.config import settings

logger = structlog.get_logger(__name__)

_RETRYABLE = (APIStatusError, APITimeoutError, APIConnectionError, ConnectionError, TimeoutError)


class BaseAgent:
    """Foundation for all AI agents. Handles client lifecycle, retries, and JSON parsing."""

    def __init__(self, model: str | None = None) -> None:
        self.model = model or settings.llm_default_model
        self.client = AsyncOpenAI(api_key=settings.openai_api_key)

    @retry(
        retry=retry_if_exception_type(_RETRYABLE),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
    )
    async def _call(
        self,
        system: str,
        messages: list[dict],
        *,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> str:
        response = await self.client.chat.completions.create(
            model=self.model,
            max_tokens=max_tokens or settings.llm_max_tokens,
            temperature=temperature if temperature is not None else settings.llm_temperature,
            messages=[
                {"role": "system", "content": system},
                *messages,
            ],
        )
        return response.choices[0].message.content or ""

    async def close(self) -> None:
        await self.client.close()
