"""
Workflow exception hierarchy.

Every failure mode has a typed exception so callers can make precise decisions
about error handling without inspecting message strings.
"""
from __future__ import annotations

from worker.workflow.types import JobStatus, RunStatus


class WorkflowError(Exception):
    """Root of all workflow errors."""


class InvalidTransitionError(WorkflowError):
    """State machine rejected the requested status transition."""

    def __init__(
        self,
        current: JobStatus | RunStatus,
        requested: JobStatus | RunStatus,
        entity: str = "",
    ) -> None:
        label = f" for {entity}" if entity else ""
        super().__init__(
            f"Cannot transition from '{current.value}' to '{requested.value}'{label}"
        )
        self.current   = current
        self.requested = requested


class JobFailedError(WorkflowError):
    """A job exhausted all retry attempts."""

    def __init__(self, step_id: str, reason: str, attempt: int) -> None:
        super().__init__(f"Job '{step_id}' failed after {attempt} attempt(s): {reason}")
        self.step_id = step_id
        self.reason  = reason
        self.attempt = attempt


class WorkflowAbortError(WorkflowError):
    """The engine must stop immediately (fail_policy=fail_run triggered)."""

    def __init__(self, step_id: str, cause: str) -> None:
        super().__init__(f"Run aborted at step '{step_id}': {cause}")
        self.step_id = step_id
        self.cause   = cause


class WorkflowPausedError(WorkflowError):
    """The run was paused externally; the engine should stop cleanly."""


class WorkflowCancelledError(WorkflowError):
    """The run was cancelled externally; the engine should stop cleanly."""


class StepNotFoundError(WorkflowError):
    """A step_id referenced in depends_on or a lookup does not exist."""

    def __init__(self, step_id: str, pipeline: str) -> None:
        super().__init__(f"Step '{step_id}' not found in pipeline '{pipeline}'")
        self.step_id  = step_id
        self.pipeline = pipeline


class ContextKeyMissingError(WorkflowError):
    """A job tried to read a required key that is not in the context."""

    def __init__(self, key: str, step_id: str) -> None:
        super().__init__(f"Step '{step_id}' requires context key '{key}' which is not set")
        self.key     = key
        self.step_id = step_id


class JobTimeoutError(WorkflowError):
    """The Celery task did not complete within the configured timeout."""

    def __init__(self, step_id: str, timeout_seconds: float) -> None:
        super().__init__(f"Step '{step_id}' timed out after {timeout_seconds}s")
        self.step_id         = step_id
        self.timeout_seconds = timeout_seconds


class PipelineNotFoundError(WorkflowError):
    """No pipeline with the given name is registered."""

    def __init__(self, name: str) -> None:
        super().__init__(f"Pipeline '{name}' is not registered")
        self.name = name
