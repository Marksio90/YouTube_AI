"""
BaseAgent — foundation for every AI agent in the system.

Contract:
  • execute(input)       — real LLM path
  • mock_execute(input)  — realistic mock path (always same shape as execute)
  • run(input)           — public entry point: routes, traces, logs, handles errors

Subclasses must implement execute() and mock_execute(). Never call execute()
directly — always call run() so tracing and error handling fire.
"""
from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from typing import ClassVar, Generic, TypeVar

import structlog

from worker.agents.errors import AgentError, AgentExecutionError
from worker.agents.schemas import AgentInput, AgentOutput, AgentTrace, ExecutionStatus
from worker.config import settings
from worker.llm import (
    LLMProvider,
    Message,
    ModelConfig,
    Role,
    get_provider,
)

InputT = TypeVar("InputT", bound=AgentInput)
OutputT = TypeVar("OutputT", bound=AgentOutput)


class BaseAgent(ABC, Generic[InputT, OutputT]):
    """
    Generic agent base. Inherit and implement:
        agent_name: ClassVar[str] = "my_agent"
        async def execute(self, inp: MyInput) -> MyOutput: ...
        async def mock_execute(self, inp: MyInput) -> MyOutput: ...

    Provider is injected — defaults to the globally configured provider
    (OpenAI or local, from settings.llm_provider).
    """

    agent_name: ClassVar[str]
    default_temperature: ClassVar[float] = 0.7

    def __init__(
        self,
        provider: LLMProvider | None = None,
        model: str | None = None,
        force_mock: bool = False,
    ) -> None:
        self._provider: LLMProvider = provider or get_provider()
        self._model: str = model or settings.llm_default_model
        self._force_mock: bool = force_mock
        self._last_input_tokens: int = 0
        self._last_output_tokens: int = 0
        self._log = structlog.get_logger(__name__).bind(agent=self.agent_name)

    # ── public api ─────────────────────────────────────────────────────────────

    @property
    def use_mock(self) -> bool:
        return self._force_mock or settings.app_env != "production"

    async def run(self, inp: InputT) -> OutputT:
        """
        Public entry point. Wraps execute()/mock_execute() with:
          - structured logging (start / complete / failed)
          - AgentTrace attached to output
          - automatic retry on transient provider errors
          - typed AgentExecutionError on failure
        """
        trace = AgentTrace(
            agent_name=self.agent_name,
            model=self._model if not self.use_mock else "mock",
            provider=self._provider.name if not self.use_mock else "mock",
            input_hash=inp.input_hash(),
        )
        trace.status = ExecutionStatus.running

        log = self._log.bind(trace_id=trace.trace_id, mock=self.use_mock)
        log.info("agent.start")

        try:
            if self.use_mock:
                output: OutputT = await self.mock_execute(inp)
            else:
                output = await self._execute_with_retry(inp)

            trace.mark_success(
                input_tokens=self._last_input_tokens,
                output_tokens=self._last_output_tokens,
                mock=self.use_mock,
            )
            output.trace = trace

            log.info(
                "agent.complete",
                duration_ms=round(trace.duration_ms or 0, 1),
                tokens=trace.total_tokens,
                status=trace.status,
            )
            return output

        except AgentError:
            raise
        except Exception as exc:
            trace.mark_failure(str(exc))
            log.exception("agent.failed", duration_ms=round(trace.duration_ms or 0, 1))
            raise AgentExecutionError(self.agent_name, str(exc), trace) from exc

    # ── abstract interface ─────────────────────────────────────────────────────

    @abstractmethod
    async def execute(self, inp: InputT) -> OutputT:
        """Real LLM path. Called only when app_env == 'production'."""
        ...

    @abstractmethod
    async def mock_execute(self, inp: InputT) -> OutputT:
        """
        Realistic mock — same output shape as execute().
        Must be deterministic (seeded from inp.input_hash()) so tests are stable.
        """
        ...

    # ── protected helpers ──────────────────────────────────────────────────────

    async def _execute_with_retry(self, inp: InputT) -> OutputT:
        return await self.execute(inp)

    async def _call_llm(
        self,
        system: str,
        user: str,
        *,
        temperature: float | None = None,
        json_mode: bool = True,
    ) -> str:
        """
        Single LLM call through the provider. Updates token counters.
        Retry and timeout are handled inside the provider (worker.llm.BaseProvider).
        """
        config = (
            ModelConfig.for_task(f"agent.{self.agent_name}")
            .replace(
                temperature=temperature if temperature is not None else self.default_temperature,
                json_mode=json_mode,
                model=self._model,
            )
        )
        messages = [Message.system(system), Message.user(user)]
        response = await self._provider.generate_text(messages, config=config)
        self._last_input_tokens = response.input_tokens
        self._last_output_tokens = response.output_tokens
        return response.content

    async def _call_json(
        self,
        system: str,
        user_message: str,
        *,
        temperature: float = 0.3,
    ) -> dict:
        """Backward-compatible helper: call LLM and parse JSON response."""
        raw = await self._call_llm(system, user_message, temperature=temperature, json_mode=True)
        return self._parse_json(raw)

    @staticmethod
    def _parse_json(raw: str) -> dict:
        raw = raw.strip()
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
            if match:
                return json.loads(match.group(1))
            match = re.search(r"\{.*\}", raw, re.DOTALL)
            if match:
                return json.loads(match.group())
            raise ValueError(f"No valid JSON in agent response: {raw[:300]}")

    @staticmethod
    def _seed(value: str) -> int:
        """Deterministic integer seed from any string — for reproducible mocks."""
        import hashlib
        return int(hashlib.sha256(value.encode()).hexdigest()[:8], 16)

    async def close(self) -> None:
        await self._provider.close()
