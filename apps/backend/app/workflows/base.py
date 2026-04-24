import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class WorkflowContext:
    """Mutable execution context passed through workflow steps."""

    run_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    owner_id: str = ""
    channel_id: str = ""
    input: dict[str, Any] = field(default_factory=dict)
    state: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def set(self, key: str, value: Any) -> None:
        self.state[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        return self.state.get(key, default)

    def fail(self, reason: str) -> None:
        self.errors.append(reason)

    @property
    def has_errors(self) -> bool:
        return bool(self.errors)


class WorkflowStep(ABC):
    """Single step in a workflow. Steps are composable and independently testable."""

    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    async def run(self, ctx: WorkflowContext) -> WorkflowContext: ...


class BaseWorkflow(ABC):
    """Orchestrates a sequence of WorkflowSteps. Stops on first error by default."""

    @property
    @abstractmethod
    def steps(self) -> list[WorkflowStep]: ...

    async def execute(self, ctx: WorkflowContext) -> WorkflowContext:
        for step in self.steps:
            if ctx.has_errors:
                break
            ctx = await step.run(ctx)
        return ctx
